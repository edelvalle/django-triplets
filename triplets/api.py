from .core import Rule, Var, rule
from .models import StoredTriplet

__all__ = [
    "Rule",
    "Var",
    "rule",
    "add",
    "bulk_add",
    "remove",
    "solve",
    "explain_solutions",
    "refresh_inference",
]

add = StoredTriplet.objects.add
bulk_add = StoredTriplet.objects.bulk_add
remove = StoredTriplet.objects.remove
solve = StoredTriplet.objects.solve
explain_solutions = StoredTriplet.objects.explain_solutions
refresh_inference = StoredTriplet.objects.refresh_inference
