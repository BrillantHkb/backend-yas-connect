"""Admin lab : settings LDAP + jobs. Secrets jamais en clair."""

from django.contrib import admin

from apps.config.models import FeatureFlag, ScheduledJob, SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = (
        "category",
        "setting_key",
        "value_type",
        "is_sensitive",
        "editable",
        "updated_at",
    )
    list_filter = ("category", "is_sensitive", "editable")
    search_fields = ("category", "setting_key")
    readonly_fields = ("id", "created_at", "updated_at", "setting_value_display")
    exclude = ()

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.is_sensitive:
            fields.append("setting_value")  # bind_password : lecture masquée, pas d’édition claire
        return fields

    def setting_value_display(self, obj):
        if obj.is_sensitive:
            return "********"
        return obj.setting_value

    setting_value_display.short_description = "Valeur"

    def get_fields(self, request, obj=None):
        fields = [
            "category",
            "setting_key",
            "value_type",
            "is_sensitive",
            "editable",
            "updated_by",
            "created_at",
            "updated_at",
        ]
        if obj and obj.is_sensitive:
            fields.insert(2, "setting_value_display")
        else:
            fields.insert(2, "setting_value")
        return fields


@admin.register(ScheduledJob)
class ScheduledJobAdmin(admin.ModelAdmin):
    list_display = (
        "job_name",
        "enabled",
        "cron_expression",
        "last_status",
        "last_execution",
        "next_execution",
    )
    list_filter = ("enabled", "last_status", "module")
    search_fields = ("job_name", "handler")
    readonly_fields = (
        "id",
        "last_execution",
        "last_status",
        "last_error",
        "created_at",
        "updated_at",
    )


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ("feature_code", "feature_name", "enabled", "rollout_percentage")
    list_filter = ("enabled",)
    search_fields = ("feature_code", "feature_name")
    readonly_fields = ("id", "created_at", "updated_at")
