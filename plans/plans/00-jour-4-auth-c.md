# Jour 4 — AUTH-C (MFA Google Authenticator)

**Statut :** clos (2026-09-08).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–3 **clos** ([jour 1](00-jour-1-auth-a.md), [jour 2](00-jour-2-admin-swagger.md), [jour 3](00-jour-3-auth-b.md)).  
Facteur 1 OK → `begin_mfa`. JWT seulement après `POST /mfa/verify`.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §1 — *Entrer dans l’application*) :


| Fonction MVP                                    | Ticket     | Statut              |
| ----------------------------------------------- | ---------- | ------------------- |
| Connexion identifiant + mot de passe            | AUTH-A     | **fait** (jour 1)   |
| Inscription AD / hors AD                        | AUTH-D     | **fait** (jour 3)   |
| Connexion compte Windows / Active Directory     | AUTH-B     | **fait** (jour 3)   |
| **Scanner le QR Google Authenticator**          | **AUTH-C** | **fait** (ce jour)  |
| **Valider le code Authenticator (6 chiffres)**  | **AUTH-C** | **fait** (ce jour)  |


**À quoi ça sert (MVP) :** après le mot de passe (app **ou** Windows), personne n’entre dans l’API sans un code à 6 chiffres (ou un code de secours). Premier login : l’app affiche un **QR** à scanner dans Google Authenticator.

**Plan métier (code à coller) :** [AUTH-C-mfa-otp.md](iam_plans/AUTH-C-mfa-otp.md) (AUTH-19 … 24).  
Table déjà en base : `otp_secrets` (`apps/iam/models.py` — `OtpSecret`). **0 ligne** en seed.

**Objectif du jour :**

1. Après facteur 1 OK (`login`, `login/ldap`, `register/ad`) → **`begin_mfa`**, plus de JWT.
2. `POST /mfa/verify` : TOTP (ou backup si déjà enrollé) → **seul** chemin vers `complete_login`.
3. Enroll : `otpauth_uri` + QR ; 1er TOTP OK → `backup_codes` **une fois**.
4. Tests AUTH-A/B/D **mis à jour** : 200 login = `mfa_required`, pas `access_token`.

**Hors jour 4 :** AUTH-J (QR 2ᵉ appareil `yasconnect://…`), AUTH-E (liste devices / push), AUTH-R (`HasPermission` — palier ADMIN comme D05), SMS / e-mail OTP, skip MFA, `devices.trusted`.

---



## Pourquoi ce jour (après AUTH-A/B/D)

Le jour 3 a volontairement laissé `complete_login` (JWT) après MDP, LDAP **et** `register/ad`, pour ne pas coder MFA dans le même incrément.

Sans AUTH-C, un MDP volé (app ou Windows) ouvre l’API. Le refresh AUTH-10 **ne** redemande **pas** d’OTP : il protège la **session déjà ouverte**, pas le premier facteur.

Ordre contractuel :

```text
facteur 1 OK (login / login/ldap / register/ad)
    → begin_mfa  (mfa_token, éventuellement otpauth_uri)
    → POST /mfa/verify  (otp ou backup)
    → complete_login  (JWT + device + session)
```

`/admin/` Django (cookie, rôle ADMIN) **n’est pas** coupé par TOTP : c’est le lab jour 2. Seule l’**API** JWT l’est.

---



## Paliers (figés pour ce jour)


| Sujet                         | Choix jour 4                                                                                          | Plus tard                                      |
| ----------------------------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| Après facteur 1               | `begin_mfa` → **pas** de JWT                                                                          | — (c’est le contrat AUTH-C)                    |
| `register/ad`                 | même `begin_mfa` que login (enroll pour un compte neuf)                                               | —                                              |
| Regen backup                  | JWT (session **déjà** MFA). Pas `HasPermission` ce jour                                               | AUTH-R : `iam.mfa.regenerate`                  |
| Reset MFA admin               | JWT + `role.code == ADMIN` (`IsAdminRole`, comme D05)                                                 | AUTH-R : `iam.mfa.reset` **sans** fallback     |
| Secret TOTP                   | Fernet (`YAS_MFA_FERNET_KEY` dans `.env`, **pas** `system_settings`)                                  | rotation = ré-enroll de tous                   |
| Message OTP faux              | même 401 AUTH-05 que MDP faux (`INVALID_CREDENTIALS`)                                                 | le front affiche « Code incorrect »            |


AUTH-C métier dit « pas de fallback ADMIN » pour le reset. **Jour 4 = même palier que D05** (rôle ADMIN). AUTH-R enlèvera le fallback.

---



## 1. Paquets + `.env`

Dans `requirements/base.txt` :

```text
pyotp>=2.9,<3.0
cryptography>=43.0,<47.0
```

```powershell
pip install -r requirements\dev.txt
```

