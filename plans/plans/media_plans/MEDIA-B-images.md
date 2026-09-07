# MEDIA-B — Images (MED-19 … 32)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MEDIA-A](MEDIA-A-upload-stockage.md).  
**Models :** `Image`, `MediaMetadata`.

**Périmètre MVP :** photos, miniatures, compression, variantes (original / allégé). Annotation / flou = même plan.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MED-19** | **Gardé** | Envoyer photo (chat / galerie) | `media_type=IMAGE`, row `images` |
| **MED-20** | **Gardé** | Envoi multiple (lot) | N uploads |
| **MED-21** | **Gardé** | Compression auto → `optimized_path` | job image |
| **MED-22** | **Gardé** | Qualité originale conservée | `storage_path` source |
| **MED-23** | **Gardé** | Prévisualisation thumbnail | `thumbnail_path` |
| **MED-24** | **Gardé** | Rotation | client ou job → nouveau blob |
| **MED-25** | **Gardé** | Annotation / dessin | `annotated=true` + fichier dérivé |
| **MED-26** | **Gardé** | Floutage zones | `blurred=true` |
| **MED-27** | **Gardé** | Géolocalisation EXIF | `media_metadata.latitude/longitude` |
| **MED-28** | **Gardé** | Date prise de vue | `captured_at` |
| **MED-29** | **Gardé** | Résolution / format / qualité | `images.*` |
| **MED-30** | **Gardé** | Choix qualité upload (original vs compressé) | query `quality=original\|standard` |
| **MED-31** | **Gardé** | GET variante `?variant=thumbnail\|optimized\|original` | download |
| **MED-32** | **Gardé** | GIF animé | `media_type=IMAGE` ou `OTHER` + mime `image/gif` |

---

## Contrat HTTP

### `PATCH /api/v1/media/{id}/image`

`media.image.manage`. Body :

```json
{
  "annotated": true,
  "blurred": true,
  "derivative_upload_id": "<uuid>"
}
```

`derivative_upload_id` = nouveau fichier dérivé déjà uploadé (MEDIA-A).

### `POST /api/v1/media/{id}/image/optimize`

Relance job compression (idempotent si READY).
