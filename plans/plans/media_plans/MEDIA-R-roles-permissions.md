# MEDIA-R — Rôles & permissions (MED-R01 … R04)

**Produit :** YAS Connect uniquement.  
**Préalable :** **AUTH-R** + tables Médias AUTH-01 (10 tables, 0 ligne).  
**Attributs :** [MEDIA-catalogue-tables.md](../../catalogues/MEDIA-catalogue-tables.md).  
**Models :** [code/media_models.py](../code/media_models.py).

**Périmètre :** seed `media.*`, enforcement propriétaire / scan / confidentialité.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MED-R01** | **Gardé** | Convention `media.{resource}.{action}` | — |
| **MED-R02** | **Gardé** | Seed **14** permissions (12 self + 2 admin) | `permissions` |
| **MED-R03** | **Gardé** | USER = self ; ADMIN = self + audit/quota admin | `role_permissions` |
| **MED-R04** | **Gardé** | Lecture fichier : owner **ou** membre conversation liée **ou** admin audit | règles métier |

**Hors incrément :** rôle archiviste GED dédié.

---

## MED-R02 — Catalogue seed

| Code | audience | Rôles | Sert à |
|------|----------|-------|--------|
| `media.file.read` | self | USER, ADMIN | Métadonnées, preview, stream |
| `media.file.upload` | self | USER, ADMIN | Upload / init presign |
| `media.file.delete` | self | USER, ADMIN | Supprimer ses fichiers |
| `media.image.manage` | self | USER, ADMIN | Annotation, floutage flags |
| `media.video.manage` | self | USER, ADMIN | Lancer transcodage |
| `media.audio.manage` | self | USER, ADMIN | Transcription STT |
| `media.document.read` | self | USER, ADMIN | GED lecture |
| `media.document.manage` | self | USER, ADMIN | GED CRUD / versions |
| `media.storage.read` | self | USER, ADMIN | Quota perso |
| `media.access_log.read` | admin | ADMIN | Journal accès d’un fichier |
| `media.storage.manage` | admin | ADMIN | Quota admin user |
| `media.file.scan_override` | admin | ADMIN | Forcer SKIP (SOC) |

Commande : `python manage.py seed_media` (idempotent).

---

## Règles d’accès (MED-R04)

| Cas | Règle |
|-----|--------|
| Owner | `media_files.owner_id = me` → lecture / delete |
| Message PJ | User membre actif du fil lié à `messages.media_id` |
| Avatar collègue | `GET /users/{id}` privacy photo (PROF-A) |
| Document confidentiel | `documents.confidential=true` → owner doc + admin |
| Scan | `scan_status=INFECTED` → **403** `FILE_INFECTED` sauf admin |
| Quota | `storage_usage.used_bytes + size` ≤ `quota_bytes` sinon **413** |
