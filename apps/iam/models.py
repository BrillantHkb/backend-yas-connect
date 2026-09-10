"""
Coller dans apps/iam/models.py.

Source : catalogues/IAM-catalogue-tables.md
Index : catalogues/INDEX-catalogue.md (btree + GIN).
Pas de user_roles (rôle unique = users.role_id).
Pas de trusted_devices (confiance = devices.trusted).
Annuaire → apps.annuaire (0 ligne au login).
Médias → apps.media (users.avatar_id UUID, sans FK ici).
"""

import uuid

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class LoginMethod(models.TextChoices):
    """Canal d’auth (sessions + login_history). AUTH-01 = PASSWORD uniquement."""

    PASSWORD = "PASSWORD"  # email + mot de passe
    LDAP = "LDAP"  # AUTH-13
    SSO = "SSO"  # non utilisé AUTH-B (OIDC abandonné)
    OTP = "OTP"  # non utilisé session (facteur 2) ; session = PASSWORD | LDAP
    REFRESH = "REFRESH"  # AUTH-09
    DEVICE_LINK = "DEVICE_LINK"  # AUTH-J : QR 2ᵉ appareil + TOTP


class ResetChannel(models.TextChoices):
    """Canal du forgot-password. AUTH-G n’écrit que TOTP (pas EMAIL/SMS/APPEL)."""

    TOTP = "TOTP"  # Google Authenticator (AUTH-47)
    SMS = "SMS"
    EMAIL = "EMAIL"
    APPEL = "APPEL"


class Visibility(models.TextChoices):
    """Qui voit last seen / photo / online (privacy_settings)."""

    EVERYONE = "EVERYONE"
    CONTACTS = "CONTACTS"
    NOBODY = "NOBODY"


class Role(models.Model):
    """Rôle IAM unique par user (users.role_id). Seed AUTH-01 : code=USER."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=32, unique=True, db_index=True)  # JWT / ACL
    name = models.CharField(max_length=128)  # libellé UI
    description = models.TextField(blank=True, default="")  # aide admin
    level = models.SmallIntegerField(default=0)  # rang (0 USER, 100 ADMIN)
    is_system = models.BooleanField(default=False)  # interdit suppression si True
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "roles"  # nom SQL métier, sans préfixe

    def __str__(self):
        return self.code


class Region(models.Model):
    """Région géographique (référentiel IAM). Table SQL `region` (ERD). 0 ligne AUTH-01."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)  # UK, ex. MARITIME
    name = models.CharField(max_length=100, unique=True)  # UK, libellé, ex. Maritime
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "region"  # nom ERD (singulier)

    def __str__(self):
        return self.code


