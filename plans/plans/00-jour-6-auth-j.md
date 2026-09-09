# Jour 6 — AUTH-J (lier un 2ᵉ appareil par QR)

**Statut :** clos (2026-09-09).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–5 **clos** ([jour 1](00-jour-1-auth-a.md), [jour 2](00-jour-2-admin-swagger.md), [jour 3](00-jour-3-auth-b.md), [jour 4](00-jour-4-auth-c.md), [jour 5](00-jour-5-auth-e.md)).  
Lien QR 2ᵉ écran **livré** : start / poll / confirm TOTP. TTL **120 s**.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §2 — *Mon profil et mes appareils*) :


| Fonction MVP                              | Ticket     | Statut                |
| ----------------------------------------- | ---------- | --------------------- |
| Liste / nommer / révoquer / alerte nouvel | AUTH-E     | **fait** (jour 5)     |
| **Relier un ordi / autre écran par QR**   | **AUTH-J** | **fait** (ce jour)    |
| **Confirmer le lien avec Authenticator**  | **AUTH-J** | **fait** (TOTP)       |
| Mot de passe oublié via Authenticator     | AUTH-G     | plus tard             |


**À quoi ça sert (MVP) :** ouvrir Connect sur un PC **sans retaper le mot de passe**. L’ordi affiche un QR ; le téléphone **déjà ouvert** le scanne **dans YAS Connect** ; un code Google Authenticator est **exigé**. Ce n’est **pas** le QR `otpauth://` du 1er login (AUTH-C).

**Plan métier (code à coller) :** [AUTH-J-lier-appareil-qr.md](iam_plans/AUTH-J-lier-appareil-qr.md) (AUTH-67 … 69).  
`LoginMethod.DEVICE_LINK` **déjà** dans `apps/iam/models.py`. **0 table SQL** : challenge = cache (Redis / LocMem), comme `mfa_token`.

**Objectif du jour :**

1. `POST /auth/device-link/start` : challenge + `qr_payload` + `waiter_secret` (secret **hors** QR). TTL 120 s.
2. `GET /auth/device-link/{id}` : poll waiter. `PENDING` sans JWT ; `APPROVED` = tokens `complete_login` **une fois** puis 410.
3. `POST /me/devices/link` : téléphone JWT + **TOTP obligatoire** (pas de backup) → `complete_login(..., login_method=DEVICE_LINK)` pour le device du waiter.
4. AUTH-29 / jailbreak / compromis : **même** pipeline que le login MFA (jour 5).

**Hors jour 6 :** WebSocket « QR approuvé » (le poll suffit), AUTH-H (logout), AUTH-F (CGU), AUTH-G, CRYPTO-A (PUT identity après tokens), Play Integrity, `HasPermission` AUTH-R, QR magique « rester connecté 14 j ».

---



## Pourquoi ce jour (après AUTH-E)

Le jour 5 a donné la liste / révocation / alerte. Sans AUTH-J, l’user doit retaper MDP + TOTP sur chaque nouvel écran. Le MVP demande : scanner depuis le téléphone **déjà** MFA, **puis** Authenticator.

Deux QR distincts (inchangé) :

| QR | App qui scanne | Effet |
|----|----------------|-------|
| `otpauth://totp/…` | **Google Authenticator** | Enroll secret TOTP (jour 4) |
| `yasconnect://device-link/v1?cid=…` | **YAS Connect** (caméra) | Propose de lier ; JWT **seulement** après TOTP |

Ordre contractuel :

```text
Waiter (ordi) : POST /auth/device-link/start + DeviceSpec
    → affiche QR (cid seulement)
    → poll GET /auth/device-link/{id} + X-Device-Link-Secret  (PENDING, pas de JWT)
Téléphone (JWT déjà MFA) : scan → écran Authenticator
    → POST /me/devices/link { challenge_id, otp }
    → complete_login (DEVICE_LINK) pour le DeviceSpec du waiter
Waiter : prochaine poll = APPROVED + access_token + refresh_token (one-shot)
```

`trusted` **non lu** : n’épargne pas le TOTP (AUTH-C-26).  
Le téléphone **ne** reçoit **pas** les JWT de l’ordi (`linked` + `device_id` seulement).

---



## Paliers (figés pour ce jour)


