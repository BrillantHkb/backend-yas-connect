# Jour 28 — MEDIA-B + C + D + E (images, vidéos, audio, GED)

**Statut :** à faire.
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.
**Préalable :** jours 0–27 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 27](00-jour-27-messagerie-e-f-g.md)). MEDIA-A (jour 22) a livré l'upload générique (`MediaFile`) — ce jour branche les 9 tables spécialisées `apps.media` qui existent **déjà** depuis AUTH-01 (0 ligne) mais n'ont jamais été exploitées.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §4 — *médias avancés*) :

| Fonction MVP                                    | Ticket                        | Statut             |
| ------------------------------------------------- | ------------------------------ | ------------------- |
| Module Messagerie (1-to-1, groupes, enrichissements) | MESSAGERIE-R…G              | **fait** (jours 25-27) |
| **Images (compression, variantes, annotation)**   | **MEDIA-B**                    | **ce jour**         |
| **Vidéos (transcodage, streaming)**               | **MEDIA-C**                    | **ce jour**         |
| **Audio (vocal, transcription)**                  | **MEDIA-D**                    | **ce jour**         |
| **Documents / GED (versions, aperçu)**            | **MEDIA-E**                    | **ce jour**         |

**À quoi ça sert (MVP) :** MEDIA-A (jour 22) ne stocke qu'un blob opaque + un checksum — utilisable pour un PJ chat basique, mais insuffisant pour une vraie galerie (miniatures), un lecteur vidéo (streaming), un message vocal (waveform + dictée) ou un coffre documentaire (versions, confidentialité). Ce jour branche les 9 tables déjà en base (`media_metadata`, `images`, `videos`, `audio_messages`, `voice_transcriptions`, `documents`, `document_versions` — `media_access_logs`/`storage_usage` déjà utilisées depuis MEDIA-A) sur de vraies routes.

**Plan métier (code à coller) :** [MEDIA-B-images.md](media_plans/MEDIA-B-images.md) (MED-19…32) + [MEDIA-C-videos.md](media_plans/MEDIA-C-videos.md) (MED-33…42) + [MEDIA-D-audio-transcription.md](media_plans/MEDIA-D-audio-transcription.md) (MED-43…54, **hors** distinction PRIVATE/GROUP — voir §0) + [MEDIA-E-documents-ged.md](media_plans/MEDIA-E-documents-ged.md) (MED-55…68, **hors** MED-66 OCR réel, MED-67 recherche plein texte, MED-68 signature — voir §0). Modèles : déjà tous créés ([code/media_models.py](code/media_models.py), AUTH-01).
Chemins lab = ce fichier.

**Déjà en base / code :**

- Les **10 tables** `apps.media` (AUTH-01, 0 ligne) : `MediaFile`, `MediaMetadata`, `Image`, `Video`, `AudioMessage`, `VoiceTranscription`, `Document`, `DocumentVersion`, `MediaAccessLog`, `StorageUsage`. **0 nouvelle migration ce jour.**
- Les **12 permissions self** `media.*` (MEDIA-R, jour 22) couvrent déjà tout ce jour : `media.image.manage`, `media.video.manage`, `media.audio.manage`, `media.document.read`, `media.document.manage`. **0 nouvelle permission.**
- `apps.media.services.upload_service.complete_upload` (MEDIA-A) : point d'entrée unique où brancher la création des lignes spécialisées (`Image`/`Video`/`AudioMessage`) selon `media_type`.
- `apps.media.services.storage` (MinIO réel, jour 22) : `presigned_get_url` réutilisé pour stream/thumbnail/preview.
- `apps.media.services.upload_service.get_own_media_or_404` : réutilisé partout (ACL owner-only, cohérent avec tout le module Média).

**Pas encore :** aucune ligne `Image`/`Video`/`AudioMessage`/`Document` n'est jamais créée. Aucune route `/media/{id}/image|video|audio/*` ni `/documents/*` n'existe. **Aucune lib de traitement média** (Pillow, ffmpeg, moteur STT) n'est installée — décision prise avec l'utilisateur (2026-09-16, AskUserQuestion) : tout en **stub synchrone** ce jour (voir §0), pas de nouvelle dépendance.

**Objectif du jour :**

