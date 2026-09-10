# Jour 11 — AUTH-R (rôles & permissions)

**Statut :** à faire.  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–10 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 10](00-jour-10-auth-i.md)).  
Rôles `USER` / `ADMIN` **déjà** seedés. `users.role_id` unique. JWT claim `role` = **code** (affichage). Table `permissions` **vide**. `IsAdminRole` = `role.code == ADMIN`. Palier actuel JWT : `IsAuthenticated` (soi) / `IsAdminRole` (admin).

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §1 — *Entrer dans l’application* / §9 comptes) :


| Fonction MVP                                    | Ticket     | Statut                 |
| ----------------------------------------------- | ---------- | ---------------------- |
| Connexion + MFA + appareils + QR + CGU/wizard   | A–F, J     | **fait** (jours 1–7)   |
| MDP, déconnexion, historique, lock              | G–I        | **fait** (jours 8–10)  |
| **Qui a le droit de faire quoi (HTTP)**         | **AUTH-R** | **ce jour**            |
| Lifecycle comptes (disable, kick, régions)      | ADMIN-A    | [jour 12](00-jour-12-admin-a.md) |


**À quoi ça sert (MVP) :** jean.dupont lit `/me` et change son MDP, mais **ne** peut **pas** approuver un compte ni déverrouiller un collègue. Un admin JWT a **toutes** les perms seed. Un rôle custom (ex. `NOC_LEAD`) n’a **que** ce qu’on lui accorde. Plus de « JWT suffit » ni « ou ADMIN ».

**Plan métier (code à coller) :** [AUTH-R-roles-permissions.md](iam_plans/AUTH-R-roles-permissions.md) (R01 … R10).  
Chemins lab = ce fichier (`views/admin_rbac.py`, `middlewares/permissions.py` — **pas** `views_admin_rbac.py` ni `apps/iam/permissions.py` à la racine IAM).

**Déjà en base / code :**

- `Role`, `Permission`, `RolePermission` (UK `(role, permission)`)
- Seed `USER` (level 0, `is_system`) + `ADMIN` (level 100) ; jean = USER, `admin@yas.tg` = ADMIN, portes AUTH-F fermées
- JWT `role` = code ; **pas** la liste des permissions
- Admin JWT : `IsAdminRole` (D05, C24, E admin, I unlock)
- `/admin/` Django = cookie `is_staff` (**hors** `HasPermission`)

**Pas encore :** colonne `permissions.resource` ; seed 58 codes ; `HasPermission` ; CRUD `/admin/roles` ; matrice add/remove/PUT ; `PATCH /admin/users/{id}/role`.

**Objectif du jour :**

1. Seed **58** permissions `is_system` (27 self + 31 admin, table AUTH-R §R03). USER ← self ; ADMIN ← toutes `is_system`.
2. `HasPermission` DRF **fail-closed** : `required_permission` **obligatoire** sur **chaque** vue JWT → 403 `FORBIDDEN` + body `permission` = code manquant. **Plus** de `IsAuthenticated` seul ni `IsAdminRole` sur l’API.
3. Brancher **toutes les vues JWT existantes** (matrice R10 lab ci-dessous). Seed les codes PROF / PRES / ADMIN-A / ANNUAIRE-B/C/D — **ne pas** créer leurs routes.
4. HTTP admin R06–R09 : CRUD rôles, catalogue permissions, matrice, changement de rôle user (`LAST_ADMIN`).
5. Cache Redis `rbac:role:{id}` TTL 60 s, invalidé R08 / delete rôle / delete perm. Redis down → SQL (pas 503).

**Hors jour 11 :** multi-rôles, perms dans le JWT, mapping AD→rôle (AUTH-15 abandonné), UI, rôles métier NOC/RH **au-delà** du seed (POST custom OK, pas de seed `NOC_LEAD`), coder ADMIN-A / PROF-A/B/C / PRES-A / ANNUAIRE write / people-picker.

