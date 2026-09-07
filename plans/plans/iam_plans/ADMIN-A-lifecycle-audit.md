# ADMIN-A — Cycle de vie compte, audit, régions (ADM-01 … 08)

**Produit :** YAS Connect uniquement (pas le SIRH).  
**Préalable :** Phase 0 + **AUTH-R** (`HasPermission`) + **AUTH-D** (D05 approve/reject) + **AUTH-G** (politique MDP) + **AUTH-H** (`revoke_sessions`) + **AUTH-I** (unlock).  
**Attributs :** [IAM](../../catalogues/IAM-catalogue-tables.md) · [Annuaire](../../catalogues/ANNUAIRE-catalogue-tables.md) (lecture `segment_id` à la création).  
**Models :** [code/iam_models.py](../code/iam_models.py).

**Périmètre :** liste / fiche admin d’un user, création RH, disable / enable, reset MDP **applicatif** par admin, kick sessions, lecture `audit_logs`, **CRUD `region`**.

Le CRUD **rôles + permissions + matrice** est **déjà** [AUTH-R06/07/08](AUTH-R-roles-permissions.md). Ne pas le dupliquer.

---

## Cartographie


| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **ADM-01** | **Gardé** | `GET /admin/users` (filtres, pas seulement pending) + `GET /admin/users/{id}` | lecture |
| **ADM-02** | **Gardé** | `POST /admin/users` : création RH hors AD, rôle `USER`, actif, enroll MFA au 1er login | `users` + prefs + privacy + notif prefs |
| **ADM-03** | **Gardé** | `POST …/disable` : `is_active=false` + `revoke_sessions` | `users` ; sessions ; audit |
| **ADM-04** | **Gardé** | `POST …/enable` : `is_active=true`. Ne déverrouille pas (`is_locked` = AUTH-I) | `users` ; audit |
| **ADM-05** | **Gardé** | `POST …/password` : pose un MDP app (politique AUTH-G) + logout-all | hash, history, sessions |
| **ADM-06** | **Gardé** | `POST …/sessions/revoke-all` : kick sans changer `is_active` | sessions ; audit |
| **ADM-07** | **Gardé** | `GET /admin/audit-logs` : pagination + filtres | lecture |
| **ADM-08** | **Gardé** | CRUD `/admin/regions` | `region` ; audit |


**Hors incrément :** invitation magique par mail, impersonation, export RGPD, soft-delete, disable d’un compte **AD** depuis YAS (c’est l’AD + AUTH-16), CRUD segments / `user_segments` ([ANNUAIRE-B](../annuaire_plans/ANNUAIRE-B-arbre-segments.md) / [C](../annuaire_plans/ANNUAIRE-C-affectations.md)), UI front. SMTP = [A→Z §4.3](../00-application-A-Z.md) (Mailhog lab, pas bloquant).

---

## Décisions figées


| Sujet | Choix |
|-------|--------|
| Liste D05 | Même `GET /admin/users`. `pending=true` reste le filtre inscription hors AD. Perm liste = `iam.user.read` (plus `iam.user.approve` sur le GET) |
| Création | Toujours `role=USER`, `pending_approval=false`, `is_active=true`, `ldap_dn=NULL`. Promotion = **AUTH-R09** |
| AD | `ldap_dn` non NULL → **400** `LDAP_MANAGED` sur create / disable / enable. Coupure = AD puis job AUTH-16 |
| Dernier ADMIN | Disable du dernier ADMIN → **409** `LAST_ADMIN` (comme R09) |
| Soi-même | Disable / reset MDP / revoke-all sur **son** id → **400** `CANNOT_ACT_ON_SELF` (unlock AUTH-I inchangé) |
| MDP admin | Body `new_password` **obligatoire** (l’admin le communique hors bande). **Jamais** renvoyé en JSON. Politique + `password_history` = AUTH-G. `logout_all` implicite |
| Kick | Réutilise `revoke_sessions` AUTH-H (`revoke_reason=ADMIN`) |
| Audit | Lecture seule. Pas de DELETE. Jobs (`user_id` NULL) visibles |
| Région | Table IAM `region`. Seed 5 régions Togo (ADM-08). DELETE **409** `REGION_IN_USE` si un `users.region_id` pointe encore |
| Portes AUTH-F | Vues **admin** : **pas** de porte CGU/wizard. `HasPermission` suffit |
| RBAC | Tout JWT + `HasPermission`. ADMIN seed = toutes `is_system` |

