# Jour 22 — MEDIA-R + MEDIA-A (upload & stockage MinIO)

**Statut :** clos (2026-09-15).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–21 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 21](00-jour-21-crypto-00.md)). CRYPTO-00 figé : `media_files.encrypted` doit être posable par le client dès ce jour (colonne déjà là depuis AUTH-01), même si le chiffrement réel du blob reste côté client (hors backend).

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §4 — *photos et fichiers*) :

| Fonction MVP                             | Ticket             | Statut          |
| ----------------------------------------- | ------------------ | --------------- |
| Décision chiffrement (revue de clôture)   | CRYPTO-00           | **fait** (jour 21) |
| **Upload générique de fichiers**          | **MEDIA-R + MEDIA-A** | **ce jour**  |
| Album / vocal / coffre (images, vidéo, audio, GED) | MEDIA-B, C, D, E | jour 28 |

**À quoi ça sert (MVP) :** aujourd'hui, seul l'avatar (PROF-A) et — via l'ORM en test seulement — une pièce jointe de certification (ANNUAIRE-D) peuvent exister comme `MediaFile`. Il n'y a **aucune route générique** pour qu'un collaborateur envoie un fichier depuis son téléphone. Ce jour construit ce socle : upload (2 façons), métadonnées, téléchargement signé, suppression — sur lequel MEDIA-B (images), C (vidéo), D (audio), E (GED) viendront se brancher au jour 28. C'est aussi le premier jour où le backend parle réellement à MinIO (`docker-compose` le fournit depuis la phase 0, mais aucun code ne l'utilisait jusqu'ici).

