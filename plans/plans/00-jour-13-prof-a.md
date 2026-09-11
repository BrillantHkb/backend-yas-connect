# Jour 13 — PROF-A (identité, fiche collègue, avatar)

**Statut :** à faire.  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–12 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 12](00-jour-12-admin-a.md)).  
`GET /me` + `gates` AUTH-F **déjà** là. `HasPermission` + perms `iam.profile.read` / `update` / `read_other` / `media.avatar.manage` **déjà** seedées (jour 11). Change email = AUTH-I. `privacy_settings` 1-1 **déjà** à `create_user`. Table `media_files` **déjà** là (0 ligne). Segments Annuaire **déjà** en base (seed types + YAS).

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §2 — *Ma fiche / photo*) :


| Fonction MVP                                   | Ticket      | Statut                          |
| ---------------------------------------------- | ----------- | ------------------------------- |
| Connexion + droits HTTP + comptes admin        | A–R, ADMIN-A | **fait** (jours 1–12)          |
| **Ma fiche, photo, fiche collègue**            | **PROF-A**  | **ce jour**                     |
| Préférences / visibilité                       | PROF-B / C  | [jour 14](00-jour-14-prof-b.md) |


**À quoi ça sert (MVP) :** jean voit son nom, son org, sa photo ; il corrige prénom / username / téléphone sans ticket RH. Marie ouvre sa fiche : photo masquée si privacy `NOBODY`. Pas de 2e table « profil ».

**Plan métier (code à coller) :** [PROF-A-identite.md](iam_plans/PROF-A-identite.md) (PROF-01 … 14).  
Chemins lab = ce fichier (`views/me.py`, `views/users.py`, `apps/media/views/avatar.py` — **pas** `views_profile.py` à la racine IAM).

**Déjà en base / code :**

- `GET /api/v1/me` : `public_user` (email, username, names, rôle `{id,code,name}`, prefs, privacy) + `gates`
- `User.get_full_name()` ; `avatar_id` UUID sans FK ; `segment_id` UUID sans FK ; `region` FK IAM
- `PrivacySetting` : `EVERYONE` / `CONTACTS` / `NOBODY` (photo, last_seen, online)
- `Segment` + `parent_segment` + `responsable` ; `GET /directory/segments` public
- `MediaFile` (`IMAGE`, `scan_status` PENDING/CLEAN/INFECTED/SKIPPED) — **aucun INSERT**
- Perms seed ; portes AUTH-F sur `/me` hors GET racine / tos / heartbeat / sessions
- Login 200 utilise encore `public_user` (ne **pas** l’enrichir ici)

**Pas encore :** `display_name` / `avatar_url` / `org` / `email_pending` sur `/me` ; `PATCH /me` ; `GET /users/{id}` ; upload avatar.

**Objectif du jour :**

1. Enrichir **la même** vue `GET /me` (PROF-01) : identité + `org` résolue + `region` objet + `avatar_url` + `email_pending` + `last_seen`. **Garder** `gates` + `preferences` + `privacy`. **Pas** de `role` (déjà le claim JWT ; change = R09).
2. `PATCH /me` : prénom, nom, username, phone. Refus `matricule` / `job_title` / `email` / rôle / segment / avatar / prefs.
3. `GET /users/{id}` : même carte **sans** `gates` / `email_pending` / prefs ; privacy du **cible** ; 404 inactif/pending ; self → 400.
4. Avatar : `POST/DELETE /me/avatar` ; scan **SKIPPED** lab ; 1er INSERT `media_files`.
5. `org_resolver` : segment courant + parents (max 16) ; manager = `responsable_id`.

**Hors jour 13 :** PROF-B (`editable`, `GET/PATCH /me/preferences`, flag `job_title_self_edit`), PROF-C (écriture privacy), PRES-A (Redis présence / `last_seen` max sessions), ANNUAIRE-A people-picker / recherche, ANNUAIRE-B/C write, MinIO prod (MEDIA-A), antivirus réel, PATCH matricule / job (défaut), recoder ADMIN-A.

