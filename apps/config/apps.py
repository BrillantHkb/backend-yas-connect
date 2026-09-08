from django.apps import AppConfig


class ConfigAppConfig(AppConfig):
    """label=config : évite le clash avec le package racine config/ (settings)."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.config"
    label = "config"
