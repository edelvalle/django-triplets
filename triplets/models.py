import typing as t
from datetime import datetime, timezone
from itertools import chain
from uuid import UUID

from django.conf import settings
from django.db import models
from uuid6 import uuid7

from . import ast, core

INFERENCE_RULES: t.Sequence[core.Rule] = getattr(
    settings, "TRIPLETS_INFERENCE_RULES", []
)

SETTINGS_ATTRIBUTES: t.Sequence[ast.Attr] = getattr(
    settings, "TRIPLETS_ATTRIBUTES", []
)
ATTRIBUTES = {attr.name: attr for attr in SETTINGS_ATTRIBUTES}


NANO_SECOND = 10**9


class Fact:
    @classmethod
    def storage_key(cls, fact: ast.Fact) -> str:
        return core.storage_hash(cls.to_str(fact))

    @classmethod
    def storage_key_for_many(cls, facts: set[ast.Fact]) -> str:
        return core.storage_hash(
            str(list(sorted(cls.to_str(f) for f in facts)))
        )

    @classmethod
    def as_dict(cls, fact: ast.Fact) -> ast.Context:
        subject, verb, obj = fact
        return {
            "subject": subject,
            "verb": verb,
            f"obj_{ast.type_name(type(obj))}": obj,
        }

    @classmethod
    def to_str(cls, fact: ast.Fact) -> str:
        entity, verb, value = fact
        return f"fact:({entity},{verb},{ast.type_name(type(value))}:{value})"