**Plan métier (code à coller) :** [MEDIA-R-roles-permissions.md](media_plans/MEDIA-R-roles-permissions.md) (MED-R01…R04) + [MEDIA-A-upload-stockage.md](media_plans/MEDIA-A-upload-stockage.md) (MED-01…18, seulement la Vague A : routes #1–6 de [MEDIA-routes.md](media_plans/MEDIA-routes.md)).  
Chemins lab = ce fichier (`services/storage.py`, `services/upload_service.py`, `views/uploads.py`, `serializers/uploads.py`).

**Déjà en base / code :**

- `MediaFile`, `MediaMetadata`, `StorageUsage`, `MediaAccessLog` (+ `Image`/`Video`/`AudioMessage`/`Document`/`DocumentVersion` pour B–E) : modèles complets depuis AUTH-01. 0 ligne pour `storage_usage`/`media_access_logs` ; `media_files` a déjà des lignes (avatars PROF-A).
- `apps/media/views/files.py` (`MediaFileView`, `GET /api/v1/media/files/{id}`) et `apps/media/services/avatar_service.py` : servent l'avatar depuis le **disque local** (`MEDIA_ROOT`). **Ne pas toucher** — l'avatar continue sur disque local, seuls les nouveaux uploads génériques de ce jour vont sur MinIO.
- MinIO tourne déjà (`docker-compose.yml`, service `minio`, ports 9000/9001) et les credentials sont **déjà** dans `.env` (`MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`) — posés par avance, jamais lus par `settings.py` jusqu'ici.
- `apps/config/models.py` (`SystemSetting`) + `apps/config/management/commands/seed_config.py` : pattern déjà utilisé pour des réglages runtime (sécurité, LDAP, profil, présence) — **réutilisé** ici pour les plafonds MED-12 (`category="media"`), pas de nouvelle table.
- Permission `media.avatar.manage` (self) : déjà seedée (PROF-A, jour 13) — **distincte** des 12 permissions MED-R02 de ce jour, ne pas la dupliquer.

**Pas encore :** aucune permission `media.file.*`/`media.image.*`/`media.storage.*`/`media.access_log.*` ; `boto3` absent des dépendances ; `settings.py` ne lit aucune variable `MINIO_*` ; aucune route `/api/v1/media/uploads`, `/api/v1/media/upload`, `/api/v1/media/{id}`, `/api/v1/media/{id}/download`.

**Objectif du jour :**

1. **MEDIA-R** : ajouter les 12 permissions `media.*` à `rbac_catalog.py` (9 self + 3 admin — voir correction §0 ci-dessous) ; ajouter les plafonds MED-12 à `seed_config.py` (`category="media"`).
2. `apps/media/services/storage.py` : client `boto3` vers MinIO (presigned PUT/GET, `put_object`, `delete_object`, création idempotente du bucket).
3. `apps/media/services/upload_service.py` : `init_presigned_upload`, `complete_upload`, `direct_upload`, `get_media_or_404`, `download_media`, `delete_media`. Plafonds MED-12, quota (`StorageUsage`), dédup checksum, scan `SKIPPED` en dev.
4. Vues + routes : `POST /media/uploads`, `POST /media/uploads/{upload_id}/complete`, `POST /media/upload`, `GET /media/{id}`, `GET /media/{id}/download`, `DELETE /media/{id}`.
5. Ne rien casser : avatar (`/me/avatar`, `/media/files/{id}`), certifs ANNUAIRE-D (`document_id`), tout le reste.

**Hors jour 22 :** MEDIA-B/C/D/E (images, vidéo, audio, GED — jour 28) ; MEDIA-F quotas/audit **admin** (`/me/storage-usage`, `/admin/users/{id}/storage-usage`, `/admin/media/{id}/access-logs` — **hors calendrier MVP**, cf. footer [MEDIA-routes.md](media_plans/MEDIA-routes.md) : « Hors ce compteur : MEDIA-F ») ; ACL « membre conversation » (Messagerie n'existe pas encore) ; 409 DELETE si référencé par un message (idem) ; vrai ClamAV (profil `scan` du docker-compose reste éteint en lab) ; dédup au niveau du stockage (on rejette le doublon, on ne réutilise pas l'objet existant) ; reprise d'upload / multipart S3.

---

## 0. Corrections apportées au plan métier (avant de coder)

| Écart trouvé | Correction |
|---|---|
| MEDIA-R dit « Seed **14** permissions (12 self + 2 admin) » mais son propre tableau MED-R02 liste 9 self + 3 admin = **12** | On seed les **12** de la table (9 self + 3 admin). `media.avatar.manage` reste séparée (déjà seedée jour 13, pas recomptée ici). |
| MEDIA-R dit « Commande `python manage.py seed_media` » | Pas de nouvelle commande : convention déjà établie depuis AUTH-R (jour 11) = ajouter les codes à `rbac_catalog.py`, `ensure_system_matrix()` les distribue automatiquement à USER (self) / ADMIN (admin). |
| MED-13 « Incrément quota à l'upload » suppose une notion de quota déjà visible | On **incrémente/décrémente** `storage_usage` (interne), mais on n'expose **pas** de route pour le lire/modifier ce jour — ça, c'est MEDIA-F (`/me/storage-usage`, `/admin/users/{id}/storage-usage`), explicitement hors calendrier MVP. `quota_bytes` reste `NULL` (illimité) tant que MEDIA-F n'existe pas. |

---

## Pourquoi ce jour (après CRYPTO-00, avant NOTIF-A / CRYPTO-A / MESSAGERIE)

MEDIA-A est le socle sur lequel s'appuient PROF-A (déjà fait, avatar), ANNUAIRE-D (déjà fait, `document_id` — jusqu'ici seulement testable via l'ORM, faute de route d'upload), puis plus tard NOTIF-A (pièces jointes de notif ? non, hors scope), CRYPTO-A (aucun lien direct) et surtout MESSAGERIE-B (PJ de message, jour 25+). Sans ce jour, aucun client mobile ne peut réellement envoyer un fichier — d'où sa place juste après la décision de chiffrement (jour 21), qui fixe déjà la règle `encrypted` que ce jour doit respecter (client pose `encrypted=true` en 1-to-1, le serveur ne déchiffre jamais).

```text
JWT + HasPermission + portes AUTH-F (self, comme tout /media/*)
    POST   /media/uploads                    media.file.upload   → init presign MinIO
    POST   /media/uploads/{upload_id}/complete media.file.upload → finalise, scan, quota
    POST   /media/upload                     media.file.upload   → multipart direct < 10 Mo
    GET    /media/{id}                       media.file.read     → métadonnées (owner)
    GET    /media/{id}/download              media.file.read     → 302 URL signée MinIO
    DELETE /media/{id}                       media.file.delete   → owner, hard delete + quota-

Déjà là (ne pas casser)
    GET  /media/files/{id}       avatar seul, disque local (PROF-A)
    POST/DELETE /me/avatar       avatar_service (disque local)
    POST/PATCH/DELETE /me/certifications(/{id})  document_id → media_files (ANNUAIRE-D)
```

