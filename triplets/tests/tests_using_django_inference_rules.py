from .. import api, models
from ..core import Solution, Var
from . import common, common_django


class TestInference(common_django.TestUsingDjango):
    def test_siblings_rule_in_action_when_using_a_db(self):
        with self.assertNumQueries(37):
            self.populate_db([common.siblings_rule])

        with self.assertNumQueries(1):
            solutions = self.explain_solutions(
                [(Var("sibling1"), "sibling_of", Var("sibling2"))]
            )
            self.assertListEqual(
                solutions,
                [
                    Solution(
                        {"sibling1": "sister", "sibling2": "brother"},
                        {("sister", "sibling_of", "brother")},
                    ),
                    Solution(
                        {"sibling1": "brother", "sibling2": "sister"},
                        {("brother", "sibling_of", "sister")},
                    ),
                ],
            )

    def test_transition_from_a_set_of_rules_to_others(self):
        with self.assertNumQueries(37):
            self.populate_db([common.siblings_rule])

        with self.assertNumQueries(1):
            solutions = self.solve([(Var("a"), "descendant_of", Var("b"))])
            self.assertListEqual(solutions, [])

        with self.assertNumQueries(61):
            models.INFERENCE_RULES = common.descendants_rules
            api.refresh_inference()

        with self.assertNumQueries(1):
            solutions = self.explain_solutions(
                [(Var("a"), "descendant_of", Var("b"))]
            )
            self.assertListEqual(
                solutions,
                [
                    Solution(
                        {"a": "brother", "b": "father"},
                        frozenset({("brother", "descendant_of", "father")}),
                    ),
                    Solution(
                        {"a": "sister", "b": "father"},
                        frozenset({("sister", "descendant_of", "father")}),
                    ),
                    Solution(
                        {"a": "father", "b": "grandfather"},
                        frozenset({("father", "descendant_of", "grandfather")}),
                    ),
                    Solution(
                        {"a": "brother", "b": "grandfather"},
                        frozenset(
                            {("brother", "descendant_of", "grandfather")}
                        ),
                    ),
                    Solution(
                        {"a": "sister", "b": "grandfather"},
                        frozenset({("sister", "descendant_of", "grandfather")}),
                    ),
                    Solution(
                        {"a": "brother", "b": "mother"},
                        frozenset({("brother", "descendant_of", "mother")}),
                    ),
                    Solution(
                        {"a": "sister", "b": "mother"},
                        frozenset({("sister", "descendant_of", "mother")}),
                    ),
                ],
            )

    def test_deleting_a_primary_triplet_deletes_its_deductions(self):
        with self.assertNumQueries(46):
            self.populate_db(common.descendants_rules)

        with self.assertNumQueries(21):
            api.remove(("father", "child_of", "grandfather"))

        with self.assertNumQueries(1):
            solutions = self.explain_solutions(
                [(Var("a"), "descendant_of", Var("b"))]
            )
            self.assertListEqual(
                solutions,
                [
                    Solution(
                        {"a": "brother", "b": "father"},
                        frozenset({("brother", "descendant_of", "father")}),
                    ),
                    Solution(
                        {"a": "sister", "b": "father"},
                        frozenset({("sister", "descendant_of", "father")}),
                    ),
                    Solution(
                        {"a": "brother", "b": "mother"},
                        frozenset({("brother", "descendant_of", "mother")}),
                    ),
                    Solution(
                        {"a": "sister", "b": "mother"},
                        frozenset({("sister", "descendant_of", "mother")}),
                    ),
                ],
            )

    def test_cant_delete_deduced_triplets(self):
        with self.assertNumQueries(46):
            self.populate_db(common.descendants_rules)

        with self.assertNumQueries(1):
            with self.assertRaises(ValueError):
                api.remove(("sister", "descendant_of", "grandfather"))