class StoredFactQS(models.QuerySet["StoredFact"]):
    def add(self, fact: ast.Fact) -> None:
        """Adds a fact to knowledge base."""
        self.bulk_add([fact])

    def bulk_add(
        self,
        facts: t.Sequence[ast.Fact],
        tx_id: t.Optional[UUID] = None,
    ):
        """Use this method to add many facts to the knowledge base.
        This method has better performance than adding the facts one by one.
        """
        tx_id = tx_id or Transaction.new().id
        self._remove_previous_values(set(facts), tx_id)
        self._bulk_add(
            tx_id,
            [(fact, None, None) for fact in facts],
        )

    def _bulk_add(
        self,
        tx_id: UUID,
        fact_rule_id_bases: t.Sequence[
            tuple[
                ast.Fact,
                t.Optional[str],
                t.Optional[set[ast.Fact]],
            ]
        ],
    ):
        while fact_rule_id_bases:
            facts = {fact for fact, _, _, in fact_rule_id_bases}
            is_inferred = any(
                rule_id is not None for _, rule_id, _ in fact_rule_id_bases
            )

            stored_facts = self.bulk_create(
                (
                    StoredFact(
                        added_id=tx_id,
                        is_inferred=is_inferred,
                        **Fact.as_dict(fact),
                    )
                    for fact in facts
                ),
                ignore_conflicts=True,
            )

            fact_to_stored_fact_id: dict[ast.Fact, UUID] = {
                stored_fact.as_fact: stored_fact.id
                for stored_fact in stored_facts
            }
            fact_to_hash = {
                fact: Fact.storage_key(fact) for fact in fact_to_stored_fact_id
            }
            InferredSolution.objects.bulk_create(
                (
                    InferredSolution(
                        inferred_fact_id=fact_to_stored_fact_id[fact],
                        inferred_fact_hash=fact_to_hash[fact],
                        rule_id=rule_id,
                        solution_hash=Fact.storage_key_for_many(bases),
                    )
                    for fact, rule_id, bases in fact_rule_id_bases
                    if rule_id and bases
                ),
                ignore_conflicts=True,
            )

            fact_rule_id_bases = list(
                core.run_rules_matching(
                    [fact for fact, _, _ in fact_rule_id_bases],
                    INFERENCE_RULES,
                    self._lookup,
                )
            )
        self._garbage_collect(tx_id)

    def _remove_previous_values(
        self,
        facts: set[ast.Fact],
        tx_id: UUID,
    ):
        cardinality_one_facts: dict[tuple[str, str], type[ast.Ordinal]] = {}
        for entity, attr, _ in facts:
            attribute = ATTRIBUTES[attr]
            if attribute.cardinality == "one":
                cardinality_one_facts[(entity, attr)] = attribute.data_type

        facts_to_remove = set(
            chain(
                *(
                    self._lookup(
                        core.Clause(entity, attr, ast.TypedAny(data_type))
                    )
                    for (
                        entity,
                        attr,
                    ), data_type in cardinality_one_facts.items()
                )
            )
        )
        if facts_to_remove:
            self.bulk_remove(facts_to_remove, tx_id=tx_id)

    def remove(self, fact: ast.Fact):
        """Removes a fact form the knowledge base"""
        self.bulk_remove({fact})

    def bulk_remove(self, facts: set[ast.Fact], tx_id: t.Optional[UUID] = None):
        tx_id = tx_id or Transaction.new().id

        q = models.Q()
        for fact in facts:
            q |= models.Q(**Fact.as_dict(fact))

        stored_facts = self._is_inferred(False)._as_of_now().filter(q)
        if stored_facts.count() != len(facts):
            raise ValueError("You can't remove inferred facts")

        q = models.Q()
        while facts:
            next_facts: set[ast.Fact] = set()
            for fact, rule_id, bases in core.run_rules_matching(
                facts, INFERENCE_RULES, self._lookup
            ):
                next_facts.add(fact)
                q |= models.Q(
                    rule_id=rule_id,
                    solution_hash=Fact.storage_key_for_many(bases),
                    inferred_fact_hash=Fact.storage_key(fact),
                )
            facts = next_facts

        InferredSolution.objects.filter(q).delete()
        stored_facts.update(removed_id=tx_id)
        self._garbage_collect(tx_id)

    def solve(
        self,
        query: core.PredicateTuples,
        *,
        as_of: t.Optional[datetime | UUID] = None,
    ) -> list[core.Context]:
        """Solves the `query` and returns answers found"""
        return [
            solution.context
            for solution in self.explain_solutions(query, as_of=as_of)
        ]

    def explain_solutions(
        self,
        query: core.PredicateTuples,
        *,
        as_of: t.Optional[datetime | UUID] = None,
    ) -> list[core.Solution]:
        """Solves the `query` and returns all Solutions so you can inspect from
        which facts those solutions are derived from
        """
        return core.Query.from_tuples(ATTRIBUTES, query).solve(
            self._as_of(as_of)._lookup
        )

    def refresh_inference(self):
        """Runs all the settings.TRIPLETS_INFERENCE_RULES configured agains the
        knowledge base to keep it consistent.
        """
        tx = Transaction.new()
        # remove inferences made by old rules
        current_rules_id = [r.id for r in INFERENCE_RULES]
        InferredSolution.objects.exclude(rule_id__in=current_rules_id).delete()
        self._garbage_collect(tx.id)

        # run the current rules on the whole DB
        self._bulk_add(
            tx.id, list(core.refresh_rules(INFERENCE_RULES, self._lookup))
        )

    def _lookup(self, predicate: core.Clause) -> t.Iterable[ast.Fact]:
        "This is used by the core engine to lookup predicates in the database"
        query: dict[str, t.Any] = {
            "verb": predicate.verb,
        }
        match predicate.subject:
            case str():
                query["subject"] = predicate.subject
            case ast.TypedIn(_, values):
                query["subject__in"] = values
            case ast.TypedAny() | ast.TypedVar():
                ...
            case int():
                raise TypeError(
                    f"I was not expecting this type {type(predicate.subject)}: "
                    f"{predicate.subject} here"
                )

        match predicate.obj:
            case int(value) | str(value):
                suffix = ast.type_name(type(predicate.obj))
                query[f"obj_{suffix}"] = value
            case ast.TypedIn(_, values, data_type):
                if values:
                    suffix = ast.type_name(data_type)
                    query[f"obj_{suffix}__in"] = values
                else:
                    # this is looking for nothing, so is safe to abort here
                    return []
            case ast.TypedAny(data_type) | ast.TypedVar(_, data_type):
                suffix = ast.type_name(data_type)

        return self.filter(**query).values_list(
            "subject", "verb", f"obj_{suffix}"
        )

    def _as_of_now(self) -> "StoredFactQS":
        return self.filter(removed__isnull=True)

    def _as_of(self, when: t.Optional[datetime | UUID]) -> "StoredFactQS":
        if when is None:
            return self._as_of_now()
        else:
            if isinstance(when, datetime):
                when = (tx := Transaction.as_of(when)) and tx.id

            if when is None:
                return self.none()
            else:
                # added before the transaction
                # and removed never or after the transaction
                return self.filter(
                    models.Q(removed__isnull=True)
                    | models.Q(removed__isnull=False, removed__gt=when),
                    added__lte=when,
                )

    def _is_inferred(self, is_inferred: bool) -> "StoredFactQS":
        return self.filter(is_inferred=is_inferred)

    def _garbage_collect(self, tx_id: UUID):
        (
            self._as_of_now()
            ._is_inferred(True)
            .annotate(n_solutions=models.Count("inferred_by"))
            .filter(n_solutions=0)
            .update(removed_id=tx_id)
        )


