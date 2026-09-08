# Jour 1 — AUTH-A (connexion locale)

**Statut :** clos (2026-09-08).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jour 0 clos ([00-creer-le-projet.md](00-creer-le-projet.md) §11). `/health` = `"db": true`.  
**Plan métier (code à coller) :** [AUTH-A-connexion-locale.md](iam_plans/AUTH-A-connexion-locale.md) (AUTH-01 … 12).  
**Modèles :** [code/iam_models.py](code/iam_models.py) · [code/media_models.py](code/media_models.py) · [code/annuaire_models.py](code/annuaire_models.py).

**Objectif du jour :** `POST /api/v1/auth/login` et `POST /api/v1/auth/refresh` fonctionnent. Un user seed `jean.dupont@yas.tg` / `Secret123!` + `device` obligatoire. JWT access 15 min, refresh opaque hashé.

**Hors jour 1 :** MFA (AUTH-C), LDAP, inscription, logout-all, HasPermission (AUTH-R), chat, MinIO métier.

---

## 1. Recréer la base (obligatoire)

Le jour 0 a créé `auth_user` Django. AUTH-A pose `AUTH_USER_MODEL = "iam.User"`. **On ne change pas ça sur une base déjà migrée.**

```powershell
docker compose down -v
docker compose up -d
docker compose ps db
```

Attendre `healthy`. Le volume Postgres est **vidé** (lab uniquement).  
`DATABASE_URL` reste en **5433** (Postgres Windows occupe 5432).

---

## 2. Apps `iam`, `media`, `annuaire`

```powershell
mkdir apps\iam, apps\media, apps\annuaire
python manage.py startapp iam apps/iam
python manage.py startapp media apps/media
python manage.py startapp annuaire apps/annuaire
```

Dans chaque `apps.py` :

| App | `name` | `label` |
|-----|--------|---------|
| iam | `apps.iam` | `iam` |
| media | `apps.media` | `media` |
| annuaire | `apps.annuaire` | `annuaire` |

`INSTALLED_APPS` utilisera le `name`. **Pas** `"iam"` seul.

---

## 3. Coller les modèles (catalogues)

Copier **tel quel** (puis ajuster `LoginHistory.email` → `CharField(max_length=254)` si ce n’est pas déjà fait — AUTH-A §5) :

- `plans/plans/code/iam_models.py` → `apps/iam/models.py`
- `plans/plans/code/media_models.py` → `apps/media/models.py`
- `plans/plans/code/annuaire_models.py` → `apps/annuaire/models.py`

Ne **pas** inventer de colonnes. 0 ligne Annuaire / Médias au login.

`notification_preferences` : table NOTIF (plus tard). Seed jour 1 = rôle USER + prefs IAM + privacy. Pas `apps.notifications`.

---

## 4. Settings — bascule AUTH-A

Dans `config/settings.py` **avant** tout `makemigrations` :

- Ajouter `"apps.iam"`, `"apps.media"`, `"apps.annuaire"` dans `INSTALLED_APPS`.
- `AUTH_USER_MODEL = "iam.User"`
- Hasher YAS : `apps.iam.hashers.YasArgon2PasswordHasher` en tête (AUTH-A §2), fallback Argon2 Django.
- DRF : `YasJWTAuthentication` + `IsAuthenticated` **sauf** login / refresh / health (`AllowAny` explicite sur ces vues).
- JWT déjà lus depuis le `.env` (jour 0 §8–9).

`django.contrib.auth` **reste** (hashers). Toujours **pas** `admin` / `sessions` cookie.

---

## 5. Migrations

```powershell
python manage.py makemigrations iam media annuaire
python manage.py migrate
python manage.py check
```

Attendu : tables IAM (`users`, `devices`, `sessions`, `refresh_tokens`, `login_history`, `roles`, …) + `media_files` + 5 Annuaire. **Plus** de `auth_user`.

---

## 6. Services (coller AUTH-A)

Fichiers sous `apps/iam/` :

| Fichier | Sert à |
|---------|--------|
| `hashers.py` | Argon2id YAS + dummy hash (anti-énumération) |
| `services/token_service.py` | `sign_access_token` / `decode` / `hash_refresh` / `issue_refresh` |
| `services/device_service.py` | upsert device + revoke sessions même appareil |
| `services/rate_limit_service.py` | compteurs identifiant + IP |
| `services/auth_service.py` | `login()` + `complete_login()` + refresh |
| `authentication.py` | `YasJWTAuthentication` (Bearer + session active + `jti`) |
| `exceptions.py` | `AuthAPIError` → `{success, code, message}` |

Code : [AUTH-A](iam_plans/AUTH-A-connexion-locale.md) §2–5.

---

## 7. HTTP

- Serializers : `DeviceSpecSerializer`, `LoginSerializer`, refresh `{ refresh_token }`
- Vues : `LoginView`, `RefreshView` — `AllowAny`, pas de JWT
- `config/urls.py` : décommenter `path("api/v1/auth/", include("apps.iam.urls"))`

Contrats : AUTH-A « Contrat HTTP ». Device **obligatoire**. Email **ou** username, pas les deux.

---

## 8. Seed

Management command (ex. `python manage.py seed_iam`) :

- Rôle `USER` (`is_system=true`)
- User `jean.dupont@yas.tg` / username `jean.dupont` / mot de passe `Secret123!`
- Lignes 1-1 `user_preferences` + `privacy_settings`
- **Pas** de device (créé au 1er login)

ADMIN + permissions : AUTH-R, **pas** jour 1.

---

## 9. Vérif

```powershell
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login -H "Content-Type: application/json" -d "{\"email\":\"jean.dupont@yas.tg\",\"password\":\"Secret123!\",\"device\":{\"device_uuid\":\"dev-1\",\"platform\":\"WEB\"}}"
```

2e même curl : 1 device, ancienne session révoquée.  
`POST /api/v1/auth/refresh` avec le `refresh_token`.  
`GET /health` toujours 200.  
Tests AUTH-A §8 (table des cas).

---

## Checklist jour 1

- [x] Volume Postgres recréé ; plus de `auth_user`
- [x] `AUTH_USER_MODEL = "iam.User"` **avant** `makemigrations`
- [x] Login email + username + device
- [x] 401 unique (inconnu / MDP / rate-limit)
- [x] 403 pending / disabled / locked **après** MDP OK
- [x] JWT `jti` = `sessions.access_jti` ; refresh hashé, jamais le clair en base
- [x] 1 session active par `device_uuid`
- [x] `/health` intact
- [x] SIRH non modifié

---

## Interdits

- SimpleJWT, cookie session Django
- Skip device au login
- `CLEAN` antivirus (pas MEDIA-A)
- Coder MFA / LDAP dans le même incrément
- `docker compose down -v` en prod
