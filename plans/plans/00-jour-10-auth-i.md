# Jour 10 — AUTH-I (sécurité compte)

**Statut :** clos (2026-09-10).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–9 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 9](00-jour-9-auth-h.md)).  
`login_history` **déjà** écrit (jour 1). `is_locked` **déjà** lu. Rate-limit AUTH-06 **déjà** là. **Livré :** lock auto N=5, historique HTTP, change email, unlock admin / lazy 30 min.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §1 — *Entrer dans l’application*) :


| Fonction MVP                                    | Ticket     | Statut                 |
| ----------------------------------------------- | ---------- | ---------------------- |
| Connexion + MFA + appareils + QR + CGU/wizard   | A–F, J     | **fait** (jours 1–7)   |
| Changer / oublier MDP ; déconnexion             | G, H       | **fait** (jours 8–9)   |
| **Historique de mes connexions**                | **AUTH-I** | **fait** (ce jour)     |
| **Compte verrouillé après trop d’essais**       | **AUTH-I** | **fait** (ce jour)     |
| Rôles / permissions HTTP                        | AUTH-R     | [jour 11](00-jour-11-auth-r.md) |


**À quoi ça sert (MVP) :** l’user voit **lui-même** « ce n’était pas moi à Lomé hier » ; après 5 mauvais MDP sur un compte **connu**, le compte se verrouille 30 min (un admin peut rouvrir). Ça ne remplace pas le rate-limit anti-énumération (inconnu = toujours 401).

**Plan métier (code à coller) :** [AUTH-I-securite.md](iam_plans/AUTH-I-securite.md) (AUTH-61 … 66).  
Chemins lab = ce fichier (`views/security.py`, pas `views_security.py` à la racine IAM).

**Livré :** `locked_at` + lock auto N=5 ; `GET /me/security/logins` + admin ; change email + verify unique ; unlock admin / lazy 30 min + job. Migration `0005_auth_i_lock_email`.

**Objectif du jour (fait) :**

1. `GET /me/security/logins` (owner) : succès **et** échecs ; geo NULL OK ; jamais de hash.
2. 5 échecs `INVALID_CREDENTIALS` sur user **connu** → `is_locked` + `locked_at` ; 5e réponse encore **401**. Bon MDP dans les 30 min → **403** `ACCOUNT_LOCKED`. `MFA_INVALID` **ne** lock **pas**.
3. Unlock admin + auto 30 min (lazy au login **avant** le 403, + job `account_unlock_reaper`). Sessions **non** tuées au lock.
4. Change email JWT (`ldap_dn` interdit) ; verify public unique service (REGISTER + EMAIL_CHANGE) ; resend JWT **429**.

**Hors jour 10 :** AUTH-R (`HasPermission`), ADMIN-A (disable, reset MDP helpdesk, kick, régions), PROF-A (fiche / avatar — PATCH `/me` n’accepte **pas** `email`), MaxMind prod, captcha, lock du compte **AD**, NOTIF-A push réel, `HasPermission`.

---



## Pourquoi ce jour (après AUTH-H)

Sans historique HTTP, « ce n’était pas moi » = ticket helpdesk. Sans lock auto, le rate-limit 15 min suffit à ralentir, pas à **fermer** un compte ciblé.

Aujourd’hui `test_locked_403` pose `is_locked=true` à la main. Le MVP demande : 5 mauvais MDP **connus** → verrou 30 min.

```text
Connecté (JWT, portes OK)
    GET  /me/security/logins?limit=&before=
    POST /me/email          { email }     → 202 ; users.email inchangé
    POST /me/email/resend                 → 200 ou 429

Public
    POST /auth/email/verify { token }     → REGISTER (D04) ou EMAIL_CHANGE
    POST /auth/register/verify-email      → même handler (alias)

Admin JWT (rôle ADMIN)
    POST /admin/users/{id}/unlock
    GET  /admin/users/{id}/logins
```

Lock : **pas** d’endpoint user. Forgot AUTH-G : locked → toujours 200 no-op (inchangé). Reset **n’unlock pas**.

---



## Paliers (figés pour ce jour)


