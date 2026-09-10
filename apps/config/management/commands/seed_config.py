"""Seed LDAP system_settings + job AUTH-16. Idempotent. Jamais de user AD."""

from datetime import datetime

from croniter import croniter
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.config.models import ScheduledJob, SystemSetting

# AUTH-G : politique MDP (même défauts que enforce_password_policy AUTH-D).
SECURITY_SETTINGS = [
    ("password_min_length", 10, "int"),
    ("password_max_length", 128, "int"),
    ("password_require_upper", True, "bool"),
    ("password_require_lower", True, "bool"),
    ("password_require_digit", True, "bool"),
    ("password_require_special", True, "bool"),
    ("password_history_n", 5, "int"),
    ("password_reset_ttl_seconds", 600, "int"),
]

LDAP_SETTINGS = [
    ("uri", "ldap://10.228.15.100:389", "string", False),  # STARTTLS obligatoire (pas LDAP clair)
    ("bind_dn", "CN=App Mission,OU=COMPTES SERVICE,DC=TOGOCOM,DC=INT", "string", False),
    ("bind_password", "CHANGE_ME", "string", True),  # is_sensitive ; à remplacer en lab AD
    ("search_base", "DC=TOGOCOM,DC=INT", "string", False),
    ("timeout_seconds", 5, "int", False),
]


class Command(BaseCommand):
    help = "Clés LDAP (system_settings) + job ldap_sync_users. Pas de secret dans .env."

    def handle(self, *args, **options):
        for key, value, value_type in SECURITY_SETTINGS:
            _, created = SystemSetting.objects.update_or_create(
                category="security",
                setting_key=key,
                defaults={
                    "setting_value": value,
                    "value_type": value_type,
                    "is_sensitive": False,
                    "editable": True,
                },
            )
            action = "créé" if created else "à jour"
            self.stdout.write(f"security.{key} {action}")
        for key, value, value_type, sensitive in LDAP_SETTINGS:
            if key == "bind_password":
                # Secret : créé une fois (placeholder), jamais écrasé par un re-seed.
                _, created = SystemSetting.objects.get_or_create(
                    category="ldap",
                    setting_key=key,
                    defaults={
                        "setting_value": value,
                        "value_type": value_type,
                        "is_sensitive": True,
                        "editable": True,
                    },
                )
                self.stdout.write("ldap.bind_password : ********")
                continue
            _, created = SystemSetting.objects.update_or_create(
                category="ldap",
                setting_key=key,
                defaults={
                    "setting_value": value,
                    "value_type": value_type,
                    "is_sensitive": sensitive,
                    "editable": True,
                },
            )
            action = "créé" if created else "à jour"
            self.stdout.write(f"ldap.{key} {action}")

        now = timezone.now()
        ScheduledJob.objects.update_or_create(
            job_name="ldap_sync_users",
            defaults={
                "module": "IAM",
                "cron_expression": "0 2 * * *",
                "interval_seconds": None,
                "handler": "apps.iam.jobs.sync_ldap_accounts",
                "enabled": True,
                "next_execution": croniter("0 2 * * *", now).get_next(datetime),
            },
        )
        self.stdout.write(self.style.SUCCESS("Job ldap_sync_users OK"))
