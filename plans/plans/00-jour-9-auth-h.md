# Jour 9 — AUTH-H (sessions, logout, idle)

**Statut :** à faire.  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–8 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 8](00-jour-8-auth-g.md)).  
Refresh + rotation + `FORCE_LOGOUT` **déjà** livrés (jour 1). `_force_logout_user` **déjà** utilisé par AUTH-G / MFA reset. Routes logout / liste / idle / blacklist JTI **à livrer**.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §1 — *Entrer dans l’application*) :


| Fonction MVP                                    | Ticket     | Statut                 |
| ----------------------------------------------- | ---------- | ---------------------- |
| Connexion + MFA + appareils + QR + CGU/wizard   | A–F, J     | **fait** (jours 1–7)   |
| Changer / oublier son mot de passe              | AUTH-G     | **fait** (jour 8)      |
| **Déconnexion (un appareil ou tous)**           | **AUTH-H** | **ce jour**            |
| Sécurité compte (logins, lock)                  | AUTH-I     | plus tard              |


**À quoi ça sert (MVP) :** l’user coupe **cet** ordi, **cet** appareil, ou **partout**, sans ticket helpdesk. Un refresh volé tue tout (`FORCE_LOGOUT`, déjà là). Une session trop vieille (idle 7 j / plafond 30 j) meurt toute seule.

**Plan métier (code à coller) :** [AUTH-H-sessions.md](iam_plans/AUTH-H-sessions.md) (AUTH-51 … 60).  
Chemins lab = ce fichier (`views/sessions.py`, pas `views_session.py` à la racine IAM).

**Déjà en base / code :**

- `POST /api/v1/auth/refresh` : rotation, ancien `ROTATED`, réuse → `_force_logout_user` + **401 `FORCE_LOGOUT`**
- `request.yas_session` posé par `YasJWTAuthentication` (commentaire AUTH-H)
- `_force_logout_user(*, except_session_id=)` dans `auth_service.py` (PASSWORD_*, MFA_RESET, REFRESH_REUSE)
- Cache Django : Redis si `REDIS_URL`, sinon `LocMemCache` (déjà AUTH-06 / AUTH-J)

**Pas encore :** routes HTTP logout / liste / heartbeat session ; `sessions.expires_at` = **15 min** (TTL access) et le refresh **recolle** ce champ à 15 min ; idle ; job `session_reaper` ; blacklist JTI.

**Objectif du jour :**

1. `expires_at` = durée **absolue** de session (`login_at` + 30 j). Access 15 min = claim JWT `exp` **seulement**. Refresh **ne plus** recoller `expires_at`.
2. `POST /auth/logout`, `/logout-all` ; `GET /me/sessions` ; logout session / appareil ; heartbeat `last_activity`.
3. Idle 7 j + plafond 30 j : check JWT **et** refresh **et** job.
4. Blacklist JTI (cache) jusqu’à `exp` access ; Redis / cache down → **ignorer**, session DB = vérité.
5. Extraire `revoke_sessions` ; AUTH-G continue de tuer les sessions (motifs inchangés) **et** blacklist les JTI.

**Hors jour 9 :** AUTH-I, ADMIN-A kick d’un autre user, PRES-A pastille, cookie httpOnly, OTP au refresh, `HasPermission` AUTH-R, révocation **appareil** AUTH-E-34 (`push_token` / `trusted`).

---



## Pourquoi ce jour (après AUTH-G)

Sans logout HTTP, changer de poste = attendre 15 min ou reset MDP. Le MVP demande : **cet** écran / **cet** appareil / **partout**.

Bug actuel (jour 1) : `complete_login` **et** `refresh` posent

```python
expires_at=now + timedelta(seconds=settings.YAS_JWT_ACCESS_TTL_SECONDS)  # 15 min
```

AUTH-58 : ce champ = **plafond session**, pas le TTL access. Si on ne corrige pas, une session « 30 j » n’existe pas, et chaque refresh **rallonge** à 15 min (ni idle 7 j ni plafond 30 j).

