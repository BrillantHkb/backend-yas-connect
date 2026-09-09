# Jour 7 — AUTH-F (CGU + wizard première connexion)

**Statut :** à faire.  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–6 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 6](00-jour-6-auth-j.md)).  
JWT après MFA (jour 4) **déjà** émis. `first_login` **déjà** posé dans `complete_login`. Il n’y a **pas** encore de portes CGU / wizard : un JWT ouvre `/me/devices*` tout de suite.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §1 — *Entrer dans l’application*) :


| Fonction MVP                                    | Ticket     | Statut              |
| ----------------------------------------------- | ---------- | ------------------- |
| Connexion + MFA + appareils + QR 2ᵉ écran       | A–E, J     | **fait** (jours 1–6) |
| **Conditions d’utilisation**                    | **AUTH-F** | **ce jour** (CGU)   |
| **Premier paramétrage** (langue / fuseau / son) | **AUTH-F** | **ce jour** (wizard) |
| Mot de passe oublié / changer MDP               | AUTH-G     | plus tard           |
| Déconnexion                                     | AUTH-H     | plus tard           |


**À quoi ça sert (MVP) :** après le 1er TOTP, l’app **n’ouvre pas** le chat tant que la personne n’a pas accepté les règles YAS et choisi langue / fuseau / sonnerie. Session JWT **oui** ; métier **non**.

**Plan métier (code à coller) :** [AUTH-F-onboarding.md](iam_plans/AUTH-F-onboarding.md) (AUTH-37 … 42). AUTH-39 (MDP forcé) **abandonné**.

**Déjà en base :** `users.first_login`, `users.language` / `timezone`, `user_preferences` (langue, tz, `notification_sound`).  
**Pas encore en base :** `tos_accepted_at`, `tos_version`, `onboarding_completed_at` (AUTH-F dit « déjà dans iam_models » — **absents** de `apps/iam/models.py` aujourd’hui → **migration additive**).

**Objectif du jour :**

1. Colonnes CGU / wizard + seed jean/admin **portes fermées**.
2. `GET /me` + `gates` ; `GET/POST /me/tos*` ; `GET/PATCH /me/onboarding` ; `POST /me/onboarding/complete`.
3. Middleware : JWT OK mais 403 `TOS_REQUIRED` puis `ONBOARDING_REQUIRED` sur le métier (`/me/devices`, admin API, etc.).
4. Adapter les fixtures A/C/E/J : users de test **déjà** CGU + wizard (sinon régression 403).

**Hors jour 7 :** AUTH-G (MDP), AUTH-H (logout / sessions liste), AUTH-I, AUTH-R (`HasPermission`), PROF-A (fiche complète / avatar), CMS des CGU, `POST /me/tos/decline`, `GET /messages` (pas d’app messaging).

---



## Pourquoi ce jour (après AUTH-J)

Sans portes, un compte neuf (inscription AUTH-D) entre dans l’API appareils / futur chat dès le TOTP. Le MVP exige : **1. CGU → 2. wizard → app**.

```text
TOTP OK → complete_login → JWT (first_login posé si NULL)
    → GET /me  (toujours 200 : gates)
    → métier  → 403 TOS_REQUIRED tant que pas accept
    → POST /me/tos/accept
    → métier  → 403 ONBOARDING_REQUIRED
    → PATCH /me/onboarding + POST /me/onboarding/complete
    → métier 200
```

Refus = ne pas appeler accept : JWT valide, API bloquée, **pas** de suppression de compte.

---



## Paliers (figés pour ce jour)


