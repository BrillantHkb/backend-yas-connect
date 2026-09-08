# Jour 5 — AUTH-E (appareils)

**Statut :** à faire.  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–4 **clos** ([jour 1](00-jour-1-auth-a.md), [jour 2](00-jour-2-admin-swagger.md), [jour 3](00-jour-3-auth-b.md), [jour 4](00-jour-4-auth-c.md)).  
`complete_login` upsert déjà un `devices` (AUTH-11) après MFA. Il n’y a **pas** encore de liste, rename, push, trusted, jailbreak bloquant, révocation, alerte nouvel appareil.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §2 — *Mon profil et mes appareils*) :


| Fonction MVP                         | Ticket     | Statut              |
| ------------------------------------ | ---------- | ------------------- |
| Scanner / valider Google Authenticator | AUTH-C   | **fait** (jour 4)   |
| **Liste de mes téléphones et ordis** | **AUTH-E** | **ce jour**         |
| **Nommer un appareil**               | **AUTH-E** | **ce jour**         |
| **Déconnecter un appareil**          | **AUTH-E** | **ce jour** (revoke) |
| **Alerte « nouvel appareil »**       | **AUTH-E** | **ce jour** (audit + stub) |
| Relier un ordi par QR                | AUTH-J     | jour suivant        |


**À quoi ça sert (MVP) :** voir où le compte est ouvert, nommer « iPhone perso », couper un téléphone perdu, être prévenu si un **nouvel** UUID apparaît. `trusted` = étiquette UI (« c’est le mien »), **pas** un skip MFA.

**Plan métier (code à coller) :** [AUTH-E-appareils.md](iam_plans/AUTH-E-appareils.md) (AUTH-27 … 36).  
Table déjà en base : `devices` (`apps/iam/models.py` — `Device`). Colonnes `trusted` / `compromised` / `jailbreak` / `push_token` **déjà** là ; AUTH-A ne les lit pas (sauf upsert partiel).

**Objectif du jour :**

1. Enrichir `upsert_device` + `complete_login` (après MFA) : jailbreak, compromis → 403, 1er UUID → `DEVICE_NEW` + `suspicious`.
2. CRUD soi : `GET/PATCH /me/devices*`, revoke, compromise.
3. Admin : compromise / clear-compromise (`IsAdminRole`, comme D05).
4. `login_history.suspicious` + `FailureReason` DEVICE_* (migration **additive**, pas `down -v`).

**Hors jour 5 :** AUTH-J (QR `yasconnect://…`), AUTH-H (logout session **sans** vider push/trusted), AUTH-I (nouveau pays / GeoIP), NOTIF-A (push FCM réel), Play Integrity / DeviceCheck, `HasPermission` AUTH-R, DELETE `devices`.

---



## Pourquoi ce jour (après AUTH-C)

Le jour 4 a coupé le JWT derrière TOTP. L’upsert appareil se fait **dans** `complete_login` (après `/mfa/verify`). Sans AUTH-E, l’user ne voit pas ses machines, ne peut pas révoquer un vol, et un jailbreak mobile n’est pas bloqué.

`trusted` reste **déclaratif** : AUTH-C ne le lit toujours pas.

Ordre contractuel (inchangé + delta) :

```text
facteur 1 OK → begin_mfa → POST /mfa/verify (TOTP)
    → complete_login
        → upsert_device
        → 403 DEVICE_COMPROMISED / DEVICE_JAILBROKEN (si politique)
        → si created : audit DEVICE_NEW + suspicious
        → session + JWT
```

Les 403 appareil sont **après** facteur 1+2 (messages **distincts** d’AUTH-05 : l’user est déjà identifié).

---



## Paliers (figés pour ce jour)


| Sujet              | Choix jour 5                                                                 | Plus tard                                      |
| ------------------ | ---------------------------------------------------------------------------- | ---------------------------------------------- |
| `/me/devices*`     | JWT + `IsAuthenticated` ; owner only (404 si autre user)                     | AUTH-R : `iam.device.{read,update,revoke,compromise}` |
| Admin compromise   | JWT + `IsAdminRole` (comme D05 / reset MFA)                                  | AUTH-R : `iam.device.manage` **sans** fallback |
| Alerte nouvel app. | `audit_logs` `DEVICE_NEW` + `logger.info` (stub)                             | NOTIF-A : `NotificationService.emit` + push    |
| Jailbreak bloquant | `YAS_BLOCK_JAILBREAK` dans `.env` (défaut `true`)                            | `system_settings` `security.block_jailbreak`   |
| `trusted`          | PATCH owner ; **aucun** effet MFA                                            | —                                              |
| Notif e-mail       | **pas** ce jour                                                              | AUTH-I / NOTIF                                 |


