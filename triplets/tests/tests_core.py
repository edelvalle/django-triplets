from unittest import TestCase

from ..core import In, Predicate, Query, Solution, Var, substitute_using
from . import common
from .common import Triplet


class TestExpressions(TestCase):

    variable_expression = Var("color")
    in_expression = In("color", {"red"})

    def test_can_substitute_using_a_single_context(self):
        self.assertEqual(
            substitute_using(self.variable_expression, [{"color": "red"}]),
            "red",
        )
        self.assertEqual(
            substitute_using(self.in_expression, [{"color": "red"}]), "red"
        )

    def test_can_substitute_using_multiple_contexts(self):
        self.assertEqual(
            substitute_using(
                self.variable_expression, [{"color": "red"}, {"color": "blue"}]
            ),
            In("color", {"red", "blue"}),
        )
        self.assertEqual(
            substitute_using(
                self.in_expression, [{"color": "red"}, {"color": "blue"}]
            ),
            In("color", {"red", "blue"}),
        )

    def test_substitution_with_non_homogeneous_contexts(self):
        self.assertEqual(
            substitute_using(
                self.variable_expression, [{"age": 12}, {"color": "blue"}]
            ),
            "blue",
        )
        self.assertEqual(
            substitute_using(
                self.in_expression, [{"age": 12}, {"color": "blue"}]
            ),
            "blue",
        )

    def test_do_not_substitute_of_name_not_found_in_context(self):
        self.assertEqual(
            substitute_using(self.variable_expression, [{"age": 12}]),
            Var("color"),
        )
        self.assertEqual(
            substitute_using(self.in_expression, [{"age": 12}]),
            self.in_expression,
        )