---



## Pourquoi ce jour (après ADMIN-A)

`/me` est un stub AUTH-F : assez pour les portes, pas pour l’écran profil. Le MVP §2 demande la carte + la photo **derrière JWT + perm**, et la fiche collègue filtrée. Les codes sont seedés depuis le jour 11.

```text
JWT + HasPermission + portes AUTH-F (sauf GET /me déjà allowlist)
    GET    /me                         iam.profile.read
    PATCH  /me                         iam.profile.update
    POST   /me/avatar                  media.avatar.manage
    DELETE /me/avatar                  media.avatar.manage
    GET    /users/{id}                 iam.profile.read_other
    GET    /media/files/{id}           (JWT ; fichier CLEAN/SKIPPED)

Déjà là (ne pas casser)
    GET /me + gates
    POST /me/email  (AUTH-I)
    PATCH rôle admin (R09)
```

---



## Paliers (figés pour ce jour)


| Sujet            | Choix jour 13                                                                                         | Plus tard        |
| ---------------- | ----------------------------------------------------------------------------------------------------- | ---------------- |
| `GET /me`        | **Même** `MeView` ; payload enrichi ; **sans** `role` ; `public_user` **login inchangé** (lui a encore `role`) | PROF-B `editable` |
| `display_name`   | calculé `get_full_name()` — **pas** de colonne                                                        | —                |
| `org`            | 0 segment / inactif → `null`. Pas de `manager_id` IAM                                                 | ANNUAIRE-B/C     |
| CONTACTS         | même `segment_id` non NULL = collègues. Sinon = `NOBODY` pour photo / last_seen / online              | graphe amis      |
| `last_seen`      | `users.last_login`                                                                                    | PRES-A           |
| `status`         | `users.status` (ONLINE/OFFLINE). Collègue masqué → `null` (pas inventer OFFLINE)                      | PRES-A Redis     |
| Prefs / privacy  | **lus** dans GET `/me` (déjà là). PATCH `/me` **n’écrit pas** ces clés                                | PROF-B / C       |
| `job_title`      | lecture OK ; PATCH → **400** `FIELD_FORBIDDEN` (flag défaut false, PROF-B)                            | PROF-B           |
| Email            | lecture + `email_pending` ; PATCH `/me` → **400** (AUTH-I)                                            | —                |
| Avatar scan      | `YAS_MEDIA_AVATAR_SCAN_SKIP=true` → `scan_status=SKIPPED`. Pas ClamAV                                 | MEDIA-A          |
| Stockage         | filesystem `MEDIA_ROOT` (pas MinIO ce jour)                                                           | MEDIA-A          |
| DELETE avatar    | `avatar_id=NULL` ; **ne** supprime **pas** `media_files`                                              | rétention        |
| Portes AUTH-F    | PATCH `/me`, avatar, `GET /users/{id}` **après** CGU + wizard. GET `/me` allowlist **inchangée**       | —                |


Codes lab (3 segments) : `iam.profile.read_other`, `media.avatar.manage` — déjà seed.

---



## 1. Tables

**0 migration IAM.** `media_files` existe (jour 0). Premier **INSERT** hors seed.  
**Interdit :** `docker compose down -v`.

`audit_logs.action` : `PROFILE_PATCH` / `AVATAR_SET` / `AVATAR_CLEAR`.

---



## 2. Settings + seed

`.env` / `.env.example` (préfixe lab `YAS_`) :

```env
YAS_AVATAR_MAX_BYTES=2097152
YAS_MEDIA_AVATAR_SCAN_SKIP=true
```

`MEDIA_ROOT` Django (ex. `var/media/`). Pas de nouveau seed org (ANNUAIRE-A). Tests : créer 2–3 `Segment` + parents en fixture.

---



## 3. Services


