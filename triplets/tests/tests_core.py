from unittest import TestCase

from ..ast import Any, Attr, In, TypedAny, TypedIn, TypedVar, Var
from ..core import Clause, Predicate, substitute_using


class TestExpressions(TestCase):

    variable_expression = TypedVar("color", str)
    in_expression = TypedIn("color", {"red"}, str)

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
            TypedIn("color", {"red", "blue"}, str),
        )
        self.assertEqual(
            substitute_using(
                self.in_expression, [{"color": "red"}, {"color": "blue"}]
            ),
            "red",
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
            TypedIn("color", set(), str),
        )

    def test_do_not_substitute_of_name_not_found_in_context(self):
        self.assertEqual(
            substitute_using(self.variable_expression, [{"age": 12}]),
            self.variable_expression,
        )
        self.assertEqual(
            substitute_using(self.in_expression, [{"age": 12}]),
            self.in_expression,
        )


class TestPredicate(TestCase):

    attributes = Attr.as_dict(
        Attr("son_of", str, cardinality="many"),
        Attr("b", str, cardinality="many"),
    )

    def test_can_substitute_using_a_context_to_a_literal(self):
        clause = Clause.from_tuple(
            (Var("person"), "son_of", Var("parent")), self.attributes
        )
        self.assertEqual(
            clause.substitute_using([{"parent": "PARENT"}]),
            Clause(TypedVar("person", str), "son_of", "PARENT"),
        )
        self.assertEqual(
            clause.substitute_using([{"person": "PERSON"}]),
            Clause("PERSON", "son_of", TypedVar("parent", str)),
        )
        self.assertEqual(
            clause.substitute_using([{"unknown": "VALUE"}]),
            clause,
        )

    def test_can_substitute_contexts_to_in_expression(self):
        clause = Clause.from_tuple(
            (Var("person"), "son_of", Var("parent")), self.attributes
        )
        self.assertEqual(
            clause.substitute_using([{"parent": "A"}, {"parent": "B"}]),
            Clause(
                TypedVar("person", str),
                "son_of",
                TypedIn("parent", {"A", "B"}, str),
            ),
        )
        self.assertEqual(
            clause.substitute_using(
                [{"person": "P", "parent": "A"}, {"person": "P", "parent": "B"}]
            ),
            Clause("P", "son_of", TypedIn("parent", {"A", "B"}, str)),
        )
        self.assertEqual(
            clause.substitute_using([{"unknown": "VALUE"}]),
            clause,
        )

    def test_can_substitute_contexts_to_any_expression(self):
        clause = Clause.from_tuple(
            (Var("person"), "son_of", Any), self.attributes
        )
        self.assertEqual(
            clause.substitute_using([{"parent": "A"}, {"parent": "B"}]),
            Clause(TypedVar("person", str), "son_of", TypedAny(str)),
        )
        self.assertEqual(
            clause.substitute_using(
                [{"person": "P", "parent": "A"}, {"person": "P", "parent": "B"}]
            ),
            Clause("P", "son_of", TypedAny(str)),
        )
        self.assertEqual(
            clause.substitute_using([{"unknown": "VALUE"}]),
            clause,
        )

    def test_sorting_protocol_prioritize_the_more_literal_one(self):
        predicate = Predicate.from_tuples(
            [
                (Any, "b", In("c", set())),
                (In("a", set()), "b", In("c", set())),
                (In("a", set()), "b", Var("c")),
                (Var("a"), "b", In("c", set())),
                ("a", "b", In("c", set())),
                (In("a", set()), "b", "c"),
                (Var("a"), "b", Var("c")),
                ("a", "b", Var("c")),
                (Var("a"), "b", "c"),
                ("a", "b", "c"),
            ],
            self.attributes,
        )

        self.assertListEqual(
            predicate.optimized_by([{}]),
            [
                Clause("a", "b", "c"),
                Clause("a", "b", TypedIn("c", set(), str)),
                Clause(TypedIn("a", set(), str), "b", "c"),
                Clause(TypedIn("a", set(), str), "b", TypedIn("c", set(), str)),
                Clause("a", "b", TypedVar("c", str)),
                Clause(TypedVar("a", str), "b", "c"),
                Clause(TypedIn("a", set(), str), "b", TypedVar("c", str)),
                Clause(TypedVar("a", str), "b", TypedIn("c", set(), str)),
                Clause(TypedVar("a", str), "b", TypedVar("c", str)),
                Clause(TypedAny(str), "b", TypedIn("c", set(), str)),
            ],
        )

    def test_variable_names_returns_the_name_of_the_variables(self):
        self.assertDictEqual(
            Clause(
                TypedVar("person", str), "son_of", TypedVar("parent", str)
            ).variable_types,
            {"person": {str}, "parent": {str}},
        )
        self.assertDictEqual(
            Clause("subject", "verb", "obj").variable_types,
            {},
        )
        self.assertDictEqual(
            Clause(TypedVar("subject", str), "verb", "obj").variable_types,
            {"subject": {str}},
        )
        self.assertDictEqual(
            Clause("subject", "verb", TypedVar("obj", int)).variable_types,
            {"obj": {int}},
        )
        self.assertDictEqual(
            Clause(
                TypedIn("subject", set(), str), "verb", TypedVar("obj", int)
            ).variable_types,
            {"subject": {str}, "obj": {int}},
        )
