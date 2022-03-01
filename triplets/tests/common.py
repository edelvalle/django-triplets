import typing as t
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

    # the existence of the fact means that it exists
    # the value tells if it is infferred
    triplets: dict[core.Fact, bool] = field(default_factory=dict)

    # this represents the dependencies of an inferred fact
    # when the set is empty it means that that fact should be deleted
    dependencies_of: defaultdict[
        core.Fact, set[tuple[str, frozenset[core.Fact]]]
    ] = field(default_factory=lambda: defaultdict(set))

    rules: list[core.Rule] = field(default_factory=list)

    def lookup(self, clause: core.Clause):
        terms = list(clause)
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

    def solve(self, predicate: core.PredicateTuples) -> list[core.Solution]:
        return core.Query.from_tuples(predicate).solve(self.lookup)

    def add(self, fact: core.Fact):
        self._add(fact, is_infferred=False)

    def _add(self, fact: core.Fact, *, is_infferred: bool) -> None:
        if fact not in self.triplets:
            self.triplets[fact] = is_infferred
            core.run_rules_matching(
                fact,
                self.rules,
                self.lookup,
                self._add_by_rule,
            )

    def _add_by_rule(
        self,
        rule_id: str,
        triplets_and_bases: t.Iterable[tuple[core.Fact, frozenset[core.Fact]]],
    ):
        for fact, derived_from in triplets_and_bases:
            self._add(fact, is_infferred=True)
            self.dependencies_of[fact].add((rule_id, derived_from))

    def refresh_inference(self):
        """Removes deductions made by all rules and runs all the inference rules
        against the database
        """
        self._remove_deductions_made_by_old_rules()
        core.refresh_rules(self.rules, self.lookup, self._add_by_rule)

    def _remove_deductions_made_by_old_rules(self):
        current_rule_ids = frozenset(r.id for r in self.rules)
        for fact, is_infferred in self.triplets.items():
            if is_infferred:
                self.dependencies_of[fact] = [
                    (rule_id, dependent_from)
                    for (rule_id, dependent_from) in self.dependencies_of[fact]
                    if rule_id in current_rule_ids
                ]
        self._garbage_collect()

    def remove(self, fact: core.Fact):
        if self.triplets[fact]:
            raise ValueError("You can't remove a inferred fact")
        core.run_rules_matching(
            fact, self.rules, self.lookup, self._remove_by_rule
        )
        del self.triplets[fact]
        self._garbage_collect()

    def _remove_by_rule(
        self,
        rule_id: str,
        triplets_and_bases: t.Iterable[tuple[core.Fact, frozenset[core.Fact]]],
    ):
        for fact, derived_from in triplets_and_bases:
            self.dependencies_of[fact].remove((rule_id, derived_from))

    def _garbage_collect(self):
        to_delete = [
            fact
            for fact, is_infferred in self.triplets.items()
            if is_infferred and not self.dependencies_of[fact]
        ]
        for fact in to_delete:
            del self.triplets[fact]
            del self.dependencies_of[fact]