| Fichier                                      | Sert à                                                                 |
| -------------------------------------------- | ---------------------------------------------------------------------- |
| `apps/iam/services/profile_service.py`       | **nouveau.** serialize fiche, PATCH, privacy collègue, `email_pending` |
| `apps/iam/services/org_resolver.py`          | **nouveau.** `resolve_org(user)` → dict ou `null`                      |
| `apps/media/services/avatar_service.py`      | **nouveau.** upload / clear / `avatar_url`                             |
| `apps/iam/services/auth_service.py`          | `public_user` **inchangé** (login)                                     |
| `apps/iam/views/me.py`                       | GET enrichi + PATCH                                                    |


`email_pending` : dernier `EmailVerification` `purpose=EMAIL_CHANGE`, `verified_at` NULL, `revoked_at` NULL, non expiré → `email` du ticket, sinon `null`.

Org (max 16, cycle-safe) :

```text
s = Segment actif id=user.segment_id
path = s puis parent_segment…
department = premier nœud type.code in (DEPARTEMENT, DEPT, SERVICE)
direction  = premier nœud type.code == DIRECTION
manager    = s.responsable ou premier ancestor.responsable
             { id, display_name, username }
```

Avatar posé seulement si `scan_status` ∈ {`CLEAN`, `SKIPPED`}. Infecté → **400** `MEDIA_INFECTED`, `avatar_id` inchangé.

---



## 4. HTTP

Arborescence `views/` / `urls/me.py`. `path("avatar")` **avant** tout catch-all.  
`config/urls.py` : `path("api/v1/users/", include("apps.iam.urls.users"))` ; `path("api/v1/media/", include("apps.media.urls"))`.


| Fichier                               | Rôle                                              |
| ------------------------------------- | ------------------------------------------------- |
| `apps/iam/views/me.py`                | GET + PATCH `/me`                                 |
| `apps/iam/views/users.py`             | **nouveau.** GET `/users/{id}`                    |
| `apps/iam/serializers/profile.py`     | PATCH body                                        |
| `apps/iam/urls/me.py`                 | `avatar`                                          |
| `apps/iam/urls/users.py`              | **nouveau.**                                      |
| `apps/media/views/avatar.py`          | POST/DELETE `/me/avatar` **ou** sous `urls/me.py` |
| `apps/media/views/files.py`           | GET fichier                                       |
| `apps/media/urls.py`                  | `files/<uuid>`                                    |


Avatar HTTP : coller les vues dans `apps/media/views/` et les **monter** depuis `urls/me.py` (préfixe `/me/avatar`) pour rester owner-only. GET fichier = `/api/v1/media/files/{id}`.


| Méthode | Chemin                         | Perm                    |
| ------- | ------------------------------ | ----------------------- |
| GET     | `/api/v1/me`                   | `iam.profile.read`      |
| PATCH   | `/api/v1/me`                   | `iam.profile.update`    |
| POST    | `/api/v1/me/avatar`            | `media.avatar.manage`   |
| DELETE  | `/api/v1/me/avatar`            | `media.avatar.manage`   |
| GET     | `/api/v1/users/{id}`           | `iam.profile.read_other`|
| GET     | `/api/v1/media/files/{id}`     | JWT (`iam.profile.read`) |


`MeView.required_permissions = {"GET": "iam.profile.read", "PATCH": "iam.profile.update"}`.

**GET `/me` 200** `{ gates, user }` — sérialiseur **fiche** (ne plus renvoyer `public_user` tel quel) :

identité actuelle (`id`, names, `username`, `email`, `phone`, `matricule`, `job_title`, `status`, `language`, `timezone`, `segment_id`, `avatar_id`, `preferences`, `privacy`) **plus** `display_name`, `email_pending`, `avatar_url`, `region` `{id,code,name}|null`, `org` ou `null`, `last_seen` (`last_login`).

