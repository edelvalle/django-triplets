from collections import defaultdict
from dataclasses import dataclass, field

from .. import core
from ..core import Var, rule

triplets = [
    # the broder
    ("brother", "child_of", "father"),
    ("brother", "child_of", "mother"),
    ("brother", "gender", "m"),
    # the sister
    ("sister", "child_of", "father"),
    ("sister", "child_of", "mother"),
    ("sister", "gender", "f"),
    # the parents
    ("father", "gender", "m"),
    ("mother", "gender", "f"),
    # the grand parent
    ("father", "child_of", "grandfather"),
    ("grandfather", "gender", "m"),
]


siblings_rule = rule(
    [
        (Var("child1"), "child_of", Var("parent")),
        (Var("child2"), "child_of", Var("parent")),
    ],
    implies=[(Var("child1"), "sibling_of", Var("child2"))],
)

symmetric_sibling_rule = rule(
    [
        (Var("child1"), "child_of", Var("parent")),
        (Var("child2"), "child_of", Var("parent")),
    ],
    implies=[
        (Var("child1"), "sibling_of", Var("child2")),
        (Var("child2"), "sibling_of", Var("child1")),
    ],
)

descendants_rules = [
    rule(
        [
            (Var("child"), "child_of", Var("parent")),
        ],
        implies=[(Var("child"), "descendant_of", Var("parent"))],
    ),
    rule(
        [
            (Var("grandchild"), "descendant_of", Var("parent")),
            (Var("parent"), "descendant_of", Var("grandparent")),
        ],
        implies=[(Var("grandchild"), "descendant_of", Var("grandparent"))],
    ),
]


@dataclass
class Database:

    # the existence of the triplet means that it exists
    # the value tells if it is infferred
    triplets: dict[core.Triplet, bool] = field(default_factory=dict)

    # this represents the dependencies of an inferred triplet
    # when the set is empty it means that that triplet should be deleted
    dependencies_of: defaultdict[
        core.Triplet, set[tuple[str, frozenset[core.Triplet]]]
    ] = field(default_factory=lambda: defaultdict(set))

    rules: list[core.Rule] = field(default_factory=list)

    def lookup(self, predicate: core.Predicate):
        terms = list(predicate)
        for fact in self.triplets:
            matches = all(
                isinstance(lookup_term, core.Var)
                or (
                    isinstance(lookup_term, core.In)
                    and fact_term in lookup_term.values
                )
                or lookup_term == fact_term
                for fact_term, lookup_term in zip(fact, terms)
            )
            if matches:
                yield fact

    def solve(
        self, predicates: core.ListOfPredicateTuples
    ) -> list[core.Solution]:
        return core.Query.from_tuples(predicates).solve(self.lookup)

    def add(self, triplet: core.Triplet):
        self._add(triplet, is_infferred=False)

    def _add(self, triplet: core.Triplet, *, is_infferred: bool) -> None:
        if triplet not in self.triplets:
            self.triplets[triplet] = is_infferred
            core.run_rules_matching(
                triplet,
                self.rules,
                self.lookup,
                self._add_by_rule,
            )

    def _add_by_rule(
        self,
        triplet: core.Triplet,
        rule_id: str,
        derived_from: frozenset[core.Triplet],
    ):
        self._add(triplet, is_infferred=True)
        self.dependencies_of[triplet].add((rule_id, derived_from))

    def refresh_inference(self):
        """Removes deductions made by all rules and runs all the inference rules
        against the database
        """
        self._remove_deductions_made_by_old_rules()
        core.refresh_rules(self.rules, self.lookup, self._add_by_rule)

    def _remove_deductions_made_by_old_rules(self):
        current_rule_ids = frozenset(r.id for r in self.rules)
        for triplet, is_infferred in self.triplets.items():
            if is_infferred:
                self.dependencies_of[triplet] = [
                    (rule_id, dependent_from)
                    for (rule_id, dependent_from) in self.dependencies_of[
                        triplet
                    ]
                    if rule_id in current_rule_ids
                ]
        self._garbage_collect()

    def remove(self, triplet: core.Triplet):
        if self.triplets[triplet]:
            raise ValueError("You can't remove a inferred triplet")
        core.run_rules_matching(
            triplet, self.rules, self.lookup, self._remove_by_rule
        )
        del self.triplets[triplet]
        self._garbage_collect()

    def _remove_by_rule(
        self,
        triplet: core.Triplet,
        rule_id: str,
        derived_from: frozenset[core.Triplet],
    ):
        self.dependencies_of[triplet].remove((rule_id, derived_from))
        core.run_rules_matching(
            triplet, self.rules, self.lookup, self._remove_by_rule
        )

    def _garbage_collect(self):
        to_delete = [
            triplet
            for triplet, is_infferred in self.triplets.items()
            if is_infferred and not self.dependencies_of[triplet]
        ]
        for triplet in to_delete:
            del self.triplets[triplet]
            del self.dependencies_of[triplet]
