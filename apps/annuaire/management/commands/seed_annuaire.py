"""Seed types DIRECTION/DEPARTEMENT/SERVICE + segment racine YAS. Pas de user AD."""

from django.core.management.base import BaseCommand

from apps.annuaire.models import Segment, SegmentType

TYPES = [
    ("DIRECTION", "Direction", 0),
    ("DEPARTEMENT", "Département", 1),
    ("SERVICE", "Service", 2),
]


class Command(BaseCommand):
    help = "Types d’unité + segment YAS Togo (dropdowns inscription)."

    def handle(self, *args, **options):
        types = {}
        for code, name, level in TYPES:
            obj, _ = SegmentType.objects.get_or_create(
                code=code,
                defaults={"name": name, "level": level, "is_active": True},
            )
            types[code] = obj
            self.stdout.write(f"Type {code}")
        Segment.objects.get_or_create(
            code="YAS",
            defaults={
                "name": "YAS Togo",
                "segment_type": types["DIRECTION"],
                "parent_segment": None,
                "responsable": None,
                "is_active": True,
            },
        )
        self.stdout.write(self.style.SUCCESS("Segment YAS OK"))
