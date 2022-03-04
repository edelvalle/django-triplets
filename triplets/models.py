import typing as t
from datetime import datetime, timezone
from uuid import UUID

from django.conf import settings
from django.db import models
from uuid6 import uuid7

from . import core

INFERENCE_RULES: list[core.Rule] = getattr(
    settings, "TRIPLETS_INFERENCE_RULES", []
)


NANO_SECOND = 10**9


class Fact:
    @staticmethod
    def storage_key(fact: core.Fact) -> str:
        return core.storage_hash(f"fact:{fact}")

    @staticmethod
    def storage_key_for_many(facts: frozenset[core.Fact]) -> str:
        return core.storage_hash(str(list(sorted(facts))))

    @staticmethod
    def as_dict(fact: core.Fact) -> dict[str, str]:
        subject, verb, obj = fact
        return {"subject": subject, "verb": verb, "obj": obj}


class StoredFactQS(models.QuerySet):
    def add(self, fact: core.Fact) -> None:
        """Adds a fact to knowledge base."""
        self.bulk_add([fact])

    def bulk_add(self, facts: t.Sequence[core.Fact]):
        """Use this method to add many facts to the knowledge base.
        This method has better performance than adding the facts one by one.
        """
        tx = Transaction.new()
        self._bulk_add(
            tx.id,
            [(fact, None, None) for fact in facts],
        )

    def _bulk_add(
        self,
        tx_id: UUID,
        fact_rule_id_bases: t.Sequence[
            tuple[
                core.Fact,
                t.Optional[str],
                t.Optional[frozenset[core.Fact]],
            ]
        ],
    ):
        while fact_rule_id_bases:
            facts_to_store = {
                fact: rule_id is not None
                for fact, rule_id, _ in fact_rule_id_bases
            }
            stored_facts = self.bulk_create(
                (
                    StoredFact(
                        added_id=tx_id,
                        is_inferred=is_inferred,
                        **Fact.as_dict(fact),
                    )
                    for fact, is_inferred in facts_to_store.items()
                ),
                ignore_conflicts=True,
            )

            fact_to_stored_fact_id = {
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

    def remove(self, fact: core.Fact):
        """Removes a fact form the knowledge base"""
        self.bulk_remove([fact])

    def bulk_remove(self, facts: t.Sequence[core.Fact]):
        tx = Transaction.new()
        facts_set = set(facts)

        q = models.Q()
        for fact in facts_set:
            q |= models.Q(**Fact.as_dict(fact))

        stored_facts = self._is_inferred(False)._as_of_now().filter(q)
        if stored_facts.count() != len(facts_set):
            raise ValueError("You can't remove inferred facts")

        q = models.Q()
        while facts_set:
            next_facts = set()
            for fact, rule_id, bases in core.run_rules_matching(
                facts_set, INFERENCE_RULES, self._lookup
            ):
                next_facts.add(fact)
                q |= models.Q(
                    rule_id=rule_id,
                    solution_hash=Fact.storage_key_for_many(bases),
                    inferred_fact_hash=Fact.storage_key(fact),
                )
            facts_set = next_facts

        InferredSolution.objects.filter(q).delete()
        stored_facts.update(removed_id=tx.id)
        self._garbage_collect(tx.id)

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
        return core.Query.from_tuples(query).solve(self._as_of(as_of)._lookup)

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

    def _lookup(self, predicate: core.Clause) -> t.Iterable[core.Fact]:
        "This is used by the core engine to lookup predicates in the database"
        query: dict[str, str | set[str]] = {}
        for name, value in predicate.as_dict.items():
            if isinstance(value, str):
                query[name] = value
            elif isinstance(value, core.In):
                query[f"{name}__in"] = value.values

        return self.filter(**query).values_list("subject", "verb", "obj")

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

    def _is_inferred(self, is_inferred) -> "StoredFactQS":
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
    id: UUID = models.UUIDField(primary_key=True)
    timestamp: datetime = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["id"]

    @property
    def mutations(self) -> t.Iterable[tuple[t.Literal["+", "-"], core.Fact]]:
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
    def as_of(self, when: datetime) -> t.Optional["Transaction"]:
        return self.objects.filter(timestamp__lte=when).last()


class StoredFact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7)

    subject: str = models.CharField(max_length=64)
    verb: str = models.CharField(max_length=64)
    obj: str = models.CharField(max_length=64)

    # flag active when this rule was derived
    is_inferred = models.BooleanField()

    # on which transaction was this added
    added_id: UUID
    added: Transaction = models.ForeignKey(
        Transaction, models.PROTECT, related_name="added_facts"
    )

    # on which transaction was this deleted
    removed_id: t.Optional[UUID]
    removed: t.Optional[Transaction] = models.ForeignKey(
        Transaction,
        models.PROTECT,
        null=True,
        related_name="removed_facts",
    )

    objects: StoredFactQS = StoredFactQS.as_manager()

    class Meta:
        unique_together = [["subject", "verb", "obj", "removed"]]
        indexes = [
            # used to delete InferredSolutions
            models.Index(fields=["subject", "verb", "obj"]),
            # use for as_of
            models.Index(fields=["added", "removed"]),
            # used for lookup
            models.Index(fields=["verb"]),
            models.Index(fields=["subject", "verb"]),
            models.Index(fields=["verb", "obj"]),
        ]

    def __str__(self):
        return f"{self.subject} -({self.verb})-> {self.obj}"

    @property
    def as_fact(self) -> core.Fact:
        return (self.subject, self.verb, self.obj)


class InferredSolution(models.Model):
    """When a Fact is inferred from a Rule and a set of facts
    we need to keep track of that because inferred facts can't be manually
    deleted by the user.

    An inference rule can generate the same fact for multiple reasons
    (different set of base facts). Those reasons are tracked by each instance
    of this model
    """

    id: UUID = models.UUIDField(primary_key=True, default=uuid7)

    inferred_fact = models.ForeignKey(
        StoredFact,
        on_delete=models.PROTECT,
        related_name="inferred_by",
    )
    inferred_fact_hash = models.CharField(max_length=32)

    rule_id: str = models.CharField(max_length=32)

    # join of inferred_fact_id and base_facts_hash
    solution_hash = models.CharField(max_length=64)

    class Meta:
        indexes = [
            models.Index(fields=["rule_id"]),
            models.Index(
                fields=["rule_id", "solution_hash", "inferred_fact_hash"]
            ),
        ]
