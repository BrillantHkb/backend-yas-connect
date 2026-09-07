# APPELS-E — Enregistrements (CALL-65 … 76)

**Produit :** YAS Connect uniquement.  
**Préalable :** **APPELS-A/C** + **MEDIA-A** (upload / `media_files`).  
**Attributs :** `recordings`, `calls.is_recorded`.  
**Models :** [code/calls_models.py](../code/calls_models.py).

**Périmètre MVP :** démarrer / arrêter l’enregistrement LiveKit, fichier MinIO, lister / télécharger, consentement UI.  
Quota plafond admin = MEDIA-F (**après**) ; l’upload suit quand même MEDIA-A.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **CALL-65** | **Gardé** | HOST/MOD démarre recording | `is_recorded=true`, LiveKit Egress |
| **CALL-66** | **Gardé** | Arrêt recording | Egress stop |
| **CALL-67** | **Gardé** | Webhook egress finished → `recordings` + `media_files` | INSERT |
| **CALL-68** | **Gardé** | `format`, `duration_seconds`, `encrypted` | colonnes |
| **CALL-69** | **Gardé** | Liste recordings d’un appel (participants) | lecture |
| **CALL-70** | **Gardé** | Download via URL signée Médias | `media.file.read` |
| **CALL-71** | **Gardé** | Admin `calls.recording.manage_all` | lecture cross |
| **CALL-72** | **Gardé** | Consent / flag UI avant start | `is_recorded` |
| **CALL-73** | **Gardé** | Quota Médias appliqué au fichier | MEDIA-F |
| **CALL-74** | **Gardé** | WS `RECORDING_STARTED` / `READY` / `FAILED` | — |
| **CALL-75** | **Gardé** | Plusieurs segments si stop/start | N lignes `recordings` |
| **CALL-76** | **Gardé** | Suppression soft : unlink media (owner/admin) | SET NULL / delete |

**Hors incrément :** transcription live pendant l’appel (→ meeting_history plan G), watermarking.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Stockage | Toujours via **Médias** (`media_id`) |
| Qui démarre | HOST ou MODERATOR uniquement |
| Qui lit | Participants de l’appel + admin |
| Chiffrement | `encrypted` aligné pipeline Médias |
| Échec egress | status FAILED WS ; pas de ligne recordings orpheline |

---

## Contrat HTTP

### CALL-65 — `POST /api/v1/calls/{id}/recordings/start`

`calls.recording.create`. **202**. Notify participants.

### CALL-66 — `POST /api/v1/calls/{id}/recordings/stop`

`calls.recording.create`.

### CALL-69 — `GET /api/v1/calls/{id}/recordings`

`calls.recording.read`.

### CALL-70 — `GET /api/v1/recordings/{id}/download`

`calls.recording.read` + ACL participant → redirige / renvoie URL Médias.

### Admin — `GET /api/v1/admin/recordings`

`calls.recording.manage_all`. Filtres call_id, user, date.

---

## Tests (E)

| Cas | Attendu |
|-----|---------|
| Start non-HOST | 403 |
| Egress OK | recording + media_id |
| Download non-participant | 403 |
| Quota plein | 413 (Médias) |
