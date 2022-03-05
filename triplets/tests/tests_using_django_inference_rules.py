from datetime import datetime, timezone

from .. import api, models
from ..core import Solution, Var
from . import common


class TestInference(common.TestUsingDjango):
    checkNumQueries = False

    def test_siblings_rule_in_action_when_using_a_db(self):
        with self.assertNumQueries(23):
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
                        frozenset({("sister", "sibling_of", "brother")}),
                    ),
                    Solution(
                        {"sibling1": "brother", "sibling2": "sister"},
                        frozenset({("brother", "sibling_of", "sister")}),
                    ),
                ],
            )

    def test_transition_from_a_set_of_rules_to_others(self):
        with self.assertNumQueries(23):
            self.populate_db([common.siblings_rule])

        with self.assertNumQueries(1):
            solutions = self.solve([(Var("a"), "descendant_of", Var("b"))])
            self.assertListEqual(solutions, [])

        with self.assertNumQueries(46):
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

    def test_deleting_a_primary_fact_deletes_its_deductions_and_travel(self):
        with self.assertNumQueries(46):
            self.populate_db(common.descendants_rules)

        before_removing_the_granfather_real_tx = (
            models.Transaction.objects.last()
        )
        before_removing_the_granfather_real_dt = (
            (datetime).utcnow().astimezone(timezone.utc)
        )

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

        # we can time travel, he he he!

        with self.assertNumQueries(1):
            solutions_from_tx = self.explain_solutions(
                [(Var("a"), "descendant_of", "grandfather")],
                as_of=before_removing_the_granfather_real_tx,
            )

        with self.assertNumQueries(1):
            solutions_from_dt = self.explain_solutions(
                [(Var("a"), "descendant_of", "grandfather")],
                as_of=before_removing_the_granfather_real_dt,
            )

        # reading from datetime and transaction are the same
        self.assertEqual(solutions_from_tx, solutions_from_dt)

        self.assertListEqual(
            solutions_from_tx,
            [
                Solution(
                    {"a": "father"},
                    frozenset({("father", "descendant_of", "grandfather")}),
                ),
                Solution(
                    {"a": "brother"},
                    frozenset({("brother", "descendant_of", "grandfather")}),
                ),
                Solution(
                    {"a": "sister"},
                    frozenset({("sister", "descendant_of", "grandfather")}),
                ),
            ],
        )

    def test_cant_delete_deduced_fact(self):
        with self.assertNumQueries(46):
            self.populate_db(common.descendants_rules)

        with self.assertNumQueries(1):
            with self.assertRaises(ValueError):
                api.remove(("sister", "descendant_of", "grandfather"))
