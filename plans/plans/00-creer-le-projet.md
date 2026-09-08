# Créer le projet YAS Connect (Django REST)

**Statut :** plan de conception — jour 0 dans **ce** repo.  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect` (`E:\iSOCProjects\backend-yas-connect`). **Jamais** dans le SIRH.  
Base PostgreSQL = `yas_connect`. Issuer JWT / bucket MinIO = `yas-connect` (identifiants produit, pas le nom du dossier).

**Backend figé :** Python **3.12+** · Django **5.2** · **Django REST Framework**.  
**Base :** PostgreSQL **16** uniquement (pas SQLite, pas la base du SIRH).  
**MVP métier :** [MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md).

**Ce fichier suffit pour le jour 0** (venv, paquets, Docker, `.env`, `settings.py`, `/health`, Swagger).  
Après `/health` vert : plans métier ([AUTH-A](iam_plans/AUTH-A-connexion-locale.md), catalogues, [A→Z §4](00-application-A-Z.md)) — pas recopiés ici.

Objectif jour 0 : `GET /health` répond **200** avec `"db": true`, et Swagger s’ouvre sur `/api/docs/`. **Pas de login** tant que AUTH-A n’est pas codé.

---



## 1. Ce que le MVP impose (stack)

Le MVP = entrer en confiance, trouver un collègue, écrire / envoyer un fichier, **être sonné téléphone fermé**, appeler.


| Job MVP                             | App Django           | Infra le jour où on code ça                         |
| ----------------------------------- | -------------------- | --------------------------------------------------- |
| Santé API, erreurs JSON             | `apps.core`          | **Jour 0**                                          |
| Compte, MFA, appareils, QR 2ᵉ écran | `apps.iam`           | AUTH-A…J — PostgreSQL + Redis (cache)               |
| Login Windows / AD + inscription    | `apps.config` + IAM  | Jour 3 : AUTH-D **puis** AUTH-B — pas de seed user AD |
| Photo, PJ, album, vidéo, vocal, GED | `apps.media`         | MEDIA-A — **MinIO** (S3) ; lab scan = `SKIPPED`     |
| Trouver un collègue                 | `apps.annuaire`      | ANNUAIRE-A — tables dès AUTH-A (0 ligne)            |
| Clés E2E / groupes                  | `apps.crypto`        | CRYPTO-A — après IAM                                |
| Alertes in-app + push               | `apps.notifications` | NOTIF-A — Redis + FCM/APNs (clés vides = no-op lab) |
| Chat 1-1 / groupe + WS              | `apps.messaging`     | MESSAGERIE — Channels + Redis                       |
| Appel audio/vidéo                   | `apps.calls`         | APPELS — **LiveKit**                                |
| Présence (en ligne)                 | IAM `PRES-A`         | Redis + Channels                                    |


**Pas au jour 0 :** Social, canaux, IA, Django Admin, cookie session Django, `djangorestframework-simplejwt`.

---



## 2. Versions — installer **seulement** ça au jour 0

Python **3.12 ou 3.13**. Django 5.2 = LTS. Bornes `>=x,<y` : on ne fige pas le patch, on **interdit** le saut majeur.

### 2.1 `requirements/base.txt` (runtime)

```text
django>=5.2.8,<6.0
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


| Paquet                | Pourquoi (pas avant d’en avoir besoin)                                |
| --------------------- | --------------------------------------------------------------------- |
| `django`              | ORM, migrations, settings                                             |
| `djangorestframework` | API JSON, serializers, `APIView`                                      |
| `drf-spectacular`     | OpenAPI + UI `/api/docs/`                                             |
| `psycopg[binary]`     | Driver PostgreSQL 16 (wheels Windows)                                 |
| `argon2-cffi`         | Hasher mots de passe (AUTH-A). Jour 0 : hasher Django standard suffit |
| `PyJWT`               | Access JWT **HS256**. **Pas** SimpleJWT                               |
| `django-environ`      | `DATABASE_URL` et le `.env`                                           |
| `django-cors-headers` | Front web / mobile plus tard                                          |
| `django-redis`        | Cache ; jour 0 `REDIS_URL` vide → LocMem                              |
| `ua-parser`           | AUTH-A : browser dans `login_history`                                 |




### 2.2 `requirements/dev.txt`

```text
-r base.txt
pytest>=8.3,<9.0
pytest-django>=4.9,<5.0
ruff>=0.8,<0.15
```



### 2.3 `requirements/prod.txt`

