from unittest import TestCase

from ..ast import Any, Attr, In, TypedAny, TypedIn, TypedVar, Var
from ..core import Clause, Predicate, compile_rules, substitute_using


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


class TestClause(TestCase):

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
            self.attributes,
            [
                (Any, "b", In("c", {"a"})),
                (In("a", {"a"}), "b", In("c", set())),
                (In("a", {"a"}), "b", Var("c")),
                (Var("a"), "b", In("c", {"a"})),
                ("a", "b", In("c", {"a"})),
                (In("a", {"a"}), "b", "c"),
                (Var("a"), "b", Var("c")),
                ("a", "b", Var("c")),
                (Var("a"), "b", "c"),
                ("a", "b", "c"),
            ],
        )

        self.assertListEqual(
            predicate.optimized_by([{}]),
            [
                Clause(TypedIn("a", {"a"}, str), "b", TypedIn("c", set(), str)),
                Clause("a", "b", "c"),
                Clause("a", "b", TypedIn("c", {"a"}, str)),
                Clause(TypedIn("a", {"a"}, str), "b", "c"),
                Clause("a", "b", TypedVar("c", str)),
                Clause(TypedVar("a", str), "b", "c"),
                Clause(TypedIn("a", {"a"}, str), "b", TypedVar("c", str)),
                Clause(TypedVar("a", str), "b", TypedIn("c", {"a"}, str)),
                Clause(TypedVar("a", str), "b", TypedVar("c", str)),
                Clause(TypedAny(str), "b", TypedIn("c", {"a"}, str)),
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


class TestPredicate(TestCase):
    def test_checks_that_the_type_of_variables_is_consistent(self):
        attributes = Attr.as_dict(
            Attr("age", int, "one"),
            Attr("color", str, "many"),
        )
        with self.assertRaises(TypeError) as e:
            Predicate.from_tuples(attributes, [(Var("age"), "age", Var("age"))])
        self.assertEqual(
            str(e.exception),
            "Variable `age` can't have more than one type, and it has: ['str', 'int']",
        )

        with self.assertRaises(TypeError) as e:
            Predicate.from_tuples(
                attributes,
                [
                    (Var("person"), "age", Var("age")),
                    ("x", "color", Var("age")),
                ],
            )
        self.assertEqual(
            str(e.exception),
            "Variable `age` can't have more than one type, and it has: ['str', 'int']",
        )


class TestRule(TestCase):
    attributes = Attr.as_dict(
        Attr("age", int, "one"),
        Attr("color", str, "many"),
    )

    def test_checks_that_is_not_missing_any_variables_with_predicate(self):
        with self.assertRaises(TypeError) as e:

            class TestRule:
                predicate = [
                    (Var("person"), "age", In("age", {1, 2})),
                    (Var("person"), "color", Any),
                ]

                implies = [(Var("parent"), "color", "blue")]

            compile_rules(self.attributes, TestRule)

        self.assertEqual(
            str(e.exception),
            "\n".join(
                [
                    "Error(s) in Rule: [(?person: str, age, ?age: int in {1, 2}), (?person: str, color, ?: str)] => [(?parent: str, color, blue)]:",
                    " - Variable `?parent: <class 'str'>` is missing in the predicate",
                ]
            ),
        )

    def test_checks_that_for_type_missmatch_with_predicate(self):
        with self.assertRaises(TypeError) as e:

            class TestRule:
                predicate = [
                    (Var("person"), "age", In("age", {1, 2})),
                    (Var("person"), "color", Any),
                ]

                implies = [(Var("person"), "color", Var("age"))]

            compile_rules(self.attributes, TestRule)

        self.assertEqual(
            str(e.exception),
            "\n".join(
                [
                    "Error(s) in Rule: [(?person: str, age, ?age: int in {1, 2}), (?person: str, color, ?: str)] => [(?person: str, color, ?age: str)]:",
                    " - Type mismatch in variable `?age`, got <class 'int'>, requires: <class 'str'>",
                ]
            ),
        )

    def test_checks_that_for_type_missmatch_with_function(self):
        with self.assertRaises(TypeError) as e:

            class TestRule:
                predicate = [
                    (Var("person"), "age", In("age", {1, 2})),
                    (Var("person"), "color", Var("color")),
                ]

                @staticmethod
                def implies(parent: str, color: int):
                    return [(parent, "color", color)]

            compile_rules(self.attributes, TestRule)

        self.assertEqual(
            str(e.exception),
            "\n".join(
                [
                    "Error(s) in Rule: [(?person: str, age, ?age: int in {1, 2}), (?person: str, color, ?color: str)] => f(parent: str, color: int):",
                    " - Variable `?parent: <class 'str'>` is missing in the predicate",
                    " - Type mismatch in variable `?color`, got <class 'str'>, requires: <class 'int'>",
                ]
            ),
        )

    def test_checks_that_is_not_missing_any_variables_with_functions(self):
        with self.assertRaises(TypeError) as e:

            class TestRule:
                predicate = [
                    (Var("person"), "age", In("age", {1, 2})),
                    (Var("person"), "color", Any),
                ]

                @staticmethod
                def implies(parent):  # type: ignore
                    return [(parent, "color", "blue")]  # type: ignore

            compile_rules(self.attributes, TestRule)

        self.assertEqual(
            str(e.exception),
            "\n".join(
                [
                    "Error(s) in Rule: [(?person: str, age, ?age: int in {1, 2}), (?person: str, color, ?: str)] => f(parent):",
                    " - Variable `?parent: None` is missing in the predicate",
                ]
            ),
        )

    def test_checks_that_has_not_any_in_the_conclusions(self):
        with self.assertRaises(TypeError) as e:

            class TestRule:
                predicate = [
                    (Var("person"), "age", In("age", {1, 2})),
                    (Var("person"), "color", "blue"),
                ]
                implies = [(Any, "color", "blue")]

            compile_rules(self.attributes, TestRule)

        self.assertEqual(
            str(e.exception),
            "\n".join(
                [
                    "Error(s) in Rule: [(?person: str, age, ?age: int in {1, 2}), (?person: str, color, blue)] => [(?: str, color, blue)]:",
                    " - Implications can't have `?` in them",
                ]
            ),
        )
