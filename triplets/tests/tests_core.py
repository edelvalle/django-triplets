from unittest import TestCase

from ..core import (
    In,
    ListOfPredicateTuples,
    Predicate,
    Predicates,
    Query,
    Solution,
    Var,
    substitute_using,
)
from . import common


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
        self.assertListEqual(
            Predicate(Var("person"), "son_of", Var("parent")).variable_names,
            ["person", "parent"],
        )
        self.assertListEqual(
            Predicate("subject", "verb", "obj").variable_names,
            [],
        )
        self.assertListEqual(
            Predicate(Var("subject"), "verb", "obj").variable_names,
            ["subject"],
        )
        self.assertListEqual(
            Predicate("subject", "verb", Var("obj")).variable_names,
            ["obj"],
        )
        self.assertListEqual(
            Predicate(In("subject", {}), "verb", Var("obj")).variable_names,
            ["subject", "obj"],
        )


class TestQuery(TestCase):
    def setUp(self):
        self.db = common.Database()
        for triplet in common.triplets:
            self.db.add(triplet)

    def solve(self, predicates: ListOfPredicateTuples) -> list[Solution]:
        return list(self.db.solve(predicates))

    def test_optimization_makes_less_abstract_query_be_first_without_solutions(
        self,
    ):
        p1, p2, p3 = [
            Predicate(Var("sibling"), "child_of", Var("parent")),
            Predicate("brother", "child_of", Var("parent")),
            Predicate(
                In("sibling", {"brother", "Pepe"}), "child_of", Var("parent")
            ),
        ]
        query = Query(Predicates([p1, p2, p3]))
        self.assertListEqual(query.optimized_predicates, [p2, p3, p1])

    def test_optimization_makes_less_abstract_query_be_first_with_solutions(
        self,
    ):
        p1, p2 = [
            Predicate(Var("grandchild"), "child_of", Var("parent")),
            Predicate(Var("parent"), "child_of", Var("grandparent")),
        ]
        query = Query(
            Predicates([p1, p2]),
            solutions=[Solution({"grandparent": "X"}, frozenset())],
        )
        self.assertListEqual(
            query.optimized_predicates,
            [Predicate(Var("parent"), "child_of", "X"), p1],
        )

    def test_solving_single_query_with_two_variables(self):
        query = [(Var("child"), "child_of", Var("parent"))]
        self.assertListEqual(
            [solution.context for solution in self.solve(query)],
            [
                {"child": "brother", "parent": "father"},
                {"child": "brother", "parent": "mother"},
                {"child": "sister", "parent": "father"},
                {"child": "sister", "parent": "mother"},
                {"child": "father", "parent": "grandfather"},
            ],
        )

    def test_solving_single_query_with_subject_variables(self):
        query = [(Var("child"), "child_of", "father")]
        self.assertListEqual(
            self.solve(query),
            [
                Solution(
                    {"child": "brother"},
                    {("brother", "child_of", "father")},
                ),
                Solution(
                    {"child": "sister"},
                    {("sister", "child_of", "father")},
                ),
            ],
        )

    def test_solving_single_query_with_object_variables(self):
        query = [("brother", "child_of", Var("parent"))]
        self.assertListEqual(
            self.solve(query),
            [
                Solution(
                    {"parent": "father"},
                    {("brother", "child_of", "father")},
                ),
                Solution(
                    {"parent": "mother"},
                    {("brother", "child_of", "mother")},
                ),
            ],
        )

    def test_solving_single_query_with_true_fact(self):
        query = [("brother", "child_of", "father")]
        self.assertListEqual(
            self.solve(query),
            [Solution({}, {("brother", "child_of", "father")})],
        )

    def test_solving_single_query_with_false_fact(self):
        query = [("brother", "child_of", "X")]
        self.assertListEqual(self.solve(query), [])

    def test_solving_multiple_queries(self):
        query = [
            (Var("grandchild"), "child_of", Var("parent")),
            (Var("parent"), "child_of", Var("grandparent")),
        ]
        self.assertListEqual(
            self.solve(query),
            [
                Solution(
                    {
                        "grandchild": "brother",
                        "parent": "father",
                        "grandparent": "grandfather",
                    },
                    {
                        ("brother", "child_of", "father"),
                        ("father", "child_of", "grandfather"),
                    },
                ),
                Solution(
                    {
                        "grandchild": "sister",
                        "parent": "father",
                        "grandparent": "grandfather",
                    },
                    {
                        ("sister", "child_of", "father"),
                        ("father", "child_of", "grandfather"),
                    },
                ),
            ],
        )

    def test_solving_multiple_queries_looking_for_male_son(self):
        query = [
            (Var("son"), "child_of", Var("parent")),
            (Var("son"), "gender", "m"),
        ]

        self.assertListEqual(
            self.solve(query),
            [
                Solution(
                    {"son": "brother", "parent": "father"},
                    {
                        ("brother", "child_of", "father"),
                        ("brother", "gender", "m"),
                    },
                ),
                Solution(
                    {"son": "brother", "parent": "mother"},
                    {
                        ("brother", "child_of", "mother"),
                        ("brother", "gender", "m"),
                    },
                ),
                Solution(
                    {"son": "father", "parent": "grandfather"},
                    {
                        ("father", "gender", "m"),
                        ("father", "child_of", "grandfather"),
                    },
                ),
            ],
        )

    def test_solving_looking_for_siblings(self):
        query = [
            (Var("child1"), "child_of", Var("parent")),
            (Var("child2"), "child_of", Var("parent")),
        ]
        self.assertListEqual(
            self.solve(query),
            [
                Solution(
                    {
                        "child1": "brother",
                        "child2": "sister",
                        "parent": "father",
                    },
                    {
                        ("brother", "child_of", "father"),
                        ("sister", "child_of", "father"),
                    },
                ),
                Solution(
                    {
                        "child1": "brother",
                        "child2": "sister",
                        "parent": "mother",
                    },
                    {
                        ("brother", "child_of", "mother"),
                        ("sister", "child_of", "mother"),
                    },
                ),
                Solution(
                    {
                        "child1": "sister",
                        "child2": "brother",
                        "parent": "father",
                    },
                    {
                        ("brother", "child_of", "father"),
                        ("sister", "child_of", "father"),
                    },
                ),
                Solution(
                    {
                        "child1": "sister",
                        "child2": "brother",
                        "parent": "mother",
                    },
                    {
                        ("brother", "child_of", "mother"),
                        ("sister", "child_of", "mother"),
                    },
                ),
            ],
        )
