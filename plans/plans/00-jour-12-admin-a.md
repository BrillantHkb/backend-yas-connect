# Jour 12 — ADMIN-A (cycle de vie compte, audit, régions)

**Statut :** clos (2026-09-11).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–11 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 11](00-jour-11-auth-r.md)).  
`HasPermission` **déjà** là. Perms ADMIN-A **déjà** seedées (jour 11). **Livré :** liste/fiche, create RH, disable/enable, reset MDP, kick, audit, CRUD régions, skip TOS `/admin/*`.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §9 — *Comptes*) :


| Fonction MVP                                   | Ticket      | Statut                          |
| ---------------------------------------------- | ----------- | ------------------------------- |
| Connexion + MFA + appareils + droits HTTP      | A–R         | **fait** (jours 1–11)           |
| **Liste / fiche comptes, créer, couper, kick** | **ADMIN-A** | **fait** (ce jour)              |
| Ma fiche / photo                               | PROF-A      | [jour 13](00-jour-13-prof-a.md) |


**À quoi ça sert (MVP) :** le RH crée un compte hors AD sans ticket SQL ; un admin coupe un compte (sessions mortes), reset le MDP app, ou kick un poste volé, sans toucher l’AD. L’audit se lit en HTTP. Les régions se gèrent ici (l’inscription lit déjà `GET /directory/regions`).

**Plan métier (code à coller) :** [ADMIN-A-lifecycle-audit.md](iam_plans/ADMIN-A-lifecycle-audit.md) (ADM-01 … 08).  
Chemins lab = ce fichier (`views/admin_users.py`, `views/admin_audit.py`, `views/admin_regions.py` — **pas** `views_admin_users.py` à la racine IAM).

**Livré :** filtres `GET /admin/users` + fiche `{id}` ; `POST /admin/users` (USER hors AD) ; disable / enable / reset MDP / kick ; `GET /admin/audit-logs` ; CRUD `/admin/regions` ; `ComplianceGates` skip `/api/v1/admin/*`. 0 migration.

**Objectif du jour (fait) :**

1. Étendre `GET /admin/users` (filtres ADM-01) + `GET /admin/users/{id}` (fiche, jamais de secret).
2. `POST /admin/users` : RH hors AD, toujours `USER`, actif, MFA au 1er login.
3. Disable / enable hors-AD ; reset MDP app ; kick sessions (`revoke_sessions` reason `ADMIN`).
4. `GET /admin/audit-logs` lecture seule, paginée.
5. CRUD `/admin/regions` (seed 5 **déjà** là — ne pas re-seeder autrement qu’idempotent).
6. `ComplianceGates` : **pas** de porte CGU/wizard sur `/api/v1/admin/`* (AUTH-R `HasPermission` suffit).

**Hors jour 12 :** invitation mail, impersonation, export RGPD, soft-delete, disable du compte **AD** (400 `LDAP_MANAGED` ; coupure = AD + AUTH-16), CRUD segments / `user_segments` (ANNUAIRE-B/C), `open_assignment` à la création (ANNUAIRE-C), PROF-A (`PATCH /me`, avatar, `display_name` colonne), recoder AUTH-R rôles/perms.

---



## Pourquoi ce jour (après AUTH-R)

Sans HTTP create / disable / kick, le RH passe par Django `/admin/` cookie ou SQL. Le MVP §9 demande ça **derrière JWT + perm**, pas derrière `is_staff`. Les codes sont seedés depuis hier : il manque les vues.

```text
Admin JWT + HasPermission (pas de porte AUTH-F)
    GET  /admin/users?q=&pending=&is_active=&is_locked=&role_code=&region_id=&segment_id=
    GET  /admin/users/{id}
    POST /admin/users
    POST /admin/users/{id}/disable | enable | password | sessions/revoke-all
    GET  /admin/audit-logs
    CRUD /admin/regions

Déjà là (ne pas casser)
    POST …/approve | reject | unlock | mfa/reset
    PATCH …/role
    GET  …/logins
```

---



## Paliers (figés pour ce jour)