1. **MEDIA-B** : `complete_upload` crée une ligne `Image` (stub) pour `media_type=IMAGE`. 2 routes (`PATCH .../image`, `POST .../image/optimize`) + variantes sur le download existant.
2. **MEDIA-C** : `complete_upload` crée une ligne `Video` (stub, `PENDING`) pour `media_type=VIDEO`. 3 routes (transcode, stream, thumbnail).
3. **MEDIA-D** : `complete_upload` crée une ligne `AudioMessage` (stub, `PENDING`) pour `media_type=AUDIO`. 2 routes (transcribe, liste transcriptions).
4. **MEDIA-E** : GED complète — 5 routes (créer, détail, modifier, versions ×2, aperçu).
5. Extension `complete_upload` : accepte un `metadata` optionnel (client-fourni : largeur/hauteur/durée/codec/GPS) — sans lib serveur, seul le client connaît ces valeurs nativement (§0).
6. Ne rien casser : MEDIA-A (upload/download/quota), tout le module Messagerie (jours 25-27).

**Hors jour 28 :** vrai traitement (resize Pillow, transcodage ffmpeg, HLS/DASH, STT) — décision utilisateur, tout reste stub synchrone ; distinction CRYPTO-00 PRIVATE (pas de STT serveur) vs GROUP pour l'audio — nécessiterait qu'`apps.media` connaisse le fil messagerie d'un fichier (lien inverse `media_id → message → conversation.type`), qui n'existe pas et créerait un import circulaire avec `apps.messaging` (§0) ; OCR réel (MED-66), recherche plein texte GED (MED-67, index GIN trgm futur) ; signature électronique (MED-68, backlog explicite du business doc) ; `GET /conversations/discoverable`-style partage GED avancé (MED-62 = déjà possible tel quel via MESSAGERIE-E forward + `GET /media/files/{id}`, aucun travail supplémentaire).

---

## 0. Corrections apportées au plan métier (avant de coder)

| Écart trouvé | Correction |
|---|---|
| MEDIA-C : « Lance worker Celery. **202** si accepté » | **Aucun Celery dans le projet** (vérifié `requirements/base.txt`). Décision utilisateur (AskUserQuestion, 2026-09-16) : stub synchrone — `POST .../video/transcode` fait la transition `PENDING→PROCESSING→READY` **dans la même requête**, retourne quand même **202** (contrat HTTP respecté), sans ffmpeg/HLS réel. |
| MEDIA-D : STT réel (langue détectée, score confiance, modèle) | Stub : `VoiceTranscription` créée avec `text=""` (ou texte factice), `model_used="stub"`, `confidence=None`. Prêt à brancher un vrai moteur STT plus tard sans changer le contrat HTTP. |
| MEDIA-B/C/D : résolution/durée/codec/GPS supposés connus dès la création des tables | Sans lib serveur, seul le **client** connaît ces valeurs (API OS locale). `POST /media/uploads/{id}/complete` (MEDIA-A) accepte désormais un objet `metadata` **optionnel** (`width`, `height`, `duration_seconds`, `codec`, `latitude`, `longitude`, `captured_at`, `device_model`) — stocké dans `MediaMetadata` et dupliqué dans la table spécialisée. Le client ment s'il veut, comme n'importe quelle métadonnée auto-déclarée côté client dans ce projet (ex. `registration_id` CRYPTO-A). |
| MEDIA-D : distinction CRYPTO-00 vocal PRIVATE (pas de STT serveur) vs GROUP (STT autorisé) | Hors jour 28 (§ Hors jour 28) — `apps.media` ne connaît aujourd'hui aucune conversation. Le jour qui enverra réellement des vocaux en messagerie (extension future de MESSAGERIE-B pour `type=AUDIO`) devra vérifier lui-même le type de fil avant d'appeler `POST /media/{id}/audio/transcribe`, pas l'inverse. |
| MEDIA-B `GET variante` : nouvelle route dans le business doc | Fusionné dans la route de téléchargement **existante** (`GET /media/{id}/download?variant=`, MEDIA-A jour 22) plutôt qu'une route séparée — même perm, même logique ACL owner-only, un seul endroit à maintenir. |
| MEDIA-E MED-66/67/68 (OCR, recherche plein texte, signature) | Le business doc les classe lui-même « backlog »/« index futur » — différés proprement (§ Hors jour 28), `extracted_text` reste une colonne vide exploitable plus tard. |
| MEDIA-E MED-62 (partage) | Déjà possible sans rien coder : `MESSAGERIE-E` (jour 27) sait transférer un message avec `media_id`, et `GET /media/files/{id}` (MEDIA-A) sert déjà n'importe quel fichier `CLEAN`/`SKIPPED` à tout utilisateur authentifié (pas d'ACL owner-only sur cette route spécifique, contrairement à `/media/{id}/download`). |