**Pas** de `role` / `role_id` / `role_code` sur `/me`.  
**Jamais** : hash, `ldap_dn`, `is_locked`, tokens.  
`avatar_url` null si pas d’avatar CLEAN/SKIPPED.

**PATCH `/me`** body : `first_name`, `last_name`, `username`, `phone` (tous optionnels, au moins un).  
`username` : 3–64, `^[a-z0-9._]+$`, unique, ≠ email d’un **autre**.  
`phone` : E.164 (`^\+[1-9]\d{6,14}$`) ou `null`.  
`matricule` / `job_title` / `email` / `role_id` / `role_code` / `segment_id` / `avatar_id` / clés prefs → **400** `FIELD_FORBIDDEN`.  
Username pris → **409** `USERNAME_TAKEN`. **200** = fiche `/me` (sans forcément re-sérialiser `gates` changés). Audit `PROFILE_PATCH`.

**GET `/users/{id}`** : 404 `NOT_FOUND` si absent / `is_active=false` / `pending_approval`.  
`{id}` = soi → **400** `USE_ME` (« Utiliser GET /me. »).  
Sans `gates`, `email_pending`, `preferences`. Email / téléphone **visibles** (annuaire interne).  
Privacy **cible** :

| Visibilité | Avatar | `last_seen` | `status` |
| ---------- | ------ | ----------- | -------- |
| `EVERYONE` | oui    | oui         | oui      |
| `CONTACTS` | si même `segment_id` non NULL | idem | idem |
| `NOBODY`   | `avatar_url=null` | `last_seen=null` | `status=null` |

Toujours visibles : `display_name`, `username`, `job_title`, `role` `{code, name}`, `org`, `matricule`.  
(`role` **ici seulement** — pas sur `GET /me`.)

**POST `/me/avatar`** : `multipart` champ `file`. MIME `image/jpeg` \| `image/png` \| `image/webp`. Max `YAS_AVATAR_MAX_BYTES`.  
**400** `INVALID_MEDIA` / `AVATAR_TOO_LARGE` / `MEDIA_INFECTED`. **200** `{ avatar_url, avatar_id }`. Remplacer = nouvel INSERT + pose `avatar_id` (ancien fichier **conservé**).

**DELETE `/me/avatar`** : `avatar_id=NULL`. **200** `{ "ok": true }`.

**GET `/media/files/{id}`** : JWT ; 404 si inconnu ou scan ∉ {CLEAN, SKIPPED}. Pas de check privacy sur l’URL directe (lab). `FileResponse`.

---



## 5. Impact tests existants


| Fichier          | Adapter                                                                 |
| ---------------- | ----------------------------------------------------------------------- |
| `test_auth_f.py` | `GET /me` **200** ; `gates` + `user.email` encore là ; **plus** de `user.role` |
| `test_auth_r.py` | jean `GET /me` 200 ; retirer `iam.profile.read` → encore 403            |
| `test_auth_a.py` | JSON login (`public_user`) **inchangé**                                 |


PATCH `/me` et avatar : portes fermées (`close_gates`) comme `/me/password`.

---



## 6. Tests nouveaux (`test_prof_a.py`)