| Sujet | Choix jour 10 | Plus tard |
| ----- | ------------- | --------- |
| `GET /me/security/logins`, `/me/email*` | JWT + `IsAuthenticated` | AUTH-R : `iam.login.read` / `iam.email.change` |
| Unlock / logins admin | JWT + `IsAdminRole` (comme MFA reset) | AUTH-R : `iam.user.unlock` / `iam.user.security.read` |
| Verify email | `AllowAny` + `authentication_classes = []` | — |
| Portes AUTH-F | historique + change email **bloqués** (réglages). Verify **public**. Unlock = admin | — |
| Geo | stub (`country` NULL). Tests AUTH-62 **écrivent** `country` en base | MaxMind licence |
| N / TTL lock | `.env` ; si `security.lock_*` en DB → les lire | UI CONFIG |
| Rate-limit AUTH-06 | **inchangé** pour ident **inconnu**. Si `is_locked` : **ne pas** court-circuiter par RATE_LIMITED **avant** le check MDP/bind (sinon le 403 `ACCOUNT_LOCKED` n’arrive jamais) | — |
| Sessions au lock | **pas** de `revoke_sessions` | — |


AUTH-I métier dit `HasPermission`. **Jour 10 = même palier que `/me/password` / logout** (JWT ; admin = rôle ADMIN).

**Collision rate-limit × lock (à coder explicitement) :**  
`LOGIN_RATE_LIMIT_ATTEMPTS=5` = N lock. Aujourd’hui le **6e** appel est `RATE_LIMITED` **avant** le MDP → un bon MDP locké resterait 401.  
Delta : user **déjà** `is_locked` → skip rate-limit **ident** (l’IP 20 reste). 6e **mauvais** MDP → encore 401 générique (history `INVALID_CREDENTIALS`, plus forcément `RATE_LIMITED`). Adapter `test_rate_limit_sixth_attempt` (toujours 401 même message ; ne plus exiger `RATE_LIMITED` si le user est locké).

`lazy_unlock` : si `is_locked` et `locked_at` **NULL** (fixture jour 1) → **ne pas** unlock (garder `test_locked_403`). Unlock auto seulement si `locked_at + TTL <= now`.

---



## 1. Tables (1 migration additive)

**Interdit :** `docker compose down -v`. Pas de `DROP`. Migration `0005_auth_i_lock_email`.

| Table | Delta |
| ----- | ----- |
| `users` | `locked_at` timestamptz NULL |
| `email_verifications` | `purpose` (`REGISTER` / `EMAIL_CHANGE`, défaut `REGISTER`) ; `expires_at` ; `revoked_at` NULL |
| `login_history` | **inchangé** (`suspicious` aussi si nouveau pays) |
| `audit_logs` | `ACCOUNT_LOCK` / `ACCOUNT_UNLOCK` / `ACCOUNT_UNLOCK_AUTO` / `LOGIN_NEW_COUNTRY` |

Lignes D04 déjà en base : `purpose=REGISTER` ; `expires_at = created_at + 48 h` (RunPython ou `default` à l’insert + backfill).

`token_hash` : garder SHA-256 AUTH-D (pas HMAC refresh) pour ne pas casser les tokens lab déjà émis.

---



## 2. Settings + seed

`.env` / `.env.example` :

```env
YAS_LOCK_AFTER_FAILURES=5
YAS_LOCK_DURATION_SECONDS=1800
YAS_EMAIL_RESEND_RATE_LIMIT=3
YAS_EMAIL_RESEND_WINDOW_SECONDS=900
```

`EMAIL_VERIFICATION_TTL_HOURS=48` **déjà** dans `settings.py` — ne pas dupliquer.  
`LOGIN_RATE_LIMIT_*` inchangés.

`seed_config` upsert `security` :

| setting_key | Défaut |
| ----------- | ------ |
| `lock_after_failures` | `5` |
| `lock_duration_seconds` | `1800` |

Job `scheduled_jobs` (comme `session_reaper`) :

| job_name | cron | handler |
| -------- | ---- | ------- |
| `account_unlock_reaper` | `*/5 * * * *` | `apps.iam.jobs.unlock_expired_locks` |

Geo enrich : **stub** `geo_service.lookup(ip) → None` (pas de job MaxMind ce jour). AUTH-62 se teste en posant `country` en fixture.

---



## 3. Middleware + services

