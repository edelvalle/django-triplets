from unittest import TestCase

from ..core import Predicate, Query, Var
from . import common


class TestVariable(TestCase):

    variable = Var("color")

    def test_can_substitute_using_a_context(self):
        self.assertEqual(
            self.variable.substitute_using({"color": "red"}), "red"
        )

    def test_do_not_substitute_of_name_not_found_in_context(self):
        self.assertEqual(
            self.variable.substitute_using({"age": 12}), Var("color")
        )


class TestPredicate(TestCase):
    predicate = Predicate(Var("person"), "son_of", Var("parent"))

    def test_can_substitute_using_a_context(self):
        self.assertEqual(
            self.predicate.substitute_using({"parent": "PARENT"}),
            Predicate(Var("person"), "son_of", "PARENT"),
        )
        self.assertEqual(
            self.predicate.substitute_using({"person": "PERSON"}),
            Predicate("PERSON", "son_of", Var("parent")),
        )
        self.assertEqual(
            self.predicate.substitute_using({"unknown": "VALUE"}),
            self.predicate,
        )

    def test_sorting_protocol(self):
        self.assertTrue(Predicate("subject", "verb", "obj") < self.predicate)
        self.assertTrue(
            Predicate(Var("subject"), "verb", "obj") < self.predicate
        )
        self.assertFalse(
            Predicate(Var("subject"), "verb", Var("obj")) < self.predicate
        )

    def test_variable_names_returns_the_name_of_the_variables(self):
        self.assertTupleEqual(
            self.predicate.variable_names,
            ("person", "parent"),
        )
        self.assertTupleEqual(
            Predicate("subject", "verb", "obj").variable_names,
            (None, None),
        )
        self.assertTupleEqual(
            Predicate(Var("subject"), "verb", "obj").variable_names,
            ("subject", None),
        )
        self.assertTupleEqual(
            Predicate("subject", "verb", Var("obj")).variable_names,
            (None, "obj"),
        )


class TestQuery(TestCase):
    db = common.Database(common.triplets)

    def solve(self, *args, **kwargs):
        return list(self.db.solve(*args, **kwargs))

    def test_optimization_makes_less_abstract_query_be_first_without_context(
        self,
    ):
        p1, p2 = [
            Predicate(Var("sibling"), "child_of", Var("parent")),
            Predicate("Juan", "child_of", Var("parent")),
        ]
        query = Query([p1, p2])
        self.assertListEqual(query._optimized_predicates, [p2, p1])

    def test_optimization_makes_less_abstract_query_be_first_with_context(self):
        p1, p2 = [
            Predicate(Var("grandchild"), "child_of", Var("parent")),
            Predicate(Var("parent"), "child_of", Var("grandparent")),
        ]
        query = Query([p1, p2], context={"grandparent": "X"})
        self.assertListEqual(
            query._optimized_predicates,
            [Predicate(Var("parent"), "child_of", "X"), p1],
        )

    def test_solving_single_query_with_two_variables(self):
        query = [Predicate(Var("child"), "child_of", Var("parent"))]
        self.assertListEqual(
            self.solve(query),
            [
                {"child": "juan", "parent": "perico"},
                {"child": "juan", "parent": "maria"},
                {"child": "juana", "parent": "perico"},
                {"child": "juana", "parent": "maria"},
                {"child": "perico", "parent": "emilio"},
            ],
        )

    def test_solving_single_query_with_subject_variables(self):
        query = [Predicate(Var("child"), "child_of", "perico")]
        self.assertListEqual(
            self.solve(query),
            [
                {"child": "juan"},
                {"child": "juana"},
            ],
        )

    def test_solving_single_query_with_object_variables(self):
        query = [Predicate("juan", "child_of", Var("parent"))]
        self.assertListEqual(
            self.solve(query),
            [
                {"parent": "perico"},
                {"parent": "maria"},
            ],
        )

    def test_solving_single_query_with_true_fact(self):
        query = [Predicate("juan", "child_of", "perico")]
        self.assertListEqual(self.solve(query), [{}])

    def test_solving_single_query_with_false_fact(self):
        query = [Predicate("juan", "child_of", "X")]
        self.assertListEqual(self.solve(query), [])

    def test_solving_multiple_queries(self):
        query = [
            Predicate(Var("grandchild"), "child_of", Var("parent")),
            Predicate(Var("parent"), "child_of", Var("grandparent")),
        ]
        self.assertListEqual(
            self.solve(query),
            [
                {
                    "grandchild": "juan",
                    "parent": "perico",
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
        self.assertListEqual(
            self.solve(query),
            [
                {"child1": "juan", "child2": "juana", "parent": "perico"},
                {"child1": "juan", "child2": "juana", "parent": "maria"},
                {"child1": "juana", "child2": "juan", "parent": "perico"},
                {"child1": "juana", "child2": "juan", "parent": "maria"},
            ],
        )