```text
Connecté (JWT, même pendant CGU / wizard)
    POST /auth/logout              → session courante LOGOUT
    POST /auth/logout-all          → partout LOGOUT_ALL
    GET  /me/sessions              → actives, is_current, jamais hash/JTI
    POST /me/sessions/{id}/logout  → owner ; 404 si autre user
    POST /me/devices/{id}/logout   → sessions de l’appareil ; device intact
    POST /me/sessions/current/heartbeat  → last_activity (debounce 60 s)

Public (déjà là)
    POST /auth/refresh  → rotation + idle/absolu + blacklist ancien JTI
```

`PATCH /me/devices/current` (AUTH-F) reste le heartbeat **appareil** (`last_seen`). AUTH-60 = `sessions.last_activity` (distinct).

---



## Paliers (figés pour ce jour)


| Sujet | Choix jour 9 | Plus tard |
| ----- | ------------ | --------- |
| Logout / liste / heartbeat | JWT + `IsAuthenticated` | AUTH-R : `iam.session.*` |
| `POST /refresh` | `AllowAny` + `authentication_classes = []` (inchangé) | — |
| Portes AUTH-F | logout*, refresh, `GET /me/sessions`, logout distant, heartbeat session **autorisés** (TOS KO / wizard KO) | — |
| Idle / absolu | `.env` ; si `system_settings` `security.session_*` présents → les lire | UI admin CONFIG |
| Blacklist | cache Django `jti:{uuid}` ; Redis si `REDIS_URL` ; down → skip | Redis HA |
| `expires_at` | `login_at` + `YAS_SESSION_ABSOLUTE_SECONDS` (30 j) | — |
| Refresh TTL | `min(now + 7 j, session.expires_at)` | — |
| Kick admin | **pas** `POST /admin/users/{id}/sessions/revoke` | ADMIN-A ADM-06 |


AUTH-H métier dit `HasPermission`. **Jour 9 = même palier que `/me/password` / `/me/devices`** (JWT). AUTH-R enlèvera le palier ouvert.

---



## 1. Tables (0 migration)

**Interdit :** `docker compose down -v`. **Pas** de nouvelle table. **Pas** de nouvelle colonne.

| Table | Rôle |
| ----- | ---- |
| `sessions` | `expires_at` = plafond **session** (commentaire modèle, plus « fin de l’access ») |
| `refresh_tokens` | rotation inchangée ; `expires_at` capé par la session |
| `devices` | **lecture** liste ; AUTH-54 **ne** touche **pas** `push_token` / `trusted` |
| `audit_logs` | `LOGOUT` / `LOGOUT_ALL` / `FORCE_LOGOUT` (déjà) / job `INACTIVITY` / `EXPIRED` |

Motifs `revoke_reason` (CharField 64, déjà libre) : `LOGOUT`, `LOGOUT_ALL`, `INACTIVITY`, `EXPIRED` — plus `PASSWORD_*`, `REFRESH_REUSE`, `NEW_LOGIN_SAME_DEVICE`, `MFA_RESET`.

Sessions lab déjà en base avec `expires_at` à 15 min : le job les passera `EXPIRED`. Les tests créent des sessions fraîches.

---



## 2. Settings + seed

`.env` / `.env.example` :

```env
YAS_SESSION_IDLE_SECONDS=604800
YAS_SESSION_ABSOLUTE_SECONDS=2592000
YAS_SESSION_HEARTBEAT_MIN_SECONDS=60
```

`config/settings.py` : mêmes clés dans `environ.Env(...)` puis assignation (comme AUTH-G).

`seed_config` : upsert `system_settings` catégorie `security` (ne pas écraser un secret — il n’y en a pas ici) :

| setting_key | Défaut |
| ----------- | ------ |
| `session_idle_seconds` | `604800` |
| `session_absolute_seconds` | `2592000` |
| `session_heartbeat_min_seconds` | `60` |

