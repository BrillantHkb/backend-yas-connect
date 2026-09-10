# Plan A→Z — Application YAS Connect (future)

**Statut :** spécification uniquement. L’application n’existe pas encore.  
**Hors périmètre :** toute modification de `backend-gestion-personnel-yas` (login HR `email1` / bcrypt).  
**Backend figé :** Python + Django + **Django REST Framework**.  
**Objectif MVP :** socle **exécutable** (IAM → picker → PJ → chat → notif → appel 1-1). Pas un 6ᵉ module (Social / Canaux / IA).  
**Chiffrement (figé) :** [CRYPTO-00](crypto_plans/CRYPTO-00-modele-chiffrement.md) · [CRYPTO-A](crypto_plans/CRYPTO-A-cles.md).  
**Notifications :** [notif_plans/](notif_plans/).  
**Détail connexion locale (AUTH-01 … 12) :** [AUTH-A-connexion-locale.md](iam_plans/AUTH-A-connexion-locale.md).  
**Inscription :** [AUTH-D-inscription.md](iam_plans/AUTH-D-inscription.md).  
**Catalogue des routes IAM :** [IAM-routes.md](iam_plans/IAM-routes.md).  
**Plans Annuaire :** [annuaire_plans/](annuaire_plans/).  
**Créer le repo (jour 0) :** [00-creer-le-projet.md](00-creer-le-projet.md) — versions, venv, PostgreSQL, checklist `/health`.

Ce document décrit **chaque étape du socle**, y compris les plus petites, et **comment chaque bibliothèque est installée, configurée et branchée**. Le code ci-dessous est à copier tel quel au moment de créer le repo. Le **parcours condensé** (quoi installer, dans quel ordre) est dans [00-creer-le-projet.md](00-creer-le-projet.md).

---

## 1. Qu’est-ce que YAS Connect

Application de **messagerie / collaboration interne** (type WhatsApp / Teams allégé) pour YAS :

- IAM (identités, sessions, rôles, MFA)
- Annuaire (picker), messagerie, **notifications**, médias, appels
- Social, canaux, télécom, IA : **après** que message + appel sonnent app fermée et que les PJ uploadent sans mentir sur scan / chiffrement

Schéma cible : catalogues IAM / Annuaire / Médias / Config / Messagerie / Appels / **Notifications** ([catalogues/](../catalogues/)). AUTH-A migre les **16 tables IAM** + **5 Annuaire** + `media_files`. AUTH-B ajoute `apps.config` et `users.ldap_dn`.

---



## 2. Décisions d’architecture (figées)


| Sujet              | Choix                                             | Pourquoi                                                                                                        |
| ------------------ | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Produit            | Repo dédié `backend-yas-connect`                  | Pas de mélange avec le SIRH Node                                                                                |
| API                | REST `/api/v1/*`                                  | Versionnée dès le jour 0                                                                                        |
| WS                 | Django Channels **plus tard**                     | Hors AUTH-01                                                                                                    |
| Runtime            | Python 3.12+ / Django 5.2                         | LTS, DRF mature                                                                                                 |
| API layer          | `djangorestframework`                             | Serializers, views, auth classes                                                                                |
| ORM                | Django ORM + PostgreSQL 16                        | Migrations natives                                                                                              |
| Driver PG          | `psycopg[binary]` (v3)                            | Driver actuel Django 5.2                                                                                        |
| Mots de passe      | Argon2id via `argon2-cffi`                        | Hasher Django, pas bcrypt                                                                                       |
| JWT                | `PyJWT` (HS256) access ; refresh **opaque hashé** | `jti` access = `sessions.access_jti`. **Pas** `simplejwt`. |
| OpenAPI            | `drf-spectacular`                                 | Schéma généré depuis les serializers                                                                            |
| Env                | `django-environ`                                  | `.env` typé (`Env()`)                                                                                           |
| CORS               | `django-cors-headers`                             | Front futur (mobile / web)                                                                                      |
| Cache / rate-limit | cache Django : LocMem puis Redis (`django-redis`) | Même API `caches["default"]`                                                                                    |
| Tests              | `pytest` + `pytest-django`                        | `APIClient` DRF                                                                                                 |
| Lint               | `ruff`                                            | Format + lint, un seul outil                                                                                    |
| Front              | Hors ce plan                                      | Consomme `/api/v1`                                                                                              |
| Chiffrement        | [CRYPTO-00](crypto_plans/CRYPTO-00-modele-chiffrement.md) | 1-to-1 = E2E Signal ; groupes = cloud (Telegram) — serveur ne lit **jamais** le 1-to-1 |
| Scan antivirus     | Lab = `SKIPPED` ; staging/prod = ClamAV           | MEDIA-A ne ment pas : pas de `CLEAN` sans scanner |
| SMTP               | Lab = Mailhog ; métier MVP = **AD-only**          | Verify-email non bloquant ; hors AD = pending RH ; forgot = TOTP (AUTH-G) |


**Ne pas** monter YAS Connect dans le projet SIRH.

---



## 3. Phase 0 — Socle (jour 0), étape par étape

**Guide condensé (créer le repo, versions, DB) :** [00-creer-le-projet.md](00-creer-le-projet.md). Ci-dessous : fichiers à coller.

Objectif : un projet Django qui démarre, parle à PostgreSQL, expose `/health` et `/api/docs`, **sans encore de login**.

### 3.0. Prérequis machine

1. Installer **Python 3.12 ou 3.13** (`python --version`).
2. Installer **Git**.
3. Installer **Docker Desktop** (PostgreSQL + Redis en local).
4. Vérifier : `docker --version`, `git --version`.
5. **Ne pas** réutiliser la base du SIRH. Créer une base neuve `yas_connect`.