class Transaction(models.Model):
    id: models.UUIDField[UUID, UUID] = models.UUIDField(primary_key=True)
    timestamp: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        db_index=True
    )

    objects: models.Manager["Transaction"]

    class Meta:  # type: ignore
        ordering = ["id"]

    @property
    def mutations(
        self,
    ) -> t.Iterable[tuple[t.Literal["+", "-"], ast.Fact]]:
        for added in StoredFact.objects.filter(added_id=self.id):
            yield "+", added.as_fact
        for removed in StoredFact.objects.filter(removed_id=self.id):
            yield "-", removed.as_fact

    @classmethod
    def new(cls) -> "Transaction":
        identifier = uuid7()
        timestamp = (
            (datetime)
            .utcfromtimestamp(identifier.time / NANO_SECOND)
            .astimezone(timezone.utc)
        )
        return cls.objects.create(id=identifier, timestamp=timestamp)

    @classmethod
    def as_of(cls, when: datetime) -> t.Optional["Transaction"]:
        return cls.objects.filter(timestamp__lte=when).last()


class StoredFact(models.Model):
    id: models.UUIDField[UUID, UUID] = models.UUIDField(
        primary_key=True, default=uuid7
    )

    subject: models.CharField[str, str] = models.CharField(max_length=64)
    verb: models.CharField[str, str] = models.CharField(max_length=64)

    obj_str: models.CharField[str, str] = models.CharField(
        max_length=64, null=True
    )
    obj_int: models.IntegerField[int, int] = models.IntegerField(null=True)

    @property
    def obj(self) -> ast.Ordinal:
        if self.obj_str is not None:
            return self.obj_str
        elif self.obj_int is not None:
            return self.obj_int
        raise ValueError("This fact has no value at all!")

    # flag active when this rule was derived
    is_inferred: models.BooleanField[bool, bool] = models.BooleanField()

    # on which transaction was this added
    added_id: UUID
    added: models.ForeignKey[Transaction, Transaction] = models.ForeignKey(
        Transaction, models.PROTECT, related_name="added_facts"  # type: ignore
    )

    # on which transaction was this deleted
    removed_id: t.Optional[UUID]
    removed: models.ForeignKey[
        t.Optional[Transaction], t.Optional[Transaction]
    ] = models.ForeignKey(
        Transaction,
        models.PROTECT,  # type: ignore
        null=True,
        related_name="removed_facts",
    )

    objects: StoredFactQS = StoredFactQS.as_manager()  # type: ignore

    class Meta:  # type: ignore
        unique_together = [
            ["subject", "verb", "obj_str", "obj_int", "removed"],
        ]
        indexes = [
            # used to delete InferredSolutions
            models.Index(fields=["subject", "verb", "obj_str"]),
            models.Index(fields=["subject", "verb", "obj_int"]),
            # use for as_of
            models.Index(fields=["added", "removed"]),
            # used for lookup
            models.Index(fields=["verb"]),
            models.Index(fields=["subject", "verb"]),
            models.Index(fields=["verb", "obj_str"]),
            models.Index(fields=["verb", "obj_int"]),
        ]

    def __str__(self):
        return f"{self.subject} -({self.verb})-> {self.obj}"

    @property
    def as_fact(self) -> ast.Fact:
        return (self.subject, self.verb, self.obj)


class InferredSolution(models.Model):
    """When a Fact is inferred from a Rule and a set of facts
    we need to keep track of that because inferred facts can't be manually
    deleted by the user.

    An inference rule can generate the same fact for multiple reasons
    (different set of base facts). Those reasons are tracked by each instance
    of this model
    """

    id: models.UUIDField[UUID, UUID] = models.UUIDField(
        primary_key=True, default=uuid7
    )

    inferred_fact: models.ForeignKey[
        StoredFact, StoredFact
    ] = models.ForeignKey(
        StoredFact,
        on_delete=models.PROTECT,  # type: ignore
        related_name="inferred_by",
    )
    inferred_fact_hash: models.CharField[str, str] = models.CharField(
        max_length=32
    )

    rule_id: models.CharField[str, str] = models.CharField(max_length=32)

    # join of inferred_fact_id and base_facts_hash
    solution_hash: models.CharField[str, str] = models.CharField(max_length=64)

    class Meta:  # type: ignore
        indexes = [
            models.Index(fields=["rule_id"]),
            models.Index(
                fields=["rule_id", "solution_hash", "inferred_fact_hash"]
            ),
        ]
