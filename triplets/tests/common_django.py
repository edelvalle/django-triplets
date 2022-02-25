from django.test import TestCase

from .. import models
from ..core import ListOfPredicateTuples, Rule
from . import common


class TestUsingDjango(TestCase):
    def tearDown(self):
        models.INFERENCE_RULES = []

    def populate_db(self, rules: list[Rule]):
        models.INFERENCE_RULES = rules
        for triplet in common.triplets:
            models.StoredTriplet.objects.add(triplet)

    def solve(self, predicates: ListOfPredicateTuples):
        return list(models.StoredTriplet.objects.solve(predicates))

    def explain(self, predicates: ListOfPredicateTuples):
        return list(models.StoredTriplet.objects.explain(predicates))
