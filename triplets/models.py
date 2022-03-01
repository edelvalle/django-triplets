import typing as t
from uuid import UUID

from django.conf import settings
from django.db import models
from uuid6 import uuid7

from . import core

INFERENCE_RULES: list[core.Rule] = getattr(
    settings, "TRIPLETS_INFERENCE_RULES", []
)
ML_SUBJECT, ML_VERB, ML_OBJ = getattr(
    settings, "TRIPLETS_MAX_LENGTHS", (32, 32, 32)
)


class Fact:
    @staticmethod
    def storage_key(fact: core.Fact) -> str:
        return core.storage_hash(f"fact:{fact}")

    @staticmethod
    def storage_key_for_many(facts: frozenset[core.Fact]) -> str:
        return core.storage_hash(str(facts))

    @staticmethod
    def as_dict(fact: core.Fact) -> dict[str, str]:
        subject, verb, obj = fact
        return {"subject": subject, "verb": verb, "obj": obj}


class StoredTripletQS(models.QuerySet):
    def add(self, fact: core.Fact) -> None:
        """Adds a fact to knowledge base."""
        self.bulk_add([fact])

    def bulk_add(self, triplets: t.Sequence[core.Fact]):
        """Use this method to add many triplets to the knowledge base.
        This method has better performance than adding the triplets one by one.
        """
        self.bulk_create(
            StoredTriplet(
                id=Fact.storage_key(fact),
                is_inferred=False,
                **Fact.as_dict(fact),
            )
            for fact in triplets
        )
        for fact in triplets:
            core.run_rules_matching(
                fact, INFERENCE_RULES, self._lookup, self._add_by_rule
            )

    def remove(self, fact: core.Fact):
        """Removes a fact form the knowledge base"""
        stored_triplet = self.filter(id=Fact.storage_key(fact)).get()
        if stored_triplet.is_inferred:
            raise ValueError("You can't remove inferred triplets")
        core.run_rules_matching(
            fact, INFERENCE_RULES, self._lookup, self._remove_by_rule
        )
        stored_triplet.delete()
        self._garbage_collect()

    def solve(self, query: core.PredicateTuples) -> list[core.Context]:
        """Solves the `query` and returns answers found"""
        return [solution.context for solution in self.explain_solutions(query)]

    def explain_solutions(
        self, query: core.PredicateTuples
    ) -> list[core.Solution]:
        """Solves the `query` and returns all Solutions so you can inspect from
        which triplets those solutions are derived from
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
        core.refresh_rules(INFERENCE_RULES, self._lookup, self._add_by_rule)

    def _add_by_rule(
        self,
        rule_id: str,
        triplets_and_bases: t.Sequence[tuple[core.Fact, frozenset[core.Fact]]],
    ):
        keys_triplets_bases_hash = [
            (
                Fact.storage_key(fact),
                fact,
                Fact.storage_key_for_many(bases),
            )
            for fact, bases in triplets_and_bases
        ]
        self.bulk_create(
            (
                StoredTriplet(
                    id=key,
                    is_inferred=True,
                    **Fact.as_dict(fact),
                )
                for key, fact, _ in keys_triplets_bases_hash
            ),
            ignore_conflicts=True,
        )
        InferredSolution.objects.bulk_create(
            (
                InferredSolution(
                    inferred_triplet_id=key,
                    rule_id=rule_id,
                    solution_hash=key + bases_hash,
                )
                for key, _, bases_hash in keys_triplets_bases_hash
            ),
            ignore_conflicts=True,
        )

    def _remove_by_rule(
        self,
        rule_id: str,
        triplets_and_bases: t.Sequence[tuple[core.Fact, frozenset[core.Fact]]],
    ):
        InferredSolution.objects.filter(
            rule_id=rule_id,
            solution_hash__in=[
                Fact.storage_key(fact) + Fact.storage_key_for_many(bases)
                for fact, bases in triplets_and_bases
            ],
        ).delete()

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


class StoredTriplet(models.Model):
    id = models.CharField(primary_key=True, max_length=32)

    subject: str = models.CharField(max_length=ML_SUBJECT)
    verb: str = models.CharField(max_length=ML_VERB)
    obj: str = models.CharField(max_length=ML_VERB)

    # uuid7, entity, attr, value, is_inferred, died_on, kills, transaction_uuid7

    is_inferred = models.BooleanField(db_index=True)

    objects: StoredTripletQS = StoredTripletQS.as_manager()

    class Meta:
        unique_together = [["subject", "verb", "obj"]]
        indexes = [
            models.Index(fields=["verb"]),
            models.Index(fields=["subject", "verb"]),
            models.Index(fields=["verb", "obj"]),
        ]

    def __str__(self):
        return " -> ".join(self)


class InferredSolution(models.Model):
    """When a Fact is inferred from a Rule and a set of triplets
    we need to keep track of that because inferred triplets can't be manually
    deleted by the user.

    An inference rule can generate the same fact for multiple reasons
    (different set of base triplets). Those reasons are tracked by each instance
    of this model
    """

    id: UUID = models.UUIDField(primary_key=True, default=uuid7)

    inferred_triplet = models.ForeignKey(
        StoredTriplet,
        on_delete=models.PROTECT,
        related_name="inferred_by",
    )
    rule_id: str = models.CharField(max_length=32, db_index=True)

    # join of inferred_triplet_id and base_triplets_hash
    solution_hash = models.CharField(max_length=64)

    class Meta:
        unique_together = [["rule_id", "solution_hash"]]
