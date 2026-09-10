import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    YAS_JWT_ACCESS_TTL_SECONDS=(int, 900),
    YAS_JWT_REFRESH_TTL_SECONDS=(int, 604800),
    YAS_LOGIN_ALLOW_USERNAME=(bool, True),
    LOGIN_RATE_LIMIT_ATTEMPTS=(int, 5),
    LOGIN_RATE_LIMIT_IP_ATTEMPTS=(int, 20),
    LOGIN_RATE_LIMIT_WINDOW_SECONDS=(int, 900),
    YAS_MFA_CHALLENGE_TTL_SECONDS=(int, 300),
    YAS_MFA_OTP_ATTEMPTS=(int, 5),
    YAS_MFA_OTP_WINDOW_SECONDS=(int, 900),
    YAS_MFA_BACKUP_COUNT=(int, 10),
    YAS_BLOCK_JAILBREAK=(bool, True),
    YAS_DEVICE_LINK_TTL_SECONDS=(int, 120),
    YAS_TOS_VERSION=(str, "2026-08-01"),
    YAS_TOS_URL=(str, "https://connect.yas.tg/legal/cgu/2026-08-01"),
    YAS_PASSWORD_HISTORY_N=(int, 5),
    YAS_PASSWORD_RESET_TTL_SECONDS=(int, 600),
    YAS_PASSWORD_FORGOT_RATE_LIMIT=(int, 3),
    YAS_PASSWORD_FORGOT_RATE_LIMIT_IP=(int, 10),
    YAS_PASSWORD_FORGOT_WINDOW_SECONDS=(int, 900),
    YAS_SESSION_IDLE_SECONDS=(int, 604800),
    YAS_SESSION_ABSOLUTE_SECONDS=(int, 2592000),
    YAS_SESSION_HEARTBEAT_MIN_SECONDS=(int, 60),
    YAS_LOCK_AFTER_FAILURES=(int, 5),
    YAS_LOCK_DURATION_SECONDS=(int, 1800),
    YAS_EMAIL_RESEND_RATE_LIMIT=(int, 3),
    YAS_EMAIL_RESEND_WINDOW_SECONDS=(int, 900),
    YAS_RBAC_CACHE_TTL_SECONDS=(int, 60),
)
environ.Env.read_env(BASE_DIR / ".env")
if os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["DATABASE_URL"].strip()

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "testserver"])

INSTALLED_APPS = [
    "django.contrib.admin",  # /admin/ lab (jour 2)
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",  # cookie staff uniquement, pas l’API
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "apps.core",
    "apps.iam",
    "apps.media",
    "apps.annuaire",
    "apps.config.apps.ConfigAppConfig",  # system_settings LDAP + jobs (pas .env)
]

AUTH_USER_MODEL = "iam.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",  # /admin/ seulement
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",  # formulaires admin ; API DRF csrf_exempt
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.iam.middlewares.compliance.ComplianceMiddleware",  # CGU puis wizard (JWT Bearer)
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Lome"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PASSWORD_HASHERS = [
    "apps.iam.helpers.hashers.YasArgon2PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.iam.middlewares.authentication.YasJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.iam.middlewares.permissions.HasPermission",
        "apps.iam.middlewares.compliance.ComplianceGates",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "YAS Connect API",
    "DESCRIPTION": "API interne YAS Connect",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "SORT_OPERATIONS": False,  # ordre = urlpatterns (parcours auth → me → admin)
    "TAGS": [
        {"name": "Santé", "description": "Liveness / base"},
        {
            "name": "Auth",
            "description": (
                "Login AUTH-A / LDAP / inscription / MFA AUTH-C / lien QR AUTH-J / "
                "MDP AUTH-G / logout AUTH-H"
            ),
        },
        {
            "name": "Me",
            "description": "Profil JWT AUTH-F : gates CGU + wizard ; sessions AUTH-H",
        },
        {
            "name": "Devices",
            "description": "Mes appareils AUTH-E + confirmer un lien QR AUTH-J",
        },
        {"name": "Admin", "description": "Approbation RH + reset MFA + appareils (rôle ADMIN)"},
        {"name": "Directory", "description": "Dropdowns publics inscription (régions / segments)"},
    ],
    "SECURITY": [{"bearerAuth": []}],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Access JWT (15 min). Login / MFA verify / refresh : pas de Bearer au facteur 1.",
            }
        }
    },
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = False

