import typing as t

from django.core.management.base import BaseCommand

from triplets.api import refresh_inference


class Command(BaseCommand):
    help = "Runs all the inference rules agains the database"

    def handle(self, *args: t.Any, **options: t.Any):
        refresh_inference()
