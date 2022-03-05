import typing as t

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def refresh_inference(**kwargs: dict[str, t.Any]):
    from . import api

    print("Refreshing inference rules... ", end="", flush=True)
    api.refresh_inference()
    print("OK")


class TripletsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "triplets"

    def ready(self):
        post_migrate.connect(
            refresh_inference,
            sender=self,
            dispatch_uid="triplets.refresh_inference",
        )