---



## Pourquoi ce jour (après AUTH-I)

Sans RBAC HTTP, « admin » = un booléen `role.code == ADMIN`. Impossible de donner *unlock* sans *approve*, ni de durcir USER (retirer `iam.profile.read`). Le MVP et tous les tickets F/G/H/E/I/C disent déjà `HasPermission` — palier ouvert jusqu’ici.

```text
JWT
    HasPermission (required_permission)
        → 401 si pas de JWT
        → 403 FORBIDDEN si attribut manquant ou code absent du rôle
    puis portes AUTH-F (TOS / onboarding)
        → 403 TOS_REQUIRED / ONBOARDING_REQUIRED
    puis métier

Public (pas de HasPermission)
    login, login/ldap, refresh, mfa/verify, register*, email/verify,
    password forgot/reset, directory*, health, docs,
    device-link start + poll
```

`POST /me/devices/link` (confirm QR) = JWT + `iam.device.update`.  
Logout / sessions / heartbeat : perm **puis** allowlist CGU (déjà AUTH-H).

---



## Paliers (figés pour ce jour)


| Sujet | Choix jour 11 | Plus tard |
| ----- | ------------- | --------- |
| Check | SQL `role_permissions` + cache rôle 60 s | perms dans le JWT |
| Fail-closed | défaut DRF = `HasPermission` ; vue JWT **sans** `required_permission` → 403 | — |
| `IsAdminRole` | **plus** utilisé sur l’API | `/admin/` Django reste `is_staff` |
| JWT claim | `role` = code (inchangé) | liste de perms |
| `audience` | **pas** une colonne SQL : constantes de seed `SELF_PERMISSION_CODES` | — |
| Portes AUTH-F | **après** `HasPermission` (inverser le middleware jour 7) | — |
| Routes PROF / PRES / ADMIN-A métier / ANNUAIRE write | seed des codes seulement | jours 12+ |
| Redis down | lecture SQL, pas 503 | — |
| `/admin/` cookie | hors RBAC API | — |


**Ordre check (à coder explicitement) :** aujourd’hui `ComplianceMiddleware` refuse `TOS_REQUIRED` **avant** la vue. AUTH-R : pas de perm → `FORBIDDEN` (même CGU ouverte). Donc **sortir** le deny TOS/onboarding du middleware Django ; le poser en classe DRF `ComplianceGates` **après** `HasPermission`. Allowlist inchangée (`GET /me`, `/me/tos*`, heartbeat appareil, logout / sessions AUTH-H). Middleware : ne plus renvoyer 403 CGU (laisser passer jusqu’à DRF). Routes publiques : inchangées (`AllowAny`).

---



## 1. Tables (1 migration additive)

**Interdit :** `docker compose down -v`. Pas de `DROP` de table. Migration `0006_auth_r_permission_resource`.

Table `permissions` **vide** en lab (jamais seedée) → UK changeable sans backfill de lignes métier.

| Table | Delta |
| ----- | ----- |
| `permissions` | `resource` varchar(64) **NOT NULL** ; `code` max **96** ; UK `(module, resource, action)` **remplace** `(module, action)` |
| `roles` / `role_permissions` | **inchangés** |
| `audit_logs` | `ROLE_CREATE` / `ROLE_PATCH` / `ROLE_DELETE` / `ROLE_PERM_ADD` / `ROLE_PERM_REMOVE` / `ROLE_PERMS_SET` / `USER_ROLE_CHANGE` |

`code` **dérivé** : toujours `f"{module}.{resource}.{action}"` (jamais un code décorrélé).

---



## 2. Settings + seed

`.env` / `.env.example` :

```env
YAS_RBAC_CACHE_TTL_SECONDS=60
```

`REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]` :

```python
[
    "apps.iam.middlewares.permissions.HasPermission",
    "apps.iam.middlewares.compliance.ComplianceGates",
]
```