| Sujet            | Choix jour 6                                                                 | Plus tard                                      |
| ---------------- | ---------------------------------------------------------------------------- | ---------------------------------------------- |
| Start / poll     | `AllowAny` + secret waiter (header)                                          | —                                              |
| Confirm téléphone | JWT + `IsAuthenticated` (comme `/me/devices*` jour 5)                       | AUTH-R : `iam.device.update` **sans** fallback |
| TTL              | `.env` `YAS_DEVICE_LINK_TTL_SECONDS=120`                                     | `system_settings` `security.device_link_ttl_seconds` |
| Backup codes     | **refusés** (`MFA_BACKUP_NOT_ALLOWED`)                                       | —                                              |
| Push / notif     | AUTH-29 stub jour 5 (`DEVICE_NEW` si 1er uuid)                               | NOTIF-A                                        |
| Temps réel       | Poll 2 s                                                                     | WS « QR approuvé »                             |


AUTH-J métier dit `HasPermission` `iam.device.update`. **Jour 6 = même palier que AUTH-E soi** (JWT). AUTH-R enlèvera le palier ouvert.

---



## 1. Settings — **0** migration

**Interdit :** `docker compose down -v`. `LoginMethod.DEVICE_LINK` est déjà en base (jour 1).

`.env` / `.env.example` :

```env
# TTL challenge QR 2ᵉ appareil (secondes)
YAS_DEVICE_LINK_TTL_SECONDS=120
```

`config/settings.py` : `YAS_DEVICE_LINK_TTL_SECONDS = env.int("YAS_DEVICE_LINK_TTL_SECONDS", default=120)`.

Cache : déjà Redis si `REDIS_URL`, sinon LocMem (comme MFA). Prod multi-workers = Redis **requis**.

---



## 2. `device_link_service`

| Fichier | Sert à |
| ------- | ------ |
| `apps/iam/services/device_link_service.py` | `start_device_link`, `poll_device_link`, `confirm_device_link` |
| `apps/iam/services/mfa_service.py` | réutiliser `_verify_totp`, `_mfa_ready`, `hash_mfa_token` (ne pas passer par `begin_mfa`) |
| `apps/iam/services/auth_service.py` | `complete_login(..., login_method=LoginMethod.DEVICE_LINK)` — **ne pas** le réécrire |

Clé cache : `device-link:{challenge_id}`. Payload : `status`, `device_spec`, `waiter_secret_hash`, `ip`, `user_id`, `tokens`.

`waiter_secret` et TOTP **jamais** dans `login_history` / logs / audit.

Rate-limit start : **10 / min / IP** (429). OTP faux : même throttle AUTH-C par `user_id` (pas de lock compte AUTH-63).

Détail coller : AUTH-J §1–3.

---



## 3. HTTP

Fichiers (arborescence actuelle) :

- `apps/iam/serializers/devices.py` — `DeviceLinkStartSerializer`, `DeviceLinkConfirmSerializer`
- `apps/iam/views/device_link.py`
- `apps/iam/urls/auth.py` — start + poll
- `apps/iam/urls/me.py` — `POST devices/link` **avant** `devices/<uuid:pk>` (sinon « link » match un uuid)

| Endpoint | Auth | Effet |
| -------- | ---- | ----- |
| `POST /api/v1/auth/device-link/start` | public | Body `{ "device": DeviceSpec }`. 200 : `challenge_id`, `waiter_secret`, `expires_in`, `qr_payload`. Secret **absent** du QR |
| `GET /api/v1/auth/device-link/{challenge_id}` | public | Header `X-Device-Link-Secret` obligatoire. PENDING / APPROVED+tokens (delete cache) / 403 secret / 410 expiré |
| `POST /api/v1/me/devices/link` | JWT | Body `{ challenge_id, otp }`. 200 `{ linked, device_id }` **sans** tokens. 400 sans otp / backup / self. 401 TOTP faux. 410 expiré. 409 uuid d’un autre user |

`jailbreak` / `push_token` dans le spec waiter : appliqués au `complete_login` (AUTH-E-32/33).  
403 appareil **après** TOTP OK (messages distincts d’AUTH-05).

---



## 4. Enroll AUTH-C vs lien (rappel)

| Situation | AUTH-J |
| --------- | ------ |
| 1er login téléphone | toujours `otpauth://` + `/mfa/verify` — **pas** device-link |
| Waiter avant confirm | poll `PENDING`, **0** JWT |
| TOTP OK | session waiter `login_method=DEVICE_LINK` ; history idem |
| 1er uuid via QR | `suspicious=true` + audit `DEVICE_NEW` (AUTH-29) |
| même uuid que le téléphone | 400 `DEVICE_LINK_SELF` |
| uuid déjà chez un autre user | 409 `DEVICE_UUID_TAKEN` |
| `trusted=true` sur le téléphone | TOTP **quand même** exigé |
| 2e poll après APPROVED | 410 |
| TTL 121 s | 410 des deux côtés |

---



## 5. Impact tests existants