---

## Paliers (figés pour ce jour)

| Sujet | Choix jour 22 | Plus tard |
| ----- | ------------- | --------- |
| Stockage | MinIO réel via `boto3` (`endpoint_url` MinIO, `signature_version=s3v4`). Bucket auto-créé si absent | S3 prod = même code, autre endpoint |
| Deux flux | **Presigné** (`/uploads` → PUT client → `/uploads/{id}/complete`) **et** **multipart direct** (`/upload`, < 10 Mo, tout ou rien, checksum calculé serveur) | — |
| `upload_id` | = `MediaFile.id` lui-même. Réservation = ligne créée à l'init avec `checksum=NULL` ; `complete` la finalise (`checksum` posé) | Nettoyage des réservations orphelines (job) |
| Checksum | Presigné : fourni par le client (`sha256` hex, 64 car.), pas recalculé serveur (coûterait un download). Multipart direct : calculé serveur (bytes déjà en mémoire) | Vérification serveur du presigné (à distance) |
| Dédup (MED-04) | `checksum` UNIQUE en base → doublon détecté = **409** `DUPLICATE_FILE`. On ne réutilise **pas** l'objet existant (pas de pointeur partagé) | Dédup réelle (réutiliser le storage_path) |
| Plafonds (MED-12) | Lus depuis `system_settings` (`category="media"`), seedés par `seed_config`. Dépassement déclaré (init) **ou** réel (complete/direct) → **413** `FILE_TOO_LARGE` | — |
| Quota | `storage_usage` (`PERSONAL`) incrémenté/décrémenté en interne. `quota_bytes=NULL` = illimité (MEDIA-F pas encore là pour le fixer) → jamais de 413 quota ce jour tant qu'aucun admin n'a de moyen de poser un plafond | 413 `QUOTA_EXCEEDED` deviendra atteignable dès MEDIA-F |
| Scan (MED-05) | Nouveau flag `YAS_MEDIA_SCAN_SKIP` (déf. `true`) — générique, **distinct** de `YAS_MEDIA_AVATAR_SCAN_SKIP` (avatar inchangé). `true` → `SKIPPED` direct, jamais `CLEAN` fantôme | ClamAV réel en staging/prod (profil `scan`) |
| ACL (MED-R04, réduit) | **Owner uniquement** pour GET/download/DELETE ce jour. « Membre conversation » (Messagerie) et « admin audit » (MEDIA-F) **pas encore branchables** | Étendu quand ces modules existeront |
| DELETE référencé | Le **409** « référencé par message non supprimé » ne s'applique pas encore (pas de table `messages`). DELETE = toujours hard delete si owner | Réactivé avec MESSAGERIE-B |
| INFECTED | `scan_status=INFECTED` → **403** `FILE_INFECTED` au download. Ne peut pas arriver en lab (`SKIPPED` seulement) mais le code le gère déjà | Vrai déclenchement en staging |
| Portes AUTH-F | Toutes les routes `/media/*` de ce jour sont sous `/api/v1/media/` (pas `/me/*`) → **allowlistées comme les autres routes non-`/me`** (voir ComplianceGates), donc **pas** de porte CGU/wizard ce jour, comme `/media/files/{id}` déjà en place | — |
| Audit | `module=MEDIA` ; `MEDIA_UPLOAD_INIT` / `MEDIA_UPLOAD_COMPLETE` / `MEDIA_UPLOAD_DIRECT` / `MEDIA_DOWNLOAD` / `MEDIA_DELETE` | — |

---

## 1. Tables

**0 migration.** `media_files`, `media_metadata`, `storage_usage`, `media_access_logs` existent depuis AUTH-01.  
**Interdit :** `docker compose down -v` (supprimerait aussi le volume MinIO `yas_connect_minio`).

---

## 2. Dépendances & configuration