Plus `IsAuthenticated` en défaut : `HasPermission` renvoie False si anonyme → DRF **401**. Authentifié sans code → **403** `FORBIDDEN` (lever `AuthAPIError`, pas le 403 générique DRF).

`seed_iam` **étendu** (idempotent) :

1. `USER` / `ADMIN` `is_system=true` (déjà) ; si `is_system` false en base → corriger.
2. Upsert **58** permissions R03 (`is_system=true`).
3. USER ← `SELF_PERMISSION_CODES` (27) ; ADMIN ← toutes `is_system`.
4. Users jean / admin inchangés (portes AUTH-F déjà fermées).

`audience` n’est **pas** persisté. Constante Python dans le seed / `rbac_service`.

**Tests existants** créent `Role(code=USER|ADMIN)` **sans** matrice. Sans filet, A–I cassent (admin approve → 403). Helper `ensure_system_matrix(role)` : si `code==USER` → self ; si `code==ADMIN` → toutes `is_system`. L’appeler depuis `UserManager.create_user` (matrice encore vide) **et** `seed_iam`. Rôles custom (`NOC_LEAD`) : **ne pas** auto-lier.

---



## 3. Middleware + services

| Fichier | Sert à |
| ------- | ------ |
| `apps/iam/middlewares/permissions.py` | **`HasPermission`**. Garder `IsAdminRole` (inutilisé API ; ne plus l’importer dans les vues) |
| `apps/iam/middlewares/compliance.py` | **`ComplianceGates`** (même allowlist / messages que le middleware actuel). Le middleware Django **ne plus** `_deny` TOS |
| `apps/iam/services/rbac_service.py` | **nouveau.** `load_role_perm_codes`, `user_has_permission`, cache get/set/invalidate, CRUD rôles / perms / matrice / assign rôle |
| `apps/iam/exceptions/auth.py` | `AuthAPIError` : extra optionnel mergé dans le JSON (`permission`, `users_count`, …) |
| `apps/core/exceptions/handler.py` | recopier les clés extra (`permission` au **top-level**) |
| `apps/iam/management/commands/seed_iam.py` | 58 perms + matrices |
| `apps/iam/models.py` | `Permission.resource` ; UK ; `code` max 96 |

```python
class HasPermission(BasePermission):
    """La vue JWT pose required_permission = 'iam.profile.read'."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False  # → 401
        code = getattr(view, "required_permission", None)
        if not code:
            raise AuthAPIError(403, "FORBIDDEN", "Accès refusé.", extra={"permission": None})
        if not user_has_permission(request.user, code):
            raise AuthAPIError(403, "FORBIDDEN", "Accès refusé.", extra={"permission": code})
        return True
```

Pas de fallback `role.code == ADMIN`. Pas de fallback « JWT suffit ».  
Cache : clé `rbac:role:{id}` ; TTL `YAS_RBAC_CACHE_TTL_SECONDS` ; miss ou Redis down → SQL `role_permissions` → (re)set cache si Redis up.

Vues JWT : **retirer** `permission_classes = [IsAuthenticated]` et `[IsAuthenticated, IsAdminRole]`. Hériter du défaut + poser **seulement** `required_permission`.  
Vues publiques : garder `AllowAny` + `authentication_classes = []` (écrase le défaut).

---



## 4. HTTP

Arborescence `views/`, `serializers/`, `urls/admin.py` (étendre). **Pas** d’endpoint user `/me/roles`.

| Fichier | Rôle |
| ------- | ---- |
| `apps/iam/views/admin_rbac.py` | CRUD rôles, permissions, matrice |
| `apps/iam/views/admin_users.py` | `PATCH …/role` (R09) ; D05 : remplacer `IsAdminRole` par `required_permission` |
| `apps/iam/serializers/rbac.py` | rôles, perms, `permission_codes` |
| `apps/iam/urls/admin.py` | chemins ci-dessous **avant** les `<uuid>` trop gourmands |

