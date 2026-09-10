"""Seed lab : USER + jean.dupont (AUTH-A) ; ADMIN + admin@yas.tg (jour 2 /admin/)."""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.iam.models import Region, Role, User
from apps.iam.services.rbac_service import seed_rbac

TEST_EMAIL = "jean.dupont@yas.tg"
TEST_USERNAME = "jean.dupont"
TEST_PASSWORD = "Secret123!"  # lab / tests uniquement

ADMIN_EMAIL = "admin@yas.tg"
ADMIN_USERNAME = "admin.yas"
ADMIN_PASSWORD = "Admin123!"  # lab : accès /admin/ (rôle ADMIN)

REGIONS = [  # dropdowns inscription ; 5 régions TG
    ("MARITIME", "Maritime"),
    ("PLATEAUX", "Plateaux"),
    ("CENTRALE", "Centrale"),
    ("KARA", "Kara"),
    ("SAVANES", "Savanes"),
]


class Command(BaseCommand):
    help = "Rôles USER + ADMIN et users de test (prefs + privacy, pas de device)."

    def handle(self, *args, **options):
        user_role, _ = Role.objects.get_or_create(
            code="USER",
            defaults={"name": "Utilisateur", "level": 0, "is_system": True},
        )
        admin_role, _ = Role.objects.get_or_create(
            code="ADMIN",
            defaults={"name": "Administrateur", "level": 100, "is_system": True},
        )
        seed_rbac()
        for code, name in REGIONS:
            Region.objects.get_or_create(code=code, defaults={"name": name})
            self.stdout.write(f"Région {code}")
        self._ensure_user(
            email=TEST_EMAIL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            role=user_role,
            first_name="Jean",
            last_name="Dupont",
        )
        self._ensure_user(
            email=ADMIN_EMAIL,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            role=admin_role,
            first_name="Admin",
            last_name="YAS",
        )

    def _ensure_user(self, *, email, username, password, role, first_name, last_name):
        """Idempotent : ne recrée pas si l’email existe déjà. Portes AUTH-F fermées (lab)."""
        existing = User.objects.filter(email=email).first()
        if existing is not None:
            self._close_gates_if_open(existing)
            self.stdout.write(f"User déjà présent : {email}")
            return
        user = User.objects.create_user(
            email=email,
            password=password,
            username=username,
            role=role,
            first_name=first_name,
            last_name=last_name,
            # ldap_dn reste NULL : un user AD ne se seed pas, uniquement register/ad.
        )
        self._close_gates_if_open(user)
        self.stdout.write(self.style.SUCCESS(f"User créé : {email}"))

    def _close_gates_if_open(self, user):
        """Pose CGU + wizard si NULL (lab déjà seedé avant AUTH-F)."""
        now = timezone.now()
        fields = []
        if user.tos_accepted_at is None:
            user.tos_accepted_at = now
            fields.append("tos_accepted_at")
        if not user.tos_version:
            user.tos_version = settings.YAS_TOS_VERSION
            fields.append("tos_version")
        if user.onboarding_completed_at is None:
            user.onboarding_completed_at = now
            fields.append("onboarding_completed_at")
        if fields:
            user.save(update_fields=[*fields, "updated_at"])
            self.stdout.write(f"Portes AUTH-F fermées : {user.email}")
