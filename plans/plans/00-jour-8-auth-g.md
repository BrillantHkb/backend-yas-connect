# Jour 8 — AUTH-G (mot de passe applicatif)

**Statut :** clos (2026-09-09).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–7 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 7](00-jour-7-auth-f.md)).  
Changement MDP JWT + oubli via Authenticator **livrés**. Politique partagée AUTH-D. Ticket `password_reset_tokens` canal `TOTP`.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §1 — *Entrer dans l’application*) :


| Fonction MVP                                    | Ticket     | Statut                 |
| ----------------------------------------------- | ---------- | ---------------------- |
| Connexion + MFA + appareils + QR + CGU/wizard   | A–F, J     | **fait** (jours 1–7)   |
| **Changer son mot de passe**                    | **AUTH-G** | **fait** (ce jour)     |
| **Mot de passe oublié via Authenticator**       | **AUTH-G** | **fait** (ce jour)     |
| Déconnexion / liste de sessions                 | AUTH-H     | [jour 9](00-jour-9-auth-h.md) |


**À quoi ça sert (MVP) :** l’user change son secret **app** sans l’informatique ; s’il l’a oublié, il prouve Google Authenticator (déjà enrollé au 1er login) — **aucun** mail, SMS ou appel.

**Plan métier (code à coller) :** [AUTH-G-mot-de-passe.md](iam_plans/AUTH-G-mot-de-passe.md) (AUTH-43 … 50).

**Livré :** `POST /me/password` (`logout_others` défaut **true**) ; forgot toujours 200 ; verify TOTP/backup → ticket HMAC ; reset `logout_all` défaut true. Migration `0004_auth_g_reset_channel_totp`. Seed `security.password_*`.

**Objectif du jour (fait) :**

1. `POST /me/password` : ancien + nouveau ; politique + anti-réemploi ; option `logout_others`.
2. Forgot public **toujours 200** (anti-énumération, **zéro** envoi).
3. Verify TOTP / backup → ticket opaque hashé, TTL, **un usage** au reset (verify **ne** pose **pas** `used_at`).
4. Reset : politique + history ; `logout_all` défaut **true** ; **pas** d’unlock (`is_locked` inchangé).

**Hors jour 8 :** AUTH-H → [jour 9](00-jour-9-auth-h.md) ; AUTH-I, ADMIN-A reset helpdesk, changement MDP **Active Directory**, SMTP/SMS/IVR, expiration MDP périodique, AUTH-39, `HasPermission` AUTH-R.

---



## Pourquoi ce jour (après AUTH-F)

Sans AUTH-G, un MDP oublié = ticket helpdesk. Le MVP demande : Authenticator **déjà** dans le téléphone (jour 4), pas un lien mail.

Deux secrets restent distincts (AUTH-B) : MDP **app** (ce jour) ≠ MDP **AD** (jamais lu/écrit ici). Un user LDAP peut changer / reset le hash app ; le bind AUTH-13 est inchangé.

```text
Connecté (JWT, portes OK)
    POST /me/password  { old, new, logout_others? }
    → 200 ; prochain login = nouveau hash + TOTP encore

Oublié (public, pas de JWT)
    POST /auth/password/forgot     → toujours 200
    POST /auth/password/reset/verify  { ident, otp|backup } → reset_token
    POST /auth/password/reset      { reset_token, new_password, logout_all? }
    → hash changé ; sessions tuées (défaut) ; prochain login = TOTP
```

Le reset **n’est pas** un login (pas de JWT). Pending / locked / disabled : forgot 200 no-op ; verify **400** `MFA_INVALID` (même body que TOTP faux).

---



## Paliers (figés pour ce jour)


| Sujet | Choix jour 8 | Plus tard |
| ----- | ------------ | --------- |
| `POST /me/password` | JWT + `IsAuthenticated` | AUTH-R : `iam.password.change` |
| Forgot / verify / reset | `AllowAny` + `authentication_classes = []` | — |
| Portes AUTH-F | `/me/password` **bloqué** (TOS / wizard). Forgot* **public** (skip middleware) | — |
| Politique | `enforce_password_policy` AUTH-D ; si `system_settings` `security.password_*` présents → les lire | UI admin CONFIG |
| TTL ticket / rate-limit | `.env` (comme MFA / device-link) | `system_settings` `password_reset_ttl_seconds` |
| Hash ticket | même primitive que le refresh : `hash_refresh_token` (HMAC-SHA256). **Pas** le TOTP | — |
| Logout HTTP | **pas** de routes AUTH-H ; réutiliser / étendre `_force_logout_user` | AUTH-H `POST /logout*` |
| Reset helpdesk | **pas** `POST /admin/users/{id}/password` | ADMIN-A ADM-05 |


AUTH-G métier dit `HasPermission`. **Jour 8 = même palier que `/me/devices` / `/me/tos`** (JWT). AUTH-R enlèvera le palier ouvert.

---



## 1. Tables (0 migration User)

**Interdit :** `docker compose down -v`. **Pas** de nouvelle colonne `users`.