### R06 — rôles (`iam.role.read` / `iam.role.manage`)

| Méthode | Chemin | Perm |
| ------- | ------ | ---- |
| GET | `/api/v1/admin/roles` | `iam.role.read` |
| GET | `/api/v1/admin/roles/{id}` | `iam.role.read` |
| POST | `/api/v1/admin/roles` | `iam.role.manage` |
| PATCH | `/api/v1/admin/roles/{id}` | `iam.role.manage` |
| DELETE | `/api/v1/admin/roles/{id}` | `iam.role.manage` |

Query liste : `q` (ILIKE `code` **ou** `name`), `is_system`, `limit` 50 (1–100), `offset`. Tri : `level` DESC, `code` ASC. Liste : `users_count`, `permissions_count` — **pas** `permission_codes` (détail seulement).

POST : `code` SCREAMING_SNAKE 2–32 ; `is_system` envoyé → **400** `FIELD_FORBIDDEN` ; toujours `false` ; `level` 0–99 (défaut 10) ; **409** `ROLE_CODE_TAKEN` ; **400** `INVALID_ROLE_CODE`. Perms initiales `[]` (ne **pas** copier USER). **201** = JSON détail.

PATCH : `code` / `is_system` → **400**. `level` sur rôle system → **400** `ROLE_SYSTEM_FROZEN`. `name` / `description` OK même sur ADMIN.

DELETE : system → **409** `ROLE_SYSTEM` ; users liés → **409** `ROLE_IN_USE` (`users_count`) ; sinon **204**. Invalider cache. Audit **avant** le DELETE.

Contrats JSON : AUTH-R §R06 (ne pas les réinventer).

### R07 — permissions

| Méthode | Chemin | Perm |
| ------- | ------ | ---- |
| GET | `/api/v1/admin/permissions` | `iam.permission.read` |
| POST | `/api/v1/admin/permissions` | `iam.permission.manage` |
| DELETE | `/api/v1/admin/permissions/{id}` | `iam.permission.manage` |

GET `?module=iam` ; `limit` / `offset` comme les rôles.  
POST `{ "module", "resource", "action", "name", "description" }` → serveur pose `code` ; regex R01 ; **409** si pris ; `is_system=false`.  
DELETE `is_system` → **409** `PERMISSION_SYSTEM`. Invalider les caches des rôles qui l’avaient.

### R08 — matrice (`iam.role.grant` ; GET liste = `iam.role.read`)

| Méthode | Chemin | Sens |
| ------- | ------ | ---- |
| GET | `/api/v1/admin/roles/{id}/permissions` | mêmes `permission_codes` que GET rôle |
| POST | `…/permissions` | ajouter (union, idempotent) |
| DELETE | `…/permissions` | retirer (idempotent) |
| PUT | `…/permissions` | remplacer le set |

Body POST/DELETE/PUT : `{ "permission_codes": ["iam.user.unlock"] }`. Vide/absent → **400** `PERMISSIONS_REQUIRED`. Code inconnu → **404** `PERMISSION_NOT_FOUND` (`permission` = le code) ; **aucune** écriture (transaction). Rôle `ADMIN` : retirer une perm `is_system` (DELETE **ou** PUT qui l’omet) → **409** `ADMIN_PERMS_FROZEN`. USER : retirer du self **autorisé**. Succès **200** = JSON détail rôle. Invalider `rbac:role:{id}`.

### R09 — rôle d’un user

| Méthode | Chemin | Perm |
| ------- | ------ | ---- |
| PATCH | `/api/v1/admin/users/{id}/role` | `iam.user.role.assign` |

Body `{ "role_code": "ADMIN" }`. **404** user ou rôle. **409** `LAST_ADMIN` si on enlève le dernier `role.code=ADMIN`. Audit `USER_ROLE_CHANGE`. Ne **pas** invalider le cache rôle (le set de perms du rôle ne change pas).

