from django.contrib import admin

from . import models


@admin.register(models.StoredTriplet)
class StoredTripletAdmin(admin.ModelAdmin):
    search_fields = ["subject", "verb", "obj"]
    list_display = search_fields + ["is_inferred"]

    # Don't use this interface to mess around with triplets, use the API

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
