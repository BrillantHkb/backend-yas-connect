# Jour 3 — AUTH-D puis AUTH-B (inscription AD, ensuite login Windows)

**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jour 0 + jour 1 (AUTH-A) + jour 2 (admin + Swagger).  
`POST /api/v1/auth/login` (MDP app) vert. `/health` = `"db": true`.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §1 — *Entrer dans l’application*) :

| Fonction MVP | Ticket | Statut avant / pendant jour 3 |
|--------------|--------|-------------------------------|
| Connexion identifiant + mot de passe | AUTH-A | **fait** (jour 1) |
| **Inscription AD / hors AD** | **AUTH-D** | **ce jour, d’abord** |
| **Connexion compte Windows / Active Directory** | **AUTH-B** | **ce jour, ensuite** |
| Scanner le QR Google Authenticator | AUTH-C | jour suivant |
| Valider le code Authenticator (6 chiffres) | AUTH-C | jour suivant |

**À quoi ça sert (MVP) :** un collaborateur AD **crée** son compte Connect en prouvant le mot de passe bureau, puis se **reconnecte** avec ce même mot de passe. Pas de second univers, **pas de user AD inventé en seed**.

**Plans métier (code à coller) :**

1. [AUTH-D-inscription.md](iam_plans/AUTH-D-inscription.md) (D01–D06) — **seul JIT**
2. [AUTH-B-sso-ldap.md](iam_plans/AUTH-B-sso-ldap.md) (AUTH-13 + AUTH-16) — login + sync

**Modèles config :** [code/config_models.py](code/config_models.py).  
IAM : `users.ldap_dn`, `pending_approval`, `email_verifications`, `LoginHistory.FailureReason.DIRECTORY_UNAVAILABLE` **déjà** dans `apps/iam/models.py`. AUTH-A pose déjà le 403 `ACCOUNT_PENDING` sur `POST /auth/login`.

**Objectif du jour :**

1. Socle LDAP (`apps.config` + `ldap_service`) — search, bind, UAC, TLS.
2. **AUTH-D** — `register/check-ad`, `register/ad`, `register` hors AD, verify-email, approve/reject. Ça **crée** le user (`ldap_dn`, UPN, sAMAccountName).
3. **AUTH-B** — `POST /login/ldap` + job sync, testé sur un compte **issu de D02**, pas sur `seed_iam`.

**Hors jour 3 :** MFA (AUTH-C — JWT encore **sans** OTP après D02 et après `login/ldap` ; AUTH-C coupera ça), mapping groupe AD → rôle, OIDC/SAML, JIT au **login**, people-picker `GET /users`, `HasPermission` AUTH-R (D05 = rôle ADMIN / `is_staff` ce jour).

---

## Pourquoi AUTH-D avant AUTH-B

AUTH-13 **n’invente pas** l’utilisateur. Si on code `login/ldap` en premier, le lab n’a qu’un choix : poser `ldap_dn` à la main ou seed un faux user AD. **Interdit ce jour.**

Ordre contractuel du jour :

```text
config + ldap_service  →  AUTH-D (création)  →  AUTH-B (login + sync)
```

`seed_iam` (`jean.dupont` / `admin`) **reste** pour AUTH-A et `/admin/`. `ldap_dn` **reste NULL** sur ces deux comptes. Aucun `python manage.py seed_*` ne crée un user lié AD.

Sans DC YAS : chemins LDAP/register **mockés** ; 503 si annuaire down. Login quotidien lab = toujours `POST /auth/login`.

AUTH-C (jour 4) s’appuie sur AUTH-A **et** AUTH-B **et** D02 : le même `complete_login` devient `begin_mfa` pour MDP app, LDAP **et** fin d’inscription AD.

---

## Paliers (figés pour ce jour)