AUTH-E métier dit `HasPermission` sans fallback ADMIN. **Jour 5 = même palier que D05 / AUTH-C reset** (JWT pour soi, rôle ADMIN pour l’admin). AUTH-R enlèvera le fallback.

---



## 1. Migration (additive)

**Interdit :** `docker compose down -v`.

Sur `LoginHistory` :

- `suspicious = BooleanField(default=False)` — 1er UUID (AUTH-29) ; AUTH-I (pays) plus tard.
- `FailureReason` : `DEVICE_COMPROMISED`, `DEVICE_JAILBROKEN`.

```powershell
python manage.py makemigrations iam
python manage.py migrate
```

`devices` : **0** nouvelle colonne. Seed `jean.dupont` / `admin` : toujours **0** ligne `devices` tant qu’on n’a pas MFA-verify.

---



## 2. Settings

`.env` / `.env.example` :

```env
# true = 403 DEVICE_JAILBROKEN sur IOS/ANDROID si spec.jailbreak
YAS_BLOCK_JAILBREAK=true
```

`config/settings.py` : `YAS_BLOCK_JAILBREAK = env.bool("YAS_BLOCK_JAILBREAK", default=True)`.  
WEB / DESKTOP : flag stocké si envoyé, **jamais** bloquant (pas de root navigateur).

---



## 3. `device_service` (étendre AUTH-11)

| Fichier | Sert à |
| ------- | ------ |
| `apps/iam/services/device_service.py` | `upsert_device` → `(device, created)` ; `jailbreak_blocked` ; `kill_device` ; `set_trusted` ; `on_new_device` |
| `apps/iam/services/notify_stub.py` | `emit_device_new` : log + **rien d’autre** (pas d’app `notifications`) |
| `apps/iam/services/auth_service.py` | `complete_login` : queue AUTH-E **avant** INSERT session |
| `apps/iam/services/auth_service.py` `_history` | kwarg `suspicious=False` |

Ne **pas** écraser `trusted` / `compromised` depuis le login.  
`push_token` : ne poser que si le spec en envoie un (ne pas vider au relogin sans token).  
`jailbreak` : écrit depuis le spec (mobile).

Détail coller : AUTH-E §2–8.

---



## 4. HTTP

Préfixe **nouveau** : `/api/v1/me/` dans `config/urls.py` (`apps/iam/urls_me.py`).  
Admin : étendre `urls_admin.py`.

| Endpoint | Auth | Effet |
| -------- | ---- | ----- |
| `GET /api/v1/me/devices` | JWT | Liste **soi** ; `is_current` via `request.yas_session.device_id` ; **pas** de `push_token` |
| `PATCH /api/v1/me/devices/current` | JWT | Heartbeat : `push_token`, `app_version`, `os_version`, `jailbreak`. Identité = session, pas un UUID forgé |
| `PATCH /api/v1/me/devices/{id}` | JWT owner | `device_name` et/ou `trusted`. Pas `compromised` |
| `POST /api/v1/me/devices/{id}/revoke` | JWT owner | Kill sessions + refresh + `push_token=""` + `trusted=false`. Ligne **conservée**. Relogin **OK** |
| `POST /api/v1/me/devices/{id}/compromise` | JWT owner | Interdit si `is_current` (400 `CANNOT_COMPROMISE_CURRENT`). Sinon kill + `compromised=true` → prochain login 403 |
| `POST /api/v1/admin/devices/{id}/compromise` | JWT + ADMIN | Y compris appareil courant de la cible |
| `POST /api/v1/admin/devices/{id}/clear-compromise` | JWT + ADMIN | `compromised=false` ; **ne** réactive **pas** `trusted` |
| Login / MFA verify | public | Body `device.jailbreak` (défaut `false`). 403 appareil **après** TOTP OK |

`is_current` : `YasJWTAuthentication` pose déjà `request.yas_session`.

Fichiers : `views_devices.py`, serializers device (out **sans** `push_token`), `DeviceSpecSerializer` + `jailbreak`.

---



## 5. Enroll vs relogin (rappel AUTH-C)

| Situation | AUTH-E |
| --------- | ------ |
| 1er `device_uuid` après MFA | 1 ligne ; history succès `suspicious=true` ; audit `DEVICE_NEW` |
| 2e login **même** UUID | `created=False` ; `suspicious=false` ; `last_seen` MAJ |
| `trusted=true` | MFA **toujours** required |
| Revoke puis même UUID | relogin autorisé (`created=False`, pas de 2e alerte) |
| Compromise | login 403 tant que admin `clear-compromise` |
| IOS/ANDROID `jailbreak` + `YAS_BLOCK_JAILBREAK` | 403 ; device quand même upsert (trace SOC) ; **pas** de session |
| WEB `jailbreak=true` | session OK |

---



## 6. Impact tests existants