class TestPredicate(TestCase):
    def test_can_substitute_using_a_context_to_a_literal(self):
        predicate = Predicate(Var("person"), "son_of", Var("parent"))
        self.assertEqual(
            predicate.substitute_using([{"parent": "PARENT"}]),
            Predicate(Var("person"), "son_of", "PARENT"),
        )
        self.assertEqual(
            predicate.substitute_using([{"person": "PERSON"}]),
            Predicate("PERSON", "son_of", Var("parent")),
        )
        self.assertEqual(
            predicate.substitute_using([{"unknown": "VALUE"}]),
            predicate,
        )

    def test_can_substitute_contexts_to_in_expression(self):
        predicate = Predicate(Var("person"), "son_of", Var("parent"))
        self.assertEqual(
            predicate.substitute_using([{"parent": "A"}, {"parent": "B"}]),
            Predicate(Var("person"), "son_of", In("parent", {"A", "B"})),
        )
        self.assertEqual(
            predicate.substitute_using(
                [{"person": "P", "parent": "A"}, {"person": "P", "parent": "B"}]
            ),
            Predicate("P", "son_of", In("parent", {"A", "B"})),
        )
        self.assertEqual(
            predicate.substitute_using([{"unknown": "VALUE"}]),
            predicate,
        )

    def test_sorting_protocol_prioritize_the_more_literal_one(self):
        predicates = [
            Predicate(In("a", {}), "b", In("c", {})),
            Predicate(In("a", {}), "b", Var("c")),
            Predicate(Var("a"), "b", In("c", {})),
            Predicate("a", "b", In("c", {})),
            Predicate(In("a", {}), "b", "c"),
            Predicate(Var("a"), "b", Var("c")),
            Predicate("a", "b", Var("c")),
            Predicate(Var("a"), "b", "c"),
            Predicate("a", "b", "c"),
        ]

        predicates.sort()
        self.assertListEqual(
            predicates,
            [
                Predicate("a", "b", "c"),
                Predicate("a", "b", In("c", {})),
                Predicate(In("a", {}), "b", "c"),
                Predicate(In("a", {}), "b", In("c", {})),
                Predicate("a", "b", Var("c")),
                Predicate(Var("a"), "b", "c"),
                Predicate(In("a", {}), "b", Var("c")),
                Predicate(Var("a"), "b", In("c", {})),
                Predicate(Var("a"), "b", Var("c")),
            ],
        )

    def test_variable_names_returns_the_name_of_the_variables(self):
        self.assertTupleEqual(
            Predicate(Var("person"), "son_of", Var("parent")).variable_names,
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
        self.assertTupleEqual(
            Predicate(In("subject", {}), "verb", Var("obj")).variable_names,
            ("subject", "obj"),
        )


class TestQuery(TestCase):
    db = common.Database(common.triplets)

    def solve(self, *args, **kwargs):
        return list(self.db.solve(*args, **kwargs))

    def test_optimization_makes_less_abstract_query_be_first_without_solutions(
        self,
    ):
        p1, p2, p3 = [
            Predicate(Var("sibling"), "child_of", Var("parent")),
            Predicate("Juan", "child_of", Var("parent")),
            Predicate(
                In("sibling", {"Juan", "Pepe"}), "child_of", Var("parent")
            ),
        ]
        query = Query([p1, p2, p3])
        self.assertListEqual(query._optimized_predicates, [p2, p3, p1])

    def test_optimization_makes_less_abstract_query_be_first_with_solutions(
        self,
    ):
        p1, p2 = [
            Predicate(Var("grandchild"), "child_of", Var("parent")),
            Predicate(Var("parent"), "child_of", Var("grandparent")),
        ]
        query = Query(
            [p1, p2],
            solutions=[Solution({"grandparent": "X"}, frozenset())],
        )
        self.assertListEqual(
            query._optimized_predicates,
            [Predicate(Var("parent"), "child_of", "X"), p1],
        )

    def test_solving_single_query_with_two_variables(self):
        query = [Predicate(Var("child"), "child_of", Var("parent"))]
        self.assertListEqual(
            [solution.context for solution in self.solve(query)],
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
                Solution(
                    {"child": "juan"},
                    {Triplet("juan", "child_of", "perico")},
                ),
                Solution(
                    {"child": "juana"},
                    {Triplet("juana", "child_of", "perico")},
                ),
            ],
        )

    def test_solving_single_query_with_object_variables(self):
        query = [Predicate("juan", "child_of", Var("parent"))]
        self.assertListEqual(
            self.solve(query),
            [
                Solution(
                    {"parent": "perico"},
                    {Triplet("juan", "child_of", "perico")},
                ),
                Solution(
                    {"parent": "maria"},
                    {Triplet("juan", "child_of", "maria")},
                ),
            ],
        )

    def test_solving_single_query_with_true_fact(self):
        query = [Predicate("juan", "child_of", "perico")]
        self.assertListEqual(
            self.solve(query),
            [Solution({}, {Triplet("juan", "child_of", "perico")})],
        )

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
                Solution(
                    {
                        "grandchild": "juan",
                        "parent": "perico",
                        "grandparent": "emilio",
                    },
                    {
                        Triplet("juan", "child_of", "perico"),
                        Triplet("perico", "child_of", "emilio"),
                    },
                ),
                Solution(
                    {
                        "grandchild": "juana",
                        "parent": "perico",
                        "grandparent": "emilio",
                    },
                    {
                        Triplet("juana", "child_of", "perico"),
                        Triplet("perico", "child_of", "emilio"),
                    },
                ),
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
                Solution(
                    {"son": "juan", "parent": "perico"},
                    {
                        Triplet("juan", "child_of", "perico"),
                        Triplet("juan", "gender", "m"),
                    },
                ),
                Solution(
                    {"son": "juan", "parent": "maria"},
                    {
                        Triplet("juan", "child_of", "maria"),
                        Triplet("juan", "gender", "m"),
                    },
                ),
                Solution(
                    {"son": "perico", "parent": "emilio"},
                    {
                        Triplet("perico", "gender", "m"),
                        Triplet("perico", "child_of", "emilio"),
                    },
                ),
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
                Solution(
                    {"child1": "juan", "child2": "juana", "parent": "perico"},
                    {
                        Triplet("juan", "child_of", "perico"),
                        Triplet("juana", "child_of", "perico"),
                    },
                ),
                Solution(
                    {"child1": "juan", "child2": "juana", "parent": "maria"},
                    {
                        Triplet("juan", "child_of", "maria"),
                        Triplet("juana", "child_of", "maria"),
                    },
                ),
                Solution(
                    {"child1": "juana", "child2": "juan", "parent": "perico"},
                    {
                        Triplet("juan", "child_of", "perico"),
                        Triplet("juana", "child_of", "perico"),
                    },
                ),
                Solution(
                    {"child1": "juana", "child2": "juan", "parent": "maria"},
                    {
                        Triplet("juan", "child_of", "maria"),
                        Triplet("juana", "child_of", "maria"),
                    },
                ),
            ],
        )