| Sujet | Choix jour 3 | Plus tard |
|--------|----------------|-----------|
| Après `register/ad` / `login/ldap` | `complete_login` → JWT (comme AUTH-A) | AUTH-C : `begin_mfa`, plus de JWT tant que `/mfa/verify` KO |
| `region_id` / `segment_id` | Obligatoires D02/D03. Seed **référentiel** (5 régions TG + types + segment `YAS`) + `GET /directory/regions` et `GET /directory/segments` publics | ANNUAIRE-A : people-picker, arbre complet |
| D05 approve / reject | JWT + rôle `ADMIN` (`is_staff` déjà AUTH-A/jour 2). Liste `GET /admin/users?pending=true` | AUTH-R : `HasPermission` (`iam.user.approve` / `reject`) |
| SMTP D04 | `EMAIL_HOST` vide = skip envoi, token quand même | Mailhog optionnel |

---

## 1. App `config` + modèles

```powershell
mkdir apps\config
python manage.py startapp config apps/config
```

`apps.py` : `name = "apps.config"`, `label = "config"`.  
Coller [code/config_models.py](code/config_models.py) → `apps/config/models.py`.  
`INSTALLED_APPS` : `"apps.config"`.  
`makemigrations config` + `migrate`.

Tables : `system_settings`, `scheduled_jobs` (+ `feature_flags` vide OK).  
Secrets LDAP : **`system_settings`** (`is_sensitive=true` sur `bind_password`), **pas** le `.env`.

---

## 2. Paquets

Dans `requirements/base.txt` (voir [00-creer-le-projet.md](00-creer-le-projet.md) §2.4) :

```text
ldap3>=2.9,<3.0
croniter>=5.0,<7.0
```

```powershell
pip install -r requirements\dev.txt
```

Interdit : `authlib`, OIDC, SimpleJWT.

---

## 3. Seeds (config LDAP + référentiels — pas de user AD)

`python manage.py seed_config` (idempotent) :

Clés `category=ldap` : `uri`, `bind_dn`, `bind_password`, `search_base`, `timeout_seconds` — valeurs **lab**. `bind_password` : `is_sensitive=true`.

Job `ldap_sync_users` (AUTH-16) : cron `0 2 * * *`, `handler` = `apps.iam.jobs.sync_ldap_accounts`.

`python manage.py seed_iam` : **étendre** (idempotent) les 5 régions TG — ce n’est **pas** un seed user :

| code | name |
|------|------|
| `MARITIME` | Maritime |
| `PLATEAUX` | Plateaux |
| `CENTRALE` | Centrale |
| `KARA` | Kara |
| `SAVANES` | Savanes |

`python manage.py seed_annuaire` (idempotent, **après** `seed_iam`) : types `DIRECTION` / `DEPARTEMENT` / `SERVICE` + segment racine `YAS` / « YAS Togo » ([ANNUAIRE-A](annuaire_plans/ANNUAIRE-A-recherche-referentiels.md) ANN-05).

Ne **jamais** logger `bind_password`. Ne **jamais** écrire `users.ldap_dn` dans un seed.

---

## 4. `ldap_service` (socle, avant toute vue)

| Fichier | Sert à |
|---------|--------|
| `apps/iam/services/ldap_service.py` | `get_ldap_settings`, search DN + UPN + sAMAccountName, bind user, UAC / `accountExpires`, TLS obligatoire |

TLS : `ldaps://` **ou** `ldap://` + STARTTLS. URI sans TLS → 503 (conf), pas 401.  
MDP AD : **jamais** en `login_history`, logs, audit.

Attributs lus au search (AUTH-D + AUTH-B) : `distinguishedName`, `userPrincipalName`, `sAMAccountName`, `userAccountControl`, `accountExpires`. **Pas** de copie displayName / title.

---

## 5. AUTH-D — inscription (avant `login/ldap`)

Coller [AUTH-D-inscription.md](iam_plans/AUTH-D-inscription.md) § D01–D06.