---

## Contrat HTTP

Préfixe `/api/v1`. JWT.

### ADM-01 — `GET /api/v1/admin/users`

`required_permission = iam.user.read`.

| Query | Défaut | Règle |
|-------|--------|--------|
| `q` | — | trgm / `ILIKE` sur email, username, matricule, first_name, last_name |
| `pending` | — | `true` = `pending_approval=true` (file D05) |
| `is_active` | — | `true` / `false` |
| `is_locked` | — | `true` / `false` |
| `role_code` | — | `USER` / `ADMIN` / custom |
| `region_id` | — | UUID |
| `segment_id` | — | UUID |
| `limit` | 50 | 1–100 |
| `offset` | 0 | ≥ 0 |

**200** `{ "count", "results": [ { id, email, username, display_name, matricule, role, is_active, pending_approval, is_locked, ldap_bound, last_login, created_at } ] }`  
`ldap_bound` : **boolean** (`ldap_dn` posé), pas le DN.

### ADM-01 — `GET /api/v1/admin/users/{id}`

Même perm. **404** si absent (pas de 403 qui confirme).  
Fiche : champs liste + `first_name`, `last_name`, `phone`, `job_title`, `region`, `segment_id`, `first_login`, `locked_at`. **Jamais** hash / refresh / TOTP.

Approve / reject / unlock / rôle / MFA reset : **inchangés** (D05, I-64, R09, C-24).

### ADM-02 — `POST /api/v1/admin/users`

`required_permission = iam.user.create`.

```json
{
  "email": "marie.koevi@yas.tg",
  "password": "SecretApp456!",
  "first_name": "Marie",
  "last_name": "Koevi",
  "phone": "+22890111111",
  "job_title": "RH",
  "region_id": "<uuid>",
  "segment_id": "<uuid>",
  "matricule": "TG2026100"
}
```

`username` auto (règle D03). `region_id` / `segment_id` **obligatoires** (même AUTH-D).  
Dès [ANNUAIRE-C](../annuaire_plans/ANNUAIRE-C-affectations.md) : `open_assignment(..., assigned_by=request.user)` dans la même transaction.  
**201** fiche admin. Audit `USER_CREATE`.  
**409** `EMAIL_TAKEN` / `MATRICULE_TAKEN`. **400** politique MDP / `REGION_INVALID` / `SEGMENT_INVALID`. Champ `role_code` / `role_id` → **400** `FIELD_FORBIDDEN`.

### ADM-03 / 04 — disable / enable

`POST /api/v1/admin/users/{id}/disable` — `iam.user.disable`  
`POST /api/v1/admin/users/{id}/enable` — `iam.user.enable`

Body optionnel `{ "reason": "…" }` → `audit_logs.metadata.reason`.  
Disable : `is_active=false`, `pending_approval` **inchangé** (reste `false` si déjà approuvé) → login **403** `ACCOUNT_DISABLED`. Kill sessions.  
Enable : `is_active=true` seulement. Compte encore `pending_approval` → **400** `STILL_PENDING` (passer par D05).  
LDAP → **400** `LDAP_MANAGED`.

### ADM-05 — reset MDP

`POST /api/v1/admin/users/{id}/password` — `iam.user.reset_password`

```json
{ "new_password": "SecretApp789!" }
```

Même `enforce_password_policy` + history qu’AUTH-G. Logout-all. Audit `PASSWORD_ADMIN_RESET`. **200** `{ "ok": true }`.  
LDAP **autorisé** (MDP **app** seulement ; bind AD inchangé).

### ADM-06 — kick sessions

`POST /api/v1/admin/users/{id}/sessions/revoke-all` — `iam.session.revoke_other`  
`revoke_sessions(..., reason="ADMIN")`. **200** `{ "revoked": <n> }`. Audit `SESSION_REVOKE_ALL`.

### ADM-07 — audit

`GET /api/v1/admin/audit-logs` — `iam.audit.read`