| Sujet | Choix jour 7 | Plus tard |
| ----- | ------------ | --------- |
| Auth vues | JWT + `IsAuthenticated` | AUTH-R : `iam.profile.read` / `iam.tos.manage` / `iam.onboarding.manage` |
| Version CGU | `.env` `YAS_TOS_VERSION` + `YAS_TOS_URL` | `system_settings` `legal.tos_*` |
| Logout pendant les portes | **pas** de routes AUTH-H | allowlist + `/auth/logout*` |
| Heartbeat | allowlist `PATCH /me/devices/current` | — |
| Liste appareils / lien QR | **bloqués** tant que portes KO | — |
| `GET /me` | `public_user` existant + `gates` (pas PROF-A) | avatar, display_name, présence |
| Métier « bloqué » dans les tests | `GET /me/devices` (existe) | `GET /messages` |


Le stub AUTH-F met `/api/v1/me` en préfixe : ça **ouvrirait** `/me/devices`. **Jour 7 :** `GET /me` = **égalité exacte** du path ; `/me/tos` et `/me/onboarding` = préfixes dédiés.

DRF pose `request.user` **dans la vue**, pas dans Django `MIDDLEWARE`. `ComplianceMiddleware` **décode le Bearer** (même logique que `YasJWTAuthentication` : jti → session active). Pas de Bearer → laisser passer (login / health / directory).

---



## 1. Migration (additive)

**Interdit :** `docker compose down -v`.

Sur `User` :

- `tos_accepted_at` timestamptz NULL
- `tos_version` varchar(32) NULL
- `onboarding_completed_at` timestamptz NULL

```powershell
python manage.py makemigrations iam
python manage.py migrate
```

`first_login` : **0** changement (déjà AUTH-A).

---



## 2. Settings + seed

`.env` / `.env.example` :

```env
YAS_TOS_VERSION=2026-08-01
YAS_TOS_URL=https://connect.yas.tg/legal/cgu/2026-08-01
```

`seed_iam` : `jean.dupont` **et** `admin@yas.tg` → `tos_accepted_at=now`, `tos_version=YAS_TOS_VERSION`, `onboarding_completed_at=now` (idempotent si user déjà là : **mettre à jour** les 3 champs si NULL, pour le lab déjà seedé).

Inscription AUTH-D : les 3 restent **NULL** (compte neuf = portes ouvertes).

---



## 3. Middleware + services

| Fichier | Sert à |
| ------- | ------ |
| `apps/iam/middlewares/compliance.py` | Portes CGU puis wizard ; JSON `{success, code, message}` |
| `apps/iam/services/compliance_service.py` | `tos_ok`, `accept_tos`, `patch_onboarding`, `complete_onboarding`, `gates_payload` |
| `config/settings.py` | `MIDDLEWARE` après `AuthenticationMiddleware` |

Allowlist **sans** Bearer (skip total) : `/health`, `/api/schema`, `/api/docs`, `/admin/`, `/api/v1/auth/login*`, `/refresh`, `/mfa/*`, `/register*`, `/auth/device-link/*`, `/api/v1/directory/*`.

Allowlist **JWT + TOS KO** : `GET /api/v1/me` (exact), `/api/v1/me/tos*`, `POST /api/v1/auth/refresh`, `PATCH /api/v1/me/devices/current`.

Allowlist **JWT + TOS OK + onboarding KO** : + `/api/v1/me/onboarding*`.

Sinon 403 `TOS_REQUIRED` / `ONBOARDING_REQUIRED`.

`complete_login` : **ne pas** toucher aux portes. `first_login` inchangé.

---



## 4. HTTP

- `apps/iam/views/me.py` — `MeView` (GET)
- `apps/iam/views/compliance.py` — tos + onboarding
- `apps/iam/serializers/compliance.py`
- `apps/iam/urls/me.py` — `path("", …)` **et** tos / onboarding **avant** `devices/<uuid>`

`config/urls.py` : `api/v1/me/` include déjà `apps.iam.urls.me`. Ajouter `GET ""` = `/api/v1/me` (attention au slash Django `APPEND_SLASH`).