`test_auth_a.py` (`test_second_login_same_device_upserts`, history) : 1er succès aura `suspicious=true`. Adapter les asserts si on lit ce champ.  
`DeviceSpecSerializer` : `jailbreak` défaut `false` → bodies A/B/C/D **inchangés**.  
401/403/503 facteur 1 + MFA **inchangés**.  
`upsert_device` change de signature (`tuple`) : tous les appelants.

Helper MFA (`mfa_helpers.login_until_jwt`) **réutilisé** pour les tests AUTH-E (JWT après verify).

---



## 7. Admin Django + Swagger

`Device` déjà enregistré (jour 2). Vérifier : `push_token` **masqué** ou exclu (comme secret TOTP / bind LDAP). Pas d’édition `compromised` à la main si on a l’API admin — lecture OK.

`/api/docs/` : tag **Devices** (ou Auth) — liste, current, patch, revoke, compromise, admin.

---



## 8. Tests nouveaux (`test_auth_e.py`)

Coller la table AUTH-E §9. Minimum jour 5 :


| Cas | Attendu |
| --- | ------- |
| 1er login MFA OK | 1 `devices` ; platform / model |
| 2e login même uuid | 1 ligne ; `last_seen` MAJ |
| `PATCH current` `push_token` | persisté ; **absent** du GET |
| 1er uuid | history `suspicious=true` ; audit `DEVICE_NEW` |
| 2e login même uuid | `suspicious=false` |
| `trusted=true` | MFA **toujours** `mfa_required` |
| PATCH trusted true / false | GET reflète ; untrust **ne** tue **pas** la session |
| IOS jailbreak + block | 403 `DEVICE_JAILBROKEN` ; flag true ; 0 session |
| WEB jailbreak true | 200 session |
| block=false + ANDROID jailbreak | 200 ; flag true |
| compromise autre device | sessions kill ; login 403 `DEVICE_COMPROMISED` |
| compromise current (owner) | 400 `CANNOT_COMPROMISE_CURRENT` |
| revoke | session inactive ; relogin **OK** |
| GET liste | `is_current` ; pas le device d’autrui |
| PATCH name | GET reflète |
| GET / PATCH id d’un autre user | 404 |
| USER appelle admin compromise | 403 |
| `/health`, `/api/docs/` | 200 |


Régression : `test_auth_a.py` `test_auth_c.py` `test_jour_2.py` encore verts.

---



## 9. Vérif manuelle

```powershell
python manage.py makemigrations iam
python manage.py migrate
python manage.py check
pytest apps/iam/tests/test_auth_e.py apps/iam/tests/test_auth_c.py apps/iam/tests/test_auth_a.py apps/iam/tests/test_jour_2.py --reuse-db
```

```powershell
# après login + MFA (jour 4) avec device_uuid=dev-1
curl -s http://127.0.0.1:8000/api/v1/me/devices -H "Authorization: Bearer <access>"
# 1 ligne is_current=true, pas de push_token
```

Second client `device_uuid=dev-2` → 2 lignes ; history du 2e verify `suspicious=true`.  
`PATCH …/{id}` `{ "trusted": true }` ; relogin `dev-1` → toujours `mfa_required`.

`/admin/` cookie **sans** TOTP (inchangé). API `/me/devices` = JWT **après** verify.

---



## Checklist jour 5

- [ ] Migration `suspicious` + `DEVICE_COMPROMISED` / `DEVICE_JAILBROKEN` (pas `down -v`)
- [ ] `upsert_device` → `(device, created)` ; ne pas écraser trusted / compromised / push vide
- [ ] `complete_login` : 403 compromis / jailbreak ; `DEVICE_NEW` si created
- [ ] `GET /me/devices` sans `push_token` ; `is_current`
- [ ] PATCH current / name / trusted ; revoke ; compromise owner
- [ ] Admin compromise + clear (`IsAdminRole`)
- [ ] `trusted` n’exempte pas le MFA
- [ ] Stub notif (log + audit), pas NOTIF-A
- [ ] `test_auth_e.py` + régression A/C/jour 2 verts
- [ ] `/api/docs/` documente `/me/devices*`
- [ ] `/admin/` cookie et `/health` intacts
- [ ] SIRH non modifié

---



## Interdits

- Coder AUTH-J (QR 2ᵉ appareil) dans le même incrément
- `HasPermission` AUTH-R (palier JWT / ADMIN seulement)
- DELETE ligne `devices`
- Renvoyer `push_token` en GET
- Lire `trusted` pour skip MFA
- E-mail / FCM réel (NOTIF-A)
- GeoIP / nouveau pays (AUTH-I)
- `docker compose down -v`

---



## Après le jour 5

Jour suivant (MVP / A→Z §4.1 **1e2**) : **AUTH-J** — lier un 2ᵉ écran (`POST /auth/device-link/start`, poll, `POST /me/devices/link` + TOTP déjà enrollé). Autre QR que l’enroll AUTH-C.
