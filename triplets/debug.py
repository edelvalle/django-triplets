from dataclasses import dataclass

from base import Predicate, Query, Var


@dataclass
class Triplet:
    subject: str
    verb: str
    obj: str


@dataclass
class Database:
    triplets: list[Triplet]

    def lookup(self, predicate: Predicate):
        lookup_data = [predicate.subject, predicate.verb, predicate.obj]

        for fact in self.triplets:
            fact_data = [fact.subject, fact.verb, fact.obj]
            matches = all(
                isinstance(lookup, Var) or lookup == fact
                for fact, lookup in zip(fact_data, lookup_data)
            )
            if matches:
                yield fact

    def solutions(self, predicates: list[Predicate]):
        return Query(predicates).solve_using(self)


db = Database(
    [
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
)

query = [
    Predicate(Var("grandchild"), "child_of", Var("parent")),
    Predicate(Var("parent"), "child_of", Var("grandparent")),
]


assert list(db.solutions(query)) == [
    {
        "grandchild": "juan",
        "parent": "juan",
        "grandparent": "perico",
    },
    {
        "grandchild": "juana",
        "parent": "juan",
        "grandparent": "perico",
    },
]
