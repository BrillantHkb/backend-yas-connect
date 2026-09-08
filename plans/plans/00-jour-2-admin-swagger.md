# Jour 2 — Admin Django + Swagger (lab)

**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jour 0 ([00-creer-le-projet.md](00-creer-le-projet.md)) + jour 1 ([00-jour-1-auth-a.md](00-jour-1-auth-a.md)).  
Login API : `POST /api/v1/auth/login` vert. `/health` = `"db": true`.

**Objectif du jour :** inspecter les tables IAM dans **Django admin** (`/admin/`) et documenter l’API AUTH-A dans **Swagger UI** (`/api/docs/`) avec schéma Bearer JWT.

**Hors jour 2 :** inscription AD (AUTH-D), LDAP login (AUTH-B), MFA (AUTH-C), `HasPermission` API (AUTH-R), cookie session sur l’API (l’admin seul utilise le cookie Django).

---

## Pourquoi ce jour (pas AUTH-D / AUTH-B)

Le chemin A→Z place **AUTH-D puis AUTH-B** en phase 1b ([00-jour-3-auth-b.md](00-jour-3-auth-b.md)). Avant d’attaquer l’AD, on pose deux outils de lab :

| Outil | Sert à |
|--------|--------|
| **Django admin** | Voir `users`, `devices`, `sessions`, `login_history` sans SQL |
| **Swagger** | Essayer login / refresh depuis le navigateur ; schéma OpenAPI pour le front |

Le jour 0 avait **volontairement** omis `django.contrib.admin` (API only). Ici on le **branche** sans changer le catalogue : **pas** de colonnes `is_staff` / `is_superuser` en base.

---

## 1. Settings — apps + middleware admin

Dans `config/settings.py` :

- `INSTALLED_APPS` : `"django.contrib.admin"`, `"django.contrib.sessions"`, `"django.contrib.messages"` (en plus de `auth` / `contenttypes` / `staticfiles` déjà là).
- Middleware **après** Security, **avant** Common : `SessionMiddleware`, `CsrfViewMiddleware`, `AuthenticationMiddleware`, `MessageMiddleware`.
- `TEMPLATES` : context processors `request`, `auth`, `messages` (sinon `/admin/` plante).
- Cookie session = **uniquement** le staff `/admin/`. Les vues API restent JWT (`YasJWTAuthentication`). DRF n’active pas `SessionAuthentication` → pas de CSRF sur `POST /api/v1/auth/login`.

`python manage.py migrate` : tables `django_session` (+ `django_admin_log`). **Pas** de `auth_user`.

---

## 2. Accès admin sans colonnes inventées

`User` reste `AbstractBaseUser` (catalogue). Pour que `/admin/` accepte un compte :

- `@property is_staff` / `is_superuser` → `True` **seulement** si `role.code == "ADMIN"`.
- `has_perm` / `has_module_perms` → même règle.
- `create_superuser` : `get_or_create` rôle `ADMIN` (`is_system=true`, `level=100`) ; **pop** `is_staff` / `is_superuser` (kwargs de `createsuperuser`, pas des champs SQL).

`jean.dupont` (rôle `USER`) **ne** voit **pas** `/admin/`. Un user seed `admin@yas.tg` (rôle `ADMIN`) oui.

---

## 3. ModelAdmin IAM (lecture lab)

`apps/iam/admin.py` : User, Role, Device, Session, RefreshToken, LoginHistory, UserPreference, PrivacySetting.

Interdits d’affichage en clair : `password` / `password_hash`, `refresh_hash`, `token_hash`.  
Session / history : plutôt `readonly`.

---

## 4. URLs

`config/urls.py` :

- `path("admin/", admin.site.urls)`
- garder `/api/schema/` et `/api/docs/` (`AllowAny` en lab)

---

## 5. Swagger / OpenAPI (drf-spectacular)

Déjà installé jour 0. Jour 2 = **contrat AUTH-A visible** :

- `SPECTACULAR_SETTINGS` : schéma `bearerAuth` (HTTP Bearer JWT), tags Auth / Santé.
- `@extend_schema` sur `LoginView`, `RefreshView`, `HealthView` : body, 200/400/401/403, `auth=[]` (public).
- Serializers de **réponse** documentaires (pas de nouvelle table) : enveloppe `{success, data}` + tokens.

Dans Swagger UI : bouton **Authorize** → coller `Bearer <access_token>` pour les routes protégées plus tard.

---

## 6. Seed

`python manage.py seed_iam` (idempotent) :

| Rôle | User | Mot de passe | `/admin/` | `/auth/login` |
|------|------|--------------|-----------|----------------|
| `USER` | `jean.dupont@yas.tg` | `Secret123!` | non | oui |
| `ADMIN` | `admin@yas.tg` / `admin.yas` | `Admin123!` | oui | oui (JWT) |

Pas de device en seed.

---

## 7. Vérif

```powershell
python manage.py migrate
python manage.py seed_iam
python manage.py check
python manage.py test apps.iam.tests.test_jour_2
```

Navigateur :

- `http://127.0.0.1:8000/admin/` → `admin@yas.tg` / `Admin123!`
- `http://127.0.0.1:8000/api/docs/` → Try it out `POST /api/v1/auth/login`
- `GET /health` toujours 200

---

## Checklist jour 2

- [ ] `/admin/` login cookie ; USER rejeté (`is_staff` faux)
- [ ] Tables IAM visibles ; hash MDP / refresh **pas** en clair
- [ ] `/api/docs/` documente login + refresh + health
- [ ] Schéma Bearer JWT dans OpenAPI
- [ ] API toujours sans cookie session
- [ ] 0 colonne inventée sur `users`

---

## Interdits

- `SessionAuthentication` DRF (CSRF sur l’API)
- Colonnes `is_staff` / `is_superuser` en SQL
- LDAP / MFA / matrice AUTH-R dans le même incrément
- `docker compose down -v` (casse le seed jour 1)
