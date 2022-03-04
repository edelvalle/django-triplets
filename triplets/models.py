import typing as t
from uuid import UUID

from django.conf import settings
from django.db import models
from uuid6 import uuid7

from . import core

INFERENCE_RULES: list[core.Rule] = getattr(
    settings, "TRIPLETS_INFERENCE_RULES", []
)


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
        self._bulk_add(
            [(Fact.storage_key(fact), fact, None, None) for fact in facts]
        )

    def _bulk_add(
        self,
        key_fact_rule_id_bases: t.Sequence[
            tuple[
                str,
                core.Fact,
                t.Optional[str],
                t.Optional[frozenset[core.Fact]],
            ]
        ],
    ):
        while key_fact_rule_id_bases:
            self.bulk_create(
                (
                    StoredFact(
                        id=key,
                        is_inferred=rule_id is not None,
                        **Fact.as_dict(fact),
                    )
                    for key, fact, rule_id, _ in key_fact_rule_id_bases
                ),
                ignore_conflicts=True,
            )

            InferredSolution.objects.bulk_create(
                (
                    InferredSolution(
                        inferred_fact_id=key,
                        rule_id=rule_id,
                        solution_hash=key + Fact.storage_key_for_many(bases),
                    )
                    for key, _, rule_id, bases in key_fact_rule_id_bases
                    if rule_id and bases
                ),
                ignore_conflicts=True,
            )

            key_fact_rule_id_bases = [
                (Fact.storage_key(fact), fact, rule_id, bases)
                for fact, rule_id, bases in core.run_rules_matching(
                    [fact for _, fact, _, _ in key_fact_rule_id_bases],
                    INFERENCE_RULES,
                    self._lookup,
                )
            ]

    def remove(self, fact: core.Fact):
        """Removes a fact form the knowledge base"""
        self.bulk_remove([fact])

    def bulk_remove(self, facts: t.Sequence[core.Fact]):
        facts_set = set(facts)
        stored_facts = self.filter(
            id__in=[Fact.storage_key(fact) for fact in facts_set],
            is_inferred=False,
        )
        if stored_facts.count() != len(facts_set):
            raise ValueError("You can't remove inferred facts")

        q = models.Q()
        while facts_set:
            next_facts = set()
            for fact, rule_id, bases in core.run_rules_matching(
                facts_set, INFERENCE_RULES, self._lookup
            ):
                key = Fact.storage_key(fact)
                next_facts.add(fact)
                q |= models.Q(
                    inferred_fact_id=key,
                    rule_id=rule_id,
                    solution_hash=key + Fact.storage_key_for_many(bases),
                )
            facts_set = next_facts

        InferredSolution.objects.filter(q).delete()
        stored_facts.delete()
        self._garbage_collect()

    def solve(self, query: core.PredicateTuples) -> list[core.Context]:
        """Solves the `query` and returns answers found"""
        return [solution.context for solution in self.explain_solutions(query)]

    def explain_solutions(
        self, query: core.PredicateTuples
    ) -> list[core.Solution]:
        """Solves the `query` and returns all Solutions so you can inspect from
        which facts those solutions are derived from
        """
        return core.Query.from_tuples(query).solve(self._lookup)

    def refresh_inference(self):
        """Runs all the settings.TRIPLETS_INFERENCE_RULES configured agains the
        knowledge base to keep it consistent.
        """
        # remove inferences made by old rules
        current_rules_id = [r.id for r in INFERENCE_RULES]
        InferredSolution.objects.exclude(rule_id__in=current_rules_id).delete()
        self._garbage_collect()

        # run the current rules on the whole DB
        self._bulk_add(
            [
                (Fact.storage_key(fact), fact, rule_id, bases)
                for fact, rule_id, bases in core.refresh_rules(
                    INFERENCE_RULES, self._lookup
                )
            ]
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

    def _garbage_collect(self):
        (
            self.filter(is_inferred=True)
            .annotate(n_solutions=models.Count("inferred_by"))
            .filter(n_solutions=0)
            .delete()
        )


class StoredFact(models.Model):
    id = models.CharField(primary_key=True, max_length=32)

    subject: str = models.CharField(max_length=64)
    verb: str = models.CharField(max_length=64)
    obj: str = models.CharField(max_length=64)

    is_inferred = models.BooleanField(db_index=True)

    objects: StoredFactQS = StoredFactQS.as_manager()

    class Meta:
        unique_together = [["subject", "verb", "obj"]]
        indexes = [
            models.Index(fields=["verb"]),
            models.Index(fields=["subject", "verb"]),
            models.Index(fields=["verb", "obj"]),
        ]

    def __str__(self):
        return f"{self.subject} -({self.verb})-> {self.obj}"


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
    rule_id: str = models.CharField(max_length=32, db_index=True)

    # join of inferred_fact_id and base_facts_hash
    solution_hash = models.CharField(max_length=64)

    class Meta:
        unique_together = [["rule_id", "solution_hash"]]
