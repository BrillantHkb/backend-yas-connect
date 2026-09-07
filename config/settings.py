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
)
environ.Env.read_env(BASE_DIR / ".env")
if os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["DATABASE_URL"].strip()

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost"])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
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

PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
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