| ID    | Cas                          | Attendu                                                      |
| ----- | ---------------------------- | ------------------------------------------------------------ |
| 01    | GET `/me` jean               | `display_name`, `org` null sans segment ; **pas** de `role` |
| 02    | collègue photo `NOBODY`      | `avatar_url` null ; nom visible                              |
| 02    | `CONTACTS`, autre segment    | photo masquée                                                |
| 02    | `CONTACTS`, même segment     | photo visible si avatar posé                                 |
| 02    | user pending / inactif       | **404** `NOT_FOUND`                                          |
| 02    | GET `/users/{son id}`        | **400** `USE_ME`                                             |
| 03    | JPEG ~100 Ko                 | `avatar_id` posé ; 1 `media_files` `SKIPPED`                 |
| 03    | 3 Mo                         | **400** `AVATAR_TOO_LARGE`                                   |
| 03    | `text/plain`                 | **400** `INVALID_MEDIA`                                      |
| 04    | DELETE                       | `avatar_id` null ; GET `/me` `avatar_url` null ; fichier encore en base |
| 05    | PATCH nom                    | `display_name` à jour                                        |
| 06    | PATCH `matricule`            | **400** `FIELD_FORBIDDEN`                                    |
| 07    | username pris                | **409** `USERNAME_TAKEN`                                     |
| 08    | PATCH `job_title`            | **400** `FIELD_FORBIDDEN`                                    |
| 09    | PATCH `email`                | **400** `FIELD_FORBIDDEN`                                    |
| 10    | PATCH phone E.164 / null     | **200**                                                      |
| 11    | GET `/users/{id}` collègue   | `role.code=USER` + libellé ; GET `/me` **sans** `role`     |
| 12–14 | segment + parents            | `org.path`, `manager.username` = responsable                 |
| —     | LDAP PATCH phone             | **200**                                                      |
| —     | jean GET `/users/{marie}`    | **403** si on retire `iam.profile.read_other`                |
| —     | sans JWT                     | **401**                                                      |
| —     | `/health`, `/api/docs/`      | schéma contient `/users/{id}` et `/me/avatar`                |


Helper MFA : `login_until_jwt`. Portes : `close_gates` sauf GET `/me` (allowlist).  
JPEG : petit fichier généré en test (`Pillow` si déjà là, sinon bytes JPEG minimaux).

Régression : F (`gates` / email) + R (`iam.profile.read`).

---



## 7. Vérif manuelle

```powershell
python manage.py check
pytest apps/iam/tests/test_prof_a.py apps/iam/tests/test_auth_f.py apps/iam/tests/test_auth_r.py --reuse-db
```

`jean.dupont@yas.tg` : GET `/me` → `display_name`, `org` null. PATCH nom. Upload JPEG.  
Marie : GET `/users/{jean}` (après TOS) ; privacy photo `NOBODY` → pas d’URL.  
Pending D03 : GET `/users/{id}` 404.  
`/admin/` cookie : **pas** ces routes.

---



## Checklist jour 13

- [ ] GET `/me` enrichi **sans** `role` ; login `public_user` inchangé
- [ ] PATCH `/me` (nom / username / phone) + `FIELD_FORBIDDEN` / `USERNAME_TAKEN`
- [ ] GET `/users/{id}` + privacy + 404 pending/inactif + `USE_ME`
- [ ] `org_resolver` (path, manager, region IAM distincte)
- [ ] POST/DELETE avatar SKIPPED lab + GET fichier
- [ ] `test_prof_a.py` + régression F/R
- [ ] SIRH non modifié
- [ ] 0 `docker compose down -v`

---



## Interdits

- Recoder ADMIN-A / AUTH-R / AUTH-I email
- Coder PROF-B / PROF-C / PRES-A / ANNUAIRE write / people-picker `GET /users` liste
- Colonne `display_name` / `manager_id` IAM
- MinIO obligatoire / ClamAV (`--profile scan`)
- `docker compose down -v`
- Changer le SIRH

---



## Après le jour 13

Jour 14 : [00-jour-14-prof-b.md](00-jour-14-prof-b.md) — **PROF-B** (`GET/PATCH /me/preferences`, whitelist `job_title`, `editable` sur `/me`).

---



## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour**. Le jour 2 (admin + Swagger) est un extra déjà clos.


| Jours  | Plan                                           | Ticket MVP                          |
| ------ | ---------------------------------------------- | ----------------------------------- |
| 0      | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health` |
| 1–2    | AUTH-A ; admin + Swagger                       | Connexion locale ; lab admin        |
| 3–11   | D+B … AUTH-R                                   | §1 entrer + droits HTTP             |
| 12     | ADMIN-A                                        | §9 comptes                          |
| **13** | **PROF-A** (ce plan)                           | §2 ma fiche / photo                 |
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