JWT_TOKEN_SECRET = env("JWT_TOKEN_SECRET")
YAS_JWT_ACCESS_TTL = env("YAS_JWT_ACCESS_TTL", default="15m")
YAS_JWT_ACCESS_TTL_SECONDS = env("YAS_JWT_ACCESS_TTL_SECONDS")
YAS_JWT_ISSUER = env("YAS_JWT_ISSUER", default="yas-connect")
YAS_JWT_ALGORITHM = "HS256"
YAS_JWT_REFRESH_TTL_SECONDS = env("YAS_JWT_REFRESH_TTL_SECONDS")
YAS_LOGIN_ALLOW_USERNAME = env("YAS_LOGIN_ALLOW_USERNAME")

LOGIN_RATE_LIMIT_ATTEMPTS = env("LOGIN_RATE_LIMIT_ATTEMPTS")
LOGIN_RATE_LIMIT_IP_ATTEMPTS = env("LOGIN_RATE_LIMIT_IP_ATTEMPTS")
LOGIN_RATE_LIMIT_WINDOW_SECONDS = env("LOGIN_RATE_LIMIT_WINDOW_SECONDS")

# AUTH-C : Fernet lab/tests par défaut (pas une clé prod). Prod : poser YAS_MFA_FERNET_KEY.
# Ne pas mettre le secret TOTP dans system_settings.
YAS_MFA_CHALLENGE_TTL_SECONDS = env("YAS_MFA_CHALLENGE_TTL_SECONDS")
YAS_MFA_OTP_ATTEMPTS = env("YAS_MFA_OTP_ATTEMPTS")
YAS_MFA_OTP_WINDOW_SECONDS = env("YAS_MFA_OTP_WINDOW_SECONDS")
YAS_MFA_BACKUP_COUNT = env("YAS_MFA_BACKUP_COUNT")
YAS_MFA_FERNET_KEY = env(
    "YAS_MFA_FERNET_KEY",
    default="nzTKKdyRvzn1yebJkYMvtBIEElklGp59BAjQYcLEkio=",
)
YAS_MFA_ISSUER = "YAS Connect"
# AUTH-E : 403 DEVICE_JAILBROKEN sur IOS/ANDROID si spec.jailbreak. WEB ignoré.
YAS_BLOCK_JAILBREAK = env("YAS_BLOCK_JAILBREAK")
# AUTH-J : TTL challenge QR 2ᵉ appareil (cache). Prod multi-workers = Redis.
YAS_DEVICE_LINK_TTL_SECONDS = env("YAS_DEVICE_LINK_TTL_SECONDS")
# AUTH-F : version CGU en vigueur (bump → re-accept, wizard non rejoué).
YAS_TOS_VERSION = env("YAS_TOS_VERSION")
YAS_TOS_URL = env("YAS_TOS_URL")
# AUTH-G : anti-réemploi, TTL ticket reset, rate-limit forgot (jamais 429).
YAS_PASSWORD_HISTORY_N = env("YAS_PASSWORD_HISTORY_N")
YAS_PASSWORD_RESET_TTL_SECONDS = env("YAS_PASSWORD_RESET_TTL_SECONDS")
YAS_PASSWORD_FORGOT_RATE_LIMIT = env("YAS_PASSWORD_FORGOT_RATE_LIMIT")
YAS_PASSWORD_FORGOT_RATE_LIMIT_IP = env("YAS_PASSWORD_FORGOT_RATE_LIMIT_IP")
YAS_PASSWORD_FORGOT_WINDOW_SECONDS = env("YAS_PASSWORD_FORGOT_WINDOW_SECONDS")
# AUTH-H : idle 7 j, plafond session 30 j (pas le TTL access 15 min), debounce heartbeat.
YAS_SESSION_IDLE_SECONDS = env("YAS_SESSION_IDLE_SECONDS")
YAS_SESSION_ABSOLUTE_SECONDS = env("YAS_SESSION_ABSOLUTE_SECONDS")
YAS_SESSION_HEARTBEAT_MIN_SECONDS = env("YAS_SESSION_HEARTBEAT_MIN_SECONDS")
# AUTH-I : lock auto N échecs / TTL ; resend change-email 429 (pas le resend inscription).
YAS_LOCK_AFTER_FAILURES = env("YAS_LOCK_AFTER_FAILURES")
YAS_LOCK_DURATION_SECONDS = env("YAS_LOCK_DURATION_SECONDS")
YAS_EMAIL_RESEND_RATE_LIMIT = env("YAS_EMAIL_RESEND_RATE_LIMIT")
YAS_EMAIL_RESEND_WINDOW_SECONDS = env("YAS_EMAIL_RESEND_WINDOW_SECONDS")
YAS_RBAC_CACHE_TTL_SECONDS = env("YAS_RBAC_CACHE_TTL_SECONDS")

# Vide = skip envoi (lab). Mailhog plus tard ; verify-email ne bloque pas.
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@yas.tg")
EMAIL_VERIFICATION_TTL_HOURS = 48

REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "KEY_PREFIX": "yas",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "yas-connect-local",
        }
    }