---

## Pourquoi ce jour (après le module Messagerie complet)

Le module Messagerie (jours 25-27) envoie déjà des pièces jointes via `media_id` (`get_own_media_or_404`), mais ne sait rien faire de plus qu'un blob opaque — pas de miniature dans l'inbox, pas de lecteur vidéo, pas de waveform vocal, pas de coffre documentaire. Construire MEDIA-B/C/D/E maintenant, une fois la Messagerie stable, permet de brancher ces enrichissements sans avoir dû deviner leur forme avant que Messagerie existe. C'est aussi le dernier jour « infrastructure lourde » avant Appels (jour 29-30), qui a ses propres exigences temps réel (LiveKit, déjà externalisé).

```text
JWT + HasPermission + portes AUTH-F. Appareil = session courante si applicable.

Delta MEDIA-A (upload)
    POST /media/uploads/{id}/complete   + metadata optionnel (§0)
    → crée Image/Video/AudioMessage (stub) selon media_type

Vague B — Images (toutes perms déjà seedées au jour 22)
    PATCH  /media/{id}/image                    media.image.manage
    POST   /media/{id}/image/optimize            media.image.manage
    GET    /media/{id}/download?variant=          media.file.read (delta)

Vague C — Vidéos
    POST   /media/{id}/video/transcode            media.video.manage
    GET    /media/{id}/video/stream                 media.file.read
    GET    /media/{id}/video/thumbnail               media.file.read

Vague D — Audio
    POST   /media/{id}/audio/transcribe            media.audio.manage
    GET    /media/{id}/audio/transcriptions          media.audio.manage

Vague E — Documents / GED
    POST   /documents                              media.document.manage
    GET    /documents/{id}                           media.document.read
    PATCH  /documents/{id}                            media.document.manage
    POST   /documents/{id}/versions                    media.document.manage
    GET    /documents/{id}/versions                     media.document.read
    GET    /documents/{id}/preview                       media.document.read

Hors jour 28
    Vrai resize/transcodage/STT, OCR, recherche plein texte, signature, distinction CRYPTO-00 audio
```

---

## Paliers (figés pour ce jour)