```text
-r base.txt
gunicorn>=23.0,<24.0
```

Prod API REST = gunicorn + `wsgi.py`. Le **WebSocket** (présence, chat, appels) passera par **Daphne / Uvicorn ASGI** à PRES-A / MESSAGERIE-D — pas gunicorn seul.

### 2.4 À **ajouter** dans `base.txt` seulement au ticket (pas maintenant)


| Quand          | Paquets                                                                | Sert à                                    |
| -------------- | ---------------------------------------------------------------------- | ----------------------------------------- |
| AUTH-B         | `ldap3>=2.9,<3.0` · `croniter>=5.0,<7.0`                               | Bind AD + next run du job sync            |
| AUTH-C         | `pyotp>=2.9,<3.0` · `cryptography>=43.0,<46.0`                         | Google Authenticator + Fernet secret TOTP |
| MEDIA-A        | `boto3>=1.35,<2.0`                                                     | Presign / PUT MinIO (API S3)              |
| MEDIA-B        | `Pillow>=11.0,<12.0`                                                   | Miniatures album                          |
| PRES-A / MSG-D | `channels>=4.2,<5.0` · `channels-redis>=4.2,<5.0` · `daphne>=4.1,<5.0` | WebSocket                                 |
| NOTIF-A        | `firebase-admin>=6.6,<8.0`                                             | Push FCM (no-op si clé vide)              |
| APPELS-C       | `livekit-api>=1.0,<2.0`                                                | Créer room + tokens LiveKit               |


Binaire **hors pip** (plus tard) : **FFmpeg** (MEDIA-C), **ClamAV** Docker profil `scan` (staging). Lab : scan = `SKIPPED`, pas FFmpeg obligatoire.

**Interdit :** Poetry obligatoire, `mysqlclient`, `sqlite3` en settings, `rest_framework_simplejwt`, `django-admin` au jour 0.

---



## 3. Prérequis machine (Windows)

1. Python 3.12+ : `py -3.12 --version` (ou `python --version`).
2. Git : `git --version`.
3. Docker Desktop : `docker --version` et `docker compose version`.
4. Port **5432** libre (sinon mapper `"5433:5432"` et adapter `DATABASE_URL`).

Ne **pas** réutiliser la base PostgreSQL du SIRH.

---



## 4. Créer le repo code

```powershell
mkdir E:\iSOCProjects\backend-yas-connect
cd E:\iSOCProjects\backend-yas-connect
git init
```

`.gitignore` **avant** tout commit :

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

---



## 5. Environnement virtuel + paquets

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Créer les trois fichiers `requirements\*.txt` (§2), puis :

```powershell
pip install -r requirements\dev.txt
pip freeze > requirements\lock.txt
```

Sans venv activé (prompt `(.venv)`), **ne pas** `pip install`.  
`lock.txt` = photo des versions exactes ; optionnel jusqu’au 1er déploiement.

Si `Activate.ps1` est bloqué : `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

---



## 6. Projet Django (`config` = settings, pas le métier)

```powershell
django-admin startproject config .
```

Résultat :

```
backend-yas-connect/
  manage.py
  config/
    settings.py
    urls.py
    asgi.py
    wsgi.py