| Endpoint | Auth | Effet |
| -------- | ---- | ----- |
| `GET /api/v1/me` | JWT | `{ user, gates }` toujours 200 si session OK |
| `GET /api/v1/me/tos` | JWT | `{ version, url }` courante |
| `POST /api/v1/me/tos/accept` | JWT | Body `{ version }`. 409 si ≠ courante. Audit `TOS_ACCEPT` |
| `GET /api/v1/me/onboarding` | JWT | Prérempli `language` / `timezone` / `notification_sound` (défauts fr / Lomé / true) |
| `PATCH /api/v1/me/onboarding` | JWT | 3 champs ; écrit prefs **et** `users.language` / `timezone`. **Pas** `onboarding_completed_at` |
| `POST /api/v1/me/onboarding/complete` | JWT | Body vide. Exige `tos_ok`. Audit `ONBOARDING_COMPLETE` |

Bump `YAS_TOS_VERSION` : user avec ancienne `tos_version` → `tos_ok` faux ; wizard **non** rejoué.

---



## 5. Impact tests existants

`create_user` dans A/C/E/J/jour 2 : poser les 3 champs (helper `apps.iam.helpers.compliance.close_gates(user)` ou dans la fixture).  
Sinon `GET /me/devices` → 403.  
`test_auth_d` comptes frais : portes **NULL** (voulu).

---



## 6. Tests nouveaux (`test_auth_f.py`)


| Cas | Attendu |
| --- | ------- |
| 1er login MFA | `first_login` posé ; 2e login inchangé |
| User neuf + JWT | `GET /me` 200 ; `gates.tos_required` + `onboarding_required` |
| User neuf + `GET /me/devices` | 403 `TOS_REQUIRED` |
| Accept mauvaise version | 409 `TOS_VERSION_MISMATCH` |
| Accept OK | `tos_accepted_at` ; devices encore 403 `ONBOARDING_REQUIRED` |
| Complete sans CGU | 403 TOS |
| PATCH langue/tz/son puis complete | prefs + `users.language` ; devices 200 |
| jean.dupont seed | portes OK (après re-seed lab) |
| bump version CGU | 403 TOS ; `onboarding_completed_at` inchangé |
| pas d’endpoint skip MFA | 404 |
| `/health`, `/api/docs/` | 200 |


Régression : A/C/E/J/jour 2 encore verts **avec fixtures portes fermées**.

---



## 7. Vérif manuelle

```powershell
python manage.py makemigrations iam
python manage.py migrate
python manage.py seed_iam
python manage.py check
pytest apps/iam/tests/test_auth_f.py apps/iam/tests/test_auth_j.py apps/iam/tests/test_auth_e.py --reuse-db
```

Compte **neuf** (register local ou user test sans CGU) : login + MFA → JWT.  
`GET /me` → `tos_required`. `GET /me/devices` → 403. Accept + wizard + complete → devices 200.

`/admin/` cookie : **pas** coupé par les portes API.

---



## Checklist jour 7

- [ ] Migration `tos_*` + `onboarding_completed_at` (pas `down -v`)
- [ ] `.env` `YAS_TOS_VERSION` / `YAS_TOS_URL` ; seed jean + admin portes fermées
- [ ] `GET /me` + `gates` ; tos accept ; onboarding PATCH + complete
- [ ] Middleware : exact `/me` ; métier 403 ; refresh OK
- [ ] `first_login` inchangé dans `complete_login` ; AUTH-39 absent
- [ ] Fixtures A/C/E/J portes fermées ; `test_auth_f.py` + régression verts
- [ ] `/api/docs/` documente `/me`, tos, onboarding
- [ ] `/admin/` cookie et `/health` intacts
- [ ] SIRH non modifié

---



## Interdits

- `HasPermission` AUTH-R
- Coder AUTH-G / AUTH-H / PROF-A complet
- `docker compose down -v`
- Préfixe `/api/v1/me` qui autorise `/me/devices` pendant TOS KO
- Forcer un changement de MDP (AUTH-39)
- Skip MFA dans le wizard
- CMS / PDF CGU en base

---



## Après le jour 7

Jour suivant (A→Z **1g**) : **AUTH-G** — mot de passe (changement + oubli via Authenticator).