Lecture : **une** helper (même style que `password_policy._security_value`) : DB si la ligne existe, sinon `.env`.

Job `scheduled_jobs` (comme `ldap_sync_users`) :

| job_name | cron | handler |
| -------- | ---- | ------- |
| `session_reaper` | `*/5 * * * *` | `apps.iam.jobs.reap_sessions` |

`REDIS_URL` **déjà** dans `.env` : ne pas inventer un 2ᵉ Redis. Lab vide = LocMem (blacklist in-process, suffisant pour les tests).

---



## 3. Middleware + services

| Fichier | Sert à |
| ------- | ------ |
| `apps/iam/services/session_service.py` | **nouveau.** `session_dead`, `revoke_sessions`, logout courant / id / device, liste, heartbeat, `reap` interne |
| `apps/iam/services/jti_blacklist.py` | **nouveau.** `blacklist_jti` / `jti_blocked` via `django.core.cache.cache`. Exception Redis → no-op |
| `apps/iam/services/auth_service.py` | `complete_login` : `expires_at = now + absolu`. `refresh` : idle/absolu, **ne pas** écrire `session.expires_at`, blacklist ancien JTI. `_force_logout_user` **délègue** à `revoke_sessions` |
| `apps/iam/services/token_service.py` | `issue_refresh` : `exp = min(now + refresh_ttl, session.expires_at)` |
| `apps/iam/services/password_service.py` | garder l’appel `_force_logout_user` (wrapper) — motifs `PASSWORD_*` inchangés ; la blacklist vient du délégué |
| `apps/iam/jobs.py` | `reap_sessions()` à côté de `sync_ldap_accounts` |
| `apps/iam/middlewares/authentication.py` | après session active : blacklist JTI → `session_dead` → 401 ; `touch_last_activity` debounce ; **même** checks dans `session_user_from_bearer` (sinon CGU 403 au lieu de 401) |
| `apps/iam/middlewares/compliance.py` | allowlist JWT portes KO (ci-dessous) |

**Cycle d’import :** `session_service` n’importe **pas** `auth_service` au module level. `_force_logout_user` peut importer `revoke_sessions` en local (comme AUTH-G aujourd’hui).

Allowlist **JWT + TOS KO** (en plus de `GET /me` exact, `/me/tos*`, `PATCH /me/devices/current`) :

- `POST` path `_is_or_under("/api/v1/auth/logout")` → `/logout` et `/logout-all`
- `_is_or_under("/api/v1/me/sessions")` → liste, `{id}/logout`, `current/heartbeat`
- `POST` + path regex `/api/v1/me/devices/<uuid>/logout` **seulement** (ne **pas** `startswith /me/devices` : ça ouvrirait la liste appareils)

`/auth/refresh` est **déjà** public. `/me/password` reste **bloqué** portes KO.

`session_dead(session, now) -> str | None` :

1. `not is_active` → `"INACTIVE"`
2. `expires_at <= now` → `"EXPIRED"`
3. `last_activity + idle <= now` → `"INACTIVITY"`

Refresh : mort → **401 `INVALID_REFRESH`** (pas `FORCE_LOGOUT`). Réuse rotaté → kill + blacklist + **401 `FORCE_LOGOUT`**. Hash inconnu → **401 `INVALID_REFRESH`**, **pas** de kill global (déjà testé jour 1).

`revoke_sessions(*, user, reason, except_session_id=None)` : blacklist chaque `access_jti` (TTL restant access, fallback `YAS_JWT_ACCESS_TTL_SECONDS`) puis `is_active=false` + refresh `revoked_at`.

Clé cache : `jti:{access_jti}` (UUID str). `YasJWTAuthentication` : si `jti_blocked` → `AuthenticationFailed` (session invalide), **sans** 503.

---



## 4. HTTP

Arborescence actuelle (`views/`, `serializers/`, `urls/auth.py`, `urls/me.py`) — **pas** de `views_session.py` / `authentication.py` à la racine IAM.

