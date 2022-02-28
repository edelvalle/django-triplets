from django.test import TestCase

from .. import api, models
from ..core import PredicateTuples, Rule
from . import common


class TestUsingDjango(TestCase):
    def tearDown(self):
        models.INFERENCE_RULES = []

    def populate_db(self, rules: list[Rule]):
        models.INFERENCE_RULES = rules
        api.bulk_add(common.triplets)

    def solve(self, predicate: PredicateTuples):
        return api.solve(predicate)

    def explain_solutions(self, predicate: PredicateTuples):
        return api.explain_solutions(predicate)