`.env` / `.env.example` (lab) :

```env
YAS_MFA_CHALLENGE_TTL_SECONDS=300
YAS_MFA_OTP_ATTEMPTS=5
YAS_MFA_OTP_WINDOW_SECONDS=900
YAS_MFA_BACKUP_COUNT=10
YAS_MFA_FERNET_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```

Ne **pas** committer une clé de prod. Tests : clé Fernet **fixe** (settings test / `conftest`).

Interdit : secret TOTP dans `system_settings`, SMS, e-mail OTP.

---



## 2. Settings

Dans `config/settings.py` : lire les `YAS_MFA_*` (voir [AUTH-C](iam_plans/AUTH-C-mfa-otp.md) §1).  
`YAS_MFA_ISSUER = "YAS Connect"` (QR).  
Swagger : tag Auth — documenter `mfa/verify`, regen, reset admin.

---



## 3. `mfa_service` (socle, avant de couper les JWT)

| Fichier                              | Sert à                                                                 |
| ------------------------------------ | ---------------------------------------------------------------------- |
| `apps/iam/services/mfa_service.py`   | Fernet, `begin_mfa`, `provision_qr`, `verify_mfa`, regen, reset admin  |
| `apps/iam/services/auth_service.py`  | `login` / `login_ldap` : `return begin_mfa(...)` **à la place** de `complete_login` |
| `apps/iam/services/register_service.py` | `register_ad` : idem (`begin_mfa`, pas JWT direct)                 |

`complete_login` **inchangé**. `rate_limit_service.reset(ident_key)` reste **après** OTP OK (dans `complete_login`), **pas** après le facteur 1.

Challenge `mfa_token` : opaque, hashé en cache (TTL 5 min). Jamais dans `login_history` / logs. Secret TOTP **jamais** en clair en base.

Détail coller : AUTH-C §3–8.

---



## 4. HTTP

| Endpoint | Auth | Effet |
| -------- | ---- | ----- |
| `POST /api/v1/auth/login` | public | Facteur 1 inchangé (401/403). **200** = `mfa_required` + `mfa_token` ; `enroll` + `otpauth_uri` si 1er login |
| `POST /api/v1/auth/login/ldap` | public | Idem après bind AD OK |
| `POST /api/v1/auth/register/ad` | public | JIT inchangé (crée le user) puis **`begin_mfa`**, pas de JWT |
| `POST /api/v1/auth/mfa/verify` | public | `otp` XOR `backup_code` → JWT (`complete_login`). Enroll : `otp` seul + `backup_codes` une fois |
| `POST /api/v1/auth/mfa/backup-codes/regenerate` | JWT | Body `{ "otp" }` ; nouveaux codes une fois |
| `POST /api/v1/admin/users/{id}/mfa/reset` | JWT + ADMIN | Supprime `otp_secrets` ; révoque sessions cible ; audit `MFA_RESET` |
| `POST /api/v1/auth/refresh` | public | **Inchangé** (pas d’OTP) |

`register` hors AD, `check-ad`, verify-email, D05 approve/reject : **inchangés** (pas de JWT à l’inscription locale ; approve puis login → MFA).

401 `MFA_CHALLENGE_EXPIRED` si `mfa_token` inconnu / périmé → refaire le facteur 1.

Fichiers : serializers MFA, `MfaVerifyView`, `BackupRegenView`, vue reset sous `urls_admin.py`.

---



## 5. Enroll vs login suivant

| Situation | Réponse facteur 1 | Verify |
| --------- | ----------------- | ------ |
| Pas de `otp_secrets.verified_at` (seed `jean.dupont` / `admin`, nouveau `register/ad`) | `enroll=true` + `otpauth_uri` | **uniquement** `otp` ; JSON + `backup_codes` une fois |
| Déjà enrollé | `enroll=false`, pas d’URI | `otp` **ou** `backup_code` ; pas de `backup_codes` dans le JSON |
| 2e `begin_mfa` **avant** verify | **nouveau** secret (QR abandonné = rotate) | — |
| `devices.trusted=true` | **toujours** MFA | — |
| USER et ADMIN | **même** règle | — |

QR enroll = `otpauth://totp/…` (Google Authenticator).  
**Ce n’est pas** le QR AUTH-J (`yasconnect://device-link/…`).

---



## 6. Impact tests existants (obligatoire)

Aujourd’hui `test_auth_a.py`, `test_auth_d.py` (`test_d02_ok`), `test_auth_b.py` (`test_login_ldap_ok_after_d02`, `test_auth_a_jean_intact`, D05 login après approve) attendent `access_token` au login.

Jour 4 : ces 200 deviennent `mfa_required` **sans** token. Helper de test :

```python
# 1) facteur 1 → mfa_token
# 2) pyotp.TOTP(secret).now() → POST /mfa/verify
# 3) assert access_token
```

