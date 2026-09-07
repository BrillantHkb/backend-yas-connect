# APPELS-D — Pistes & partage d’écran (CALL-53 … 64)

**Produit :** YAS Connect uniquement.  
**Préalable :** **APPELS-C** (webhooks tracks).  
**Attributs :** `media_tracks`, `screen_shares`.  
**Models :** [code/calls_models.py](../code/calls_models.py).

**Périmètre MVP :** pistes live + partage d’écran (démarrer / arrêter, 1 share actif / user, liste, WS).  
**Hors incrément :** annotation collaborative sur le share, prise de contrôle à distance.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **CALL-53** | **Gardé** | Upsert piste sur `track_published` | `media_tracks` |
| **CALL-54** | **Gardé** | `active=false` sur `track_unpublished` | `media_tracks` |
| **CALL-55** | **Gardé** | Types `AUDIO` / `VIDEO` / `SCREEN_SHARE` | enum |
| **CALL-56** | **Gardé** | Stocker codec, bitrate, resolution | colonnes |
| **CALL-57** | **Gardé** | Démarrer partage écran → `screen_shares` | INSERT |
| **CALL-58** | **Gardé** | Arrêter partage → `ended_at`, `active=false` | UPDATE |
| **CALL-59** | **Gardé** | Plusieurs shares successifs par user | multi-lignes |
| **CALL-60** | **Gardé** | Liste pistes d’un appel | lecture |
| **CALL-61** | **Gardé** | Liste screen shares | lecture |
| **CALL-62** | **Gardé** | WS `SCREEN_SHARE_STARTED` / `STOPPED` | — |
| **CALL-63** | **Gardé** | Limite 1 share actif / user (nouveau share clôt l’ancien) | règle |
| **CALL-64** | **Gardé** | GUEST : publish screen interdit | **403** |

**Hors incrément :** annotation collaborative sur share, remote control.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Source de vérité live | LiveKit ; PG = historique / support |
| Sync | Webhooks prioritaires ; client peut PATCH confirm |
| SCREEN_SHARE | Ligne `media_tracks` **et** `screen_shares` (métier durée) |

---

## Contrat HTTP

### CALL-60 — `GET /api/v1/calls/{id}/tracks`

`calls.track.read`. Query `active=true|false`.

### CALL-61 — `GET /api/v1/calls/{id}/screen-shares`

`calls.track.read`.

### CALL-57 — `POST /api/v1/calls/{id}/screen-shares`

`calls.call.control` (self publish). Optionnel si webhook suffit ; endpoint pour clients sans webhook delay.

### CALL-58 — `POST /api/v1/calls/{id}/screen-shares/{share_id}/stop`

Self ou HOST.

---

## Tests (D)

| Cas | Attendu |
|-----|---------|
| Track published webhook | ligne `media_tracks` active |
| Double screen | ancien `active=false` |
| GUEST publish screen | 403 |
