import typing as t
from datetime import datetime
from uuid import UUID

from django.test import TestCase

from .. import api, models
from ..ast import Attr, Ordinal, Var
from ..core import PredicateTuples, Rule, compile_rules

attributes = Attr.as_dict(
    Attr("gender", str, "one"),
    Attr("child_of", str, "many"),
    Attr("sibling_of", str, "many"),
    Attr("descendant_of", str, "many"),
    Attr("mom_of", str, "many"),
    Attr("dad_of", str, "many"),
    Attr("age", int, "one"),
)


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


class DadOf:
    predicate = [
        (Var("child"), "child_of", Var("parent")),
        (Var("parent"), "gender", "m"),
    ]
    implies = [(Var("parent"), "dad_of", Var("child"))]


class MomOf:
    predicate = [
        (Var("child"), "child_of", Var("parent")),
        (Var("parent"), "gender", "f"),
    ]
    implies = [(Var("parent"), "mom_of", Var("child"))]


parent_role_rules = compile_rules(attributes, [DadOf, MomOf])


class SiblingOf:
    predicate = [
        (Var("child1"), "child_of", Var("parent")),
        (Var("child2"), "child_of", Var("parent")),
    ]
    implies = [(Var("child1"), "sibling_of", Var("child2"))]


siblings_rule = compile_rules(attributes, [SiblingOf])


class SymmetricSibingOf:
    predicate = [
        (Var("child1"), "child_of", Var("parent")),
        (Var("child2"), "child_of", Var("parent")),
    ]
    implies = [
        (Var("child1"), "sibling_of", Var("child2")),
        (Var("child2"), "sibling_of", Var("child1")),
    ]


symmetric_sibling_rule = compile_rules(attributes, [SiblingOf])


class DescendentOfDirectParent:
    predicate = [(Var("child"), "child_of", Var("parent"))]
    implies = [(Var("child"), "descendant_of", Var("parent"))]


class DescendantOfRecursive:
    predicate = [
        (Var("grandchild"), "descendant_of", Var("parent")),
        (Var("parent"), "descendant_of", Var("grandparent")),
    ]
    implies = [(Var("grandchild"), "descendant_of", Var("grandparent"))]


descendants_rules = compile_rules(
    attributes, [DescendentOfDirectParent, DescendantOfRecursive]
)


class TestUsingDjango(TestCase):
    def tearDown(self):
        models.INFERENCE_RULES = []

    def populate_db(self, rules: list[Rule]):
        models.INFERENCE_RULES = rules
        models.ATTRIBUTES = attributes
        api.bulk_add(triplets)

    def solve(
        self,
        query: PredicateTuples,
        *,
        as_of: t.Optional[datetime | UUID] = None,
    ) -> set[frozenset[tuple[str, Ordinal]]]:
        return {
            frozenset(solution.items())
            for solution in api.solve(query, as_of=as_of)
        }

    def explain_solutions(
        self,
        query: PredicateTuples,
        *,
        as_of: t.Optional[datetime | UUID] = None,
    ):
        return set(api.explain_solutions(query, as_of=as_of))

    checkNumQueries = True

    def print_transaction_log(self):
        print()
        for tx in models.Transaction.objects.all():
            print(tx)
            for mutation in tx.mutations:
                print(*mutation)

    def assertNumQueries(self, number: int):
        if self.checkNumQueries:
            return super().assertNumQueries(number)
        else:
            from contextlib import contextmanager

            @contextmanager
            def dummy(number: int):
                yield None

            return dummy(number)