| Sujet | Choix jour 28 | Plus tard |
| ----- | ------------- | --------- |
| Traitement média | **Stub synchrone partout** (décision utilisateur) : aucune nouvelle dépendance, transitions d'état immédiates dans la requête, valeurs par défaut ou copiées | Pillow (images) / ffmpeg (vidéo) / STT (audio) réels : tickets futurs |
| Création ligne spécialisée | À `complete_upload` (MEDIA-A), selon `media_type` : `IMAGE`→`Image`, `VIDEO`→`Video` (`PENDING`), `AUDIO`→`AudioMessage` (`PENDING`). `DOCUMENT` : **jamais automatique**, seulement via `POST /documents` explicite (le business doc l'exige : titre/catégorie ne se déduisent pas d'un upload générique) | — |
| `metadata` optionnel à l'upload | `{width?, height?, duration_seconds?, codec?, latitude?, longitude?, captured_at?, device_model?}`, déclaré par le client, stocké tel quel (`MediaMetadata`) + dupliqué dans la table spécialisée. Jamais validé pour cohérence avec le fichier réel (pas de lib pour vérifier) | — |
| Image : variantes | `thumbnail_path`/`optimized_path` = `storage_path` original au stub (même objet MinIO, pas de vrai redimensionnement). `GET /media/{id}/download?variant=thumbnail\|optimized\|original` (défaut `original`, rétrocompatible) | Vrais fichiers distincts par variante |
| Image : dérivé annoté/flouté | `PATCH /media/{id}/image {"derivative_upload_id"}` : doit être un upload **du même owner**, déjà complété — remplace `optimized_path` par le `storage_path` du dérivé | — |
| Vidéo : transcodage | `POST .../video/transcode` : `PENDING→PROCESSING→READY` synchrone, `streaming_ready=true`, `thumbnail_path=storage_path` (stub), retourne **202** | — |
| Vidéo : stream | `GET .../video/stream` : **409** si `transcoding_status != READY` ; sinon URL présignée (tient lieu de manifest HLS, pas de vrai HLS) | — |
| Audio : transcription | `POST .../audio/transcribe {"language"?}` : `PENDING→PROCESSING→DONE` synchrone, crée `VoiceTranscription(text="", model_used="stub", language=<fourni ou "fr">)`, retourne **202** | Vrai moteur STT : remplace juste le contenu de `text`/`confidence` |
| Audio : re-transcription | Chaque appel `POST .../transcribe` crée une **nouvelle** ligne `VoiceTranscription` (MED-53, historique conservé), `GET .../transcriptions` liste tout | — |
| Document création | `POST /documents {upload_id, title, category, confidential}` : `upload_id` doit être **à soi**, `scan_status` ≠ `INFECTED`, et **pas déjà** un document (`Document` est 1-1 `MediaFile`) → **409** `ALREADY_DOCUMENT` sinon. Crée `Document(version=1)` + `DocumentVersion(version_number=1)` | — |
| Document lecture/gestion | **Owner-only** (`get_own_media_or_404` sous-jacent), comme tout le reste du module Média — `confidential` est un flag d'affichage/futur-partage, pas une deuxième couche d'ACL ce jour (déjà owner-only par défaut) | Partage GED à des tiers non-owner : hors MVP |
| Nouvelle version | `POST /documents/{id}/versions {upload_id, comment?}` : `upload_id` à soi, pas déjà lié à un autre document. Incrémente `documents.version`, crée `DocumentVersion` | — |
| Aperçu | `GET /documents/{id}/preview` : redirect présignée vers le `media` de la version **courante** (pas de vrai rendu HTML/PDF, stub). **403** si `confidential=true` et appelant ≠ owner (filet — déjà owner-only en amont, donc jamais atteint en pratique, mais codé pour cohérence avec le contrat) | Vrai rendu preview : hors MVP |
| Portes AUTH-F | Toutes les routes sous JWT + CGU/wizard (comme tout `/api/v1/*`) | — |
| Audit | Réutilise `MediaAccessLog`/`_audit` déjà en place (MEDIA-A) — pas de nouvelle table d'audit | — |

---

## 1. Tables

**Aucune migration ce jour.** Les 10 tables `apps.media` existent depuis AUTH-01 (`0001_initial.py`), 0 ligne jusqu'ici pour les 9 spécialisées.

---

## 2. Fichiers

| Fichier | Rôle |
| ------- | ---- |
| `apps/media/services/upload_service.py` | **delta.** `complete_upload` accepte `metadata`, crée `Image`/`Video`/`AudioMessage` selon `media_type` ; `download_media` accepte `variant` |
| `apps/media/services/image_service.py` | **nouveau.** `update_image`, `optimize_image` |
| `apps/media/services/video_service.py` | **nouveau.** `transcode`, `stream_url`, `thumbnail_url` |
| `apps/media/services/audio_service.py` | **nouveau.** `transcribe`, `list_transcriptions` |
| `apps/media/services/document_service.py` | **nouveau.** `create_document`, `get_document`, `update_document`, `add_version`, `list_versions`, `preview_url` |
| `apps/media/serializers/uploads.py` | **delta.** `UploadCompleteSerializer` + `metadata` |
| `apps/media/serializers/images.py`, `serializers/videos.py`, `serializers/audio.py`, `serializers/documents.py` | **nouveau.** |
| `apps/media/views/images.py`, `views/videos.py`, `views/audio.py`, `views/documents.py` | **nouveau.** |
| `apps/media/views/uploads.py` | **delta.** `MediaDownloadView` gère `?variant=` |
| `apps/media/urls.py` | **delta.** + 12 routes |
| `apps/iam/tests/test_media_b.py`, `test_media_c.py`, `test_media_d.py`, `test_media_e.py` | **nouveau.** |