| Fichier | Changement |
|---|---|
| `requirements/base.txt` | `+ boto3>=1.35,<2.0` |
| `config/settings.py` | `MINIO_ENDPOINT = env("MINIO_ENDPOINT")`, `MINIO_ACCESS_KEY = env("MINIO_ACCESS_KEY")`, `MINIO_SECRET_KEY = env("MINIO_SECRET_KEY")`, `MINIO_BUCKET = env("MINIO_BUCKET")`, `YAS_MEDIA_SCAN_SKIP=(bool, True)` dans le schéma `env.Env(...)` |
| `.env` / `.env.example` | Déjà présents (`MINIO_*`), rien à ajouter |

```powershell
.venv\Scripts\python.exe -m pip install boto3
```

---

## 3. Fichiers

| Fichier | Rôle |
| ------- | ---- |
| `apps/media/services/storage.py` | **nouveau.** Client `boto3`/MinIO : `presigned_put_url`, `presigned_get_url`, `put_object_bytes`, `delete_object`, `head_object`, `build_key`, `_ensure_bucket` |
| `apps/media/services/upload_service.py` | **nouveau.** `init_presigned_upload`, `complete_upload`, `direct_upload`, `get_media_or_404`, `download_media`, `delete_media`, quota, audit |
| `apps/media/serializers/uploads.py` | **nouveau.** `UploadInitSerializer`, `UploadCompleteSerializer` |
| `apps/media/views/uploads.py` | **nouveau.** `MediaUploadInitView`, `MediaUploadCompleteView`, `MediaDirectUploadView`, `MediaDetailView` (GET+DELETE), `MediaDownloadView` |
| `apps/media/urls.py` | **delta.** + 5 routes, avant `files/<uuid:pk>` ou après peu importe (préfixes distincts) |
| `apps/iam/services/rbac_catalog.py` | **delta.** + 12 permissions `media.*` |
| `apps/config/management/commands/seed_config.py` | **delta.** + `MEDIA_SETTINGS` (6 plafonds MED-12, `category="media"`) |
| `apps/iam/tests/test_media_a.py` | **nouveau.** |

---

## 4. Contrat HTTP

Préfixe `/api/v1/media`. JWT. Pas de porte CGU/wizard (comme `/media/files/{id}` déjà en place).

### `POST /media/uploads` (MED-01, init presign)

`media.file.upload`. Body `{ "filename", "mime_type", "size_bytes", "media_type" }` (`media_type` ∈ `IMAGE|VIDEO|AUDIO|DOCUMENT|OTHER`).  
**201** `{ "upload_id", "presigned_url", "expires_in": 900 }`.  
**400** `VALIDATION_ERROR` (`media_type` invalide). **413** `FILE_TOO_LARGE` si `size_bytes` > plafond seedé du type.

### `POST /media/uploads/{upload_id}/complete`

`media.file.upload`. Body `{ "checksum": "<sha256 hex>" }`.  
Vérifie que l'objet existe réellement dans MinIO (`head_object`) sinon **400** `UPLOAD_INCOMPLETE`. Recalcule la taille réelle (`ContentLength`) : si > plafond → **413** `FILE_TOO_LARGE` (objet supprimé de MinIO + ligne nettoyée). `checksum` déjà pris par un autre fichier → **409** `DUPLICATE_FILE`. Déjà complété (`checksum` déjà posé) → **409** `ALREADY_COMPLETED`.  
**200** métadonnées finales (`scan_status=SKIPPED` en lab).

### `POST /media/upload` (MED-01, multipart direct)

`media.file.upload`. Multipart : `file` (binaire) + `media_type` (optionnel, sinon déduit du `content_type`). < 10 Mo **et** < plafond du type, sinon **413** `FILE_TOO_LARGE`. Checksum calculé serveur ; doublon → **409** `DUPLICATE_FILE`.  
**201** métadonnées (`checksum` déjà posé, `scan_status=SKIPPED`).

### `GET /media/{id}` (MED-09)

`media.file.read`. Owner seul, sinon **404**. Pas d'URL de téléchargement dans la réponse (MED-10 séparé).

### `GET /media/{id}/download` (MED-10)

`media.file.read`. Owner seul → **404** sinon. `scan_status=INFECTED` → **403** `FILE_INFECTED`. Sinon **302** vers une URL MinIO signée (`expires_in=900`) + `MediaAccessLog(action=DOWNLOAD)`.

### `DELETE /media/{id}` (MED-11)

