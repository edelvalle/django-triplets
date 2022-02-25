from django.apps import AppConfig
from django.db.models.signals import post_migrate


def refresh_inference(sender, **kwargs):
    from . import api

    api.refresh_inference()


class TripletsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "triplets"

    def ready(self):
        post_migrate.connect(refresh_inference, sender=self)