---

## 3. Contrat HTTP

Préfixe `/api/v1`. JWT + portes AUTH-F. **401** sans JWT, **403** `FORBIDDEN`/`TOS_REQUIRED`/`ONBOARDING_REQUIRED` (toutes les routes, non répété ci-dessous). ACL owner-only (`get_own_media_or_404`) sauf mention contraire.

### 3.0 Delta upload (MEDIA-A étendu)

| # | Route | Perm | Requête | Flux serveur | Réponse | Erreurs |
|---|-------|------|---------|---------------|---------|----------------------|
| U1 | `POST /media/uploads/{id}/complete` (delta) | `media.file.upload` | `{ "checksum", "metadata"? : {width?,height?,duration_seconds?,codec?,latitude?,longitude?,captured_at?,device_model?} }` | 1. Flux MEDIA-A inchangé (checksum, taille réelle, dédup, scan).<br>2. Si `metadata` fourni : `MediaMetadata.objects.update_or_create(media, defaults={...})`.<br>3. Selon `media.media_type` : `IMAGE` → crée `Image` (stub, `thumbnail_path=optimized_path=storage_path`) ; `VIDEO` → crée `Video(transcoding_status=PENDING, duration_seconds=metadata.duration_seconds or 0, resolution=f"{w}x{h}" si fourni)` ; `AUDIO` → crée `AudioMessage(transcription_status=PENDING, duration_seconds=..., waveform=[])`. | **200** — shape MEDIA-A + `detail` (image/video/audio selon type) | 400/409/413 (inchangés) |

### 3.1 Vague B — Images

| # | Route | Perm | Requête | Flux serveur | Réponse | Erreurs |
|---|-------|------|---------|---------------|---------|----------------------|
| B1 | `PATCH /media/{id}/image` (MED-25/26) | `media.image.manage` | `{ "annotated"?, "blurred"?, "derivative_upload_id"? }` | 1. `get_own_media_or_404` ; 404 si pas de `Image` liée (`media_type != IMAGE`).<br>2. `derivative_upload_id` fourni → `get_own_media_or_404(user, id)` (doit être à soi, `scan_status != INFECTED`) → `Image.optimized_path = derivative.storage_path`.<br>3. `annotated`/`blurred` mis à jour si fournis. | **200** `{ annotated, blurred, thumbnail_path_url, optimized_path_url }` | 400/404 |
| B2 | `POST /media/{id}/image/optimize` (MED-21) | `media.image.manage` | — | Stub idempotent : si `optimized_path` vide, le fixe à `storage_path` ; sinon no-op. | **202** `{ "optimized": true }` | 404 |
| B3 | `GET /media/{id}/download?variant=` (MED-31, delta) | `media.file.read` | Query `variant` ∈ `{original, thumbnail, optimized}` (défaut `original`) | `thumbnail`/`optimized` → nécessite `Image` liée (404 sinon) → URL présignée sur `thumbnail_path`/`optimized_path`. `original` → comportement MEDIA-A inchangé. | **302** redirect présignée | 400 (variant inconnu), 403 `FILE_INFECTED`, 404 |

### 3.2 Vague C — Vidéos

| # | Route | Perm | Requête | Flux serveur | Réponse | Erreurs |
|---|-------|------|---------|---------------|---------|----------------------|
| C1 | `POST /media/{id}/video/transcode` (MED-34) | `media.video.manage` | — | `get_own_media_or_404` ; 404 si pas de `Video` liée. Stub : `transcoding_status=PROCESSING` puis `READY` (même requête), `streaming_ready=True`, `thumbnail_path=storage_path` si vide. | **202** `{ "transcoding_status": "READY" }` | 404 |
| C2 | `GET /media/{id}/video/stream` (MED-35/38) | `media.file.read` | — | `transcoding_status != READY` → **409** `VIDEO_NOT_READY`. Sinon URL présignée. | **200** `{ "stream_url" }` | 404, 409 `VIDEO_NOT_READY` |
| C3 | `GET /media/{id}/video/thumbnail` (MED-36) | `media.file.read` | — | `thumbnail_path` vide → **404**. Sinon redirect présignée. | **302** redirect | 404 |