`media.file.delete`. Owner seul → **404** sinon. Supprime l'objet MinIO + la ligne (cascade `media_access_logs`) + décrémente `storage_usage`. **204**.

**401** sans JWT. **403** `FORBIDDEN` sans la permission.

---

## 5. Impact tests existants

| Fichier | Adapter |
| ------- | ------- |
| `test_prof_a.py` | Avatar inchangé (disque local, `MediaFileView` intact) |
| `test_annuaire_d.py` | `document_id` continue de fonctionner (les tests créent le `MediaFile` par l'ORM ; aucune dépendance à MinIO n'est introduite pour ces tests) |
| `test_auth_f.py` | Les nouvelles routes `/media/*` ne sont pas sous `/me/*` → pas de porte CGU/wizard, pas de régression sur l'allowlist |

---

## 6. Tests nouveaux (`test_media_a.py`)

Prérequis : MinIO doit tourner (`docker compose up -d minio` — déjà up dans cet environnement). Le test « simule » le client en faisant un vrai `PUT` HTTP sur l'URL présignée (`urllib.request`, pas de nouvelle dépendance) avant d'appeler `/complete`.

| ID | Cas | Attendu |
| -- | --- | ------- |
| 01 | POST `/media/uploads` `media_type=DOCUMENT` taille OK | 201 `upload_id` + `presigned_url` |
| 01 | `size_bytes` > plafond document | 413 `FILE_TOO_LARGE` |
| 01 | `media_type` invalide | 400 `VALIDATION_ERROR` |
| — | PUT réel sur l'URL présignée puis `POST .../complete` | 200 ; `scan_status=SKIPPED` ; `checksum` posé |
| — | `complete` sans PUT préalable | 400 `UPLOAD_INCOMPLETE` |
| — | `complete` deux fois de suite | 409 `ALREADY_COMPLETED` |
| — | `complete` avec un checksum déjà utilisé par un autre fichier | 409 `DUPLICATE_FILE` |
| 01 | `POST /media/upload` multipart < 10 Mo | 201 ; fichier réellement dans MinIO (`head_object` OK) |
| 01 | `POST /media/upload` > 10 Mo | 413 `FILE_TOO_LARGE` |
| 01 | `POST /media/upload` doublon (même bytes) | 409 `DUPLICATE_FILE` |
| 09 | `GET /media/{id}` par l'owner | 200 |
| 09 | `GET /media/{id}` par un autre user | 404 |
| 10 | `GET /media/{id}/download` par l'owner | 302 + `Location` MinIO ; `MediaAccessLog` créé |
| 10 | `download` fichier `INFECTED` (créé directement en base pour le test) | 403 `FILE_INFECTED` |
| 11 | `DELETE /media/{id}` par l'owner | 204 ; objet absent de MinIO (`head_object` lève) ; `storage_usage.used_bytes` décrémenté |
| 11 | `DELETE` par un autre user | 404 |
| — | sans JWT | 401 |
| — | sans la permission `media.file.upload` | 403 `FORBIDDEN` |
| — | `/api/schema/` | contient `/api/v1/media/uploads` et `/api/v1/media/{id}/download` |

---

## 7. Vérif manuelle

```powershell
python manage.py check
python manage.py seed_config
pytest apps/iam/tests/test_media_a.py apps/iam/tests/test_prof_a.py apps/iam/tests/test_annuaire_d.py --reuse-db
```

Login jean → `POST /api/v1/media/upload` (multipart, petit fichier) → `GET /api/v1/media/{id}` → métadonnées visibles → `GET /api/v1/media/{id}/download` → 302 vers MinIO → ouvrir l'URL dans un navigateur pendant les 15 min de validité → fichier téléchargé.

---

## Checklist jour 22