| Query | Sens |
|-------|------|
| `user_id` | Acteur |
| `entity_type` + `entity_id` | Cible |
| `module` | `IAM` / … |
| `action` | ex. `USER_DISABLE` |
| `success` | bool |
| `from` / `to` | `created_at` ISO |
| `limit` / `offset` | 1–100 / ≥ 0 |

**200** lignes brutes. Les services n’y mettent **jamais** un hash.  
Pas de DELETE.

### ADM-08 — régions

| Méthode | Chemin | Perm |
|---------|--------|------|
| GET | `/admin/regions` | `iam.region.read` |
| GET | `/admin/regions/{id}` | `iam.region.read` |
| POST | `/admin/regions` | `iam.region.manage` |
| PATCH | `/admin/regions/{id}` | `iam.region.manage` |
| DELETE | `/admin/regions/{id}` | `iam.region.manage` |

POST `{ "code": "MARITIME", "name": "Maritime" }` — `code` SCREAMING_SNAKE 2–50, unique.  
DELETE si users liés → **409** `REGION_IN_USE`. Audit `REGION_*`.

Liste **publique** (inscription) = [ANNUAIRE-A](../annuaire_plans/ANNUAIRE-A-recherche-referentiels.md) `GET /directory/regions`.

---

## Seed `region`

`seed_iam` (idempotent) :

| code | name |
|------|------|
| `MARITIME` | Maritime |
| `PLATEAUX` | Plateaux |
| `CENTRALE` | Centrale |
| `KARA` | Kara |
| `SAVANES` | Savanes |

---

## 1. Fichiers

```
apps/iam/views_admin_users.py      # étendre D05
apps/iam/views_admin_audit.py
apps/iam/views_admin_regions.py
apps/iam/services/admin_user_service.py
```

`complete_login` / AUTH-16 **inchangés** (`LDAP_MANAGED` évite le conflit enable YAS vs sync AD).

---

## 2. Tests (acceptation)


| ID | Cas | Attendu |
|----|-----|---------|
| 01 | GET liste USER jean | 403 |
| 01 | GET `pending=true` | file D05 |
| 01 | GET `{id}` | pas de hash |
| 02 | POST create | 201 USER actif ; MFA au login |
| 02 | POST `role_code` | 400 `FIELD_FORBIDDEN` |
| 03 | disable hors-AD | `ACCOUNT_DISABLED` au login ; sessions mortes |
| 03 | disable dernier ADMIN | 409 `LAST_ADMIN` |
| 03 | disable `ldap_dn` posé | 400 `LDAP_MANAGED` |
| 03 | disable soi | 400 `CANNOT_ACT_ON_SELF` |
| 04 | enable pending | 400 `STILL_PENDING` |
| 05 | reset MDP | politique ; logout-all ; 200 sans password |
| 06 | revoke-all | n sessions ; user encore `is_active` |
| 07 | GET audit après disable | ligne `USER_DISABLE` |
| 08 | POST région | 201 ; DELETE in use 409 |
| — | sans perm | 403 |


---

## Critères d’acceptation

- [ ] Liste admin ≠ seulement pending ; fiche sans secrets
- [ ] Create RH USER ; disable/enable hors-AD ; LDAP géré par AD
- [ ] Reset MDP admin + kick sessions
- [ ] Lecture audit paginée
- [ ] CRUD `region` + seed 5 régions TG
- [ ] Rôles/perms **pas** recopiés (AUTH-R)
- [ ] Perms seed ; spec seulement

---

## Écarts documents liés

- **AUTH-D05** : GET pending = filtre ADM-01 ; perm GET = `iam.user.read`.
- **AUTH-G** : reset admin **n’est plus** hors incrément — ici. Self-service TOTP inchangé.
- **AUTH-H** : kick d’un autre user = ADM-06.
- **AUTH-R** : + 9 perms admin IAM ; total seed **58** `is_system` (27 self + 31 admin, dont `annuaire.*`).
- **ANNUAIRE-A** : recherche collègues + listes directory publiques + seed org.
- **ANNUAIRE-C** : create RH ouvre une ligne `user_segments`.
- **AUTH-16** : ne réactive pas un compte disable côté YAS (les LDAP restent côté AD).