### R10 — vues JWT **existantes** (brancher ce jour)

| Vue | `required_permission` |
| --- | --------------------- |
| `GET /me` | `iam.profile.read` |
| `GET/POST /me/tos*` | `iam.tos.manage` |
| `GET/PATCH/POST /me/onboarding*` | `iam.onboarding.manage` |
| `POST /me/password` | `iam.password.change` |
| `GET /me/sessions` | `iam.session.read` |
| `POST /auth/logout`, `/logout-all`, `/me/sessions/{id}/logout`, `/me/devices/{id}/logout` | `iam.session.logout` |
| `POST /me/sessions/current/heartbeat` | `iam.session.heartbeat` |
| `GET /me/devices` | `iam.device.read` |
| `PATCH /me/devices/current`, `PATCH /me/devices/{id}`, `POST /me/devices/link` | `iam.device.update` |
| `POST /me/devices/{id}/revoke` | `iam.device.revoke` |
| `POST /me/devices/{id}/compromise` (owner) | `iam.device.compromise` |
| admin compromise / clear | `iam.device.manage` |
| `GET /me/security/logins` | `iam.login.read` |
| `POST /me/email`, `/me/email/resend` | `iam.email.change` |
| unlock admin | `iam.user.unlock` |
| admin logins | `iam.user.security.read` |
| backup regen | `iam.mfa.regenerate` |
| MFA reset admin | `iam.mfa.reset` |
| D05 `GET /admin/users` | `iam.user.read` |
| D05 approve / reject | `iam.user.approve` / `iam.user.reject` |
| R06–R09 | table admin ci-dessus |

**Ne pas** ajouter ce jour : `PATCH /me`, avatar, `/me/preferences`, `/me/privacy`, présence, `GET /users`, create/disable/enable/reset MDP/kick/audit/régions admin, ANNUAIRE write.

Public (rappel, **pas** de `required_permission`) : liste AUTH-R « Routes publiques » + `/health` + `/api/docs/` + `/api/schema/` + `device-link/start` + poll.

---



## 5. Impact tests existants

Tous les `create_user` USER/ADMIN doivent recevoir la matrice (helper §2) — sinon D05 approve, `/me`, devices, logout **403**.

| Fichier | Adapter |
| ------- | ------- |
| `test_auth_d.py` | jean (USER) approve → toujours 403, code **`FORBIDDEN`** (plus le message `IsAdminRole`) ; admin + matrice → 200 |
| `test_auth_c.py` / `e` / `i` | idem admin MFA reset / compromise / unlock |
| `test_auth_f.py` | user neuf `/me/devices` : perm OK (self) **puis** `TOS_REQUIRED` (ordre inversé, **même** code si USER a `iam.device.read`) |
| `test_auth_a.py` … `test_auth_j.py` | régression 200 sur les self-routes seed |

Cas « USER sans `iam.profile.read` » : seulement `test_auth_r.py` (retirer la perm puis `GET /me` → 403). Ne pas casser le seed jean des autres fichiers (ré-attacher en fin de test ou `transaction=True`).

---



## 6. Tests nouveaux (`test_auth_r.py`)


