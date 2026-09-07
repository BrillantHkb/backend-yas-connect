# MEDIA-E — Documents & GED (MED-55 … 68)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MEDIA-A](MEDIA-A-upload-stockage.md).  
**Models :** `Document`, `DocumentVersion`.

**Périmètre MVP :** coffre documents (PDF/Office), aperçu, versions, confidentialité. Signature électronique = hors incrément.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MED-55** | **Gardé** | PDF, Word, Excel, PPT, ZIP | mime validation |
| **MED-56** | **Gardé** | Créer entrée GED | `documents` + `media_files` |
| **MED-57** | **Gardé** | Titre, catégorie | `title`, `category` |
| **MED-58** | **Gardé** | Flag confidentiel | `confidential` |
| **MED-59** | **Gardé** | Propriétaire métier GED | `documents.owner_id` |
| **MED-60** | **Gardé** | Aperçu document | service preview PDF |
| **MED-61** | **Gardé** | Téléchargement | download signé |
| **MED-62** | **Gardé** | Partage (messagerie / lien interne) | MSG forward + log SHARE |
| **MED-63** | **Gardé** | Nouvelle version | `document_versions` + nouveau `media_id` |
| **MED-64** | **Gardé** | Commentaire de version | `document_versions.comment` |
| **MED-65** | **Gardé** | Numéro version courant | `documents.version` |
| **MED-66** | **Gardé** | OCR / extraction texte | `extracted_text` |
| **MED-67** | **Gardé** | Recherche plein texte GED | index futur GIN trgm |
| **MED-68** | **Gardé** | Signature document | **backlog** — non modélisé |

---

## Contrat HTTP

### `POST /api/v1/documents`

`media.document.manage`.

```json
{
  "upload_id": "<uuid>",
  "title": "Contrat 2026",
  "category": "RH",
  "confidential": false
}
```

### `GET /api/v1/documents/{id}`

Métadonnées + version courante.

### `PATCH /api/v1/documents/{id}`

`title`, `category`, `confidential`, `owner_id` (si autorisé).

### `POST /api/v1/documents/{id}/versions`

```json
{
  "upload_id": "<uuid>",
  "comment": "Correction typo"
}
```

Incrémente `version`, crée `document_versions`.

### `GET /api/v1/documents/{id}/versions`

Historique.

### `GET /api/v1/documents/{id}/preview`

HTML ou PDF rendu ; **403** si confidentiel et non autorisé.
