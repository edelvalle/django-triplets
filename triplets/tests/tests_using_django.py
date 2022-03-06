from ..core import Var
from . import common


class TestDjango(common.TestUsingDjango):
    checkNumQueries = False

    def setUp(self):
        self.populate_db([])

    def test_solving_single_query_with_two_variables(self):
        query = [(Var("child"), "child_of", Var("parent"))]
        with self.assertNumQueries(1):
            self.assertSetEqual(
                self.solve(query),
                {
                    frozenset({("child", "brother"), ("parent", "father")}),
                    frozenset({("child", "sister"), ("parent", "father")}),
                    frozenset({("child", "father"), ("parent", "grandfather")}),
                    frozenset({("child", "brother"), ("parent", "mother")}),
                    frozenset({("child", "sister"), ("parent", "mother")}),
                },
            )

    def test_solving_single_query_with_subject_variables(self):
        query = [(Var("child"), "child_of", "father")]
        with self.assertNumQueries(1):
            self.assertSetEqual(
                self.solve(query),
                {
                    frozenset({("child", "brother")}),
                    frozenset({("child", "sister")}),
                },
            )

    def test_solving_single_query_with_object_variables(self):
        query = [("brother", "child_of", Var("parent"))]
        with self.assertNumQueries(1):
            self.assertSetEqual(
                self.solve(query),
                {
                    frozenset({("parent", "father")}),
                    frozenset({("parent", "mother")}),
                },
            )

    def test_solving_single_query_with_true_fact(self):
        query = [("brother", "child_of", "father")]
        with self.assertNumQueries(1):
            self.assertSetEqual(self.solve(query), {frozenset({})})

    def test_solving_single_query_with_false_fact(self):
        query = [("brother", "child_of", "X")]
        with self.assertNumQueries(1):
            self.assertSetEqual(self.solve(query), set())

    def test_solving_multiple_queries(self):
        query = [
            (Var("parent"), "child_of", Var("grandparent")),
            (Var("grandchild"), "child_of", Var("parent")),
        ]
        with self.assertNumQueries(2):
            self.assertSetEqual(
                self.solve(query),
                {
                    frozenset(
                        {
                            ("parent", "father"),
                            ("grandchild", "brother"),
                            ("grandparent", "grandfather"),
                        }
                    ),
                    frozenset(
                        {
                            ("grandchild", "sister"),
                            ("parent", "father"),
                            ("grandparent", "grandfather"),
                        }
                    ),
                },
            )

    def test_solving_multiple_queries_looking_for_male_son(self):
        query = [
            (Var("son"), "child_of", Var("parent")),
            (Var("son"), "gender", "m"),
        ]
        with self.assertNumQueries(2):
            self.assertSetEqual(
                self.solve(query),
                {
                    frozenset({("son", "brother"), ("parent", "father")}),
                    frozenset({("son", "brother"), ("parent", "mother")}),
                    frozenset({("son", "father"), ("parent", "grandfather")}),
                },
            )

    def test_solving_looking_for_siblings(self):
        query = [
            (Var("child1"), "child_of", Var("parent")),
            (Var("child2"), "child_of", Var("parent")),
        ]

        with self.assertNumQueries(2):
            self.assertSetEqual(
                self.solve(query),
                {
                    frozenset(
                        {
                            ("child1", "brother"),
                            ("child2", "sister"),
                            ("parent", "father"),
                        }
                    ),
                    frozenset(
                        {
                            ("child1", "sister"),
                            ("child2", "brother"),
                            ("parent", "father"),
                        }
                    ),
                    frozenset(
                        {
                            ("child1", "brother"),
                            ("child2", "sister"),
                            ("parent", "mother"),
                        }
                    ),
                    frozenset(
                        {
                            ("child1", "sister"),
                            ("child2", "brother"),
                            ("parent", "mother"),
                        }
                    ),
                },
            )