```

```powershell
mkdir apps
New-Item apps\__init__.py -ItemType File
mkdir apps\core
python manage.py startapp core apps/core
```

Dans `apps/core/apps.py` :

```python
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
```

`INSTALLED_APPS` = `"apps.core"` (le `name`), jamais `"core"` seul.

**Ne pas** `startapp iam` au jour 0. AUTH-A pose `AUTH_USER_MODEL = "iam.User"` **avant** la première migration `auth`. Si on `migrate` trop tôt avec le `User` Django par défaut, il faudra **recréer la base** (`docker compose down -v`).

---



## 7. Base de données — Docker + `DATABASE_URL`



### 7.1 `docker-compose.yml` (lab complet)

Créer `docker-compose.yml` à la racine `backend-yas-connect/` :

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

Jour 0, **seul PostgreSQL est obligatoire**. Les autres services peuvent tourner déjà (ports) : . ClamAV : `docker compose --profile scan up -d` (staging seulement).

Démarrage lab (**sans** ClamAV) :

```powershell
docker compose up -d
docker compose ps
docker compose exec db psql -U yas -d yas_connect -c '\conninfo'
```


| Service             | URL locale                                                   | Quand Django s’en sert                                                            |
| ------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| PostgreSQL          | `127.0.0.1:5432` · base `yas_connect` · user/mdp `yas`/`yas` | **Jour 0**                                                                        |
| Redis               | `127.0.0.1:6379`                                             | AUTH-C challenge, AUTH-J QR, présence, WS — `REDIS_URL` vide = LocMem OK au début |
| MinIO API / console | `:9000` / [console](http://127.0.0.1:9001)                   | MEDIA-A                                                                           |
| LiveKit             | `:7880`                                                      | APPELS-C                                                                          |
| Mailhog SMTP / UI   | `:1025` / [UI](http://127.0.0.1:8025)                        | AUTH-D verify-email (non bloquant)                                                |




### 7.2 Comment Django se branche

`django-environ` parse **une** URL :

```
DATABASE_URL=postgres://yas:yas@127.0.0.1:5432/yas_connect
```

Dans `config/settings.py` (§9) :

```python
DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
```

Ça pose `ENGINE = django.db.backends.postgresql` + `NAME` / `USER` / `HOST` / `PORT`. **Aucun** `django.db.backends.sqlite3`.

Vérifications :

```powershell
python manage.py check
python manage.py dbshell
# dans psql : \conninfo   puis  \q
```

`check` échoue tant que `.env` + Postgres ne sont pas là — normal.

### 7.3 Si le port 5432 est déjà pris

Dans `docker-compose.yml` : `"5433:5432"`.  
`.env` : `DATABASE_URL=postgres://yas:yas@127.0.0.1:5433/yas_connect`.

---



## 8. Secrets — `.env`

Créer `.env.example` (commité) :

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

Puis :

```powershell
Copy-Item .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Coller deux secrets **différents** dans `.env` (lancer la commande **deux fois**) :

- `DJANGO_SECRET_KEY` — cookies / CSRF Django (on n’utilise presque pas les cookies).
- `JWT_TOKEN_SECRET` — signature des access tokens (AUTH-A). **≠** `DJANGO_SECRET_KEY`.

Jour 0 : `REDIS_URL=` (vide). Dès MFA / QR appareil / plusieurs workers : `REDIS_URL=redis://127.0.0.1:6379/0`.

`.env` est dans `.gitignore`. `.env.example` est commité (valeurs lab, pas de vrais secrets prod).

---



## 9. Fichiers Python / config du jour 0 (à coller tels quels)

Tant que `apps.iam` n’existe pas : **pas** de `AUTH_USER_MODEL`, **pas** `django.contrib.sessions` ni `admin`.

### 9.1 `config/settings.py`

Remplacer le fichier généré par `startproject` :

```python
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
```

À AUTH-A : ajouter `apps.iam`, `apps.media`, `apps.annuaire`, `AUTH_USER_MODEL = "iam.User"`, hasher YAS, `YasJWTAuthentication` — voir [AUTH-A](iam_plans/AUTH-A-connexion-locale.md) et [A→Z §3.7](00-application-A-Z.md) bloc AUTH-01.

### 9.2 `apps/core/views.py`

```python
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            db_ok = False
        status = 200 if db_ok else 503
        return Response(
            {"success": True, "data": {"status": "ok" if db_ok else "degraded", "db": db_ok}},
            status=status,
        )
```



### 9.3 `apps/core/urls.py`

```python
from django.urls import path

from apps.core.views import HealthView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
]
```



### 9.4 `apps/core/exceptions.py`

```python
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
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
            code = getattr(data["detail"], "code", "ERROR")
            if hasattr(code, "upper"):
                code = str(code).upper()
        elif data:
            message = "Données invalides."
            code = "VALIDATION_ERROR"

    response.data = {
        "success": False,
        "code": code,
        "message": message,
        "errors": data if isinstance(data, dict) and "detail" not in data else None,
    }
    return response
```



### 9.5 `config/urls.py`

```python
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("", include("apps.core.urls")),  # GET /health
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    # path("api/v1/auth/", include("apps.iam.urls")),  # AUTH-A
]
```



### 9.6 `pyproject.toml` (ruff)

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



