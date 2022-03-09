import typing as t
from datetime import datetime, timezone
from uuid import UUID

from .. import api, models
from ..ast import Var
from ..core import Solution
from . import common


class TestInference(common.TestUsingDjango):
    def test_siblings_rule_in_action_when_using_a_db(self):
        with self.assertNumQueries(29):
            self.populate_db(common.siblings_rule)

        with self.assertNumQueries(1):
            solutions = self.explain_solutions(
                [(Var("sibling1"), "sibling_of", Var("sibling2"))]
            )
            self.assertSetEqual(
                solutions,
                {
                    Solution(
                        {"sibling1": "sister", "sibling2": "brother"},
                        {("sister", "sibling_of", "brother")},
                    ),
                    Solution(
                        {"sibling1": "brother", "sibling2": "sister"},
                        {("brother", "sibling_of", "sister")},
                    ),
                },
            )

    def test_transition_from_a_set_of_rules_to_others(self):
        with self.assertNumQueries(29):
            self.populate_db(common.siblings_rule)

        with self.assertNumQueries(1):
            solutions = self.solve([(Var("a"), "descendant_of", Var("b"))])
            self.assertSetEqual(solutions, set())

        with self.assertNumQueries(46):
            models.INFERENCE_RULES = common.descendants_rules
            api.refresh_inference()

        with self.assertNumQueries(1):
            solutions = self.explain_solutions(
                [(Var("a"), "descendant_of", Var("b"))]
            )
            self.assertSetEqual(
                solutions,
                {
                    Solution(
                        {"a": "brother", "b": "father"},
                        {("brother", "descendant_of", "father")},
                    ),
                    Solution(
                        {"a": "sister", "b": "father"},
                        {("sister", "descendant_of", "father")},
                    ),
                    Solution(
                        {"a": "father", "b": "grandfather"},
                        {("father", "descendant_of", "grandfather")},
                    ),
                    Solution(
                        {"a": "brother", "b": "grandfather"},
                        {("brother", "descendant_of", "grandfather")},
                    ),
                    Solution(
                        {"a": "sister", "b": "grandfather"},
                        {("sister", "descendant_of", "grandfather")},
                    ),
                    Solution(
                        {"a": "brother", "b": "mother"},
                        {("brother", "descendant_of", "mother")},
                    ),
                    Solution(
                        {"a": "sister", "b": "mother"},
                        {("sister", "descendant_of", "mother")},
                    ),
                },
            )

    def test_deleting_a_primary_fact_deletes_its_deductions_and_travel(self):
        with self.assertNumQueries(52):
            self.populate_db(common.descendants_rules)

        before_removing_the_granfather_real_tx = (
            models.Transaction.objects.last()
        )
        before_removing_the_granfather_real_dt = (
            (datetime).utcnow().astimezone(timezone.utc)
        )

        with self.assertNumQueries(18):
            api.remove(("father", "child_of", "grandfather"))

        with self.assertNumQueries(1):
            solutions = self.explain_solutions(
                [(Var("a"), "descendant_of", Var("b"))]
            )
            self.assertSetEqual(
                solutions,
                {
                    Solution(
                        {"a": "brother", "b": "father"},
                        {("brother", "descendant_of", "father")},
                    ),
                    Solution(
                        {"a": "sister", "b": "father"},
                        {("sister", "descendant_of", "father")},
                    ),
                    Solution(
                        {"a": "brother", "b": "mother"},
                        {("brother", "descendant_of", "mother")},
                    ),
                    Solution(
                        {"a": "sister", "b": "mother"},
                        {("sister", "descendant_of", "mother")},
                    ),
                },
            )

        # we can time travel, he he he!

        with self.assertNumQueries(1):
            if before_removing_the_granfather_real_tx:
                solutions_from_tx = self.explain_solutions(
                    [(Var("a"), "descendant_of", "grandfather")],
                    as_of=before_removing_the_granfather_real_tx.id,
                )
            else:
                solutions_from_tx: set[Solution] = set()

        with self.assertNumQueries(2):
            solutions_from_dt = self.explain_solutions(
                [(Var("a"), "descendant_of", "grandfather")],
                as_of=before_removing_the_granfather_real_dt,
            )

        # reading from datetime and transaction are the same
        self.assertEqual(solutions_from_tx, solutions_from_dt)

        self.assertSetEqual(
            solutions_from_tx,
            {
                Solution(
                    {"a": "father"},
                    {("father", "descendant_of", "grandfather")},
                ),
                Solution(
                    {"a": "brother"},
                    {("brother", "descendant_of", "grandfather")},
                ),
                Solution(
                    {"a": "sister"},
                    {("sister", "descendant_of", "grandfather")},
                ),
            },
        )

    def test_cant_delete_deduced_fact(self):
        with self.assertNumQueries(52):
            self.populate_db(common.descendants_rules)

        with self.assertNumQueries(2):
            with self.assertRaises(ValueError) as e:
                api.remove(("sister", "descendant_of", "grandfather"))

            self.assertEqual(
                str(e.exception), "You can't delete inferred facts"
            )

    def test_change_of_gender(self):
        with self.assertNumQueries(39):
            self.populate_db(common.parent_role_rules)

        self._assert_father_is_dad_and_mother_is_mom()

        # change dad's gender
        with self.assertNumQueries(13):
            api.add(("father", "gender", "f"))

        last_transaction = models.Transaction.objects.last()

        # removes the primary fact, the inferred ones
        # adds the new fact and adds the inferred ones
        if last_transaction:
            self.assertEqual(
                set(last_transaction.mutations),
                {
                    ("-", ("father", "gender", "m")),
                    ("-", ("father", "dad_of", "brother")),
                    ("-", ("father", "dad_of", "sister")),
                    ("+", ("father", "gender", "f")),
                    ("+", ("father", "mom_of", "brother")),
                    ("+", ("father", "mom_of", "sister")),
                },
            )
        else:
            self.assertIsNotNone(None)

        with self.assertNumQueries(1):
            solutions = self.explain_solutions(
                [(Var("dad"), "dad_of", Var("child"))]
            )
            self.assertEqual(
                solutions,
                {
                    Solution(
                        {"dad": "grandfather", "child": "father"},
                        {("grandfather", "dad_of", "father")},
                    ),
                },
            )

        with self.assertNumQueries(1):
            solutions = self.explain_solutions(
                [(Var("mom"), "mom_of", Var("child"))]
            )
            self.assertEqual(
                solutions,
                {
                    Solution(
                        {"mom": "mother", "child": "brother"},
                        {("mother", "mom_of", "brother")},
                    ),
                    Solution(
                        {"mom": "mother", "child": "sister"},
                        {("mother", "mom_of", "sister")},
                    ),
                    Solution(
                        {"mom": "father", "child": "brother"},
                        {("father", "mom_of", "brother")},
                    ),
                    Solution(
                        {"mom": "father", "child": "sister"},
                        {("father", "mom_of", "sister")},
                    ),
                },
            )

        # time travel before last transaction
        before_father_changed_sex = list(models.Transaction.objects.all())[-2]
        self._assert_father_is_dad_and_mother_is_mom(
            as_of=before_father_changed_sex.id
        )

    def _assert_father_is_dad_and_mother_is_mom(
        self, as_of: t.Optional[UUID] = None
    ):
        with self.assertNumQueries(1):
            solutions = self.explain_solutions(
                [(Var("dad"), "dad_of", Var("child"))], as_of=as_of
            )
            self.assertEqual(
                solutions,
                {
                    Solution(
                        {"dad": "father", "child": "brother"},
                        {("father", "dad_of", "brother")},
                    ),
                    Solution(
                        {"dad": "father", "child": "sister"},
                        {("father", "dad_of", "sister")},
                    ),
                    Solution(
                        {"dad": "grandfather", "child": "father"},
                        {("grandfather", "dad_of", "father")},
                    ),
                },
            )

        with self.assertNumQueries(1):
            solutions = self.explain_solutions(
                [(Var("mom"), "mom_of", Var("child"))], as_of=as_of
            )
            self.assertEqual(
                solutions,
                {
                    Solution(
                        {"mom": "mother", "child": "brother"},
                        {("mother", "mom_of", "brother")},
                    ),
                    Solution(
                        {"mom": "mother", "child": "sister"},
                        {("mother", "mom_of", "sister")},
                    ),
                },
            )

    def test_using_multiple_data_types(self):
        with self.assertNumQueries(7):
            self.populate_db(common.age_stage_rules)

        query = [
            (Var("person"), "age", Var("age")),
            (Var("person"), "age_stage", Var("stage")),
        ]
        with self.assertNumQueries(1):
            solutions = self.solve(query)
            self.assertSetEqual(solutions, set())

        with self.assertNumQueries(11):
            api.bulk_add([("brother", "age", 2), ("sister", "age", 22)])

        with self.assertNumQueries(2):
            solutions = self.solve(query)
            self.assertSetEqual(
                solutions,
                {
                    frozenset(
                        {
                            ("person", "sister"),
                            ("age", 22),
                            ("stage", "adult"),
                        }
                    ),
                    frozenset(
                        {
                            ("person", "brother"),
                            ("age", 2),
                            ("stage", "minor"),
                        }
                    ),
                },
            )

        with self.assertNumQueries(14):
            api.bulk_add(
                [
                    ("brother", "age", 100),
                    ("sister", "age", 2),
                    ("father", "age", 54),
                ]
            )

        with self.assertNumQueries(2):
            solutions = self.solve(query)
            self.assertSetEqual(
                solutions,
                {
                    frozenset(
                        {
                            ("person", "sister"),
                            ("age", 2),
                            ("stage", "minor"),
                        }
                    ),
                    frozenset(
                        {
                            ("person", "brother"),
                            ("age", 100),
                            ("stage", "adult"),
                        }
                    ),
                    frozenset(
                        {
                            ("person", "father"),
                            ("age", 54),
                            ("stage", "adult"),
                        }
                    ),
                },
            )
