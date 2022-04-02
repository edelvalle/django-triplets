from unittest import TestCase

from .. import ast as typed
from ..ast import Attr, LookUpExpression
from ..ast_untyped import Any, In, Var
from ..core import Clause, Predicate, compile_rules
from ..result import Err, Ok


class TestExpressions(TestCase):

    variable_expression = typed.Var("color", str)
    in_expression = typed.In("color", {"red"}, str)

    def test_can_substitute_using_a_single_context(self):
        self.assertEqual(
            LookUpExpression.substitute(
                self.variable_expression, [{"color": "red"}]
            ),
            "red",
        )
        self.assertEqual(
            LookUpExpression.substitute(self.in_expression, [{"color": "red"}]),
            "red",
        )

    def test_can_substitute_using_multiple_contexts(self):
        self.assertEqual(
            LookUpExpression.substitute(
                self.variable_expression, [{"color": "red"}, {"color": "blue"}]
            ),
            typed.In("color", {"red", "blue"}, str),
        )
        self.assertEqual(
            LookUpExpression.substitute(
                self.in_expression, [{"color": "red"}, {"color": "blue"}]
            ),
            "red",
        )

    def test_substitution_with_non_homogeneous_contexts(self):
        self.assertEqual(
            LookUpExpression.substitute(
                self.variable_expression, [{"age": 12}, {"color": "blue"}]
            ),
            self.variable_expression,
        )
        self.assertEqual(
            LookUpExpression.substitute(
                self.in_expression, [{"age": 12}, {"color": "blue"}]
            ),
            self.in_expression,
        )

    def test_do_not_substitute_of_name_not_found_in_context(self):
        self.assertEqual(
            LookUpExpression.substitute(
                self.variable_expression, [{"age": 12}]
            ),
            self.variable_expression,
        )
        self.assertEqual(
            LookUpExpression.substitute(self.in_expression, [{"age": 12}]),
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
            clause.substitute([{"parent": "PARENT"}]),
            Clause(typed.Var("person", str), "son_of", "PARENT"),
        )
        self.assertEqual(
            clause.substitute([{"person": "PERSON"}]),
            Clause("PERSON", "son_of", typed.Var("parent", str)),
        )
        self.assertEqual(
            clause.substitute([{"unknown": "VALUE"}]),
            clause,
        )

    def test_can_substitute_contexts_to_in_expression(self):
        clause = Clause.from_tuple(
            (Var("person"), "son_of", Var("parent")), self.attributes
        )
        self.assertEqual(
            clause.substitute([{"parent": "A"}, {"parent": "B"}]),
            Clause(
                typed.Var("person", str),
                "son_of",
                typed.In("parent", {"A", "B"}, str),
            ),
        )
        self.assertEqual(
            clause.substitute(
                [{"person": "P", "parent": "A"}, {"person": "P", "parent": "B"}]
            ),
            Clause("P", "son_of", typed.In("parent", {"A", "B"}, str)),
        )
        self.assertEqual(
            clause.substitute([{"unknown": "VALUE"}]),
            clause,
        )

    def test_can_substitute_contexts_to_any_expression(self):
        clause = Clause.from_tuple(
            (Var("person"), "son_of", Any), self.attributes
        )
        self.assertEqual(
            str(clause.substitute([{"parent": "A"}, {"parent": "B"}])),
            "(?person: str, son_of, ?: str)",
        )
        self.assertEqual(
            str(
                clause.substitute(
                    [
                        {"person": "P", "parent": "A"},
                        {"person": "P", "parent": "B"},
                    ]
                )
            ),
            "(P, son_of, ?: str)",
        )
        self.assertEqual(
            clause.substitute([{"unknown": "VALUE"}]),
            clause,
        )

    def test_predicate_query_planning_can_sort_clauses(self):
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
            [str(clause) for clause in predicate.planned],
            [
                "(a, b, c)",
                "(a, b, ?c: str in {'a'})",
                "(a, b, ?c: str)",
                "(?a: str in {'a'}, b, ?c: str in set())",
                "(?a: str in {'a'}, b, ?c: str)",
                "(?a: str, b, ?c: str in {'a'})",
                "(?a: str in {'a'}, b, c)",
                "(?a: str, b, ?c: str)",
                "(?a: str, b, c)",
                "(?: str, b, ?c: str in {'a'})",
            ],
        )

    def test_variable_names_returns_the_name_of_the_variables(self):
        self.assertEqual(
            Clause(
                typed.Var("person", str), "son_of", typed.Var("parent", str)
            ).variable_types,
            Ok({"person": str, "parent": str}),
        )
        self.assertEqual(
            Clause("entity", "attr", "value").variable_types,
            Ok({}),
        )

        self.assertEqual(
            Clause(typed.Var("entity", str), "attr", "value").variable_types,
            Ok(value={"entity": str}),
        )
        self.assertEqual(
            Clause("entity", "attr", typed.Var("value", int)).variable_types,
            Ok({"value": int}),
        )
        self.assertEqual(
            Clause(
                typed.In("entity", set(), str), "attr", typed.Var("value", int)
            ).variable_types,
            Ok({"entity": str, "value": int}),
        )
        self.assertEqual(
            Clause(
                typed.Var("entity", str), "attr", typed.Var("entity", int)
            ).variable_types,
            Err({"entity": {str, int}}),
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
            "\n".join(
                [
                    "Type mismatch in Predicate [(?age: str, age, ?age: int)], these variables have different types:",
                    "- age: str, int",
                ]
            ),
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
            "\n".join(
                [
                    "Type mismatch in Predicate [(?person: str, age, ?age: int), (x, color, ?age: str)], these variables have different types:",
                    "- age: str, int",
                ]
            ),
        )


class TestRule(TestCase):
    attributes = Attr.as_dict(
        Attr("age", int, "one"),
        Attr("color", str, "many"),
    )

    def test_checks_that_is_not_missing_any_variables(self):
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
            "TestRule: [(?person: str, age, ?age: int in {1, 2}), "
            "(?person: str, color, ?: str)] => [(?parent: str, color, blue)], "
            "is missing these variables in the predicate: {'parent'}",
        )

    def test_checks_that_for_type_missmatch(self):
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
                    "Type mismatch in TestRule: [(?person: str, age, ?age: int in {1, 2}), (?person: str, color, ?: str)] => [(?person: str, color, ?age: str)]:",
                    "- age: str, int",
                ]
            ),
        )

    def test_checks_that_has_not_any_in_the_implication(self):
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
            "TestRule: [(?person: str, age, ?age: int in {1, 2}), (?person: str, color, blue)] => [(?: str, color, blue)], implications can't have Any on them",
        )
