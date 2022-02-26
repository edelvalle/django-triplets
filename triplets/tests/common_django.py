from django.test import TestCase

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
        return api.solve(predicates)

    def explain_solutions(self, predicates: ListOfPredicateTuples):
        return api.explain_solutions(predicates)