### 3.1. Créer le dossier et Git

```powershell
mkdir E:\iSOCProjects\backend-yas-connect
cd E:\iSOCProjects\backend-yas-connect
git init
```

Créer `.gitignore` **avant** tout commit :

```gitignore
.venv/
__pycache__/
*.py[cod]
*.sqlite3
.env
.pytest_cache/
.ruff_cache/
htmlcov/
.coverage
staticfiles/
media/
*.egg-info/
dist/
build/
```



### 3.2. Environnement virtuel

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Sans venv activé, **ne pas** installer les paquets (pollution du Python système).

### 3.3. Fichier de dépendances — `requirements/base.txt`

Créer `requirements/base.txt`, `requirements/dev.txt`, `requirements/prod.txt`.  
**Gestion :** un fichier par environnement ; `dev.txt` inclut `base.txt` via `-r`. Pas de `package.json`. Pas de Poetry obligatoire (pip + venv suffit).

`requirements/base.txt` :

```text
django>=5.2,<6.0
djangorestframework>=3.15,<3.17
drf-spectacular>=0.28,<0.29
psycopg[binary]>=3.2,<4.0
argon2-cffi>=23.1,<26.0
PyJWT>=2.9,<3.0
django-environ>=0.11,<0.13
django-cors-headers>=4.6,<5.0
django-redis>=5.4,<6.0
ua-parser>=0.18,<1.0
```

`requirements/dev.txt` :

```text
-r base.txt
pytest>=8.3,<9.0
pytest-django>=4.9,<5.0
ruff>=0.8,<0.15
```

`requirements/prod.txt` :

```text
-r base.txt
gunicorn>=23.0,<24.0
```

Installation :

```powershell
pip install -r requirements\dev.txt
pip freeze > requirements\lock.txt
```

`lock.txt` est optionnel au jour 0 ; le figer avant le premier déploiement.

#### Rôle de chaque lib (intégration)


| Lib                        | Où elle se branche                   | Ce qu’elle fait                                      |
| -------------------------- | ------------------------------------ | ---------------------------------------------------- |
| `django`                   | `manage.py`, `config/`               | Framework, ORM, settings, migrations                 |
| `djangorestframework`      | `INSTALLED_APPS` + `REST_FRAMEWORK`  | API JSON, serializers, `APIView`                     |
| `drf-spectacular`          | `INSTALLED_APPS` + urls schema/docs  | Génère OpenAPI 3 depuis les vues DRF                 |
| `psycopg[binary]`          | `DATABASES["default"]["ENGINE"]`     | Driver PostgreSQL (wheels Windows)                   |
| `argon2-cffi`              | `PASSWORD_HASHERS`                   | Implémentation Argon2id ; Django l’appelle tout seul |
| `PyJWT`                    | `apps.iam.services.token_service`    | Encode / décode le JWT (pas un app Django)           |
| `django-environ`           | tout en haut de `config/settings.py` | Lit `.env` → `env("VAR")`                            |
| `django-cors-headers`      | `INSTALLED_APPS` + middleware        | En-têtes CORS pour le front                          |
| `django-redis`             | `CACHES` si `REDIS_URL`              | Backend cache Redis                                  |
| `ua-parser`                | `apps.iam.services.auth_service`     | Parse User-Agent → `browser` / `browser_version`     |
| `pytest` / `pytest-django` | `pytest.ini`                         | Lance les tests avec Django chargé                   |
| `ruff`                     | `pyproject.toml` `[tool.ruff]`       | Lint + format                                        |




### 3.4. Créer le projet Django (package `config`)

À la racine `backend-yas-connect/` :

```powershell
django-admin startproject config .
```

Cela produit :

```
backend-yas-connect/
  manage.py
  config/
    __init__.py
    settings.py
    urls.py
    asgi.py
    wsgi.py
```

Vérifier : `python manage.py check` (échoue tant que la DB n’est pas configurée — normal).

### 3.5. Layout des apps (dossier `apps/`)

Django cherche les apps par **dotted path**. On isole le métier sous `apps/` pour ne pas mélanger avec `config/`.

```powershell
mkdir apps
New-Item apps\__init__.py -ItemType File
```

Plus tard, chaque module :

```powershell
python manage.py startapp iam apps/iam
```

Puis dans `apps/iam/apps.py` :

```python
class IamConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"  # PK par défaut
    name = "apps.iam"  # chemin Python (INSTALLED_APPS)
    label = "iam"  # AUTH_USER_MODEL = "iam.User"
    verbose_name = "IAM"
```

`INSTALLED_APPS` utilisera `"apps.iam"` (le `name`), jamais `"iam"` seul.

Structure cible après Phase 0 + AUTH-01 :

```
backend-yas-connect/
  manage.py
  pytest.ini
  pyproject.toml          # ruff uniquement
  .env.example
  .env                    # gitignored
  docker-compose.yml
  requirements/
    base.txt
    dev.txt
    prod.txt
  config/
    __init__.py
    settings.py
    urls.py
    asgi.py
    wsgi.py
  apps/
    __init__.py
    iam/                  # AUTH-01 — catalogue IAM
    media/                # AUTH-01 — media_files (0 ligne)
    annuaire/            # AUTH-01 — 5 tables annuaire (0 ligne)
    core/                 # health, exceptions API (Phase 0)
  tests/
```

Créer l’app `core` dès la Phase 0 (healthcheck, exception handler) :

```powershell
python manage.py startapp core apps/core
```