| Fichier | Sert à |
| ------- | ------ |
| `apps/iam/services/lock_service.py` | **nouveau.** `maybe_lock_after_failure`, `lazy_unlock`, `unlock_user` (admin), `unlock_expired` |
| `apps/iam/services/email_verification_service.py` | **nouveau.** D04 + change + resend ; `register_service.verify_email` / `resend` **déléguent** |
| `apps/iam/services/geo_service.py` | **nouveau.** stub NULL |
| `apps/iam/services/auth_service.py` | après échec `INVALID_CREDENTIALS` user connu → `maybe_lock`. Après MDP/bind OK → `lazy_unlock` **puis** 403 si encore locké. Skip rate-limit ident si `is_locked` |
| `apps/iam/services/notify_stub.py` | `notify_suspicious_login` (log, comme `emit_device_new`) |
| `apps/iam/jobs.py` | `unlock_expired_locks()` |
| `apps/iam/middlewares/compliance.py` | **ne pas** allowlist `/me/security` ni `/me/email` |

`complete_login` / AUTH-29 : après INSERT history succès, `mark_suspicious` (device créé **ou** pays ≠ dernier succès géolocalisé). 1er geo **n’alerte pas**. Login **réussit** quand même.

LDAP : même `is_locked` YAS ; bind KO connu = `INVALID_CREDENTIALS` → même compteur. **Pas** de write AD.

---



## 4. HTTP

Arborescence `views/`, `serializers/`, `urls/me.py`, `urls/auth.py`, `urls/admin.py`.

| Fichier | Rôle |
| ------- | ---- |
| `apps/iam/views/security.py` | logins me, email change/resend, verify (public) |
| `apps/iam/views/admin_users.py` | unlock + logins admin (étendre) |
| `apps/iam/serializers/security.py` | listes + email + unlock |
| `apps/iam/urls/me.py` | `security/logins` ; `email` **avant** `email/resend` |
| `apps/iam/urls/auth.py` | `email/verify` (alias D04 OK) |
| `apps/iam/urls/admin.py` | `users/<uuid>/unlock`, `users/<uuid>/logins` |

| Endpoint | Auth | Effet |
| -------- | ---- | ----- |
| `GET /api/v1/me/security/logins` | JWT | `limit` défaut 50 max 100 ; `before` cursor `created_at`. Owner. Échecs inclus (`user_id` = lui) |
| `POST /api/v1/me/email` | JWT | `{ email }` → **202**. `users.email` inchangé. **400** `EMAIL_CHANGE_FORBIDDEN` si `ldap_dn`. **409** si pris. **400** si égal à l’actuel |
| `POST /api/v1/me/email/resend` | JWT | dernier `EMAIL_CHANGE` unused. **429** `EMAIL_RESEND_RATE_LIMITED` |
| `POST /api/v1/auth/email/verify` | public | token OK → `verified_at`. `EMAIL_CHANGE` → pose `users.email`. `REGISTER` = D04 (`is_active` inchangé). Replay déjà vérifié → **200**. **400** `INVALID_TOKEN` |
| `POST /api/v1/admin/users/{id}/unlock` | JWT ADMIN | `is_locked=false`, `locked_at=NULL`. **200** idempotent. Audit `ACCOUNT_UNLOCK` |
| `GET /api/v1/admin/users/{id}/logins` | JWT ADMIN | même forme que me ; **404** user inconnu |

Liste logins (forme figée) : `id`, `created_at`, `success`, `suspicious`, `ip_address`, `country`, `city`, `device_id`, `device_name`, `platform`, `browser`, `login_method`, `failure_reason`. Jamais hash / UA brut complet au-delà de `browser`.

`VerifyEmailView` AUTH-D : appeler le **même** service (alias `email/verify`).

---



## 5. Impact tests existants

`test_locked_403` (jour 1) : `is_locked=true` sans `locked_at` → **toujours 403** (pas de lazy unlock).  
`test_rate_limit_sixth_attempt` : **adapter** (voir paliers) — 401 générique inchangé.  
`test_auth_d` verify-email / resend public **200** anti-énumération.  
`test_auth_g` locked → forgot 200, verify `MFA_INVALID`.  
`test_auth_e` 1er uuid `suspicious` **encore** vrai (AUTH-29).  
Fixtures : `close_gates` pour `/me/security/logins`. User neuf AUTH-F → **403 TOS** sur l’historique (voulu).

Régression : A (lock manuel + 401 identique) + D (verify) + G + F.

---



## 6. Tests nouveaux (`test_auth_i.py`)