`test_auth_c.py` enroll `otpauth://` **inchangé**.  
`test_auth_e.py` `/me/devices*` **inchangé** (nouvelle route `devices/link` à côté).  
401/403 facteur 1 + MFA **inchangés**.

Helper MFA (`apps.iam.helpers.mfa`) **réutilisé** pour obtenir un JWT téléphone.

---



## 6. Admin Django + Swagger

Pas de nouvelle table. `login_history.login_method=DEVICE_LINK` déjà dans les choices (lecture admin).

`/api/docs/` : tag **Auth** (start / poll) + **Devices** (confirm). Décrire le header `X-Device-Link-Secret`.

---



## 7. Tests nouveaux (`test_auth_j.py`)

Coller la table AUTH-J §5. Minimum jour 6 :


| Cas | Attendu |
| --- | ------- |
| start | 200 challenge + `qr_payload` ; secret **absent** du QR |
| poll sans secret / secret faux | 403 `DEVICE_LINK_FORBIDDEN` |
| poll avant confirm | `PENDING`, pas de JWT |
| confirm **sans** `otp` | 400 |
| confirm `backup_code` | 400 `MFA_BACKUP_NOT_ALLOWED` |
| TOTP faux | 401 AUTH-05 ; waiter toujours `PENDING` |
| TOTP OK | téléphone `linked` ; 1re poll waiter = tokens ; 2e poll = 410 |
| TTL 121 s | 410 des deux côtés |
| même `device_uuid` que le téléphone | 400 `DEVICE_LINK_SELF` |
| uuid déjà chez un autre user | 409 |
| 1er uuid via QR | `suspicious=true` + `DEVICE_NEW` |
| `trusted=true` sur le téléphone | TOTP **quand même** exigé |
| session waiter | `login_method=DEVICE_LINK` |
| enroll AUTH-C | `otpauth://` **inchangé** |
| `/health`, `/api/docs/` | 200 |


Régression : `test_auth_e.py` `test_auth_c.py` `test_auth_a.py` `test_jour_2.py` encore verts.

---



## 8. Vérif manuelle

```powershell
python manage.py check
pytest apps/iam/tests/test_auth_j.py apps/iam/tests/test_auth_e.py apps/iam/tests/test_auth_c.py --reuse-db
```

```powershell
# Waiter (ordi)
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/device-link/start -H "Content-Type: application/json" -d "{\"device\":{\"device_uuid\":\"web-2\",\"platform\":\"WEB\",\"device_name\":\"PC test\"}}"

# Poll (secret du start)
curl -s http://127.0.0.1:8000/api/v1/auth/device-link/<challenge_id> -H "X-Device-Link-Secret: <waiter_secret>"

# Téléphone déjà connecté (JWT jour 4+5) + code Authenticator
curl -s -X POST http://127.0.0.1:8000/api/v1/me/devices/link -H "Authorization: Bearer <jwt>" -H "Content-Type: application/json" -d "{\"challenge_id\":\"<uuid>\",\"otp\":\"<6 chiffres>\"}"
```

`/admin/` cookie **sans** TOTP (inchangé). Confirm lien = JWT **après** verify.

---



## Checklist jour 6

- [x] 0 migration ; `YAS_DEVICE_LINK_TTL_SECONDS` (120) ; cache `device-link:`
- [x] `POST /auth/device-link/start` : secret hors QR ; rate-limit IP
- [x] `GET` poll : PENDING sans JWT ; APPROVED one-shot puis 410
- [x] `POST /me/devices/link` : TOTP obligatoire ; pas de backup ; pas de JWT téléphone
- [x] `complete_login` `DEVICE_LINK` ; AUTH-29 / jailbreak / compromis inchangés
- [x] `DEVICE_LINK_SELF` / `DEVICE_UUID_TAKEN` / TTL 410
- [x] `trusted` n’exempte pas le TOTP
- [x] `test_auth_j.py` + régression A/C/E/jour 2 verts
- [x] `/api/docs/` documente start / poll / link
- [x] `/admin/` cookie et `/health` intacts
- [x] SIRH non modifié
- [x] QR enroll AUTH-C inchangé

---



## Interdits

- JWT au waiter **avant** TOTP (scan seul ≠ connexion)
- Mettre `waiter_secret` dans le QR
- Accepter un `backup_code` sur `/me/devices/link`
- Passer par `begin_mfa` / nouvel enroll
- WebSocket / CRYPTO-A / AUTH-H / AUTH-F dans le même incrément
- `HasPermission` AUTH-R (palier JWT seulement)
- `docker compose down -v`

---



## Après le jour 6

Jour 7 : [00-jour-7-auth-f.md](00-jour-7-auth-f.md) — **AUTH-F** (CGU + wizard premier paramétrage).