- [x] 12 permissions `media.*` seedées (9 self + 3 admin), `media.avatar.manage` non dupliquée
- [x] Plafonds MED-12 seedés (`seed_config`, `category="media"`)
- [x] `boto3` installé, MinIO configuré depuis `.env` (`MINIO_*`)
- [x] Presign : init → PUT client → complete, avec `UPLOAD_INCOMPLETE` / `ALREADY_COMPLETED` / `DUPLICATE_FILE`
- [x] Multipart direct < 10 Mo, checksum serveur, `DUPLICATE_FILE`
- [x] `FILE_TOO_LARGE` sur les 3 chemins (init, complete, direct)
- [x] GET métadonnées + download signé (302) + `MediaAccessLog`
- [x] DELETE hard + décrément quota
- [x] ACL owner-only ; `FILE_INFECTED` géré
- [x] Audit `MEDIA_UPLOAD_*` / `MEDIA_DELETE` (`MEDIA_DOWNLOAD` couvert par `MediaAccessLog`, pas de doublon AuditLog — voir note ci-dessous)
- [x] `test_media_a.py` (19 tests, contre MinIO réel) + régression PROF-A / ANNUAIRE-D / AUTH-F
- [x] 0 migration ; 0 `docker compose down -v`
- [x] SIRH non modifié

**Note de clôture :** `MEDIA_DOWNLOAD` n'a pas de ligne `AuditLog` dédiée — `MediaAccessLog(action=DOWNLOAD)` joue déjà ce rôle (c'est sa raison d'être, MED-14) ; dupliquer aurait été redondant. En revanche `MEDIA_DELETE` reste en `AuditLog` (pas `MediaAccessLog`, qui serait cascadé/supprimé avec la ligne `media_files`).

---

## Interdits

- MEDIA-B/C/D/E (images, vidéo, audio, GED) — jour 28
- MEDIA-F (quotas/audit admin, `/me/storage-usage`, `/admin/users/{id}/storage-usage`, `/admin/media/{id}/access-logs`) — hors calendrier MVP
- Toucher `avatar_service.py` / `MediaFileView` (avatar reste sur disque local)
- ACL « membre conversation » (Messagerie n'existe pas)
- 409 DELETE « référencé par message » (idem)
- Vrai ClamAV (profil `scan` du docker-compose reste éteint)
- Dédup au niveau du stockage (juste un rejet 409, pas de réutilisation d'objet)
- `docker compose down -v`
- Changer le SIRH

---

## Après le jour 22

Jour 23 : [00-jour-23-notif-r-a.md](00-jour-23-notif-r-a.md) — **NOTIF-R + NOTIF-A** (centre de notifications + push, remplace le stub `DEVICE_NEW`).

---

## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour**. Le jour 2 (admin + Swagger) est un extra déjà clos.

| Jours  | Plan                                           | Ticket MVP                            |
| ------ | ----------------------------------------------- | -------------------------------------- |
| 0      | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health`    |
| 1–2    | AUTH-A ; admin + Swagger                        | Connexion locale ; lab admin           |
| 3–11   | D+B … AUTH-R                                    | §1 entrer + droits HTTP                |
| 12     | ADMIN-A                                         | §9 comptes                             |
| 13     | PROF-A                                          | §2 ma fiche / photo                    |
| 14     | PROF-B                                          | Préférences                            |
| 15     | PROF-C                                          | §2 visibilité                          |
| 16     | PRES-A                                          | §2 statut en ligne                     |
| 17     | ANNUAIRE-A                                      | §3 recherche collègue                  |
| 18     | ANNUAIRE-B                                      | §3 organigramme (types + arbre)        |
| 19     | ANNUAIRE-C                                      | §3 mutations / affectations            |
| 20     | ANNUAIRE-D                                      | §3 compétences / certifications        |
| 21     | CRYPTO-00                                       | §6 décision E2E                        |
| **22** | **MEDIA-R + MEDIA-A** (ce plan)                 | §4 upload (plafonds ; pas de reprise)  |
| 23     | NOTIF-R + NOTIF-A                               | §5 alertes + MOB-PUSH (VoIP / worker)  |
| 24     | CRYPTO-R + CRYPTO-A                             | Clés HTTP                              |
| 25     | MESSAGERIE-R, A, B                              | §7 1-to-1                              |
| 26     | MESSAGERIE-C, D                                 | §7 groupes + temps réel                |
| 27     | MESSAGERIE-E (partiel), F, G                    | §7 enrichissements                     |
| 28     | MEDIA-B, C, D, E                                | §4 album / vocal / coffre              |
| 29     | APPELS-R, A, B, C                               | §8 appel 1-1 + `CALL_CANCELLED`        |
| 30     | APPELS-D, E, G                                  | §8 écran / CR                          |

**Total : 31 plans (jours 0 à 30).**  
Déjà clos : **22** (0–21). Restant : **9** (22–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.