| Cas | Attendu |
| --- | ------- |
| `GET /me/security/logins` | 200 ; succès et échecs ; pas de hash |
| geo pas encore | `country` NULL OK |
| 1er uuid | `suspicious` (AUTH-29) |
| même device, `country` TG puis FR (fixture) | 2e succès `suspicious=true` ; login **200** MFA |
| 1er succès avec geo | **pas** d’alerte pays |
| 5e mauvais MDP user connu | `is_locked` + `locked_at` ; 5e encore **401** |
| 6e **bon** MDP dans les 30 min | **403** `ACCOUNT_LOCKED` |
| 5 `MFA_INVALID` | **pas** de lock |
| email inconnu × 20 | 0 `is_locked` |
| admin unlock | `is_locked=false` ; audit ; login + TOTP 200 |
| TTL 30 min + bon MDP | lazy unlock ; MFA / JWT |
| job `unlock_expired_locks` | `ACCOUNT_UNLOCK_AUTO` ; `locked_at` NULL |
| change email | **202** ; `users.email` ancien jusqu’au verify |
| verify change | email mis à jour ; login nouveau |
| `ldap_dn` | **400** `EMAIL_CHANGE_FORBIDDEN` |
| 4e resend JWT / 900 s | **429** |
| resend register email inconnu | **200** ; 0 mail |
| LDAP bind KO × 5 | `is_locked` YAS (mock bind) ; AD non touché |
| `/me/security/logins` user neuf | **403** `TOS_REQUIRED` |
| `/health`, `/api/docs/` | schéma contient `/me/security/logins` et `/admin/users/{id}/unlock` |


Helper MFA : `login_until_jwt`. Portes : `close_gates` sauf cas TOS.  
Lock 5 échecs : `cache.clear()` entre tests ; mot de passe faux `WrongPass1!`.

---



## 7. Vérif manuelle

```powershell
python manage.py migrate
python manage.py seed_config
python manage.py seed_iam
python manage.py check
pytest apps/iam/tests/test_auth_i.py apps/iam/tests/test_auth_a.py apps/iam/tests/test_auth_d.py apps/iam/tests/test_auth_g.py --reuse-db
```

`jean.dupont@yas.tg` : 5 × mauvais MDP → 6e bon → 403 ; attendre / forcer `locked_at` dans le passé → login + TOTP OK.  
`GET /me/security/logins` après MFA.  
`/admin/` cookie staff : **pas** l’API unlock (JWT ADMIN).

---



## Checklist jour 10

- [x] `locked_at` + lock auto N=5 ; 403 seulement si secret OK
- [x] Unlock admin + lazy 30 min + job
- [x] `GET /me/security/logins` + admin logins
- [x] Suspect pays (fixture) ; pas de blocage login
- [x] Change email + verify unique ; LDAP interdit
- [x] Resend JWT 429 ; register resend toujours 200
- [x] Rate-limit inconnu inchangé ; `is_locked` skip ident
- [x] Compliance : `/me/security*` et `/me/email*` sous portes
- [x] `test_auth_i.py` + régression A/D/G/F
- [x] SIRH non modifié

---



## Interdits

- `HasPermission` AUTH-R
- Coder ADMIN-A (disable, password helpdesk, kick, régions) / PROF-A / PRES-A
- MaxMind / GeoIP réel (stub NULL)
- Unlock self-service SMS ; captcha
- Lock / unlock le compte **Active Directory**
- `revoke_sessions` au lock
- Unlock via reset MDP AUTH-G
- `docker compose down -v`

---



## Après le jour 10

Jour 11 : [00-jour-11-auth-r.md](00-jour-11-auth-r.md) — **AUTH-R** (seed USER/ADMIN, `HasPermission` sur les vues JWT).

---



## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour** (comme les jours 3–9). Le jour 2 (admin + Swagger) est un extra déjà clos.

| Jours | Plan | Ticket MVP |
| ----- | ---- | ---------- |
| 0 | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health` |
| 1–2 | AUTH-A ; admin + Swagger | Connexion locale ; lab admin |
| 3–9 | D+B, C, E, J, F, G, H | §1 entrer + §2 appareils (sauf histo / lock) |
| **10** | **AUTH-I** (ce plan) | Historique + lock |
| 11 | AUTH-R | Qui est admin (socle droits HTTP) |
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
