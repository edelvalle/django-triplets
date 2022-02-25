import typing as t
from uuid import UUID, uuid4

from django.conf import settings
from django.db import models

from . import core

INFERENCE_RULES: list[core.Rule] = getattr(
    settings, "TRIPLETS_INFERENCE_RULES", []
)
ML_SUBJECT, ML_VERB, ML_OBJ = getattr(
    settings, "TRIPLETS_MAX_LENGTHS", (32, 32, 32)
)


class Triplet:
    @staticmethod
    def storage_key(triplet: core.Triplet) -> str:
        return core.storage_hash(f"triplet:{triplet}")

    @staticmethod
    def storage_key_for_many(triplets: frozenset[core.Triplet]) -> str:
        return core.storage_hash(str(triplets))

    @staticmethod
    def as_dict(triplet: core.Triplet) -> dict[str, str]:
        subject, verb, obj = triplet
        return {"subject": subject, "verb": verb, "obj": obj}


class StoredTripletQS(models.QuerySet):
    def add(self, triplet: core.Triplet) -> None:
        """Adds a triplet to knowledge base."""
        self.bulk_add([triplet])

    def bulk_add(self, triplets: t.Sequence[core.Triplet]):
        """Use this method to add many triplets to the knowledge base.

        This method has better performance than adding the triplets one by one.
        """
        self.bulk_create(
            StoredTriplet(
                id=Triplet.storage_key(triplet),
                is_inferred=False,
                **Triplet.as_dict(triplet),
            )
            for triplet in triplets
        )
        for triplet in triplets:
            core.run_rules_matching(
                triplet, INFERENCE_RULES, self._lookup, self._add_by_rule
            )

    def remove(self, triplet: core.Triplet):
        """Removes a triplet form the knowledge base"""
        stored_triplet = self.filter(id=Triplet.storage_key(triplet)).first()
        if stored_triplet.is_inferred:
            raise ValueError("You can't remove inferred triplets")
        core.run_rules_matching(
            triplet, INFERENCE_RULES, self._lookup, self._remove_by_rule
        )
        stored_triplet.delete()
        self._garbage_collect()

    def solve(self, query: core.ListOfPredicateTuples) -> list[core.Context]:
        """Solves the `query` and returns answers found"""
        return [solution.context for solution in self.explain(query)]

    def explain(self, query: core.ListOfPredicateTuples) -> list[core.Solution]:
        """Solves the `query` and returns all Solutions so you can inspect from
        which triplets those solutions are derived from
        """
        return core.Query.from_tuples(query).solve(self._lookup)

    def refresh_inference(self):
        """Runs all the settings.TRIPLETS_INFERENCE_RULES configured"""
        # remove inferences made by old rules
        current_rules_id = [r.id for r in INFERENCE_RULES]
        InferredSolution.objects.exclude(rule_id__in=current_rules_id).delete()
        self._garbage_collect()

        # run the current rules on the whole DB
        core.refresh_rules(INFERENCE_RULES, self._lookup, self._add_by_rule)

    def _add_by_rule(
        self,
        triplet: core.Triplet,
        rule_id: str,
        base_triplets: frozenset[core.Triplet],
    ):
        _, created = self.get_or_create(
            id=Triplet.storage_key(triplet),
            defaults=Triplet.as_dict(triplet) | {"is_inferred": True},
        )
        if created:
            core.run_rules_matching(
                triplet, INFERENCE_RULES, self._lookup, self._add_by_rule
            )

        InferredSolution.objects.get_or_create(
            inferred_triplet_id=Triplet.storage_key(triplet),
            rule_id=rule_id,
            base_triplets_hash=Triplet.storage_key_for_many(base_triplets),
        )

    def _remove_by_rule(
        self,
        triplet: core.Triplet,
        rule_id: str,
        base_triplets: frozenset[core.Triplet],
    ):
        InferredSolution.objects.filter(
            inferred_triplet_id=Triplet.storage_key(triplet),
            rule_id=rule_id,
            base_triplets_hash=Triplet.storage_key_for_many(base_triplets),
        ).delete()

        core.run_rules_matching(
            triplet, INFERENCE_RULES, self._lookup, self._remove_by_rule
        )

    def _lookup(self, predicate: core.Predicate) -> t.Iterable[core.Triplet]:
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

    # TODO: max_length here should be configurable
    subject: str = models.CharField(max_length=ML_SUBJECT)
    verb: str = models.CharField(max_length=ML_VERB)
    obj: str = models.CharField(max_length=ML_VERB)

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

    def __iter__(self) -> t.Iterable[str]:
        return iter([self.subject, self.verb, self.obj])


class InferredSolution(models.Model):
    """When a Triplet is inferred from a Rule and a set of triplets
    we need to keep track of that because inferred triplets can't be manually
    deleted by the user.

    An inference rule can generate the same triplet for multiple reasons
    (different set of base triplets). Those reasons are tracked by each instance
    of this model
    """

    id: UUID = models.UUIDField(primary_key=True, default=uuid4)

    inferred_triplet = models.ForeignKey(
        StoredTriplet,
        on_delete=models.PROTECT,
        related_name="inferred_by",
    )
    rule_id: str = models.CharField(max_length=32, db_index=True)
    base_triplets_hash = models.CharField(max_length=32)

    class Meta:
        unique_together = [
            ["inferred_triplet", "rule_id", "base_triplets_hash"]
        ]
