from django.db import DEFAULT_DB_ALIAS, connections
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from .. import api, models
from ..core import ListOfPredicateTuples, Rule
from . import common


class TestUsingDjango(TestCase):
    def tearDown(self):
        models.INFERENCE_RULES = []

    def populate_db(self, rules: list[Rule]):
        models.INFERENCE_RULES = rules
        api.bulk_add(common.triplets)

    def solve(self, predicates: ListOfPredicateTuples):
        return list(api.solve(predicates))

    def explain(self, predicates: ListOfPredicateTuples):
        return list(api.explain(predicates))

    def assertNumQueriesBetween(
        self, lower, upper, func=None, *args, using=DEFAULT_DB_ALIAS, **kwargs
    ):
        """This is an extension of `self.assertNumQueries()`"""
        conn = connections[using]

        context = _AssertNumQueriesContextBetween(self, lower, upper, conn)
        if func is None:
            return context

        with context:
            func(*args, **kwargs)


class _AssertNumQueriesContextBetween(CaptureQueriesContext):
    def __init__(self, test_case, lower, upper, connection):
        test_case.assertLess(lower, upper)
        self.test_case = test_case
        self.lower = lower
        self.upper = upper
        super().__init__(connection)

    def __exit__(self, exc_type, exc_value, traceback):
        super().__exit__(exc_type, exc_value, traceback)
        if exc_type is not None:
            return
        executed = len(self)
        self.test_case.assertLessEqual(self.lower, executed)
        self.test_case.assertLessEqual(executed, self.upper)