### 9.7 `pytest.ini`

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py
addopts = -q --reuse-db
```

Fuseau : `TIME_ZONE = "Africa/Lome"`, `USE_TZ = True` (UTC en base).

---



## 10. Premier `migrate` + serveur

```powershell
python manage.py migrate
python manage.py runserver 8000
```


| URL                                                                | Attendu                                                   |
| ------------------------------------------------------------------ | --------------------------------------------------------- |
| [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)       | `{"success": true, "data": {"status": "ok", "db": true}}` |
| [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/) | Swagger, encore vide de routes métier                     |


`db: false` / 503 → Postgres down ou mauvais `DATABASE_URL`.

```powershell
ruff check .
ruff format .
pytest
```

---



## 11. Checklist jour 0

- [x] Repo `backend-yas-connect` **hors** SIRH (conception peut vivre dans `plans/`)
- [x] venv + `pip install -r requirements\dev.txt` (Django **5.2.17**)
- [x] Docker `db` healthy ; `\conninfo` OK (`yas_connect` / `yas`, hôte **5433**)
- [x] `.env` avec deux secrets distincts (`DJANGO_SECRET_KEY` ≠ `JWT_TOKEN_SECRET`)
- [x] `python manage.py check` OK
- [x] `GET /health` → `db: true`
- [x] `/api/docs/` s’affiche
- [x] `ruff check` vert (`apps` + `config`)
- [x] Aucune table métier IAM (seulement `auth_*` + `django_content_type` / `django_migrations`)

---



## 12. Après le jour 0 — ordre (ne pas tout créer d’un coup)

**Jour 1 (maintenant) :** [00-jour-1-auth-a.md](00-jour-1-auth-a.md) — login local AUTH-01…12.

Ordre figé détaillé : [A→Z §4.1](00-application-A-Z.md). Résumé :


| Étape                               | Commande / action                                                                                                                         | Plan                                                                       |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| AUTH-A                              | `startapp iam` + `media` + `annuaire` ; coller [code/iam_models.py](code/iam_models.py) ; `AUTH_USER_MODEL` **avant migrate** ; seed USER | [AUTH-A](iam_plans/AUTH-A-connexion-locale.md)                             |
| AUTH-B…J, F–I, R, ADMIN, PROF, PRES | même app `iam` (+ `config`, Channels)                                                                                                     | [iam_plans/](iam_plans/) · routes [IAM-routes.md](iam_plans/IAM-routes.md) |
| MEDIA-R/A                           | MinIO + `boto3`                                                                                                                           | [MEDIA-A](media_plans/MEDIA-A-upload-stockage.md)                          |
| NOTIF-R/A                           | push ; event message/appel                                                                                                                | [NOTIF-A](notif_plans/NOTIF-A-in-app-push.md)                              |
| CRYPTO-R/A                          | bundles par appareil                                                                                                                      | [CRYPTO-A](crypto_plans/CRYPTO-A-cles.md)                                  |
| MESSAGERIE                          | 1-to-1 puis groupes + WS                                                                                                                  | [messaging_plans/](messaging_plans/)                                       |
| APPELS                              | LiveKit 1-1                                                                                                                               | [calls_plans/](calls_plans/)                                               |


**Règle AUTH_USER_MODEL :** dès AUTH-A, poser `AUTH_USER_MODEL = "iam.User"` **avant** `makemigrations`. Si Phase 0 a déjà migré `auth_user` Django : `docker compose down -v`, `up -d`, `migrate` à neuf (jour 0 uniquement).

Modèles : coller depuis [plans/code/](code/) ; attributs = [catalogues/](../catalogues/). Ne pas inventer de colonnes.

---



## 13. Arborescence cible (après AUTH-A, pas jour 0)

```
backend-yas-connect/
  manage.py
  pytest.ini
  pyproject.toml
  .env.example
  .env                 # gitignored
  docker-compose.yml
  requirements/
    base.txt
    dev.txt
    prod.txt
    lock.txt           # optionnel
  config/              # settings, urls, asgi, wsgi
  apps/
    core/              # Phase 0
    iam/               # AUTH-A
    media/
    annuaire/
    config/            # AUTH-B (system_settings)
    notifications/     # plus tard
    crypto/
    messaging/
    calls/
    realtime/          # Channels PRES / chat — plus tard
  tests/
```

---



## 14. Interdits (à graver)

- Coder dans le SIRH ou fusionner les bases.
- SQLite « pour aller plus vite ».
- SimpleJWT, cookie session Django pour l’API.
- Installer Channels / LiveKit SDK / ldap3 **avant** le ticket (ça pollue et ça ne sert pas `/health`).
- Changer `AUTH_USER_MODEL` après des migrations de prod.
- Marquer un fichier `CLEAN` sans ClamAV (lab = `SKIPPED`).
- Social / Canaux / IA tant que message + appel ne sonnent pas app fermée.

