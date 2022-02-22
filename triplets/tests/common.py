from dataclasses import dataclass

from .. import core
from ..models import Triplet

triplets = [
    # the broder
    Triplet("juan", "child_of", "perico"),
    Triplet("juan", "child_of", "maria"),
    Triplet("juan", "gender", "m"),
    # the sister
    Triplet("juana", "child_of", "perico"),
    Triplet("juana", "child_of", "maria"),
    Triplet("juana", "gender", "f"),
    # the parents
    Triplet("perico", "gender", "m"),
    Triplet("maria", "gender", "f"),
    # the grand parent
    Triplet("perico", "child_of", "emilio"),
    Triplet("emilio", "gender", "m"),
]


@dataclass
class Database(core.Database):
    triplets: list[Triplet]

    def lookup(self, predicate: core.Predicate):
        lookup_data = [predicate.subject, predicate.verb, predicate.obj]

        for fact in self.triplets:
            fact_data = [fact.subject, fact.verb, fact.obj]
            matches = all(
                isinstance(lookup, core.Var)
                or (isinstance(lookup, core.In) and fact_term in lookup.values)
                or lookup == fact_term
                for fact_term, lookup in zip(fact_data, lookup_data)
            )
            if matches:
                yield fact

    def solve(self, predicates: list[core.Predicate]):
        return core.Query(predicates).solve_using(self)