class Permission(models.Model):
    """Droit atomique. code = {module}.{resource}.{action} (AUTH-R)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=96, unique=True, db_index=True)  # iam.user.approve
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")
    module = models.CharField(max_length=64)  # domaine (iam, media, annuaire)
    resource = models.CharField(max_length=64)  # 2e segment (user, device, role)
    action = models.CharField(max_length=64)  # verbe (read, manage, approve)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "permissions"
        unique_together = [("module", "resource", "action")]


class UserManager(BaseUserManager):
    """Création user + lignes 1-1 prefs/privacy (catalogue : à l’ouverture du compte)."""

    def _create_user(self, email, password, username, role, **extra):
        if not email:
            raise ValueError("email obligatoire")
        email = self.normalize_email(email).strip().lower()  # login toujours en lower
        user = self.model(email=email, username=username, role=role, **extra)
        user.set_password(password)  # Argon2id via PASSWORD_HASHERS
        user.save(using=self._db)
        UserPreference.objects.get_or_create(user=user)  # 1-1 obligatoire
        PrivacySetting.objects.get_or_create(user=user)
        from apps.iam.services.rbac_service import ensure_system_matrix

        ensure_system_matrix(role)  # USER/ADMIN vides → seed self / tout (tests A–I)
        return user

    def create_user(self, email, password, username, role, **extra):
        extra.setdefault("is_active", True)  # sinon 403 ACCOUNT_DISABLED
        extra.setdefault("pending_approval", False)
        extra.setdefault("is_locked", False)  # sinon 403 ACCOUNT_LOCKED
        extra.setdefault("status", User.PresenceStatus.OFFLINE)  # présence, pas le login
        extra.setdefault("language", "fr")
        extra.setdefault("timezone", "Africa/Lome")
        return self._create_user(email, password, username, role, **extra)

    def create_superuser(self, email, password, username=None, role=None, **extra):
        # createsuperuser Django envoie is_staff/is_superuser : pas des colonnes catalogue
        extra.pop("is_staff", None)
        extra.pop("is_superuser", None)
        extra["is_active"] = True
        extra["pending_approval"] = False
        extra["is_locked"] = False
        if role is None:
            role, _ = Role.objects.get_or_create(
                code="ADMIN",
                defaults={"name": "Administrateur", "level": 100, "is_system": True},
            )
        if not username:
            username = extra.pop("username", None) or email.split("@")[0]
        return self.create_user(email, password, username, role, **extra)


class User(AbstractBaseUser):
    """AUTH_USER_MODEL. Login = pending_approval / is_active / is_locked, jamais status (présence)."""

    class PresenceStatus(models.TextChoices):
        ONLINE = "ONLINE"  # pastille contacts (WS plus tard)
        OFFLINE = "OFFLINE"  # défaut ; AUTH-01 ne le change pas

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=254, unique=True)  # identifiant de login
    username = models.CharField(max_length=64, unique=True)  # handle / mentions
    first_name = models.CharField(max_length=128, blank=True, default="")
    last_name = models.CharField(max_length=128, blank=True, default="")
    matricule = models.CharField(max_length=32, unique=True, null=True, blank=True)
    phone = models.CharField(max_length=32, null=True, blank=True)  # E.164
    job_title = models.CharField(max_length=128, blank=True, default="")  # poste actuel
    status = models.CharField(
        max_length=16,
        choices=PresenceStatus.choices,
        default=PresenceStatus.OFFLINE,
        db_index=True,
    )  # ONLINE/OFFLINE — pas un statut de compte
    language = models.CharField(max_length=8, default="fr")  # fallback i18n profil
    timezone = models.CharField(max_length=64, default="Africa/Lome")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="users")
    region = models.ForeignKey(
        Region,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )  # users.region_id ; NULL au seed AUTH-01
    # UUID sans FK : évite cycle iam ↔ annuaire (table segments existe déjà)
    segment_id = models.UUIDField(null=True, blank=True, db_index=True)
    # UUID sans FK : évite cycle iam ↔ media
    avatar_id = models.UUIDField(null=True, blank=True)
    ldap_dn = models.CharField(max_length=512, unique=True, null=True, blank=True)  # lien AD (AUTH-D02 / 13/16)
    password = models.CharField(max_length=255, db_column="password_hash")  # jamais en API
    is_active = models.BooleanField(default=True)  # False → 403 ACCOUNT_DISABLED (si pas pending)
    pending_approval = models.BooleanField(default=False)  # True → 403 ACCOUNT_PENDING (AUTH-D03)
    is_locked = models.BooleanField(default=False)  # True → 403 ACCOUNT_LOCKED
    locked_at = models.DateTimeField(null=True, blank=True)  # AUTH-I : début du verrou (NULL = lock manuel sans TTL)
    last_login = models.DateTimeField(null=True, blank=True)  # écrit AUTH-01
    first_login = models.DateTimeField(null=True, blank=True)  # 1er succès AUTH-01
    tos_accepted_at = models.DateTimeField(null=True, blank=True)  # AUTH-40 : quand les CGU
    tos_version = models.CharField(max_length=32, null=True, blank=True)  # quelle version
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)  # AUTH-42 wizard fini
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"  # Django : login par email, pas username
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["is_active", "is_locked"], name="users_active_locked_idx"),
            GinIndex(fields=["first_name"], name="users_first_name_trgm", opclasses=["gin_trgm_ops"]),
            GinIndex(fields=["last_name"], name="users_last_name_trgm", opclasses=["gin_trgm_ops"]),
            GinIndex(fields=["email"], name="users_email_trgm", opclasses=["gin_trgm_ops"]),
            GinIndex(fields=["username"], name="users_username_trgm", opclasses=["gin_trgm_ops"]),
            GinIndex(fields=["matricule"], name="users_matricule_trgm", opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self):
        return self.email

    @property
    def is_staff(self):
        """Accès /admin/ lab : rôle ADMIN seulement (pas une colonne SQL)."""
        role = getattr(self, "role", None)
        return bool(role) and role.code == "ADMIN"

    @property
    def is_superuser(self):
        """Même règle que is_staff : pas de PermissionsMixin au catalogue."""
        return self.is_staff

    def has_perm(self, perm, obj=None):
        """Django admin exige cette API ; AUTH-R (HasPermission) viendra plus tard."""
        return self.is_staff

    def has_module_perms(self, app_label):
        """Voir une app dans /admin/ si rôle ADMIN."""
        return self.is_staff

    def get_full_name(self):
        """Libellé admin : prénom + nom."""
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_short_name(self):
        """Libellé court admin."""
        return self.first_name or self.username


class RolePermission(models.Model):
    """Matrice ACL rôle ↔ permission. 0 ligne AUTH-01."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name="role_permissions"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_role_permissions",
    )  # audit : qui a accordé
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "role_permissions"
        unique_together = [("role", "permission")]