| Sujet          | Choix jour 12                                                                                                                 | Plus tard              |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| Portes AUTH-F  | `/api/v1/admin/*` **hors** TOS/onboarding                                                                                     | —                      |
| Liste          | Même URL D05 ; `pending=true` = file ; perm `iam.user.read`                                                                   | —                      |
| Create         | Toujours `USER`, `pending_approval=false`, `is_active=true`, `ldap_dn=NULL`                                                   | Promotion = R09 (déjà) |
| `display_name` | **calculé** `get_full_name()` (prénom+nom ou email) — **pas** de colonne                                                      | PROF-A                 |
| `notif prefs`  | **pas** ce jour (pas de table) ; prefs + privacy déjà `create_user`                                                           | NOTIF-A                |
| ANNUAIRE-C     | create **n’écrit pas** `user_segments`                                                                                        | jour ANNUAIRE-C        |
| AD             | create / disable / enable → **400** `LDAP_MANAGED` si `ldap_dn`                                                               | AUTH-16                |
| Dernier ADMIN  | disable → **409** `LAST_ADMIN` (même règle que R09)                                                                           | —                      |
| Soi-même       | disable / reset MDP / revoke-all → **400** `CANNOT_ACT_ON_SELF`                                                               | unlock I **inchangé**  |
| Reset MDP      | Body `new_password` obligatoire ; **jamais** dans la réponse ; politique + history G ; logout-all ; LDAP **OK** (MDP **app**) | —                      |
| Kick           | `revoke_sessions(..., reason="ADMIN")` ; `is_active` inchangé                                                                 | —                      |
| Régions        | Seed 5 **déjà** `seed_iam` ; HTTP CRUD seulement                                                                              | —                      |
| Audit          | Lecture ; pas de DELETE                                                                                                       | —                      |


Codes lab (3 segments, jour 11) : `iam.user.role_assign`, `iam.user_security.read` — **pas** les 4 segments du ticket AUTH-R.

---



## 1. Tables

**0 migration.** `region`, `users`, `audit_logs`, `sessions`, `password_history` existent.  
**Interdit :** `docker compose down -v`.

`audit_logs.action` nouveaux : `USER_CREATE` / `USER_DISABLE` / `USER_ENABLE` / `PASSWORD_ADMIN_RESET` / `SESSION_REVOKE_ALL` / `REGION_CREATE` / `REGION_PATCH` / `REGION_DELETE`.

---



## 2. Settings + seed

Aucun nouveau `YAS_*`.  
`seed_iam` : les 5 régions **restent** idempotentes (déjà jour 3). Ne pas dupliquer la table.

---



## 3. Middleware + services


| Fichier                                   | Sert à                                                                                                        |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `apps/iam/middlewares/compliance.py`      | `ComplianceGates` : si path sous `/api/v1/admin` → **True** (après HasPermission)                             |
| `apps/iam/services/admin_user_service.py` | **nouveau.** liste filtrée, fiche, create, disable, enable, reset MDP, kick                                   |
| `apps/iam/services/region_service.py`     | **nouveau.** CRUD régions + `REGION_IN_USE`                                                                   |
| `apps/iam/services/register_service.py`   | `list_users` **délègue** à `admin_user_service` (garder le nom pour D05) ou y déplacer les filtres            |
| `apps/iam/services/session_service.py`    | réutiliser `revoke_sessions` (pas de copie)                                                                   |
| `apps/iam/services/password_service.py`   | extraire ou appeler `_assert_not_reused` / `_archive_and_set` pour le reset admin (pas recopier la politique) |


Create : `suggest_username` + `enforce_password_policy` + `User.objects.create_user` (matrice USER auto) + `region` / `segment_id` via `_validate_region_segment`.  
`role_code` / `role_id` dans le body → **400** `FIELD_FORBIDDEN`.  
Email déjà pris → **409** `EMAIL_TAKEN`. Matricule déjà pris (non NULL) → **409** `MATRICULE_TAKEN`.