| ID | Cas | Attendu |
| -- | --- | ------- |
| R01 | seed codes | regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` ; rôles `USER`/`ADMIN` SCREAMING |
| R03 | 58 `is_system` | 27 self + 31 admin |
| R04 | jean `GET /me` | **200** |
| R04 | jean approve pending | **403** `FORBIDDEN` ; `permission` = `iam.user.approve` |
| R04 | retirer `iam.profile.read` à USER | jean `GET /me` → **403** |
| R04 | admin approve | **200** (D05) |
| R05 | vue JWT sans `required_permission` | **403** `FORBIDDEN` ; `permission` null (helper / vue test) |
| R05 | sans JWT `GET /me` | **401** |
| R06 | `GET /admin/roles` jean | **403** |
| R06 | liste admin | **200** ; USER + ADMIN ; `users_count` |
| R06 | GET ADMIN | `permission_codes` longueur **58** |
| R06 | POST `noc_lead` | **400** `INVALID_ROLE_CODE` |
| R06 | POST `NOC_LEAD` | **201** `is_system=false` ; perms `[]` |
| R06 | POST `NOC_LEAD` 2e | **409** `ROLE_CODE_TAKEN` |
| R06 | POST `{ "is_system": true }` | **400** `FIELD_FORBIDDEN` |
| R06 | PATCH ADMIN `code` / `level` / `is_system` | **400** |
| R06 | PATCH ADMIN `name` | **200** |
| R06 | PATCH `NOC_LEAD` `level: 25` | **200** |
| R06 | DELETE USER / ADMIN | **409** `ROLE_SYSTEM` |
| R06 | DELETE `NOC_LEAD` avec 1 user | **409** `ROLE_IN_USE` |
| R06 | DELETE `NOC_LEAD` 0 user | **204** ; GET → 404 |
| R07 | POST `iam.user.approve` (déjà system) | **409** |
| R08 | POST add `iam.user.unlock` à `NOC_LEAD` | **200** ; user NOC_LEAD unlock OK |
| R08 | POST add déjà présent | **200** ; `added` vide |
| R08 | POST code inconnu | **404** ; set inchangé |
| R08 | DELETE remove `iam.user.unlock` | **200** ; unlock → **403** |
| R08 | DELETE `iam.mfa.reset` sur ADMIN | **409** `ADMIN_PERMS_FROZEN` |
| R08 | PUT `[iam.device.read]` sur `NOC_LEAD` | **200** ; uniquement ce code |
| R08 | PUT `[]` sur ADMIN | **409** `ADMIN_PERMS_FROZEN` |
| R09 | dernier ADMIN → USER | **409** `LAST_ADMIN` |
| R09 | jean → ADMIN | **200** ; audit |
| R10 | `POST /me/password` sans `iam.password.change` | **403** |
| R10 | `GET /me/sessions` USER seed | **200** |
| R10 | E compromise admin sans `iam.device.manage` | **403** |
| — | Redis down (mock cache) | check SQL, **pas** 503 |
| — | `/health`, `/api/docs/` | schéma contient `/admin/roles` |


Helper MFA : `login_until_jwt`. Portes : `close_gates` sauf cas TOS.  
R09 `LAST_ADMIN` : seed n’a **qu’un** ADMIN (`admin@yas.tg`) — le rétrograder doit 409 ; créer un 2ᵉ ADMIN avant de tester un rétrograde OK.

Régression : A, C (reset MFA), D (approve), E, F, G, H, I, J.

---



## 7. Vérif manuelle

```powershell
python manage.py migrate
python manage.py seed_iam
python manage.py check
pytest apps/iam/tests/test_auth_r.py apps/iam/tests/test_auth_a.py apps/iam/tests/test_auth_d.py apps/iam/tests/test_auth_f.py apps/iam/tests/test_auth_c.py --reuse-db
```

`jean.dupont@yas.tg` : `GET /me` 200 ; `GET /admin/roles` 403 ; `POST /admin/users/{id}/approve` 403.  
`admin@yas.tg` : liste rôles 200 ; ADMIN a 58 codes.  
Créer `NOC_LEAD`, add `iam.user.unlock`, assigner un user, unlock OK ; retirer la perm → 403.  
`/admin/` cookie staff : **pas** l’API rôles (JWT + perm).

---



## Checklist jour 11

- [ ] Migration `resource` + UK + `code` 96
- [ ] Seed 58 + USER self / ADMIN tout ; `ensure_system_matrix` pour les tests
- [ ] `HasPermission` fail-closed + body `permission`
- [ ] `ComplianceGates` **après** HasPermission ; middleware Django sans deny TOS
- [ ] Toutes les vues JWT existantes : `required_permission` ; plus `IsAdminRole`
- [ ] R06 CRUD rôles (gardes system / in-use)
- [ ] R07 catalogue + custom
- [ ] R08 add / remove / PUT ; `ADMIN_PERMS_FROZEN`
- [ ] R09 `PATCH …/role` + `LAST_ADMIN`
- [ ] Cache Redis 60 s ; Redis down → SQL
- [ ] `test_auth_r.py` + régression A/C/D/E/F/G/H/I/J
- [ ] SIRH non modifié

---



## Interdits

- Coder ADMIN-A (disable, password helpdesk, kick, régions, audit HTTP) / PROF-A/B/C / PRES-A / ANNUAIRE write / `GET /users`
- Perms dans le JWT ; multi-rôles ; mapping groupe AD → rôle
- Seed d’un rôle métier `NOC_LEAD` (seul le **test** le crée via POST)
- Remettre un fallback `role.code == ADMIN` ou `IsAuthenticated` sur une vue JWT
- `docker compose down -v`
- Changer le SIRH

---



## Après le jour 11

Jour 12 : [00-jour-12-admin-a.md](00-jour-12-admin-a.md) — **ADMIN-A** (liste/fiche users, create RH, disable/enable, reset MDP helpdesk, kick sessions, audit, CRUD `region`). Les perms `iam.user.create` / `disable` / … sont **déjà** seedées ici.

---



## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour** (comme les jours 3–10). Le jour 2 (admin + Swagger) est un extra déjà clos.

| Jours | Plan | Ticket MVP |
| ----- | ---- | ---------- |
| 0 | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health` |
| 1–2 | AUTH-A ; admin + Swagger | Connexion locale ; lab admin |
| 3–10 | D+B, C, E, J, F, G, H, I | §1 entrer + §2 appareils |
| **11** | **AUTH-R** (ce plan) | Qui a le droit (socle HTTP) |
| 12 | ADMIN-A | §9 comptes (liste, disable, MDP helpdesk, kick, régions, audit) |
| 13 | PROF-A | §2 ma fiche / photo |
| 14 | PROF-B | Préférences (langue / son — wizard déjà F) |
| 15 | PROF-C | §2 visibilité |
| 16 | PRES-A | §2 statut en ligne |
| 17 | ANNUAIRE-A | §3 recherche collègue |
| 18 | CRYPTO-00 | §6 décision E2E 1-to-1 vs groupes |
| 19 | MEDIA-R + MEDIA-A | §4 joindre un fichier (upload) |
| 20 | NOTIF-R + NOTIF-A | §5 alertes + push app fermée |
| 21 | CRYPTO-R + CRYPTO-A | Clés HTTP |
| 22 | MESSAGERIE-R, A, B | §7 liste + chat 1-to-1 + PJ |
| 23 | MESSAGERIE-C, D | §7 groupes + temps réel |
| 24 | MESSAGERIE-E (partiel), F (blocage), G | §7 emoji, transfert, sondage, favoris, bloquer, typing |
| 25 | MEDIA-B, C, D, E | §4 album, vidéo, vocal, coffre |
| 26 | APPELS-R, A, B, C | §8 appel 1-1 + sonnerie |
| 27 | APPELS-D, E, G | §8 écran, enregistrement, CR auto |

**Total : 28 plans (jours 0 à 27).**  
Déjà clos : **11** (0–10). Restant : **17** (11–27).

Hors ce compteur (A→Z §4.2, *après* le MVP sonnant) : ANNUAIRE-B/C/D, MEDIA-F, APPELS-F, mentions / modération, social, IA.

Le jour **25** (MEDIA-B…E) est le plus large : s’il explose au lab, on le **découpera** (le total passerait alors vers 30–31). On ne découpe pas maintenant.
