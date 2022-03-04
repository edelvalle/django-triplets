from django.test import TestCase

from .. import api, models
from ..core import PredicateTuples, Rule, Var, rule

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


class TestUsingDjango(TestCase):
    def tearDown(self):
        models.INFERENCE_RULES = []

    def populate_db(self, rules: list[Rule]):
        models.INFERENCE_RULES = rules
        api.bulk_add(triplets)

    def solve(self, predicate: PredicateTuples):
        return api.solve(predicate)

    def explain_solutions(self, predicate: PredicateTuples):
        return api.explain_solutions(predicate)
