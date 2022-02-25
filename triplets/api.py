from .models import StoredTriplet

__all__ = ["add", "remove", "solve", "explain", "refresh_inference"]

add = StoredTriplet.objects.add
bulk_add = StoredTriplet.objects.bulk_add
remove = StoredTriplet.objects.remove
solve = StoredTriplet.objects.solve
explain = StoredTriplet.objects.explain
refresh_inference = StoredTriplet.objects.refresh_inference