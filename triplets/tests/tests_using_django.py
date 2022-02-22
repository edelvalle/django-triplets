from django.test import TestCase

from ..core import Predicate, Var
from ..models import StoredTriplet
from . import common


class TestDjangoInference(TestCase):
    def setUp(self):
        for triplet in common.triplets:
            StoredTriplet.objects.add(triplet)

    def solve(self, *args, **kwargs):
        return list(StoredTriplet.objects.solve(*args, **kwargs))

    def test_solving_single_query_with_two_variables(self):
        query = [Predicate(Var("child"), "child_of", Var("parent"))]
        with self.assertNumQueries(1):
            self.assertListEqual(
                self.solve(query),
                [
                    {"child": "perico", "parent": "emilio"},
                    {"child": "juan", "parent": "maria"},
                    {"child": "juana", "parent": "maria"},
                    {"child": "juan", "parent": "perico"},
                    {"child": "juana", "parent": "perico"},
                ],
            )

    def test_solving_single_query_with_subject_variables(self):
        query = [Predicate(Var("child"), "child_of", "perico")]
        with self.assertNumQueries(1):
            self.assertListEqual(
                self.solve(query),
                [
                    {"child": "juan"},
                    {"child": "juana"},
                ],
            )

    def test_solving_single_query_with_object_variables(self):
        query = [Predicate("juan", "child_of", Var("parent"))]

        with self.assertNumQueries(1):
            self.assertListEqual(
                self.solve(query),
                [
                    {"parent": "perico"},
                    {"parent": "maria"},
                ],
            )

    def test_solving_single_query_with_true_fact(self):
        query = [Predicate("juan", "child_of", "perico")]
        with self.assertNumQueries(1):
            self.assertListEqual(self.solve(query), [{}])

    def test_solving_single_query_with_false_fact(self):
        query = [Predicate("juan", "child_of", "X")]
        with self.assertNumQueries(1):
            self.assertListEqual(self.solve(query), [])

    def test_solving_multiple_queries(self):
        query = [
            Predicate(Var("parent"), "child_of", Var("grandparent")),
            Predicate(Var("grandchild"), "child_of", Var("parent")),
        ]
        with self.assertNumQueries(2):
            self.assertListEqual(
                self.solve(query),
                [
                    {
                        "parent": "perico",
                        "grandchild": "juan",
                        "grandparent": "emilio",
                    },
                    {
                        "grandchild": "juana",
                        "parent": "perico",
                        "grandparent": "emilio",
                    },
                ],
            )

    def test_solving_multiple_queries_looking_for_male_son(self):
        query = [
            Predicate(Var("son"), "child_of", Var("parent")),
            Predicate(Var("son"), "gender", "m"),
        ]
        with self.assertNumQueries(2):
            self.assertListEqual(
                self.solve(query),
                [
                    {"son": "juan", "parent": "perico"},
                    {"son": "juan", "parent": "maria"},
                    {"son": "perico", "parent": "emilio"},
                ],
            )


    def test_solving_looking_for_siblings(self):
        query = [
            Predicate(Var("child1"), "child_of", Var("parent")),
            Predicate(Var("child2"), "child_of", Var("parent")),
        ]
        with self.assertNumQueries(2):
            self.assertListEqual(
                self.solve(query),
                [
                    {"child1": "juan", "child2": "juana", "parent": "maria"},
                    {"child1": "juana", "child2": "juan", "parent": "maria"},
                    {"child1": "juan", "child2": "juana", "parent": "perico"},
                    {"child1": "juana", "child2": "juan", "parent": "perico"},
                ],
            )
