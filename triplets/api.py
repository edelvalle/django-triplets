from .ast import Any, Var
from .core import Rule, rule
from .models import StoredFact

__all__ = [
    "Any",
    "Rule",
    "Var",
    "rule",
    "add",
    "bulk_add",
    "remove",
    "bulk_remove",
    "solve",
    "explain_solutions",
    "refresh_inference",
]

add = StoredFact.objects.add
bulk_add = StoredFact.objects.bulk_add
remove = StoredFact.objects.remove
bulk_remove = StoredFact.objects.bulk_remove
solve = StoredFact.objects.solve
explain_solutions = StoredFact.objects.explain_solutions
refresh_inference = StoredFact.objects.refresh_inference
