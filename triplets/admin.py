from django.contrib import admin
from django.http import HttpRequest

from . import models


@admin.register(models.StoredFact)  # type: ignore
class StoredFactAdmin(admin.ModelAdmin):  # type: ignore
    search_fields = ["subject", "verb", "obj"]
    list_display = search_fields + ["is_inferred"]

    # Don't use this interface to mess around with facts, use the API

    def has_add_permission(self, request: HttpRequest):
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: models.StoredFact | None = None
    ):
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: models.StoredFact | None = None
    ):
        return False