Ajuster `apps/core/apps.py` : `name = "apps.core"`, `label = "core"`.

### 3.6. Fichiers d’environnement

`.env.example` (commité) :

```env
DJANGO_SECRET_KEY=change-me-generate-with-python
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://yas:yas@127.0.0.1:5432/yas_connect
REDIS_URL=
JWT_TOKEN_SECRET=change-me-32-bytes-min
YAS_JWT_ACCESS_TTL=15m
YAS_JWT_ACCESS_TTL_SECONDS=900
YAS_JWT_ISSUER=yas-connect
YAS_JWT_REFRESH_TTL_SECONDS=604800
YAS_LOGIN_ALLOW_USERNAME=true
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
LOGIN_RATE_LIMIT_ATTEMPTS=5
LOGIN_RATE_LIMIT_IP_ATTEMPTS=20
LOGIN_RATE_LIMIT_WINDOW_SECONDS=900
# --- lus à MEDIA-A / CRYPTO-A / APPELS-C / AUTH-D (vides = no-op lab) ---
CRYPTO_MASTER_KEY=
MINIO_ENDPOINT=http://127.0.0.1:9000
MINIO_ACCESS_KEY=yas
MINIO_SECRET_KEY=yasminio12
MINIO_BUCKET=yas-connect
LIVEKIT_URL=http://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
EMAIL_HOST=127.0.0.1
EMAIL_PORT=1025
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
FCM_SERVER_KEY=
APNS_KEY_PATH=
CLAMAV_HOST=
```

Copier vers `.env` (non commité) et **changer** `DJANGO_SECRET_KEY` et `JWT_TOKEN_SECRET` :

```powershell
Copy-Item .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

`JWT_TOKEN_SECRET` **≠** `DJANGO_SECRET_KEY` : rotation JWT indépendante des sessions Django (on n’utilise pas le cookie session Django pour l’API).

### 3.7. `config/settings.py` — intégration de toutes les libs

Remplacer le `settings.py` généré. `django-environ` se charge **en premier**.

```python
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent  # racine du projet (manage.py)

env = environ.Env(
    DJANGO_DEBUG=(bool, False),  # prod = false si la var manque
    YAS_JWT_ACCESS_TTL_SECONDS=(int, 900),  # 15 min
    YAS_JWT_REFRESH_TTL_SECONDS=(int, 604800),
    YAS_LOGIN_ALLOW_USERNAME=(bool, True),
    LOGIN_RATE_LIMIT_ATTEMPTS=(int, 5),
    LOGIN_RATE_LIMIT_IP_ATTEMPTS=(int, 20),
    LOGIN_RATE_LIMIT_WINDOW_SECONDS=(int, 900),
)
environ.Env.read_env(BASE_DIR / ".env")  # charge .env sans l’écraser si déjà exporté

SECRET_KEY = env("DJANGO_SECRET_KEY")  # cookies / CSRF Django ; ≠ JWT_TOKEN_SECRET
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost"])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",       # obligatoire pour les hashers Argon2
    "django.contrib.staticfiles",
    "django.contrib.postgres",   # GinIndex (jsonb + pg_trgm)
    "rest_framework",            # DRF
    "drf_spectacular",           # OpenAPI
    "corsheaders",               # CORS
    "apps.core",
    "apps.iam",                  # commenter tant que l’app n’existe pas
    "apps.media",                # AUTH-01 : media_files, 0 ligne
    "apps.annuaire",            # AUTH-01 : 5 tables annuaire, 0 ligne
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # le plus haut possible après Security
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
    "default": env.db("DATABASE_URL"),  # parse postgres://…
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True  # 1 requête HTTP = 1 transaction

AUTH_USER_MODEL = "iam.User"  # dès la 1re migration iam ; ne plus changer ensuite

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Lome"
USE_I18N = True
USE_TZ = True  # DateTimeField en UTC en base

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Mots de passe : Argon2id uniquement (argon2-cffi) ---
PASSWORD_HASHERS = [
    "apps.iam.hashers.YasArgon2PasswordHasher",  # m=65536,t=3,p=1
    # fallback lecture seule si un hash Django standard existait (aucun au jour 0)
    "django.contrib.auth.hashers.Argon2PasswordHasher",
]

# --- DRF ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.iam.authentication.YasJWTAuthentication",  # Bearer + session DB
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",  # login = AllowAny explicite
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",  # pas de browsable API
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "UNAUTHENTICATED_USER": None,  # request.user = None si pas de JWT (pas AnonymousUser)
}

# --- OpenAPI (drf-spectacular) ---
SPECTACULAR_SETTINGS = {
    "TITLE": "YAS Connect API",
    "DESCRIPTION": "API interne YAS Connect",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
}

# --- CORS ---
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = False  # JWT dans Authorization, pas de cookie

# --- JWT applicatif (PyJWT, pas simplejwt) ---
JWT_TOKEN_SECRET = env("JWT_TOKEN_SECRET")  # HS256 ; rotation indépendante de SECRET_KEY
YAS_JWT_ACCESS_TTL = env("YAS_JWT_ACCESS_TTL", default="15m")  # doc / logs
YAS_JWT_ACCESS_TTL_SECONDS = env("YAS_JWT_ACCESS_TTL_SECONDS")  # claim exp
YAS_JWT_ISSUER = env("YAS_JWT_ISSUER", default="yas-connect")
YAS_JWT_ALGORITHM = "HS256"  # unique ; jamais “none”
YAS_JWT_REFRESH_TTL_SECONDS = env("YAS_JWT_REFRESH_TTL_SECONDS")
YAS_LOGIN_ALLOW_USERNAME = env("YAS_LOGIN_ALLOW_USERNAME")