class UserPreference(models.Model):
    """Préférences UI (1-1). Créée à la création du compte / seed. Peut ≠ users.language."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    language = models.CharField(max_length=10, default="fr")  # langue de l’app
    timezone = models.CharField(max_length=100, default="Africa/Lome")
    notification_sound = models.BooleanField(default=True)
    auto_download_media = models.BooleanField(default=False)  # économie data
    read_receipts = models.BooleanField(default=True)  # souhait accusés
    typing_indicator = models.BooleanField(default=True)
    last_updated = models.DateTimeField(auto_now=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )

    class Meta:
        db_table = "user_preferences"


class PrivacySetting(models.Model):
    """Confidentialité (1-1). Créée à la création du compte / seed."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    last_seen_visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.EVERYONE
    )
    profile_photo_visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.EVERYONE
    )
    online_status_visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.EVERYONE
    )
    read_receipts_enabled = models.BooleanField(default=True)  # envoyer/afficher accusés
    typing_indicator_enabled = models.BooleanField(default=True)
    allow_calls = models.BooleanField(default=True)
    allow_mentions = models.BooleanField(default=True)
    allow_group_invites = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="privacy",
    )

    class Meta:
        db_table = "privacy_settings"


class Device(models.Model):
    """Terminal (app / web). Upsert AUTH-11 (login local AUTH-A). Confiance = trusted (AUTH-27)."""

    class Platform(models.TextChoices):
        IOS = "IOS"
        ANDROID = "ANDROID"
        WEB = "WEB"
        DESKTOP = "DESKTOP"
        OTHER = "OTHER"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices"
    )
    device_uuid = models.CharField(max_length=128)  # ID install, unique avec user
    device_name = models.CharField(max_length=128, blank=True, default="")
    model = models.CharField(max_length=128, blank=True, default="")
    platform = models.CharField(max_length=16, choices=Platform.choices)
    os_version = models.CharField(max_length=64, blank=True, default="")
    app_version = models.CharField(max_length=32, blank=True, default="")
    device_fingerprint = models.CharField(max_length=255, null=True, blank=True)
    push_token = models.TextField(blank=True, default="")  # FCM / APNs
    ip_address = models.GenericIPAddressField(null=True, blank=True, unpack_ipv4=True)
    last_location = models.CharField(max_length=255, null=True, blank=True)
    trusted = models.BooleanField(default=False)  # non lu AUTH-C (pas de skip MFA)
    compromised = models.BooleanField(default=False)
    jailbreak = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "devices"
        unique_together = [("user", "device_uuid")]
        indexes = [
            models.Index(fields=["last_seen"], name="devices_last_seen_idx"),
        ]