| Endpoint | Effet |
|----------|--------|
| `POST /api/v1/auth/register/check-ad` | Search + bind ; **200** `{ ad_available: true\|false }` (jamais 401). AD down → 503 |
| `POST /api/v1/auth/register/ad` | Refait search + bind. Crée user `USER`, `is_active=true`, `ldap_dn` + UPN + sAMAccountName, MDP **app** distinct. Puis `complete_login` (JWT ce jour) |
| `POST /api/v1/auth/register` | Hors AD : `ldap_dn=NULL`, `pending_approval=true`, `is_active=false`, **pas** de JWT. Garde-fou : AD loggable → 409 `AD_ACCOUNT_EXISTS` |
| `POST /api/v1/auth/register/verify-email` | Pose `verified_at` ; **`is_active` inchangé** |
| `POST /api/v1/auth/register/resend-verification` | Hors AD inactif seulement |
| `GET /api/v1/admin/users?pending=true` | File RH |
| `POST /api/v1/admin/users/{id}/approve` | `is_active=true`, `pending_approval=false`. **400** si `ldap_dn` |
| `POST /api/v1/admin/users/{id}/reject` | Reste inactif + motif audit |
| `GET /api/v1/directory/regions` | Public, dropdowns inscription |
| `GET /api/v1/directory/segments` | Public (`YAS` au minimum) |

Fichiers : `register_service.py`, `password_policy.py`, serializers / vues register + admin users (D05).  
`login()` AUTH-A : 403 `ACCOUNT_PENDING` **déjà** en place — ne pas casser.

Deux secrets D02 : `password_ad` (preuve, jamais stocké) + `password` (Argon2, politique AUTH-D).

---

## 6. AUTH-B — login LDAP + sync (après D02)

| Fichier | Sert à |
|---------|--------|
| `apps/iam/services/auth_service.py` | **ajouter** `login_ldap()` ; réutiliser `complete_login(..., login_method=LDAP)` |
| `apps/iam/jobs.py` | `sync_ldap_accounts` : users **avec** `ldap_dn` → `is_active=false` si AD non loggable |
| `apps/config/management/commands/run_scheduled_jobs.py` | jobs `next_execution` dus (`croniter`) |

Ordre `login_ldap` (contractuel) : rate-limit → lookup YAS → dummy si absent (**pas** d’appel AD) → search/bind → 401 si AD non loggable → **403 YAS** (`ACCOUNT_PENDING` / `DISABLED` / `LOCKED`) **après** bind OK → `ldap_dn` si vide → `complete_login`.

User YAS absent (jamais passé par D02) → **401**, sans JIT.

`POST /auth/login` et `/auth/refresh` **inchangés** (hors `ACCOUNT_PENDING` déjà AUTH-A).

---

## 7. HTTP + Swagger

- Register* + `login/ldap` : `AllowAny`, `@extend_schema` tag Auth.
- Directory régions / segments : `AllowAny`.
- D05 : JWT, rôle ADMIN.
- `/api/docs/` : Try it out **d’abord** `register/ad` (mock), **ensuite** `login/ldap` sur le même email.

Codes LDAP : 200 / 401 / 403 / 400 / **503** `DIRECTORY_UNAVAILABLE`.  
Check-ad : 200 ou 503 (pas 401).

---

## 8. Lab sans DC YAS

| Situation | Comportement |
|-----------|----------------|
| Settings LDAP absents / AD down / timeout | **503** `DIRECTORY_UNAVAILABLE` |
| Bind / DN introuvable / UAC non loggable | D01 : 200 `ad_available=false` ; D02 / `login/ldap` : **401** |
| Tests | **mock** `ldap3` — pas de réseau YAS, **pas** de `ldap_dn` en seed |
| Login quotidien lab | `POST /auth/login` (jean.dupont / admin) |

Optionnel plus tard : OpenLDAP Docker. **Pas** obligatoire pour fermer le jour 3.

Ne **pas** lier jean.dupont à l’AD dans l’admin Django.

---

## 9. Admin Django

Enregistrer `SystemSetting` (masquer `setting_value` si `is_sensitive`) et `ScheduledJob`.  
Ne pas afficher `bind_password` en clair.

---

## 10. Tests (mocks)

**AUTH-D d’abord** (`test_auth_d.py`) :

