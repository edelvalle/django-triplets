from .ast import Attr
from .ast_untyped import Any, Fact, In, Var
from .core import compile_rules
from .models import StoredFact

__all__ = [
    "Attr",
    "Any",
    "Fact",
    "Var",
    "In",
    "compile_rules",
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
