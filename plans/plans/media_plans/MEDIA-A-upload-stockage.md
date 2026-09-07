# MEDIA-A — Upload & stockage (MED-01 … 18)

**Produit :** YAS Connect uniquement.  
**Préalable :** **MEDIA-R** + MinIO/S3 configuré (phase 0 Docker).  
**Models :** [code/media_models.py](../code/media_models.py).

**Périmètre :** ingest fichier, métadonnées communes, checksum, scan antivirus, chiffrement, suppression.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MED-01** | **Gardé** | Upload multipart ou presigné | `media_files` |
| **MED-02** | **Gardé** | Conserver `original_name` | colonne |
| **MED-03** | **Gardé** | Détecter `mime_type`, `media_type` | enum IMAGE/VIDEO/AUDIO/DOCUMENT/OTHER |
| **MED-04** | **Gardé** | Calcul `checksum` SHA-256 ; UK dédup | `checksum` UNIQUE |
| **MED-05** | **Gardé** | File scan async `PENDING→CLEAN/INFECTED` | `scan_status`, `virus_scanned` |
| **MED-06** | **Gardé** | Chiffrement au repos optionnel | `encrypted` |
| **MED-07** | **Gardé** | Compression flag | `compressed` |
| **MED-08** | **Gardé** | Métadonnées EXIF communes | `media_metadata` auto |
| **MED-09** | **Gardé** | GET métadonnées fichier | lecture owner ou ACL |
| **MED-10** | **Gardé** | URL téléchargement signée TTL 15 min | pas de path public |
| **MED-11** | **Gardé** | DELETE soft ou hard (orphan S3) | job cleanup |
| **MED-12** | **Gardé** | Taille max par type (config) | validation |
| **MED-13** | **Gardé** | Incrément quota à l’upload | `storage_usage` |
| **MED-14** | **Gardé** | Journal accès DOWNLOAD | `media_access_logs` |
| **MED-15** | **Gardé** | Avatar profil (PROF-A) | `users.avatar_id` |
| **MED-16** | **Gardé** | PJ messagerie | `messages.media_id` |
| **MED-17** | **Gardé** | Certif annuaire | `user_certifications.document_id` |
| **MED-18** | **Gardé** | Portes AUTH-F sur upload | — |

**Hors incrément :** CDN public, watermark global.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Flow presign | `POST /media/uploads` → `{ upload_id, presigned_url }` → client PUT → `POST /media/uploads/{id}/complete` |
| Flow multipart | `POST /media/upload` direct < 10 Mo |
| Bucket | `bucket_name` depuis settings ; path `/{type}/{yyyy}/{uuid}` |
| Scan (MED-05) | **Lab / dev :** pas de worker → `SKIPPED` (jamais `CLEAN` fantôme). **Staging / prod :** ClamAV `PENDING` → `CLEAN` \| `INFECTED`. Figé A→Z §4.3. |
| INFECTED | Pas de download ; message chat refusé (MSG-38) |
| 1-to-1 E2E | Ciphertext MinIO (`encrypted=true`) ; scan du blob opaque — [CRYPTO-00](../crypto_plans/CRYPTO-00-modele-chiffrement.md) |

---

## Contrat HTTP

### MED-01 — `POST /api/v1/media/uploads`

`media.file.upload`. Body : `{ "filename", "mime_type", "size_bytes", "media_type" }`.

**201** `{ "upload_id", "presigned_url", "expires_in" }`.

### `POST /api/v1/media/uploads/{upload_id}/complete`

`{ "checksum": "sha256..." }` → crée `media_files` + lance scan.

### MED-09 — `GET /api/v1/media/{id}`

Métadonnées sans URL longue durée.

### MED-10 — `GET /api/v1/media/{id}/download`

Redirect 302 URL signée ; log `DOWNLOAD`.

### MED-11 — `DELETE /api/v1/media/{id}`

Owner seul ; 409 si référencé par message non supprimé.