class Session(models.Model):
    """Session applicative. AUTH-A INSERT : device_id, access_jti, refresh_jti, IP, UA."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions"
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )  # AUTH-12 : NOT NULL au login local (succès)
    access_jti = models.UUIDField(unique=True, db_index=True)  # = jti du JWT access
    refresh_jti = models.UUIDField(unique=True, null=True, blank=True)  # AUTH-10
    refresh_hash = models.TextField(blank=True, default="")  # AUTH-10 hash, jamais le clair
    ip_address = models.GenericIPAddressField(null=True, blank=True, unpack_ipv4=True)
    user_agent = models.TextField(blank=True, default="")
    login_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField()  # sliding idle AUTH-H ; MAJ JWT / heartbeat
    expires_at = models.DateTimeField(db_index=True)  # plafond session (login + 30 j)
    is_active = models.BooleanField(default=True, db_index=True)  # False = logout / kill
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=64, null=True, blank=True)
    login_method = models.CharField(
        max_length=16, choices=LoginMethod.choices, default=LoginMethod.PASSWORD
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sessions"
        indexes = [
            models.Index(fields=["user", "is_active"], name="sessions_user_active_idx"),
        ]


class RefreshToken(models.Model):
    """Refresh opaque hashé. INSERT AUTH-10 (login / rotation /refresh)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name="refresh_tokens"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="refresh_tokens"
    )
    token_hash = models.TextField()  # jamais le token clair
    jti = models.UUIDField(unique=True)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    rotated_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=64, null=True, blank=True)
    created_ip = models.GenericIPAddressField(null=True, blank=True, unpack_ipv4=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "refresh_tokens"
        indexes = [
            models.Index(fields=["user", "expires_at"], name="refresh_user_exp_idx"),
            models.Index(fields=["expires_at"], name="refresh_expires_idx"),
        ]


class LoginHistory(models.Model):
    """Append-only. AUTH-01 INSERT succès et échecs. UA parsé tout de suite ; geo NULL OK."""

    class FailureReason(models.TextChoices):
        INVALID_CREDENTIALS = "INVALID_CREDENTIALS"  # aussi rate-limit (même 401)
        ACCOUNT_PENDING = "ACCOUNT_PENDING"  # AUTH-D hors AD non approuvé
        ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
        ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
        RATE_LIMITED = "RATE_LIMITED"
        DIRECTORY_UNAVAILABLE = "DIRECTORY_UNAVAILABLE"  # AUTH-13 AD timeout / down
        MFA_INVALID = "MFA_INVALID"  # AUTH-C TOTP / backup faux
        MFA_CHALLENGE_EXPIRED = "MFA_CHALLENGE_EXPIRED"  # AUTH-C mfa_token TTL
        DEVICE_COMPROMISED = "DEVICE_COMPROMISED"  # AUTH-E : install bannie
        DEVICE_JAILBROKEN = "DEVICE_JAILBROKEN"  # AUTH-E : mobile root + politique

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_events",
    )  # NULL si email inconnu
    device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_events",
    )  # NULL si échec (pas d’upsert device avant MDP OK)
    session = models.ForeignKey(
        Session,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_events",
    )  # renseigné seulement si succès
    email = models.CharField(max_length=254)  # identifiant tenté (email ou username AUTH-02)
    ip_address = models.GenericIPAddressField(null=True, blank=True, unpack_ipv4=True)
    country = models.CharField(max_length=64, null=True, blank=True)  # GeoIP async OK
    city = models.CharField(max_length=128, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    browser = models.CharField(max_length=64, null=True, blank=True)  # ua-parser, AUTH-01
    browser_version = models.CharField(max_length=32, null=True, blank=True)  # major.minor
    login_method = models.CharField(
        max_length=16, choices=LoginMethod.choices, default=LoginMethod.PASSWORD
    )
    success = models.BooleanField(db_index=True)
    suspicious = models.BooleanField(default=False)  # AUTH-29 1er UUID ; AUTH-I nouveau pays
    failure_reason = models.CharField(
        max_length=64,
        choices=FailureReason.choices,
        null=True,
        blank=True,
    )  # NULL si succès
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "login_history"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="login_hist_user_created_idx"),
            models.Index(fields=["email", "-created_at"], name="login_hist_email_created_idx"),
            models.Index(fields=["ip_address", "-created_at"], name="login_hist_ip_created_idx"),
        ]