### 3.3 Vague D — Audio

| # | Route | Perm | Requête | Flux serveur | Réponse | Erreurs |
|---|-------|------|---------|---------------|---------|----------------------|
| D1 | `POST /media/{id}/audio/transcribe` (MED-49/50/53) | `media.audio.manage` | `{ "language"? }` | `get_own_media_or_404` ; 404 si pas d'`AudioMessage` liée. Stub : `transcription_status=PROCESSING` puis `DONE`, crée `VoiceTranscription(text="", language=language or "fr", model_used="stub")` (nouvelle ligne à chaque appel, historique conservé). | **202** `{ "transcription_status": "DONE", "transcription_id" }` | 404 |
| D2 | `GET /media/{id}/audio/transcriptions` (MED-53) | `media.audio.manage` | — | Liste `VoiceTranscription` triée `-created_at`. | **200** `{ "results": [{ id, language, text, confidence, model_used, created_at }] }` | 404 |

### 3.4 Vague E — Documents / GED

| # | Route | Perm | Requête | Flux serveur | Réponse | Erreurs |
|---|-------|------|---------|---------------|---------|----------------------|
| E1 | `POST /documents` (MED-56/57/58/59) | `media.document.manage` | `{ "upload_id", "title", "category"?, "confidential"? }` | `get_own_media_or_404(user, upload_id)` ; `scan_status=INFECTED` → 422 ; déjà un `Document` pour ce media → **409** `ALREADY_DOCUMENT`. Transaction : `Document(version=1)` + `DocumentVersion(version_number=1, media=upload, comment="Version initiale")`. | **201** `{ id, title, category, confidential, version, created_at }` | 400, 404, 409 `ALREADY_DOCUMENT`, 422 |
| E2 | `GET /documents/{id}` (MED-60→ métadonnées) | `media.document.read` | — | Owner-only (404 sinon). | **200** — shape E1 + `owner_id` | 404 |
| E3 | `PATCH /documents/{id}` (MED-57/58) | `media.document.manage` | `{ "title"?, "category"?, "confidential"?, "owner_id"? }` | Owner-only. `owner_id` : transfert vers un autre user actif (404 si inconnu). | **200** — shape E1 | 400, 404 |
| E4 | `POST /documents/{id}/versions` (MED-63/64) | `media.document.manage` | `{ "upload_id", "comment"? }` | `get_own_media_or_404(user, upload_id)`, pas déjà lié à un `DocumentVersion`. `version_number = documents.version + 1`, incrémente `documents.version`. | **201** `{ version_number, comment, created_at }` | 400, 404, 409 |
| E5 | `GET /documents/{id}/versions` (MED-65) | `media.document.read` | — | Owner-only. Liste triée `-version_number`. | **200** `{ "results": [{ version_number, media_id, comment, changed_by, created_at }] }` | 404 |
| E6 | `GET /documents/{id}/preview` (MED-60) | `media.document.read` | — | Owner-only (donc le filet `confidential` ci-dessous n'est jamais atteint en pratique, codé pour cohérence contrat). URL présignée du `media` de la version courante. | **200** `{ "preview_url" }` | 403 (filet confidential), 404 |

---

## 4. Tests nouveaux

### `test_media_b.py`

| Cas | Attendu |
| --- | ------- |
| Upload IMAGE + complete avec `metadata` | `Image` créée, `MediaMetadata` avec `width`/`height` |
| PATCH image `annotated=true` | reflété |
| PATCH image `derivative_upload_id` (à soi) | `optimized_path` mis à jour |
| PATCH image `derivative_upload_id` d'un autre user | 404 |
| POST image/optimize, rejoué | idempotent, 202 les deux fois |
| GET download `variant=thumbnail` | 302 vers l'URL présignée |
| GET download `variant=invalide` | 400 |
| GET download sur un fichier sans `Image` (ex. DOCUMENT) avec `variant=thumbnail` | 404 |

### `test_media_c.py`

| Cas | Attendu |
| --- | ------- |
| Upload VIDEO + complete | `Video(transcoding_status=PENDING)` créée |
| GET stream avant transcode | 409 `VIDEO_NOT_READY` |
| POST transcode | 202, `transcoding_status=READY`, `streaming_ready=true` |
| GET stream après transcode | 200 `stream_url` |
| GET thumbnail après transcode | 302 |

### `test_media_d.py`

| Cas | Attendu |
| --- | ------- |
| Upload AUDIO + complete | `AudioMessage(transcription_status=PENDING)` créée |
| POST transcribe | 202, `transcription_status=DONE`, `VoiceTranscription` créée |
| POST transcribe ×2 | 2 lignes `VoiceTranscription` (historique) |
| GET transcriptions | liste triée, contient les 2 lignes |

### `test_media_e.py`

| Cas | Attendu |
| --- | ------- |
| POST documents | 201, `Document(version=1)` + `DocumentVersion(1)` |
| POST documents, même `upload_id` rejoué | 409 `ALREADY_DOCUMENT` |
| POST documents, upload d'un autre user | 404 |
| GET documents/{id} par non-owner | 404 |
| PATCH documents (title, confidential) | reflété |
| PATCH documents `owner_id` | transfert effectif, ancien owner perd l'accès (404) |
| POST versions | `version=2`, `DocumentVersion(2)` créée |
| GET versions | 2 lignes, triées desc |
| GET preview | 200 `preview_url` (URL de la version courante) |
| `/api/schema/` | contient `/api/v1/documents` |

---

## 5. Vérif manuelle

```powershell
python manage.py check
pytest apps/iam/tests/test_media_b.py apps/iam/tests/test_media_c.py apps/iam/tests/test_media_d.py apps/iam/tests/test_media_e.py apps/iam/tests/test_media_a.py --reuse-db
```

---

## Checklist jour 28

- [ ] `complete_upload` : `metadata` optionnel + création `Image`/`Video`/`AudioMessage` selon type
- [ ] MEDIA-B : PATCH image, optimize, download `?variant=`
- [ ] MEDIA-C : transcode (stub), stream (409 si pas prêt), thumbnail
- [ ] MEDIA-D : transcribe (stub, historique conservé), liste transcriptions
- [ ] MEDIA-E : créer/lire/modifier document, versions, aperçu
- [ ] `test_media_b/c/d/e.py`
- [ ] 0 régression MEDIA-A, tout le module Messagerie
- [ ] 0 nouvelle migration, 0 nouvelle permission, 0 nouvelle dépendance
- [ ] SIRH non modifié

---

## Interdits

- Toute nouvelle dépendance de traitement média (Pillow, ffmpeg, STT) — décision utilisateur, tout reste stub ce jour
- OCR réel, recherche plein texte GED, signature électronique (MED-66/67/68 — backlog du business doc lui-même)
- Distinction CRYPTO-00 PRIVATE/GROUP pour l'audio (apps.media ne connaît pas la messagerie, import circulaire)
- `docker compose down -v`
- Changer le SIRH

---

## Après le jour 28

Jour 29 : **APPELS-R, A, B, C** — cycle de vie d'appel (1-1), participants/sessions, intégration LiveKit temps réel, `CALL_CANCELLED`. Premier jour du dernier module MVP. Lab pas encore écrit.

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
| 22     | MEDIA-R + MEDIA-A                               | §4 upload (plafonds ; pas de reprise)  |
| 23     | NOTIF-R + NOTIF-A                               | §5 alertes + MOB-PUSH (VoIP / worker)  |
| 24     | CRYPTO-R + CRYPTO-A                             | Clés HTTP                              |
| 25     | MESSAGERIE-R, A, B                              | §7 1-to-1                              |
| 26     | MESSAGERIE-C, D                                 | §7 groupes + temps réel                |
| 27     | MESSAGERIE-E (partiel), F, G                    | §7 enrichissements                     |
| **28** | **MEDIA-B, C, D, E** (ce plan)                  | §4 album / vocal / coffre              |
| 29     | APPELS-R, A, B, C                               | §8 appel 1-1 + `CALL_CANCELLED`        |
| 30     | APPELS-D, E, G                                  | §8 écran / CR                          |

**Total : 31 plans (jours 0 à 30).**
Déjà clos : **28** (0–27). Restant : **3** (28–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.
