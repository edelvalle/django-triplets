from ..core import Var
from . import common_django


class TestDjango(common_django.TestUsingDjango):
    def setUp(self):
        self.populate_db([])

    def test_solving_single_query_with_two_variables(self):
        query = [(Var("child"), "child_of", Var("parent"))]
        with self.assertNumQueries(1):
            self.assertListEqual(
                self.solve(query),
                [
                    {"child": "brother", "parent": "father"},
                    {"child": "sister", "parent": "father"},
                    {"child": "father", "parent": "grandfather"},
                    {"child": "brother", "parent": "mother"},
                    {"child": "sister", "parent": "mother"},
                ],
            )

    def test_solving_single_query_with_subject_variables(self):
        query = [(Var("child"), "child_of", "father")]
        with self.assertNumQueries(1):
            self.assertListEqual(
                self.solve(query),
                [
                    {"child": "brother"},
                    {"child": "sister"},
                ],
            )

    def test_solving_single_query_with_object_variables(self):
        query = [("brother", "child_of", Var("parent"))]
        with self.assertNumQueries(1):
            self.assertListEqual(
                self.solve(query),
                [
                    {"parent": "father"},
                    {"parent": "mother"},
                ],
            )

    def test_solving_single_query_with_true_fact(self):
        query = [("brother", "child_of", "father")]
        with self.assertNumQueries(1):
            self.assertListEqual(self.solve(query), [{}])

    def test_solving_single_query_with_false_fact(self):
        query = [("brother", "child_of", "X")]
        with self.assertNumQueries(1):
            self.assertListEqual(self.solve(query), [])

    def test_solving_multiple_queries(self):
        query = [
            (Var("parent"), "child_of", Var("grandparent")),
            (Var("grandchild"), "child_of", Var("parent")),
        ]
        with self.assertNumQueries(2):
            self.assertListEqual(
                self.solve(query),
                [
                    {
                        "parent": "father",
                        "grandchild": "brother",
                        "grandparent": "grandfather",
                    },
                    {
                        "grandchild": "sister",
                        "parent": "father",
                        "grandparent": "grandfather",
                    },
                ],
            )

    def test_solving_multiple_queries_looking_for_male_son(self):
        query = [
            (Var("son"), "child_of", Var("parent")),
            (Var("son"), "gender", "m"),
        ]
        with self.assertNumQueries(2):
            self.assertListEqual(
                self.solve(query),
                [
                    {"son": "brother", "parent": "father"},
                    {"son": "brother", "parent": "mother"},
                    {"son": "father", "parent": "grandfather"},
                ],
            )

    def test_solving_looking_for_siblings(self):
        query = [
            (Var("child1"), "child_of", Var("parent")),
            (Var("child2"), "child_of", Var("parent")),
        ]

        with self.assertNumQueries(2):
            self.assertListEqual(
                self.solve(query),
                [
                    {
                        "child1": "brother",
                        "child2": "sister",
                        "parent": "father",
                    },
                    {
                        "child1": "sister",
                        "child2": "brother",
                        "parent": "father",
                    },
                    {
                        "child1": "brother",
                        "child2": "sister",
                        "parent": "mother",
                    },
                    {
                        "child1": "sister",
                        "child2": "brother",
                        "parent": "mother",
                    },
                ],
            )