LOGIN_RATE_LIMIT_ATTEMPTS = env("LOGIN_RATE_LIMIT_ATTEMPTS")
LOGIN_RATE_LIMIT_IP_ATTEMPTS = env("LOGIN_RATE_LIMIT_IP_ATTEMPTS")
LOGIN_RATE_LIMIT_WINDOW_SECONDS = env("LOGIN_RATE_LIMIT_WINDOW_SECONDS")

# --- Cache : LocMem si pas de Redis, sinon django-redis ---
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
            "KEY_PREFIX": "yas",  # isole les clés vs autres apps sur le même Redis
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",  # 1 process
            "LOCATION": "yas-connect-local",
        }
    }
```

**Ordre d’activation AUTH-01 :** commenter `apps.iam`, `AUTH_USER_MODEL` et les classes `apps.iam.`* **tant que** l’app `iam` n’existe pas. Décommenter **avant** la première `makemigrations` iam.

Phase 0 minimale (health seulement) : retirer `apps.iam`, `AUTH_USER_MODEL`, `YasJWTAuthentication`, hasher custom. Utiliser :

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],  # Phase 0 : pas encore YasJWTAuthentication
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "UNAUTHENTICATED_USER": None,
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]  # hasher YAS dès AUTH-01
```

Puis basculer vers le bloc complet au début d’AUTH-01.

