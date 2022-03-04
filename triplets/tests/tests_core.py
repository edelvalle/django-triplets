from unittest import TestCase

from ..core import Any, Clause, In, Var, substitute_using


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
        predicate = Clause(Var("person"), "son_of", Var("parent"))
        self.assertEqual(
            predicate.substitute_using([{"parent": "PARENT"}]),
            Clause(Var("person"), "son_of", "PARENT"),
        )
        self.assertEqual(
            predicate.substitute_using([{"person": "PERSON"}]),
            Clause("PERSON", "son_of", Var("parent")),
        )
        self.assertEqual(
            predicate.substitute_using([{"unknown": "VALUE"}]),
            predicate,
        )

    def test_can_substitute_contexts_to_in_expression(self):
        predicate = Clause(Var("person"), "son_of", Var("parent"))
        self.assertEqual(
            predicate.substitute_using([{"parent": "A"}, {"parent": "B"}]),
            Clause(Var("person"), "son_of", In("parent", {"A", "B"})),
        )
        self.assertEqual(
            predicate.substitute_using(
                [{"person": "P", "parent": "A"}, {"person": "P", "parent": "B"}]
            ),
            Clause("P", "son_of", In("parent", {"A", "B"})),
        )
        self.assertEqual(
            predicate.substitute_using([{"unknown": "VALUE"}]),
            predicate,
        )

    def test_can_substitute_contexts_to_any_expression(self):
        predicate = Clause(Var("person"), "son_of", Any)
        self.assertEqual(
            predicate.substitute_using([{"parent": "A"}, {"parent": "B"}]),
            Clause(Var("person"), "son_of", Any),
        )
        self.assertEqual(
            predicate.substitute_using(
                [{"person": "P", "parent": "A"}, {"person": "P", "parent": "B"}]
            ),
            Clause("P", "son_of", Any),
        )
        self.assertEqual(
            predicate.substitute_using([{"unknown": "VALUE"}]),
            predicate,
        )

    def test_sorting_protocol_prioritize_the_more_literal_one(self):
        predicate = [
            Clause(Any, "b", In("c", {})),
            Clause(In("a", {}), "b", In("c", {})),
            Clause(In("a", {}), "b", Var("c")),
            Clause(Var("a"), "b", In("c", {})),
            Clause("a", "b", In("c", {})),
            Clause(In("a", {}), "b", "c"),
            Clause(Var("a"), "b", Var("c")),
            Clause("a", "b", Var("c")),
            Clause(Var("a"), "b", "c"),
            Clause("a", "b", "c"),
        ]

        predicate.sort()
        self.assertListEqual(
            predicate,
            [
                Clause("a", "b", "c"),
                Clause("a", "b", In("c", {})),
                Clause(In("a", {}), "b", "c"),
                Clause(In("a", {}), "b", In("c", {})),
                Clause("a", "b", Var("c")),
                Clause(Var("a"), "b", "c"),
                Clause(In("a", {}), "b", Var("c")),
                Clause(Var("a"), "b", In("c", {})),
                Clause(Var("a"), "b", Var("c")),
                Clause(Any, "b", In("c", {})),
            ],
        )

    def test_variable_names_returns_the_name_of_the_variables(self):
        self.assertListEqual(
            Clause(Var("person"), "son_of", Var("parent")).variable_names,
            ["person", "parent"],
        )
        self.assertListEqual(
            Clause("subject", "verb", "obj").variable_names,
            [],
        )
        self.assertListEqual(
            Clause(Var("subject"), "verb", "obj").variable_names,
            ["subject"],
        )
        self.assertListEqual(
            Clause("subject", "verb", Var("obj")).variable_names,
            ["obj"],
        )
        self.assertListEqual(
            Clause(In("subject", {}), "verb", Var("obj")).variable_names,
            ["subject", "obj"],
        )