| Fichier | Rôle |
| ------- | ---- |
| `apps/iam/views/sessions.py` | logout, logout-all, liste, session logout, device logout, heartbeat |
| `apps/iam/serializers/sessions.py` | enveloppes liste + heartbeat |
| `apps/iam/urls/auth.py` | `logout`, `logout-all` (après `refresh`) |
| `apps/iam/urls/me.py` | `sessions/current/heartbeat` **avant** `sessions/<uuid>/logout` ; `devices/<uuid>/logout` à côté de `revoke` |

| Endpoint | Auth | Effet |
| -------- | ---- | ----- |
| `POST /api/v1/auth/refresh` | public | déjà là + idle/absolu + blacklist ancien JTI ; **pas** d’OTP |
| `POST /api/v1/auth/logout` | JWT | body vide ; session **courante** `LOGOUT` ; **200** |
| `POST /api/v1/auth/logout-all` | JWT | partout `LOGOUT_ALL` (y compris courant) ; **200** |
| `GET /api/v1/me/sessions` | JWT | actives et pas `session_dead` ; `is_current` ; jamais hash / JTI |
| `POST /api/v1/me/sessions/{id}/logout` | JWT | owner ; `{id}` = courante → même effet qu’AUTH-53 ; **404** autre user (pas 403) |
| `POST /api/v1/me/devices/{id}/logout` | JWT | owner ; toutes les sessions de l’appareil ; `devices.trusted` / `push_token` **inchangés** ; **404** autre user |
| `POST /api/v1/me/sessions/current/heartbeat` | JWT | body vide ; write `last_activity` si ≥ 60 s sinon 200 no-op ; `{ "last_activity": "…" }` ; **pas** `users.status` |

Liste (forme figée) :

```json
{
  "success": true,
  "data": {
    "sessions": [
      {
        "id": "<uuid>",
        "device_id": "<uuid>",
        "device_name": "iPhone de Jean",
        "platform": "IOS",
        "ip_address": "10.0.0.12",
        "login_at": "2026-08-27T08:00:00Z",
        "last_activity": "2026-08-27T10:15:00Z",
        "login_method": "PASSWORD",
        "is_current": true
      }
    ]
  }
}
```

`RefreshView` : description OpenAPI à mettre à jour (idle / plafond / blacklist). Tag Spectacular : logout* = **Auth** ; `/me/sessions*` = **Me** (ou tag Sessions si tu en ajoutes un — rester cohérent avec `/me/password` = Me).

---



## 5. Impact tests existants

`test_auth_a` `test_refresh_rotates` / `test_refresh_unknown_401` : **doivent rester verts** (rotation + `FORCE_LOGOUT` + inconnu sans kill).  
Le refresh ne doit plus avancer `session.expires_at` : un test H le verrouillera ; A n’assert pas ce champ aujourd’hui.

`test_auth_g` reset `logout_all` : 0 session active **et** JTI blacklistés (même service).

Fixtures A/C/E/J/F/G : `close_gates` déjà posé — logout / liste **passent** les portes.  
Users neufs AUTH-F `user_fresh` : logout / `GET /me/sessions` / heartbeat → **200** (allowlist), **pas** 403 TOS. Contraste : `GET /me/devices` reste 403 TOS.

Régression : A (refresh) + G + F encore verts.

---



## 6. Tests nouveaux (`test_auth_h.py`)