Disable dernier `role.code=ADMIN` → **409** `LAST_ADMIN`.  
Enable si `pending_approval` → **400** `STILL_PENDING`. Enable **ne** pose **pas** `is_locked=false`.

Reset MDP : LDAP **autorisé**. Réponse `{ "ok": true }` sans password.

---



## 4. HTTP

Arborescence `views/`, `serializers/`, `urls/admin.py`. **Suffixes** `users/<uuid>/…` **avant** `users/<uuid>`.


| Fichier                               | Rôle                                                                          |
| ------------------------------------- | ----------------------------------------------------------------------------- |
| `apps/iam/views/admin_users.py`       | étendre liste ; ajouter create, detail, disable, enable, password, revoke-all |
| `apps/iam/views/admin_audit.py`       | `GET /admin/audit-logs`                                                       |
| `apps/iam/views/admin_regions.py`     | CRUD régions                                                                  |
| `apps/iam/serializers/admin_users.py` | create, reason, password, query optionnels                                    |
| `apps/iam/urls/admin.py`              | étendre                                                                       |



| Méthode | Chemin                                         | Perm                       |
| ------- | ---------------------------------------------- | -------------------------- |
| GET     | `/api/v1/admin/users`                          | `iam.user.read`            |
| GET     | `/api/v1/admin/users/{id}`                     | `iam.user.read`            |
| POST    | `/api/v1/admin/users`                          | `iam.user.create`          |
| POST    | `/api/v1/admin/users/{id}/disable`             | `iam.user.disable`         |
| POST    | `/api/v1/admin/users/{id}/enable`              | `iam.user.enable`          |
| POST    | `/api/v1/admin/users/{id}/password`            | `iam.user.reset_password`  |
| POST    | `/api/v1/admin/users/{id}/sessions/revoke-all` | `iam.session.revoke_other` |
| GET     | `/api/v1/admin/audit-logs`                     | `iam.audit.read`           |
| GET     | `/api/v1/admin/regions`                        | `iam.region.read`          |
| GET     | `/api/v1/admin/regions/{id}`                   | `iam.region.read`          |
| POST    | `/api/v1/admin/regions`                        | `iam.region.manage`        |
| PATCH   | `/api/v1/admin/regions/{id}`                   | `iam.region.manage`        |
| DELETE  | `/api/v1/admin/regions/{id}`                   | `iam.region.manage`        |


Liste — query (tout optionnel sauf limites) :


| Param                      | Règle                                                                                 |
| -------------------------- | ------------------------------------------------------------------------------------- |
| `q`                        | `icontains` email **ou** username **ou** matricule **ou** first_name **ou** last_name |
| `pending`                  | `true` = `pending_approval` (D05 inchangé)                                            |
| `is_active` / `is_locked`  | `true` / `false`                                                                      |
| `role_code`                | exact                                                                                 |
| `region_id` / `segment_id` | UUID                                                                                  |
| `limit`                    | défaut 50, 1–100                                                                      |
| `offset`                   | ≥ 0                                                                                   |


**200** `{ "count", "results": [ … ] }`.  
Ligne liste : champs D05 **plus** `display_name`, `matricule`, `role` `{code, name}`, `is_locked`, `last_login`. `ldap_bound` boolean — **jamais** le DN.

Fiche `{id}` : liste + `phone`, `job_title`, `region` `{id, code, name}` (nullable), `segment_id`, `first_login`, `locked_at`. **404** `NOT_FOUND` si absent (pas de 403 qui confirme). Jamais hash / refresh / TOTP / `ldap_dn`.

Create body : `email`, `password`, `first_name`, `last_name`, `phone`, `job_title`, `region_id`, `segment_id`, `matricule` (matricule optionnel). `region_id` + `segment_id` **obligatoires**. **201** = fiche. Audit `USER_CREATE`.

Disable / enable : body optionnel `{ "reason" }` → `metadata.reason`. Disable : `is_active=false`, sessions tuées, `pending_approval` inchangé → login **403** `ACCOUNT_DISABLED`.

Password : `{ "new_password" }` ; **200** `{ "ok": true }`. Audit `PASSWORD_ADMIN_RESET`.

