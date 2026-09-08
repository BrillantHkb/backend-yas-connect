"""Seed lab : USER + jean.dupont (AUTH-A) ; ADMIN + admin@yas.tg (jour 2 /admin/)."""

from django.core.management.base import BaseCommand

from apps.iam.models import Region, Role, User

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
        """Idempotent : ne recrée pas si l’email existe déjà."""
        if User.objects.filter(email=email).exists():
            self.stdout.write(f"User déjà présent : {email}")
            return
        User.objects.create_user(
            email=email,
            password=password,
            username=username,
            role=role,
            first_name=first_name,
            last_name=last_name,
            # ldap_dn reste NULL : un user AD ne se seed pas, uniquement register/ad.
        )
        self.stdout.write(self.style.SUCCESS(f"User créé : {email}"))