Pour enroll : lire / décrypter le secret de `otp_secrets` (Fernet de test) **ou** stub `provision_qr` avec un `b32` connu.

401/403/503 facteur 1 (**inconnu, MDP, pending, AD down**) **restent** identiques — ne pas casser ces cas.

`seed_iam` : **toujours 0** ligne `otp_secrets`. `ldap_dn` jean.dupont **toujours NULL**.

---



## 7. Admin Django + Swagger

`OtpSecret` : enregistrer en admin **lecture** ; **ne pas** afficher `secret` en clair (masquer comme `bind_password`). `backup_codes` = hash, pas le clair.

`/api/docs/` : Try it out login → copier `mfa_token` + `otpauth_uri` → verify. Authorize Bearer **après** verify.

---



## 8. Tests nouveaux (`test_auth_c.py`)

Coller la table AUTH-C §11. Minimum jour 4 :


| Cas | Attendu |
| --- | ------- |
| Login MDP OK | 200 `mfa_required` ; **pas** d’`access_token` |
| Login LDAP bind OK (user D02) | idem |
| 1er login | `enroll=true` + `otpauth_uri` ; `otp_secrets.enabled=false` |
| Verify TOTP enroll | JWT + `backup_codes` une fois ; `verified_at` posé |
| 2e login + verify | JWT **sans** `backup_codes` |
| TOTP faux | 401 AUTH-05 ; 0 session |
| `mfa_token` périmé | 401 `MFA_CHALLENGE_EXPIRED` |
| Backup valide / rejoué | 200 puis 401 |
| Backup pendant enroll | 400 |
| `trusted=true` | quand même `mfa_required` |
| `register/ad` | user créé + `mfa_required`, pas JWT |
| Refresh après MFA | 200 sans OTP |
| Reset ADMIN | plus d’`otp_secrets` ; sessions révoquées ; enroll au login suivant |
| USER appelle reset | 403 |
| `POST /login` jean.dupont facteur 1 | 200 MFA ; `ldap_dn` NULL |
| `/health`, `/api/docs/` | 200 |


---



## 9. Vérif manuelle

```powershell
pip install -r requirements\dev.txt
# poser YAS_MFA_FERNET_KEY dans .env
python manage.py check
pytest apps/iam/tests/test_auth_c.py apps/iam/tests/test_auth_a.py apps/iam/tests/test_auth_d.py apps/iam/tests/test_auth_b.py apps/iam/tests/test_jour_2.py --reuse-db
```

```powershell
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login -H "Content-Type: application/json" -d "{\"email\":\"jean.dupont@yas.tg\",\"password\":\"Secret123!\",\"device\":{\"device_uuid\":\"dev-1\",\"platform\":\"WEB\"}}"
# scanner otpauth_uri dans Google Authenticator, puis POST /api/v1/auth/mfa/verify
```

`/admin/` : toujours `admin@yas.tg` / `Admin123!` (cookie, **sans** TOTP).  
API admin (approve, reset MFA) : JWT **après** verify.

---



## Checklist jour 4

- [x] `pyotp` + `cryptography` ; `YAS_MFA_FERNET_KEY` dans `.env` (pas git / pas `system_settings`)
- [x] `login` / `login/ldap` / `register/ad` → `begin_mfa` (plus de JWT)
- [x] `POST /mfa/verify` → seul `complete_login`
- [x] Enroll : `otpauth_uri` ; 1er OTP → `backup_codes` une fois
- [x] `devices.trusted` et le rôle n’exemptent pas
- [x] Refresh sans OTP
- [x] Regen backup (JWT) ; reset MFA (JWT + ADMIN) ; pas de `DELETE /mfa` user
- [x] Secret TOTP chiffré ; backups hashés ; rien en logs
- [x] Tests A/B/D adaptés + `test_auth_c.py` verts
- [x] `/api/docs/` documente verify / regen / reset
- [x] `/admin/` cookie et `/health` intacts
- [x] SIRH non modifié

---



## Interdits

- JWT après facteur 1 (même pour ADMIN)
- Skip MFA, SMS, e-mail OTP
- Lire `devices.trusted` pour alléger
- Coder AUTH-J (QR 2ᵉ appareil) dans le même incrément
- Stocker secret TOTP ou backup en clair
- Committer `YAS_MFA_FERNET_KEY` de prod
- `docker compose down -v`
- HasPermission AUTH-R (palier ADMIN seulement)

---



## Après le jour 4

Jour 5 : [00-jour-5-auth-e.md](00-jour-5-auth-e.md) — **AUTH-E** (liste / rename / push / trusted / jailbreak / révocation).  
Puis **AUTH-J** (QR 2ᵉ écran `yasconnect://…` + TOTP déjà enrollé).