class PasswordHistory(models.Model):
    """Anciens hash (politique anti-réemploi). 0 ligne AUTH-01."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_history"
    )
    password_hash = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "password_history"


class PasswordResetToken(models.Model):
    """Forgot-password. 0 ligne AUTH-01."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token_hash = models.TextField()  # lien / code hashé
    reset_channel = models.CharField(max_length=16, choices=ResetChannel.choices)
    requested_ip = models.GenericIPAddressField(null=True, blank=True, unpack_ipv4=True)
    user_agent = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)  # one-shot
    revoked_at = models.DateTimeField(null=True, blank=True)  # nouveau reset invalide l’ancien
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "password_reset_tokens"
        indexes = [
            models.Index(fields=["expires_at"], name="pwd_reset_expires_idx"),
        ]


class OtpSecret(models.Model):
    """TOTP obligatoire AUTH-C. enabled+verified_at = enroll fini. backup_codes = hash SHA-256."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otp_secret"
    )
    secret = models.BinaryField()  # chiffré côté appli
    algorithm = models.CharField(max_length=16, default="SHA1")  # RFC 6238
    digits = models.SmallIntegerField(default=6)
    period = models.SmallIntegerField(default=30)
    issuer = models.CharField(max_length=64, default="YAS Connect")  # QR authenticator
    backup_codes = models.JSONField(default=list, blank=True)
    enabled = models.BooleanField(default=False)  # True avec verified_at (enroll fini), pas une option user
    verified_at = models.DateTimeField(null=True, blank=True)  # 1er TOTP OK = enroll fini
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "otp_secrets"
        indexes = [
            GinIndex(fields=["backup_codes"], name="otp_backup_codes_gin"),
        ]


class EmailVerification(models.Model):
    """Confirmation d’adresse (inscription D04 ou changement AUTH-I)."""

    class Purpose(models.TextChoices):
        REGISTER = "REGISTER"
        EMAIL_CHANGE = "EMAIL_CHANGE"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verifications",
    )
    email = models.EmailField(max_length=254)  # adresse à confirmer
    token_hash = models.TextField(unique=True)  # SHA-256 du token clair (jamais le clair)
    purpose = models.CharField(
        max_length=16,
        choices=Purpose.choices,
        default=Purpose.REGISTER,
    )
    expires_at = models.DateTimeField()  # created_at + EMAIL_VERIFICATION_TTL_HOURS
    verified_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)  # resend / nouveau ticket
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_verifications"


class AuditLog(models.Model):
    """Journal d’audit haute volumétrie. 0 ligne AUTH-01. PK bigint (pas UUID)."""

    id = models.BigAutoField(primary_key=True)
    trace_id = models.UUIDField()  # corrélation requête (header ou généré)
    module = models.CharField(max_length=80)  # IAM, CHAT, …
    action = models.CharField(max_length=120)  # USER_DISABLE, …
    entity_type = models.CharField(max_length=80, null=True, blank=True)
    entity_id = models.UUIDField(null=True, blank=True)
    old_values = models.JSONField(null=True, blank=True)  # snapshot avant
    new_values = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, unpack_ipv4=True)
    severity = models.CharField(max_length=30)  # INFO / WARNING / CRITICAL
    success = models.BooleanField()  # les échecs aussi
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    device = models.ForeignKey(
        Device,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )  # NULL si job système

    class Meta:
        db_table = "audit_logs"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="audit_user_created_idx"),
            models.Index(fields=["module", "action"], name="audit_module_action_idx"),
            models.Index(fields=["entity_type", "entity_id"], name="audit_entity_idx"),
            GinIndex(fields=["old_values"], name="audit_old_values_gin"),
            GinIndex(fields=["new_values"], name="audit_new_values_gin"),
            GinIndex(fields=["metadata"], name="audit_metadata_gin"),
        ]
