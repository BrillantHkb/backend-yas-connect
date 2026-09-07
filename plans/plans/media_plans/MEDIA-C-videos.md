# MEDIA-C — Vidéos (MED-33 … 42)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MEDIA-A](MEDIA-A-upload-stockage.md).  
**Models :** `Video`, `MediaMetadata`.

**Périmètre MVP :** envoi vidéo, transcodage, miniature, lecture (stream). Trim côté client.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MED-33** | **Gardé** | Envoyer vidéo | `media_type=VIDEO`, `videos` |
| **MED-34** | **Gardé** | Compression / transcodage async | `transcoding_status` |
| **MED-35** | **Gardé** | Lecture intégrée player | URL stream signée |
| **MED-36** | **Gardé** | Miniature poster | `thumbnail_path` |
| **MED-37** | **Gardé** | Découpage vidéo (trim) | **client** ou backlog job |
| **MED-38** | **Gardé** | Qualité adaptative HLS/DASH | `streaming_ready` |
| **MED-39** | **Gardé** | Durée, résolution, codec | `videos` + `media_metadata` |
| **MED-40** | **Gardé** | État pipeline visible client | polling `transcoding_status` |
| **MED-41** | **Gardé** | Échec transcodage | `FAILED` + retry |
| **MED-42** | **Gardé** | Limite taille / durée (config) | validation upload |

---

## Contrat HTTP

### `POST /api/v1/media/{id}/video/transcode`

`media.video.manage`. Lance worker Celery. **202** si accepté.

### `GET /api/v1/media/{id}/video/stream`

`media.file.read`. Retourne manifest HLS ou redirect segment si `streaming_ready=true`. **409** si `PENDING`.

### `GET /api/v1/media/{id}/video/thumbnail`

Redirect thumbnail ; généré à la fin transcodage si absent.
