from dataclasses import dataclass

import ulid
from django.db import models

from . import core


@dataclass
class Triplet(core.Triplet):
    subject: str
    verb: str
    obj: str


class TripletQS(models.QuerySet):
    def add(self, triplet: Triplet) -> ulid.ULID:
        stored_triplet, _created = self.update_or_create(
            subject=triplet.subject,
            verb=triplet.verb,
            obj=triplet.obj,
        )
        return stored_triplet.id

    def lookup(
        self, predicate: core.Predicate, consumed: list["StoredTriplet"]
    ):
        query = {
            term_name: term_value
            for term_name, term_value in predicate.as_dict().items()
            if isinstance(term_value, str)
        }
        return self.exclude(id__in=[c.id for c in consumed]).filter(**query)

    def solve(self, query: core.Query | list):
        if isinstance(query, list):
            query = core.Query(query)
        return query.solve_using(self)


def new_ulid():
    return ulid.new().uuid


class StoredTriplet(models.Model):
    id = models.UUIDField(primary_key=True, default=new_ulid)

    # TODO: max_length here should be configurable
    subject: str = models.CharField(max_length=32)
    verb: str = models.CharField(max_length=32)
    obj: str = models.CharField(max_length=32)

    objects: TripletQS = TripletQS.as_manager()

    class Meta:
        unique_together = [["subject", "verb", "obj"]]
        indexes = [
            models.Index(fields=["verb"]),
            models.Index(fields=["subject", "verb"]),
            models.Index(fields=["verb", "obj"]),
        ]

    def __str__(self):
        return f"{self.subject} {self.verb} {self.obj}"
