from dataclasses import replace
from unittest import TestCase

from ..core import Solution, Var, rule
from .common import (
    Database,
    descendants_rules,
    siblings_rule,
    symmetric_sibling_rule,
    triplets,
)


class TestRules(TestCase):
    def test_have_and_id_that_is_a_hash_of_itself(self):
        self.assertEqual(siblings_rule.id, "9056cdd077155ee4875727c9e834757f")
        self.assertEqual(
            symmetric_sibling_rule.id,
            "cd5c3bfc04018be8d346e05667a79a6f",
        )

    def test_fail_if_conclusion_variables_are_missing_in_predicates(self):
        with self.assertRaises(TypeError):
            replace(
                siblings_rule,
                conclusions=siblings_rule.conclusions
                + [(Var("x"), "is", "green")],
            )

    def test_can_match_a_triplet_and_genrate_an_optimized_rule(self):
        self.assertEqual(
            list(siblings_rule.matches(("x", "child_of", "y"))),
            [
                rule(
                    [("x", "child_of", "y"), (Var("child2"), "child_of", "y")],
                    implies=[("x", "sibling_of", Var("child2"))],
                ),
                rule(
                    [(Var("child1"), "child_of", "y"), ("x", "child_of", "y")],
                    implies=[(Var("child1"), "sibling_of", "x")],
                ),
            ],
        )


class TestInference(TestCase):
    def setUp(self) -> None:
        self.db = Database()
        for fact in triplets:
            self.db.add(fact)

    def test_siblings_rule_in_action_when_using_a_db(self):
        self.db.rules = [siblings_rule]
        self.db.refresh_inference()
        solutions = self.db.solve(
            [(Var("sibling1"), "sibling_of", Var("sibling2"))]
        )
        self.assertListEqual(
            solutions,
            [
                Solution(
                    {"sibling1": "brother", "sibling2": "sister"},
                    {("brother", "sibling_of", "sister")},
                ),
                Solution(
                    {"sibling1": "sister", "sibling2": "brother"},
                    {("sister", "sibling_of", "brother")},
                ),
            ],
        )

    def test_transition_from_a_set_of_rules_to_others(self):
        self.db.rules = [siblings_rule]
        self.db.refresh_inference()  # previous case covers this case

        solutions = self.db.solve([(Var("a"), "descendant_of", Var("b"))])
        self.assertListEqual(solutions, [])

        self.db.rules = descendants_rules
        self.db.refresh_inference()

        solutions = self.db.solve([(Var("a"), "descendant_of", Var("b"))])
        self.assertListEqual(
            solutions,
            [
                Solution(
                    {"a": "brother", "b": "father"},
                    frozenset({("brother", "descendant_of", "father")}),
                ),
                Solution(
                    {"a": "brother", "b": "mother"},
                    frozenset({("brother", "descendant_of", "mother")}),
                ),
                Solution(
                    {"a": "sister", "b": "father"},
                    frozenset({("sister", "descendant_of", "father")}),
                ),
                Solution(
                    {"a": "sister", "b": "mother"},
                    frozenset({("sister", "descendant_of", "mother")}),
                ),
                Solution(
                    {"a": "father", "b": "grandfather"},
                    frozenset({("father", "descendant_of", "grandfather")}),
                ),
                Solution(
                    {"a": "brother", "b": "grandfather"},
                    frozenset({("brother", "descendant_of", "grandfather")}),
                ),
                Solution(
                    {"a": "sister", "b": "grandfather"},
                    frozenset({("sister", "descendant_of", "grandfather")}),
                ),
            ],
        )

    def test_deleting_a_primary_triplet_deletes_its_deductions(self):
        self.db.rules = descendants_rules
        self.db.refresh_inference()

        self.db.remove(("father", "child_of", "grandfather"))
        solutions = self.db.solve([(Var("a"), "descendant_of", Var("b"))])
        self.assertListEqual(
            solutions,
            [
                Solution(
                    {"a": "brother", "b": "father"},
                    frozenset({("brother", "descendant_of", "father")}),
                ),
                Solution(
                    {"a": "brother", "b": "mother"},
                    frozenset({("brother", "descendant_of", "mother")}),
                ),
                Solution(
                    {"a": "sister", "b": "father"},
                    frozenset({("sister", "descendant_of", "father")}),
                ),
                Solution(
                    {"a": "sister", "b": "mother"},
                    frozenset({("sister", "descendant_of", "mother")}),
                ),
            ],
        )

    def test_cant_delete_deduced_triplets(self):
        self.db.rules = descendants_rules
        self.db.refresh_inference()
        with self.assertRaises(ValueError):
            self.db.remove(("sister", "descendant_of", "grandfather"))