| Cas | Attendu |
| --- | ------- |
| refresh OK | 200 nouveaux tokens ; ancien `ROTATED` ; `session.expires_at` **inchangé** vs avant refresh |
| refresh sans OTP | 200 (user MFA enrollé) |
| refresh après `expires_at` session (freezer) | 401 `INVALID_REFRESH` |
| réuse refresh rotaté | 401 `FORCE_LOGOUT` ; 0 session active |
| refresh inconnu | 401 `INVALID_REFRESH` ; **pas** de kill |
| `POST /auth/logout` | courante inactive `LOGOUT` ; autre appareil **intact** |
| logout session distante | cette session morte ; courante OK |
| logout `device_id` | sessions de l’appareil mortes ; `trusted` / `push_token` **inchangés** |
| logout session d’un **autre** user | **404** |
| `POST /auth/logout-all` | 0 session ; refresh tous révoqués |
| `GET /me/sessions` | courante `is_current=true` ; pas de `refresh_hash` / `access_jti` |
| idle : `last_activity` trop vieux | JWT 401 ; job pose `INACTIVITY` |
| `expires_at` passé, idle OK | JWT 401 ; job `EXPIRED` |
| logout puis **même** access JWT | 401 (blacklist **ou** session inactive) |
| 2 heartbeats à moins de 60 s | 1 seul write `last_activity` |
| heartbeat | `users.status` **inchangé** |
| user neuf (portes ouvertes) + JWT | `POST /auth/logout` **200** ; `GET /me/devices` **403** `TOS_REQUIRED` |
| AUTH-G reset `logout_all` | toujours 0 session |
| `complete_login` | `expires_at` ≈ now + 30 j (pas 15 min) |
| `/health`, `/api/docs/` | 200 ; schéma contient `/auth/logout` et `/me/sessions` |


Helper MFA : `from apps.iam.helpers.mfa import login_until_jwt`.  
Helper portes : `close_gates` **sauf** le cas TOS allowlist.  
2ᵉ appareil : 2e `device_uuid` + `login_until_jwt` (comme AUTH-E).  
Idle / absolu : `freezegun` ou `last_activity` / `expires_at` écrits en base dans le test (pas d’attente 7 j).

---



## 7. Vérif manuelle

```powershell
python manage.py migrate
python manage.py seed_config
python manage.py seed_iam
python manage.py check
pytest apps/iam/tests/test_auth_h.py apps/iam/tests/test_auth_a.py apps/iam/tests/test_auth_g.py apps/iam/tests/test_auth_f.py --reuse-db
```

`jean.dupont@yas.tg` (portes fermées) : login + MFA → `GET /me/sessions` → `POST /auth/logout` → même access 401 ; relogin OK.

2e appareil : logout device → push/trusted intacts ; relogin sur cet uuid OK.

`/admin/` cookie : **pas** coupé par `/auth/logout` (session Django staff ≠ `sessions` IAM).

---



## Checklist jour 9

- [ ] `sessions.expires_at` = 30 j au login ; refresh **ne** recollera **pas** 15 min
- [ ] `POST /auth/logout` / `logout-all` ; liste ; logout session / device
- [ ] Device logout ≠ AUTH-E revoke (push / trusted intacts)
- [ ] Idle 7 j + plafond 30 j (JWT + refresh + job `session_reaper`)
- [ ] Blacklist JTI cache ; Redis down → skip, pas 503
- [ ] Heartbeat debounce 60 s ; pas `users.status`
- [ ] Refresh sans TOTP ; réuse → `FORCE_LOGOUT` (régression A)
- [ ] Compliance : logout / sessions / heartbeat pendant CGU/wizard ; **pas** `/me/devices` liste
- [ ] AUTH-G `_force_logout_user` passe par `revoke_sessions` + blacklist
- [ ] `test_auth_h.py` + régression A/G/F verts
- [ ] `/api/docs/` documente les nouvelles routes
- [ ] SIRH non modifié

---



## Interdits

- `HasPermission` AUTH-R
- Coder AUTH-I / ADMIN-A kick / PRES-A
- Cookie httpOnly, OTP au refresh
- Vider `push_token` / `trusted` sur AUTH-54
- `startswith /me/devices` dans l’allowlist CGU
- Recoller `session.expires_at` au TTL access 15 min
- 503 si Redis down
- `docker compose down -v`

---



## Après le jour 9

Jour suivant (A→Z **1i**) : **AUTH-I** — sécurité compte (historique de connexions, lock).