| Table | Rôle |
| ----- | ---- |
| `password_history` | AUTH-45 : archiver le hash **courant** avant `set_password` ; garder N |
| `password_reset_tokens` | Ticket **après** TOTP OK. `reset_channel=TOTP` toujours |
| `otp_secrets` | Preuve AUTH-47/48 (lecture ; backup éventuellement consommé) |
| `sessions` / `refresh_tokens` | `PASSWORD_CHANGE` / `PASSWORD_RESET` |
| `audit_logs` | `PASSWORD_CHANGE` / `PASSWORD_FORGOT` / `PASSWORD_RESET` / `PASSWORD_FORGOT_RATE_LIMITED` |

`EMAIL` / `SMS` / `APPEL` : enum **non écrite** ce jour.

Si une migration s’impose (index unique `token_hash`, etc.) : **additive** seulement.

---



## 2. Settings + seed

`.env` / `.env.example` :

```env
YAS_PASSWORD_HISTORY_N=5
YAS_PASSWORD_RESET_TTL_SECONDS=600
YAS_PASSWORD_FORGOT_RATE_LIMIT=3
YAS_PASSWORD_FORGOT_RATE_LIMIT_IP=10
YAS_PASSWORD_FORGOT_WINDOW_SECONDS=900
```

`seed_config` : upsert `system_settings` catégorie `security` (défauts = AUTH-D, **ne pas** écraser un secret sensible — il n’y en a pas ici) :

| setting_key | Défaut |
| ----------- | ------ |
| `password_min_length` | `10` |
| `password_max_length` | `128` |
| `password_require_upper` / `_lower` / `_digit` / `_special` | `true` |
| `password_history_n` | `5` |
| `password_reset_ttl_seconds` | `600` |

`enforce_password_policy` : **une** fonction partagée AUTH-D / AUTH-G. Lire settings DB si la ligne existe, sinon défauts ci-dessus / `.env` pour N et TTL.

TOTP : paramètres AUTH-C inchangés (`digits=6`, `period=30`, `valid_window=1`). Pas de 2e config.

---



## 3. Middleware + services

| Fichier | Sert à |
| ------- | ------ |
| `apps/iam/services/password_policy.py` | Lire `security.password_*` si présent ; garder charset AUTH-D |
| `apps/iam/services/password_service.py` | `rotate_password`, `request_reset` (forgot), `verify_reset_mfa`, `reset_password` — **étendre** le module actuel (`verify_password`) |
| `apps/iam/services/auth_service.py` | Étendre `_force_logout_user(*, except_session_id=None)` (AUTH-43 `logout_others`) |
| `apps/iam/services/mfa_service.py` | **Réutiliser** `_verify_totp` / `_consume_backup` (exporter si besoin, pas de 2e secret) |
| `apps/iam/services/rate_limit_service.py` | Compteurs `pwdforgot:` ident + IP (distincts du login) |
| `apps/iam/middlewares/compliance.py` | Ajouter `/api/v1/auth/password` aux préfixes **publics** |

Allowlist public **nouvelle** : `/api/v1/auth/password*` (forgot, reset/verify, reset).  
`POST /me/password` : **pas** d’allowlist → 403 `TOS_REQUIRED` / `ONBOARDING_REQUIRED` si portes KO (voulu).

`complete_login` : **ne pas** toucher.

Dummy anti-énumération sur verify : user inconnu / pas d’enroll / pending / locked / disabled → **même** 400 `MFA_INVALID` (ne pas 404).

---



## 4. HTTP

Arborescence actuelle (`views/`, `serializers/`, `urls/auth.py`, `urls/me.py`) — **pas** de `views_password.py` à la racine IAM.

| Fichier | Rôle |
| ------- | ---- |
| `apps/iam/views/password.py` | 4 vues |
| `apps/iam/serializers/password.py` | change / forgot / verify / reset |
| `apps/iam/urls/me.py` | `path("password", …)` **avant** `devices/<uuid>` |
| `apps/iam/urls/auth.py` | `password/reset/verify` **avant** `password/reset` |

| Endpoint | Auth | Effet |
| -------- | ---- | ----- |
| `POST /api/v1/me/password` | JWT | `{ old_password, new_password, logout_others? }` défaut `logout_others=true`. 400 `INVALID_OLD_PASSWORD` / `WEAK_PASSWORD` / `PASSWORD_REUSED` / `SAME_PASSWORD` |
| `POST /api/v1/auth/password/forgot` | public | `{ email }` **xor** `{ username }`. **Toujours 200** même message. Rate-limit → 200 + audit. Révoque tickets unused si user envoyable |
| `POST /api/v1/auth/password/reset/verify` | public | ident + `otp` xor `backup_code`. **Pas** de champ `channel` (400 validation). 200 `{ reset_token, expires_in }` ou 400 `MFA_INVALID` |
| `POST /api/v1/auth/password/reset` | public | `{ reset_token, new_password, logout_all? }` défaut `logout_all=true`. 400 `INVALID_TOKEN` / `WEAK_PASSWORD` / `PASSWORD_REUSED` |

Message forgot (figé) :

```json
{
  "success": true,
  "message": "Si un compte correspond, saisissez le code Google Authenticator."
}
```