Revoke-all : **200** `{ "revoked": <n> }`. Audit `SESSION_REVOKE_ALL`.

Audit-logs query : `user_id` (acteur), `entity_type` + `entity_id`, `module`, `action`, `success`, `from` / `to` (`created_at`), `limit` / `offset`. **200** `{ "count", "results" }` — lignes telles qu’en base (pas de hash : les services n’en écrivent pas).

Régions : POST `{ "code", "name" }` — `code` `^[A-Z][A-Z0-9_]*$` 2–50, unique. PATCH `name` (et `code` si pas gelé — lab : `code` **immutable** après create, comme les rôles). DELETE users liés → **409** `REGION_IN_USE` (`users_count`). Audit `REGION_`*.

---



## 5. Impact tests existants


| Fichier                | Adapter                                                                                             |
| ---------------------- | --------------------------------------------------------------------------------------------------- |
| `test_auth_d.py`       | `GET /admin/users` + `pending=true` : **200** ; `results[].email` encore là ; champs **en plus** OK |
| `test_auth_r.py`       | jean approve encore 403 ; admin approve 200                                                         |
| `test_auth_c.py` / `i` | MFA reset / unlock inchangés                                                                        |


`ComplianceGates` : un admin JWT **sans** TOS peut appeler `/admin/users` (voulu). Ne pas casser les tests qui `close_gates` déjà.

---



## 6. Tests nouveaux (`test_admin_a.py`)


| ID  | Cas                     | Attendu                                                            |
| --- | ----------------------- | ------------------------------------------------------------------ |
| 01  | GET liste jean          | **403** `FORBIDDEN` ; `permission` = `iam.user.read`               |
| 01  | GET `pending=true`      | file D05 (count / email)                                           |
| 01  | GET `{id}`              | 200 ; pas de `password` / hash / `ldap_dn`                         |
| 01  | GET uuid inconnu        | **404** `NOT_FOUND`                                                |
| 02  | POST create             | **201** ; `role.code=USER` ; `is_active` ; login → MFA enroll      |
| 02  | POST `role_code`        | **400** `FIELD_FORBIDDEN`                                          |
| 02  | POST email pris         | **409** `EMAIL_TAKEN`                                              |
| 03  | disable hors-AD         | login **403** `ACCOUNT_DISABLED` ; 0 session active                |
| 03  | disable dernier ADMIN   | **409** `LAST_ADMIN`                                               |
| 03  | disable `ldap_dn`       | **400** `LDAP_MANAGED`                                             |
| 03  | disable soi             | **400** `CANNOT_ACT_ON_SELF`                                       |
| 04  | enable pending          | **400** `STILL_PENDING`                                            |
| 04  | enable après disable    | login + TOTP OK ; `is_locked` inchangé                             |
| 05  | reset MDP               | politique ; logout-all ; 200 **sans** password ; login nouveau MDP |
| 05  | reset LDAP              | **200** (MDP app) ; `ldap_dn` inchangé                             |
| 06  | revoke-all              | `revoked` ≥ 1 ; `is_active` encore true ; refresh 401              |
| 06  | revoke-all soi          | **400** `CANNOT_ACT_ON_SELF`                                       |
| 07  | GET audit après disable | ligne `USER_DISABLE`                                               |
| 08  | POST région             | **201** ; DELETE sans user **204**                                 |
| 08  | DELETE région in use    | **409** `REGION_IN_USE`                                            |
| —   | sans JWT                | **401**                                                            |
| —   | `/health`, `/api/docs/` | schéma contient `/admin/users/{id}` et `/admin/regions`            |


Helper MFA : `login_until_jwt`. Portes : `close_gates` pour les users qui passent par `/me` ; **pas** obligatoire pour les appels `/admin/`*.  
Create : `region` + `segment` YAS (fixtures AUTH-D). MDP `SecretApp456!`.

Régression : D (liste/approve) + R (R09 `LAST_ADMIN` encore vrai sur **rôle** ; disable = **autre** endpoint).

