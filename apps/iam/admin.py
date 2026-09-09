"""Django admin lab (jour 2). Cookie session ; API reste JWT. Hash jamais en clair."""

from django.contrib import admin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.forms import ModelForm

from apps.iam.models import (
    Device,
    LoginHistory,
    OtpSecret,
    PrivacySetting,
    RefreshToken,
    Role,
    Session,
    User,
    UserPreference,
)


class UserAdminForm(ModelForm):
    """Le hash Argon2 est affiché en lecture seule (pas d’édition du clair)."""

    password = ReadOnlyPasswordHashField(label="Hash mot de passe")

    class Meta:
        model = User
        fields = "__all__"


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "level", "is_system")
    search_fields = ("code", "name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    list_display = (
        "email",
        "username",
        "role",
        "is_active",
        "pending_approval",
        "is_locked",
        "last_login",
    )
    list_filter = ("is_active", "pending_approval", "is_locked", "role")
    search_fields = ("email", "username", "first_name", "last_name", "matricule")
    readonly_fields = ("id", "password", "last_login", "first_login", "created_at", "updated_at")
    raw_id_fields = ("role", "region")
    ordering = ("email",)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    """push_token masqué ; compromised via API admin, pas d’édition claire ici."""

    list_display = (
        "device_uuid",
        "user",
        "platform",
        "trusted",
        "compromised",
        "jailbreak",
        "last_seen",
    )
    list_filter = ("platform", "trusted", "compromised", "jailbreak")
    search_fields = ("device_uuid", "device_name", "user__email")
    readonly_fields = ("id", "push_token_display", "compromised", "created_at", "updated_at")
    exclude = ("push_token",)
    raw_id_fields = ("user",)

    def push_token_display(self, obj):
        return "********" if obj.push_token else ""

    push_token_display.short_description = "Push token"


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    """refresh_hash en readonly : jamais le clair."""

    list_display = ("id", "user", "device", "is_active", "login_method", "login_at", "expires_at")
    list_filter = ("is_active", "login_method")
    search_fields = ("user__email", "access_jti")
    readonly_fields = (
        "id",
        "access_jti",
        "refresh_jti",
        "refresh_hash",
        "login_at",
        "created_at",
        "updated_at",
    )
    raw_id_fields = ("user", "device")


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    """token_hash HMAC : pas le refresh opaque."""

    list_display = ("id", "user", "jti", "expires_at", "revoked_reason", "issued_at")
    list_filter = ("revoked_reason",)
    search_fields = ("user__email", "jti")
    readonly_fields = (
        "id",
        "token_hash",
        "jti",
        "issued_at",
        "created_at",
        "rotated_at",
        "revoked_at",
    )
    raw_id_fields = ("session", "user")


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "email", "success", "failure_reason", "ip_address", "browser")
    list_filter = ("success", "failure_reason", "login_method")
    search_fields = ("email", "ip_address")
    readonly_fields = [f.name for f in LoginHistory._meta.fields]
    raw_id_fields = ("user", "device", "session")

    def has_add_permission(self, request):
        return False  # journal append-only

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "language", "timezone")
    raw_id_fields = ("user",)
    readonly_fields = ("id", "last_updated")


@admin.register(PrivacySetting)
class PrivacySettingAdmin(admin.ModelAdmin):
    list_display = ("user", "last_seen_visibility", "online_status_visibility")
    raw_id_fields = ("user",)
    readonly_fields = ("id", "updated_at")


@admin.register(OtpSecret)
class OtpSecretAdmin(admin.ModelAdmin):
    """Secret TOTP masqué ; backup_codes = hash, jamais le clair."""

    list_display = ("user", "enabled", "verified_at", "algorithm", "updated_at")
    list_filter = ("enabled",)
    search_fields = ("user__email",)
    readonly_fields = (
        "id",
        "secret_display",
        "backup_codes",
        "created_at",
        "updated_at",
    )
    exclude = ("secret",)
    raw_id_fields = ("user",)

    def secret_display(self, obj):
        return "********"  # Fernet : jamais le clair, même en lab

    secret_display.short_description = "Secret TOTP"