Verify **ne consomme pas** le ticket (`used_at` NULL). Un 2e verify OK **révoque** l’ancien unused et en émet un nouveau.  
Reset pose `used_at` ; replay → 400 `INVALID_TOKEN`.  
`logout_others=true` : toutes les sessions **sauf** `request.yas_session` (`revoke_reason=PASSWORD_CHANGE`).  
`logout_all` (reset) : toutes (`PASSWORD_RESET`), y compris s’il restait un JWT.

Hash **jamais** en JSON. Prochain login = TOTP encore (AUTH-C).

---



## 5. Impact tests existants

`test_auth_d` : `enforce_password_policy` inchangé (register encore 400 `WEAK_PASSWORD`).  
Fixtures A/C/E/J/F : `close_gates` déjà posé — `POST /me/password` des users seedés **passe** les portes.  
Comptes neufs AUTH-D / `test_auth_f` `user_fresh` : `/me/password` → 403 TOS (voulu). Forgot/verify/reset **sans** JWT : pas de porte.

Régression : A/C/D/F encore verts.

---



## 6. Tests nouveaux (`test_auth_g.py`)


| Cas | Attendu |
| --- | ------- |
| ancien OK + nouveau conforme | 200 ; `password_history` +1 ; login ancien → 401 AUTH-05 |
| ancien faux | 400 `INVALID_OLD_PASSWORD` |
| `new == old` | 400 `SAME_PASSWORD` |
| trop court | 400 `WEAK_PASSWORD` |
| réemploi hash courant / N derniers | 400 `PASSWORD_REUSED` |
| `logout_others` défaut true (champ omis) | autres sessions inactives ; courante **active** |
| `/me/password` sans JWT | 401 |
| user neuf (portes ouvertes) + JWT | 403 `TOS_REQUIRED` |
| email inconnu forgot | **200** même message ; 0 ticket |
| jean.dupont forgot | 200 ; **0** mail / SMS |
| TOTP OK | 200 `reset_token` ; `reset_channel=TOTP` ; `used_at` NULL |
| `channel=EMAIL` dans le body | 400 validation |
| pas d’enroll MFA | 400 `MFA_INVALID` |
| 2e verify OK | nouveau ticket ; ancien `revoked_at` |
| reset OK | hash changé ; `used_at` ; 2e reset → 400 `INVALID_TOKEN` |
| `logout_all` défaut | 0 session active |
| backup AUTH-22 à la place du TOTP | 200 puis reset OK ; hash backup retiré |
| user `ldap_dn` set | hash **app** seulement (pas d’appel LDAP write) |
| pending / locked / disabled | forgot 200 ; verify 400 `MFA_INVALID` |
| 4e forgot / fenêtre | 200 ; audit `PASSWORD_FORGOT_RATE_LIMITED` |
| `/health`, `/api/docs/` | 200 ; schéma contient `/me/password` et `/auth/password/forgot` |


Helper MFA : `from apps.iam.helpers.mfa import login_until_jwt, totp_now`.  
Helper portes : `close_gates` sur les fixtures qui appellent `/me/password`.

---



## 7. Vérif manuelle

```powershell
python manage.py migrate
python manage.py seed_config
python manage.py seed_iam
python manage.py check
pytest apps/iam/tests/test_auth_g.py apps/iam/tests/test_auth_f.py apps/iam/tests/test_auth_d.py --reuse-db
```

`jean.dupont@yas.tg` (portes fermées) : login + MFA → `POST /me/password`.  
Forgot → verify TOTP → reset → login ancien 401 ; login nouveau + TOTP 200.

`/admin/` cookie : **pas** coupé. Reset **n’ouvre pas** un compte locked.

---



## Checklist jour 8

- [x] `POST /me/password` (JWT) ; jamais le hash en JSON
- [x] Politique partagée AUTH-D ; anti-réemploi N + hash courant
- [x] Forgot toujours 200 ; **zéro** envoi mail/SMS/appel
- [x] Verify TOTP / backup → ticket hashé, TTL, verify sans `used_at`
- [x] Reset : `logout_all` défaut true ; pas d’unlock ; pas de JWT
- [x] Rate-limit ident + IP ; forgot jamais 429
- [x] Compliance : skip `/api/v1/auth/password*` ; `/me/password` sous portes AUTH-F
- [x] User LDAP : hash app seulement
- [x] `test_auth_g.py` + régression D/F/A verts
- [x] `/api/docs/` documente les 4 routes
- [x] SIRH non modifié

---



## Interdits

- `HasPermission` AUTH-R
- Coder AUTH-H / AUTH-I / ADMIN-A reset
- Écrire / lire le MDP Active Directory
- SMTP, SMS, IVR, champ `channel` sur forgot
- Skip MFA / skip CGU pour changer le MDP
- 429 sur forgot (casse l’anti-énumération)
- `docker compose down -v`
- AUTH-39 (MDP forcé à la 1re connexion)

---



## Après le jour 8

Jour 9 : [00-jour-9-auth-h.md](00-jour-9-auth-h.md) — **AUTH-H** (logout, liste de sessions, idle / expiration absolue, heartbeat).