**Pourquoi** `django.contrib.auth` **sans** `sessions` **/** `admin` **:** on n’utilise pas le login cookie Django ni l’admin au jour 0. `contrib.auth` reste **nécessaire** pour `PASSWORD_HASHERS` et `AUTH_USER_MODEL`.

**Pourquoi pas** `django.contrib.sessions` **:** l’API est stateless + table `sessions` métier (AUTH-01), distincte de `django_session`.

### 3.8. Docker Compose — PostgreSQL + Redis + lab (MinIO, LiveKit, Mailhog)

`docker-compose.yml` :

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: yas
      POSTGRES_PASSWORD: yas
      POSTGRES_DB: yas_connect
    ports:
      - "5432:5432"
    volumes:
      - yas_connect_pg:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U yas -d yas_connect"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: yas
      MINIO_ROOT_PASSWORD: yasminio12
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - yas_connect_minio:/data

  livekit:
    image: livekit/livekit-server:latest
    command: --dev --bind 0.0.0.0
    ports:
      - "7880:7880"
      - "7881:7881"
      - "7882:7882/udp"

  mailhog:
    image: mailhog/mailhog:latest
    ports:
      - "1025:1025"   # SMTP
      - "8025:8025"   # UI

  clamav:
    image: clamav/clamav:latest
    profiles: ["scan"]   # pas au `up` lab (scan = SKIPPED). Staging : --profile scan
    ports:
      - "3310:3310"

volumes:
  yas_connect_pg:
  yas_connect_minio:
```

Démarrer (lab, **sans** ClamAV) :

```powershell
docker compose up -d
docker compose ps
```

ClamAV (staging) : `docker compose --profile scan up -d`.

Vérifier PostgreSQL : `docker compose exec db psql -U yas -d yas_connect -c '\conninfo'`

`DATABASE_URL` local : `postgres://yas:yas@127.0.0.1:5432/yas_connect`  
Redis optionnel AUTH-01 : laisser `REDIS_URL` vide (LocMem). Pour l’activer : `REDIS_URL=redis://127.0.0.1:6379/0`.  
Mailhog UI : `http://127.0.0.1:8025`. MinIO console : `http://127.0.0.1:9001`.

**Gestion Redis :** `django-redis` n’est importé que si `REDIS_URL` est non vide (branche `if` dans settings). Pas de connexion Redis au boot sinon.

### 3.9. Healthcheck — `apps/core`

`apps/core/views.py` :

```python
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes = []  # public, même après AUTH-01
    permission_classes = [AllowAny]

    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")  # ping PostgreSQL
        except Exception:
            db_ok = False
        status = 200 if db_ok else 503
        return Response(
            {"success": True, "data": {"status": "ok" if db_ok else "degraded", "db": db_ok}},
            status=status,
        )
```

`apps/core/urls.py` :

```python
from django.urls import path

from apps.core.views import HealthView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),  # GET /health
]
```



### 3.10. Enveloppe d’erreur API — `apps/core/exceptions.py`

DRF appelle `EXCEPTION_HANDLER` pour toute exception non catchée. On uniformise `{success, code, message}`.

```python
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response
from rest_framework import status


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)  # None si exception non-DRF
    if response is None:
        return Response(
            {
                "success": False,
                "code": "INTERNAL_ERROR",
                "message": "Une erreur interne est survenue.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code = "ERROR"
    message = "Requête invalide."
    data = response.data
    if isinstance(data, dict):
        if "detail" in data:
            message = str(data["detail"])
            code = getattr(data["detail"], "code", "ERROR")  # code DRF (not_authenticated, …)
            if hasattr(code, "upper"):
                code = str(code).upper()
        elif data:
            message = "Données invalides."
            code = "VALIDATION_ERROR"  # serializer.is_valid(raise_exception=True)

    response.data = {
        "success": False,
        "code": code,
        "message": message,
        "errors": data if isinstance(data, dict) and "detail" not in data else None,
    }
    return response
```

Les erreurs métier AUTH-01 (`INVALID_CREDENTIALS`, etc.) sont renvoyées **explicitement** par la vue, pas via ce handler.

### 3.11. URLs racine + OpenAPI

`config/urls.py` :

```python
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("health", include("apps.core.urls")),  # GET /health
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),  # OpenAPI JSON
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/auth/", include("apps.iam.urls")),  # AUTH-01 ; commenter avant
]
```

**Intégration spectacular :**

1. App dans `INSTALLED_APPS`.
2. `DEFAULT_SCHEMA_CLASS` dans `REST_FRAMEWORK`.
3. Deux routes : JSON OpenAPI (`/api/schema/`) et UI Swagger (`/api/docs/`).
4. Sur chaque vue métier : décorateur `@extend_schema` (voir AUTH-01).

Pas de `yasg` / `coreapi`. Spectacular uniquement.

### 3.12. Ruff — `pyproject.toml`

```toml
[tool.ruff]
target-version = "py312"
line-length = 100
src = ["apps", "config", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.ruff.lint.per-file-ignores]
"apps/*/migrations/*" = ["E501"]
```

Usage : `ruff check .` et `ruff format .`. Pas de Black + isort séparés.

### 3.13. Pytest — `pytest.ini`

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py
addopts = -q --reuse-db
```

Créer `tests/conftest.py` (fixtures AUTH-01 dans le plan IAM).  
Lancer : `pytest`.  
Django Test DB : pytest-django crée `test_yas_connect` à partir de `DATABASE_URL`.

### 3.14. Première migration (contrib seulement)

Tant que `AUTH_USER_MODEL` n’est pas posé :

```powershell
python manage.py migrate
python manage.py runserver 8000
```

Vérifier :

- `GET http://127.0.0.1:8000/health` → `{"success": true, "data": {"status": "ok", "db": true}}`
- `GET http://127.0.0.1:8000/api/docs/` → UI Swagger vide de routes métier

**Dès AUTH-01 :** `AUTH_USER_MODEL = "iam.User"` **avant** toute migration `auth`. Si `migrate` a déjà créé `auth_user`, **recréer la base** (base neuve, c’est le jour 0) :

```powershell
docker compose down -v
docker compose up -d
python manage.py migrate
```

Ne jamais changer `AUTH_USER_MODEL` après des migrations de prod.

### 3.15. Checklist Phase 0

- [ ] Repo `E:\iSOCProjects\backend-yas-connect` + Git + `.gitignore`
- [ ] venv + `requirements/dev.txt` installé
- [ ] `.env` présent, secrets générés
- [ ] PostgreSQL up via Docker
- [ ] `python manage.py check` OK
- [ ] `GET /health` 200
- [ ] `GET /api/docs/` s’affiche
- [ ] `ruff check .` vert
- [ ] `pytest` vert (même sans tests métier)

---



## 4. Ordre de livraison (modules)

Le métier IAM → Annuaire-A → Messagerie → Médias → Appels est **rédigé**. Le blocage de fermeture MVP = **ordre** + **transverses** (crypto, notif, scan, mail).  
**MEDIA-A avant / avec MESSAGERIE-B** (PJ, avatars). **CRYPTO-A avant** MESSAGERIE-B (bundles). **NOTIF-A avant** MSG-67 et CALL-44.

### 4.1 Chemin MVP « ça sonne / ça uploade »

| Phase | App Django | Premier ticket | Tables / notes |
|-------|------------|----------------|----------------|
| 0 | `apps.core` | Socle | aucune métier |
| 1 | `apps.iam` + `apps.media` + `apps.annuaire` | **AUTH-A** (01–12) | 16 tables IAM + `media_files` + 5 Annuaire. Login local : devices, sessions, refresh, history. |
| 1b | `apps.config` + IAM + seed annuaire min | **AUTH-D puis AUTH-B** | `ldap_service` + inscription (`register/ad` = seul JIT) **puis** `login/ldap` + job AUTH-16. Pas de seed user AD. Seed régions TG + segment `YAS`. JWT encore sans OTP. |
| 1c | `apps.iam` | **AUTH-C** (19–24) | `otp_secrets`. TOTP obligatoire chaque login **et** après `register/ad`. Lab : [00-jour-4-auth-c.md](00-jour-4-auth-c.md) **clos**. |
| 1e | `apps.iam` | **AUTH-E** (27–36) | `devices` : liste, **push_token**, trusted, jailbreak. Lab : [00-jour-5-auth-e.md](00-jour-5-auth-e.md) **clos**. |
| 1e2 | `apps.iam` | **AUTH-J** (67–69) | QR 2ᵉ appareil + TOTP Authenticator. Cache Redis, 0 table. Lab : [00-jour-6-auth-j.md](00-jour-6-auth-j.md) **clos**. |
| 1f | `apps.iam` | **AUTH-F** (37–42) | CGU + wizard. Lab : [00-jour-7-auth-f.md](00-jour-7-auth-f.md) **clos**. |
| 1g | `apps.iam` | **AUTH-G** (43–50) | MDP app (change + forgot TOTP). Lab : [00-jour-8-auth-g.md](00-jour-8-auth-g.md) **clos**. |
| 1h | `apps.iam` | **AUTH-H** (51–60) | Sessions / logout / idle. Lab : [00-jour-9-auth-h.md](00-jour-9-auth-h.md) **clos**. |
| 1i | `apps.iam` | **AUTH-I** (61–66) | Historique / lock. Lab : [00-jour-10-auth-i.md](00-jour-10-auth-i.md) **clos**. |
| 1j | `apps.iam` | **AUTH-R** | Seed USER/ADMIN, `HasPermission`. Lab : [00-jour-11-auth-r.md](00-jour-11-auth-r.md). |
| 1k | `apps.iam` | **ADMIN-A** | Lifecycle, audit, `region`. Lab : [00-jour-12-admin-a.md](00-jour-12-admin-a.md) (après jour 11). |
| 2 | `apps.iam` + `apps.media` | **PROF-A** | `/me`, avatar (scan SKIPPED lab). |
| 2b–2c | `apps.iam` | **PROF-B / PROF-C** | Prefs + privacy. |
| 2d | `apps.iam` + `apps.realtime` | **PRES-A** | Présence Redis + WS. |
| 2e | `apps.iam` + `apps.annuaire` | **ANNUAIRE-A** | People-picker `GET /users`. Seed types + `YAS` **déjà** jour 3 (AUTH-D). |
| **2x** | — | **[CRYPTO-00](crypto_plans/CRYPTO-00-modele-chiffrement.md)** | Décision 1 page. **0 table.** Clés HTTP = phase **3c**. |
| **3a** | `apps.media` | **MEDIA-R + MEDIA-A** | Seed `media.*` + upload MinIO (PJ, avatars) **avant** les messages. |
| **3b** | `apps.notifications` | **NOTIF-R + NOTIF-A** | 2 tables ; in-app + push ; events message/appel. |
| **3c** | `apps.crypto` | **CRYPTO-R + CRYPTO-A** | Bundles Signal / appareil + `conversation_keys` (GROUP). |
| **3d** | `apps.messaging` | **MESSAGERIE-R, A, B** | Inbox + 1-to-1 + PJ. Gardes `CRYPTO_*_MISSING`. |
| **3e** | `apps.messaging` | **MESSAGERIE-C, D** | Groupes (`ensure_conversation_key`) + WS + MSG-67 → NOTIF. |
| **3f** | `apps.messaging` | **MESSAGERIE-E (partiel), F (blocage), G** | Emoji, transfert, sondage, favoris ; bloquer ; « en train d’écrire ». |
| **4a** | `apps.media` | **MEDIA-B, C, D, E** | Album / thumbs ; transcodage vidéo ; vocal + dictée STT ; GED (coffre documents). |
| **5a** | `apps.calls` | **APPELS-R, A, B, C** | Appel 1-1 LiveKit + hook CALL-44 → NOTIF (`IN_MEETING`). |
| **5b** | `apps.calls` | **APPELS-D, E, G** | Partage d’écran ; enregistrement MinIO ; CR + STT/résumé auto. |

Critère de fermeture MVP : **message + appel sonnent app fermée** ; **PJ uploadent** avec `scan_status` honnête (`SKIPPED` ou ClamAV, jamais `CLEAN` fantôme).  
Inventaire fonctions (à quoi chacune sert) : [MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md).

### 4.2 Après le MVP sonnant (plans déjà rédigés, pas le chemin critique)

| Phase | Ticket | Commentaire |
|-------|--------|-------------|
| 3g | MESSAGERIE-E reste | Mentions, localisation, épingles message, type IA — **après** |
| 3h | MESSAGERIE-F reste | Signalement / file modération — **après** |
| 4f | MEDIA-F | Quotas admin / audit accès — **après** |
| 5c | APPELS-F | QoS 90 j — **après** |
| 2f–2h | ANNUAIRE-B, C, D | Arbre RH, affectations, skills — **après** chat/appel |
| 6 | **CONFIG-A** | Rate-limits messages/appels, flags — après NOTIF |
| — | Social / Canaux / IA | **Interdit** tant que le MVP sonnant n’est pas vrai |
| — | Rétention / RGPD | **Après** |

### 4.3 Transverses figés (scan & mail)

| Sujet | Lab / dev | Staging / prod |
|-------|-----------|----------------|
| Antivirus (MEDIA-A MED-05) | Worker **absent** → `scan_status=SKIPPED` (pas `CLEAN`) | **ClamAV** : `PENDING` → `CLEAN` \| `INFECTED` |
| SMTP | **Mailhog** (catch-all, AUTH-D04 verify-email optionnel) | SMTP réel **ou** désactiver l’envoi : activation métier = **AD + MFA** ; hors AD = **pending RH** (pas de mail bloquant) |
| Forgot password | TOTP (AUTH-G) — **aucun** mail | idem |

Chaque module = une **app Django** `apps/<nom>/` (`models`, `serializers`, `views`, `urls`, `services`, `tests`). **Pas de mélange avec le SIRH.**


**Ordre de code des 86 routes IAM** (vagues 1→16 + 4b) : [IAM-routes.md](iam_plans/IAM-routes.md).  
**Ordre de code des 38 routes Annuaire** (A→D) : [ANNUAIRE-routes.md](annuaire_plans/ANNUAIRE-routes.md).  
**Ordre de code des 6 routes Notifications** (R, A) : [NOTIF-routes.md](notif_plans/NOTIF-routes.md).  
**Ordre de code des 6 routes Crypto** (R, A) : [CRYPTO-routes.md](crypto_plans/CRYPTO-routes.md).  
**Ordre de code des 52 routes Messagerie** (R, A→G) : [MESSAGERIE-routes.md](messaging_plans/MESSAGERIE-routes.md).  
**Ordre de code des 34 routes Médias** (R, A→F) : [MEDIA-routes.md](media_plans/MEDIA-routes.md).  
**Ordre de code des 36 routes Appels** (R, A→G) : [APPELS-routes.md](calls_plans/APPELS-routes.md).

---



## 5. Modèles — les catalogues font foi

Attributs, types, contraintes, « renseigné par » : **uniquement** les fichiers [catalogues/](../catalogues/).

| Catalogue | App | AUTH-A |
|-----------|-----|---------|
| [IAM-catalogue-tables.md](../catalogues/IAM-catalogue-tables.md) | `apps.iam` | 16 tables (+ `ldap_dn` sur `users`) ; [code/iam_models.py](code/iam_models.py) |
| [CONFIG-catalogue-tables.md](../catalogues/CONFIG-catalogue-tables.md) | `apps.config` | AUTH-B ; [code/config_models.py](code/config_models.py) |
| [MEDIA-catalogue-tables.md](../catalogues/MEDIA-catalogue-tables.md) | `apps.media` | 10 tables, 0 ligne ; [code/media_models.py](code/media_models.py) ; plans [media_plans/](media_plans/) |
| [ANNUAIRE-catalogue-tables.md](../catalogues/ANNUAIRE-catalogue-tables.md) | `apps.annuaire` | 5 tables ; seed ANNUAIRE-A ; [code/annuaire_models.py](code/annuaire_models.py) |
| [MESSAGERIE-catalogue-tables.md](../catalogues/MESSAGERIE-catalogue-tables.md) | `apps.messaging` | Phase 3d ; 18 tables ; [code/messaging_models.py](code/messaging_models.py) ; plans [messaging_plans/](messaging_plans/) |
| [APPELS-catalogue-tables.md](../catalogues/APPELS-catalogue-tables.md) | `apps.calls` | Phase 5a ; 9 tables MVP (+ `webrtc_sessions` doc) ; [code/calls_models.py](code/calls_models.py) ; plans [calls_plans/](calls_plans/) |
| [NOTIF-catalogue-tables.md](../catalogues/NOTIF-catalogue-tables.md) | `apps.notifications` | Phase 3b ; 2 tables ; [code/notif_models.py](code/notif_models.py) ; plans [notif_plans/](notif_plans/) |
| [CRYPTO-catalogue-tables.md](../catalogues/CRYPTO-catalogue-tables.md) | `apps.crypto` | Phase 3c ; 4 tables ; [code/crypto_models.py](code/crypto_models.py) ; plans [crypto_plans/](crypto_plans/) |
| [INDEX-catalogue.md](../catalogues/INDEX-catalogue.md) | btree / GIN | Dès `0001` ; `TrigramExtension` + `django.contrib.postgres` |

Chiffrement : [CRYPTO-00](crypto_plans/CRYPTO-00-modele-chiffrement.md) (décision) · [CRYPTO-A](crypto_plans/CRYPTO-A-cles.md) (API) · [CRYPTO-R](crypto_plans/CRYPTO-R-roles-permissions.md) · [routes](crypto_plans/CRYPTO-routes.md).

Plans fonctionnels Notifications : [NOTIF-R](notif_plans/NOTIF-R-roles-permissions.md) · [A in-app + push](notif_plans/NOTIF-A-in-app-push.md) · [routes](notif_plans/NOTIF-routes.md).

Plans fonctionnels Messagerie : [MESSAGERIE-R](messaging_plans/MESSAGERIE-R-roles-permissions.md) · [A inbox](messaging_plans/MESSAGERIE-A-inbox-conversations.md) · [B messages](messaging_plans/MESSAGERIE-B-messages.md) · [C groupes](messaging_plans/MESSAGERIE-C-groupes.md) · [D temps réel](messaging_plans/MESSAGERIE-D-temps-reel.md) · [E enrichi](messaging_plans/MESSAGERIE-E-contenu-enrichi.md) · [F modération](messaging_plans/MESSAGERIE-F-moderation-blocage.md) · [G typing](messaging_plans/MESSAGERIE-G-indicateurs-saisie.md).

Plans fonctionnels Médias : [MEDIA-R](media_plans/MEDIA-R-roles-permissions.md) · [A upload](media_plans/MEDIA-A-upload-stockage.md) · [B images](media_plans/MEDIA-B-images.md) · [C vidéos](media_plans/MEDIA-C-videos.md) · [D audio](media_plans/MEDIA-D-audio-transcription.md) · [E documents](media_plans/MEDIA-E-documents-ged.md) · [F quotas](media_plans/MEDIA-F-quotas-audit.md).

Plans fonctionnels Appels : [APPELS-R](calls_plans/APPELS-R-roles-permissions.md) · [A cycle](calls_plans/APPELS-A-cycle-vie.md) · [B participants](calls_plans/APPELS-B-participants-sessions.md) · [C LiveKit](calls_plans/APPELS-C-livekit-temps-reel.md) · [D pistes](calls_plans/APPELS-D-pistes-ecran.md) · [E enregistrements](calls_plans/APPELS-E-enregistrements.md) · [F QoS](calls_plans/APPELS-F-qualite-qos.md) · [G compte-rendu](calls_plans/APPELS-G-compte-rendu.md).

Comportement login local : [AUTH-A-connexion-locale.md](iam_plans/AUTH-A-connexion-locale.md).  
MFA : [AUTH-C-mfa-otp.md](iam_plans/AUTH-C-mfa-otp.md) (TOTP obligatoire ; coupe le JWT tant que `/mfa/verify` n’est pas OK).  
Inscription : [AUTH-D-inscription.md](iam_plans/AUTH-D-inscription.md) (AD + hors AD / RH).  
Appareils : [AUTH-E-appareils.md](iam_plans/AUTH-E-appareils.md) (27–36 ; `trusted` ≠ skip MFA). Lab [00-jour-5-auth-e.md](00-jour-5-auth-e.md) **clos**.  
Lier un 2ᵉ écran : [AUTH-J-lier-appareil-qr.md](iam_plans/AUTH-J-lier-appareil-qr.md) (QR Connect **puis** Google Authenticator ; ≠ QR enroll AUTH-C). Lab [00-jour-6-auth-j.md](00-jour-6-auth-j.md) **clos**.  
Première connexion / CGU : [AUTH-F-onboarding.md](iam_plans/AUTH-F-onboarding.md) (37–42). Lab : [00-jour-7-auth-f.md](00-jour-7-auth-f.md).  
Mot de passe : [AUTH-G-mot-de-passe.md](iam_plans/AUTH-G-mot-de-passe.md) (43–50).  
Sessions / logout : [AUTH-H-sessions.md](iam_plans/AUTH-H-sessions.md) (51–60).  
Sécurité compte : [AUTH-I-securite.md](iam_plans/AUTH-I-securite.md) (61–66).  
Rôles & permissions : [AUTH-R-roles-permissions.md](iam_plans/AUTH-R-roles-permissions.md) (R01–R10).  
Admin comptes / audit / régions : [ADMIN-A-lifecycle-audit.md](iam_plans/ADMIN-A-lifecycle-audit.md) (01–08).  
Profil : [PROF-A-identite.md](iam_plans/PROF-A-identite.md) (01–14).  
Édition & préférences : [PROF-B-edition-preferences.md](iam_plans/PROF-B-edition-preferences.md) (15–22).  
Confidentialité : [PROF-C-confidentialite.md](iam_plans/PROF-C-confidentialite.md) (23–30).  
Présence : [PRES-A-presence.md](iam_plans/PRES-A-presence.md) (01–16).  
Recherche & référentiels : [ANNUAIRE-A-recherche-referentiels.md](annuaire_plans/ANNUAIRE-A-recherche-referentiels.md).  
Arbre RH : [ANNUAIRE-B-arbre-segments.md](annuaire_plans/ANNUAIRE-B-arbre-segments.md).  
Affectations : [ANNUAIRE-C-affectations.md](annuaire_plans/ANNUAIRE-C-affectations.md).  
Skills / certifs : [ANNUAIRE-D-competences-certifications.md](annuaire_plans/ANNUAIRE-D-competences-certifications.md).  
**Index des routes IAM :** [IAM-routes.md](iam_plans/IAM-routes.md) (86 routes).  
**Index des routes Annuaire :** [ANNUAIRE-routes.md](annuaire_plans/ANNUAIRE-routes.md) (38 routes).  
**Index des routes Notifications :** [NOTIF-routes.md](notif_plans/NOTIF-routes.md) (6 routes).

Pas de `user_roles` / `trusted_devices`. Présence = [PRES-A](iam_plans/PRES-A-presence.md) (Redis + `users.status` sticky, pas le login). Prefs/privacy = tables 1-1, pas des colonnes `users`.

---



## 6. AUTH-A — résumé (01–12)

`POST /api/v1/auth/login` : `email` **ou** `username` + `password` + `device`.  
`POST /api/v1/auth/refresh` : rotation du refresh opaque.

- Rate-limit identifiant **et** IP
- 401 unique (inconnu / MDP / throttle) ; dummy Argon2
- 403 `ACCOUNT_DISABLED` / `ACCOUNT_LOCKED` après MDP OK
- Succès : upsert `devices`, 1 session active / appareil, JWT access + refresh hashé, `last_login`, `login_history`
Hors AUTH-A : MFA ([AUTH-C](iam_plans/AUTH-C-mfa-otp.md)), LDAP/AD (**AUTH-B**), inscription (**AUTH-D**), appareils (**AUTH-E**), lien QR 2ᵉ appareil (**AUTH-J**), onboarding/CGU (**AUTH-F**), mot de passe (**AUTH-G**), sessions/logout (**AUTH-H**), sécurité compte (**AUTH-I**), rôles/permissions (**AUTH-R**), admin comptes (**ADMIN-A**), profil (**PROF-A**), préférences (**PROF-B**), confidentialité (**PROF-C**), présence (**PRES-A**), annuaire ([ANNUAIRE-A…D](annuaire_plans/ANNUAIRE-A-recherche-referentiels.md)).

---



## 7. Tests & qualité (dès AUTH-A)

- `pytest` + `pytest-django` + `APIClient`
- Cas : 200, 401 (mauvais MDP / email inconnu), 403 inactif / lock, 400 validation, pas de hash en JSON, lignes `login_history`
- CI : `ruff check` + `pytest` sur PR
- Base de test isolée (`test_yas_connect`), jamais la base Docker de dev

---



## 8. Critères de « projet prêt »

Socle jour 0 :

- [x] Repo `backend-yas-connect` créé, indépendant du SIRH
- [x] PostgreSQL + 16 tables IAM + 5 Annuaire + `media_files`
- [x] AUTH-A vert (login email/username, refresh, device, tests)
- [x] `/api/docs` documente `POST /api/v1/auth/login` et `/refresh`
- [x] SIRH `/api/auth/login` **non concerné**

Fermeture MVP (chemin §4.1) :

- [ ] CRYPTO-A : bundles par appareil ; 409 `CRYPTO_KEYS_MISSING` / `PEER_KEYS_MISSING` ; clé cloud GROUP
- [ ] MEDIA-A : upload MinIO ; `scan_status=SKIPPED` (lab) ou ClamAV (staging) — jamais `CLEAN` sans scan
- [ ] NOTIF-A : in-app + push routé FCM/APNs via `devices.platform` ; hooks message + appel
- [ ] MESSAGERIE-B : PJ `media_id` ; 1-to-1 opaque (CRYPTO-00)
- [ ] APPELS-C : 1-to-1 LiveKit ; `CALL_INCOMING` sonne app fermée
- [ ] CRYPTO-00 respecté (pas de plaintext 1-to-1 en notif / logs)