| Cas | Attendu |
|-----|---------|
| D01 bind OK | 200 `ad_available=true` |
| D01 mauvais MDP AD | 200 `ad_available=false` |
| D02 OK | 200 JWT ; `ldap_dn` + UPN + sAMAccountName ; hash ≠ MDP AD ; rôle USER |
| D02 UPN déjà pris | 409 |
| D02 MDP app faible | 400 `WEAK_PASSWORD` |
| D02 sans region/segment | 400 |
| D03 hors AD | 201 ; `pending_approval` ; pas de JWT |
| D03 alors qu’AD loggable | 409 `AD_ACCOUNT_EXISTS` |
| Login pending | 403 `ACCOUNT_PENDING` |
| D05 approve | `is_active=true` ; login MDP 200 |

**AUTH-B ensuite** (`test_auth_b.py`) — user créé **via D02 mock**, pas via seed :

| Cas | Attendu |
|-----|---------|
| Bind OK + device | 200, `login_method=LDAP`, JWT, 1 device |
| User YAS absent | 401 + dummy, **pas** d’appel AD |
| Bind KO / DN manquant | 401 |
| AD down | 503 |
| `is_active=false` **après** bind OK | 403 `ACCOUNT_DISABLED` |
| UAC disable AD | 401 (pas 403) |
| Job : DN disparu / UAC disable | `is_active=false` |
| `POST /auth/login` jean.dupont | toujours 200 ; `ldap_dn` toujours NULL |
| `/health`, `/api/docs/` | 200 |

---

## 11. Vérif manuelle

```powershell
pip install -r requirements\dev.txt
python manage.py startapp config apps/config
# coller models + INSTALLED_APPS
python manage.py makemigrations config
python manage.py migrate
python manage.py seed_config
python manage.py seed_iam
python manage.py seed_annuaire
python manage.py check
pytest apps/iam/tests/test_auth_d.py apps/iam/tests/test_auth_b.py apps/iam/tests/test_auth_a.py --reuse-db
```

Sans AD réel : `register/ad` et `login/ldap` → 503.  
`POST /auth/login` jean.dupont → 200.

Avec mocks (tests) : D02 crée le user → `login/ldap` 200 sur **ce** user.

---

## Checklist jour 3

- [ ] App `config` + tables `system_settings` / `scheduled_jobs`
- [ ] `ldap_service` **avant** les vues register / login LDAP
- [ ] Seed **référentiels** (régions + `YAS`) ; **0** user AD en seed ; jean.dupont `ldap_dn` NULL
- [ ] `POST /register/check-ad` + `POST /register/ad` + `POST /register` dans Swagger
- [ ] D02 = seul JIT ; `login/ldap` ne crée jamais de user
- [ ] `POST /login/ldap` testé sur un compte **D02**, pas sur seed
- [ ] 401 unique login LDAP (inconnu YAS / bind KO / AD non loggable / rate-limit)
- [ ] 403 YAS seulement **après** bind AD OK (`ACCOUNT_PENDING` / `DISABLED` / `LOCKED`)
- [ ] 503 si annuaire injoignable ; **pas** de fallback automatique vers AUTH-A
- [ ] `complete_login` réutilisé (D02 `PASSWORD`, login LDAP `LDAP`)
- [ ] Job AUTH-16 coupe `is_active` (users avec `ldap_dn` seulement)
- [ ] D05 approve/reject (rôle ADMIN) ; pending → 403
- [ ] 0 secret LDAP dans `.env` / git
- [ ] AUTH-A, `/admin/`, `/health` intacts
- [ ] SIRH non modifié

---

## Interdits

- Seed ou insert admin d’un user « déjà AD » (`ldap_dn` posé à la main)
- Créer l’user au **login** (JIT) — uniquement `register/ad`
- Copier `userAccountControl` en colonne `users`
- Mapper groupe AD → `role_id`
- Stocker le MDP AD
- Coder AUTH-C (QR Authenticator) dans le même incrément
- `docker compose down -v`

---

## Après le jour 3

Jour 4 prévu (MVP §1) : **AUTH-C** — QR Google Authenticator + TOTP à chaque login (MDP **et** LDAP) **et** à la fin de `register/ad`. Plus de JWT tant que `POST /mfa/verify` n’est pas OK.