---



## 7. Vérif manuelle

```powershell
python manage.py check
pytest apps/iam/tests/test_admin_a.py apps/iam/tests/test_auth_d.py apps/iam/tests/test_auth_r.py --reuse-db
```

`admin@yas.tg` : créer `marie.koevi@yas.tg`, login → TOTP enroll. Disable → 403 `ACCOUNT_DISABLED`. Enable → MFA.  
Kick jean : sessions mortes, compte encore actif.  
`GET /admin/audit-logs?action=USER_DISABLE`.  
`/admin/` cookie staff : **pas** ces routes (JWT + perm).

---



## Checklist jour 12

- [x] `ComplianceGates` skip `/api/v1/admin/*`
- [x] Liste filtrée + fiche `{id}` sans secrets
- [x] POST create RH (USER, username D03, MFA au 1er login)
- [x] Disable / enable + `LDAP_MANAGED` / `LAST_ADMIN` / `CANNOT_ACT_ON_SELF` / `STILL_PENDING`
- [x] Reset MDP admin + kick (`revoke_sessions`)
- [x] `GET /admin/audit-logs`
- [x] CRUD `/admin/regions` + `REGION_IN_USE`
- [x] `test_admin_a.py` + régression D/R
- [x] SIRH non modifié
- [x] 0 `docker compose down -v`

---



## Interdits

- Recoder AUTH-R (CRUD rôles / matrice / `PATCH …/role`)
- Coder PROF-A / PROF-B/C / PRES-A / ANNUAIRE write / `GET /users` people-picker
- `open_assignment` `user_segments` (ANNUAIRE-C)
- Disable / enable un compte **AD** (`ldap_dn`)
- Invitation magique, impersonation, DELETE user, DELETE audit
- SMTP / Mailhog bloquant
- Changer le SIRH

---



## Après le jour 12

Jour 13 : [00-jour-13-prof-a.md](00-jour-13-prof-a.md) — **PROF-A** (fiche `/me`, `PATCH /me`, avatar SKIPPED lab, `GET /users/{id}` collègue).

---



## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour**. Le jour 2 (admin + Swagger) est un extra déjà clos.


| Jours  | Plan                                           | Ticket MVP                          |
| ------ | ---------------------------------------------- | ----------------------------------- |
| 0      | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health` |
| 1–2    | AUTH-A ; admin + Swagger                       | Connexion locale ; lab admin        |
| 3–11   | D+B … AUTH-R                                   | §1 entrer + droits HTTP             |
| **12** | **ADMIN-A** (ce plan)                          | §9 comptes                          |
| 13     | PROF-A                                         | §2 ma fiche / photo                 |
| 14     | PROF-B                                         | Préférences                         |
| 15     | PROF-C                                         | §2 visibilité                       |
| 16     | PRES-A                                         | §2 statut en ligne                  |
| 17     | ANNUAIRE-A                                     | §3 recherche collègue               |
| 18     | CRYPTO-00                                      | §6 décision E2E                     |
| 19     | MEDIA-R + MEDIA-A                              | §4 upload                           |
| 20     | NOTIF-R + NOTIF-A                              | §5 alertes                          |
| 21     | CRYPTO-R + CRYPTO-A                            | Clés HTTP                           |
| 22     | MESSAGERIE-R, A, B                             | §7 1-to-1                           |
| 23     | MESSAGERIE-C, D                                | §7 groupes + temps réel             |
| 24     | MESSAGERIE-E (partiel), F, G                   | §7 enrichissements                  |
| 25     | MEDIA-B, C, D, E                               | §4 album / vocal / coffre           |
| 26     | APPELS-R, A, B, C                              | §8 appel 1-1                        |
| 27     | APPELS-D, E, G                                 | §8 écran / CR                       |


**Total : 28 plans (jours 0 à 27).**  
Déjà clos : **13** (0–12). Restant : **15** (13–27).

Hors ce compteur (A→Z §4.2) : ANNUAIRE-B/C/D, MEDIA-F, APPELS-F, mentions / modération, social, IA.