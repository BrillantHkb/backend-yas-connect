# Médias — Catalogue des routes planifiées

**Produit :** YAS Connect uniquement.  
**Source :** [MEDIA-R](MEDIA-R-roles-permissions.md) · [A](MEDIA-A-upload-stockage.md) … [F](MEDIA-F-quotas-audit.md).  
**Préfixe :** `/api/v1`.  
**Consommateurs :** IAM (avatar PROF-A), Messagerie (PJ), Annuaire (certifs).

**Permission** = `required_permission`. **34 routes HTTP**.

**Hors tableau :** workers (scan, transcode, STT, OCR), cleanup S3 orphelins.

---

## Pourquoi cet ordre

| Vague | Plan | Pourquoi |
|-------|------|----------|
| **0** | MEDIA-R | Seed `media.*` |
| **A** | MEDIA-A | Upload socle (tables AUTH-01 déjà créées) |
| **B–E** | MEDIA-B…E | Extensions par type après premier byte en bucket |
| **F** | MEDIA-F | Quotas + audit une fois uploads actifs |

**Note :** avatar `PATCH /me` reste dans [PROF-A](../iam_plans/PROF-A-identite.md) mais appelle `media_id` issu de MEDIA-A.

---

## Vague 0 — RBAC (MEDIA-R)

Hors HTTP : `python manage.py seed_media`.

---

## Vague A — Upload & stockage (MEDIA-A)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 1 | `POST` | `/api/v1/media/uploads` | Collaborateur | `media.file.upload` | USER, ADMIN | A-01 | Init presign | Retourne URL PUT. |
| 2 | `POST` | `/api/v1/media/uploads/{upload_id}/complete` | Collaborateur | `media.file.upload` | USER, ADMIN | A-01 | Finaliser upload | Checksum, scan async. |
| 3 | `POST` | `/api/v1/media/upload` | Collaborateur | `media.file.upload` | USER, ADMIN | A-01 | Multipart direct | < 10 Mo. |
| 4 | `GET` | `/api/v1/media/{id}` | Collaborateur | `media.file.read` | USER, ADMIN | A-09 | Métadonnées | ACL owner / conversation. |
| 5 | `GET` | `/api/v1/media/{id}/download` | Collaborateur | `media.file.read` | USER, ADMIN | A-10 | Téléchargement | URL signée ; log. |
| 6 | `DELETE` | `/api/v1/media/{id}` | Collaborateur | `media.file.delete` | USER, ADMIN | A-11 | Supprimer | 409 si référencé. |

---

## Vague B — Images (MEDIA-B)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 7 | `PATCH` | `/api/v1/media/{id}/image` | Collaborateur | `media.image.manage` | USER, ADMIN | B-25/26 | Annotation, flou | |
| 8 | `POST` | `/api/v1/media/{id}/image/optimize` | Collaborateur | `media.image.manage` | USER, ADMIN | B-21 | Compression | Job async. |
| 9 | `GET` | `/api/v1/media/{id}/image` | Collaborateur | `media.file.read` | USER, ADMIN | B-31 | Variante | Query `variant=thumbnail\|optimized\|original`. |

---

## Vague C — Vidéos (MEDIA-C)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 10 | `POST` | `/api/v1/media/{id}/video/transcode` | Collaborateur | `media.video.manage` | USER, ADMIN | C-34 | Lancer transcodage | 202. |
| 11 | `GET` | `/api/v1/media/{id}/video/stream` | Collaborateur | `media.file.read` | USER, ADMIN | C-35/38 | Stream HLS | |
| 12 | `GET` | `/api/v1/media/{id}/video/thumbnail` | Collaborateur | `media.file.read` | USER, ADMIN | C-36 | Poster | |

---

## Vague D — Audio (MEDIA-D)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 13 | `POST` | `/api/v1/media/{id}/audio/transcribe` | Collaborateur | `media.audio.manage` | USER, ADMIN | D-49 | STT | 202. |
| 14 | `GET` | `/api/v1/media/{id}/audio/transcriptions` | Collaborateur | `media.file.read` | USER, ADMIN | D-50 | Texte vocal | Liste. |
| 15 | `GET` | `/api/v1/media/{id}/audio/waveform` | Collaborateur | `media.file.read` | USER, ADMIN | D-47 | Waveform | Points json. |

---

## Vague E — Documents GED (MEDIA-E)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 16 | `POST` | `/api/v1/documents` | Collaborateur | `media.document.manage` | USER, ADMIN | E-56 | Créer document | Après upload. |
| 17 | `GET` | `/api/v1/documents/{id}` | Collaborateur | `media.document.read` | USER, ADMIN | E-57 | Détail GED | |
| 18 | `PATCH` | `/api/v1/documents/{id}` | Collaborateur | `media.document.manage` | USER, ADMIN | E-57/58 | Modifier métadonnées | |
| 19 | `POST` | `/api/v1/documents/{id}/versions` | Collaborateur | `media.document.manage` | USER, ADMIN | E-63 | Nouvelle version | |
| 20 | `GET` | `/api/v1/documents/{id}/versions` | Collaborateur | `media.document.read` | USER, ADMIN | E-63 | Historique | |
| 21 | `GET` | `/api/v1/documents/{id}/preview` | Collaborateur | `media.document.read` | USER, ADMIN | E-60 | Aperçu | |
| 22 | `GET` | `/api/v1/documents` | Collaborateur | `media.document.read` | USER, ADMIN | E | Liste GED | Filtres `category`, `q`. |

---

## Vague F — Quotas & audit (MEDIA-F)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 23 | `GET` | `/api/v1/me/storage-usage` | Collaborateur | `media.storage.read` | USER, ADMIN | F-70 | Mon quota | |
| 24 | `GET` | `/api/v1/admin/users/{id}/storage-usage` | Admin | `media.storage.manage` | ADMIN | F-72 | Quota user | |
| 25 | `PATCH` | `/api/v1/admin/users/{id}/storage-usage` | Admin | `media.storage.manage` | ADMIN | F-72 | Fixer plafond | |
| 26 | `GET` | `/api/v1/admin/media/{id}/access-logs` | Admin | `media.access_log.read` | ADMIN | F-75 | Audit fichier | |

---

## Routes liées (autres modules)

| Route | Module | Lien Médias |
|-------|--------|-------------|
| `PATCH /api/v1/me` (`avatar_id`) | PROF-A | MED-15 |
| `POST /api/v1/conversations/{id}/messages` (`media_id`) | Messagerie | MED-16 |
| `POST /api/v1/me/certifications` (`document_id`) | Annuaire-D | MED-17 |

---

## Index par acteur

| Acteur | Combien | Qui |
|--------|---------|-----|
| **Collaborateur** | 23 | Upload, images, vidéo, audio, documents, quota perso |
| **Admin** | +3 | Quota user, logs accès (#24–26) |

---

## Mapping fonctionnalités produit (module 4) → routes

| Bloc produit | Routes / plan |
|--------------|---------------|
| Images (envoi, compression, preview, rotation, annotation, flou, GPS, date) | #1–9, B |
| Vidéo (envoi, compression, lecture, miniature, découpage client, adaptatif) | #1–6, #10–12, C |
| Audio (vocal, enregistrement, transcription, lecture rapide client) | #1–6, #13–15, D |
| Documents (PDF/Office/ZIP, preview, download, partage, version, commentaire) | #16–22, E |
| Signature document | **Backlog** MED-68 (pas de route) |
