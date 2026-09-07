# APPELS-B — Participants & sessions (CALL-21 … 36)

**Produit :** YAS Connect uniquement.  
**Préalable :** **APPELS-A**.  
**Attributs :** `call_participants`, `call_sessions`.  
**Models :** [code/calls_models.py](../code/calls_models.py).

**Périmètre :** qui est dans l’appel (métier) vs comment (device / réseau) ; mute, caméra, invite, kick, multi-device.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **CALL-21** | **Gardé** | Liste participants actifs | lecture |
| **CALL-22** | **Gardé** | Inviter users (HOST/MOD) tant que `ACTIVE`/`RINGING` | `call_participants` |
| **CALL-23** | **Gardé** | Éjecter participant | `left_at` |
| **CALL-24** | **Gardé** | Changer rôle (`HOST`, `MODERATOR`, `PARTICIPANT`, `GUEST`) | `role` |
| **CALL-25** | **Gardé** | Mute / unmute self | `muted` |
| **CALL-26** | **Gardé** | Mute forcé par HOST/MOD | `muted` |
| **CALL-27** | **Gardé** | Caméra on/off self | `camera_enabled` |
| **CALL-28** | **Gardé** | Join session technique (device) | `call_sessions` |
| **CALL-29** | **Gardé** | Leave / disconnect session | `disconnected_at` |
| **CALL-30** | **Gardé** | Multi-device : 1 participant, N sessions | — |
| **CALL-31** | **Gardé** | Capturer `ip_address`, `network_type` au join | session |
| **CALL-32** | **Gardé** | Reconnexion : nouvelle session sans `left_at` sur participant | session |
| **CALL-33** | **Gardé** | UK `(call_id, user_id)` participants | contrainte |
| **CALL-34** | **Gardé** | Dernier HOST : transfert obligatoire avant leave | — |
| **CALL-35** | **Gardé** | Présence Redis `call_presence:{room_id}` | Redis |
| **CALL-36** | **Gardé** | WS `PARTICIPANT_JOINED` / `LEFT` / `MUTED` / `CAMERA` | — |

**Hors incrément :** lobby / waiting room, raise hand, breakout rooms.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Participant vs session | Métier = `call_participants` ; technique = `call_sessions` |
| Drop réseau | Ne pas `ENDED` l’appel ; clôturer ou retry la session (TTL reconnect) |
| Mute forcé | HOST/MOD seulement ; client sync via LiveKit + WS |
| Invite | Respect `allow_calls` + `max_participants` + non bloqué |
| Guest | `GUEST` = lecture audio/vidéo limitée (pas d’enregistrement) |

---

## Contrat HTTP

### CALL-21 — `GET /api/v1/calls/{id}/participants`

`calls.participant.read`.

### CALL-22 — `POST /api/v1/calls/{id}/participants`

`calls.participant.manage`. Body `{ "user_ids": ["…"] }`.

### CALL-23 — `DELETE /api/v1/calls/{id}/participants/{user_id}`

Kick. HOST/MOD. Self-leave via `POST …/leave`.

### CALL-24 — `PATCH /api/v1/calls/{id}/participants/{user_id}`

`{ "role": "MODERATOR" }`.

### CALL-25/27 — `PATCH /api/v1/calls/{id}/me`

`calls.call.control`. `{ "muted": true, "camera_enabled": false }`.

### CALL-28 — `POST /api/v1/calls/{id}/sessions`

`calls.session.manage`.

```json
{
  "device_id": "<uuid>",
  "network_type": "WIFI",
  "connection_id": "lk-…"
}
```

**201** session. IP prise côté serveur.

### CALL-29 — `POST /api/v1/calls/{id}/sessions/{session_id}/disconnect`

Pose `disconnected_at`.

### CALL- leave — `POST /api/v1/calls/{id}/leave`

Pose `left_at` ; si plus personne ACTIVE → enchaîne APPELS-A end.

---

## Tests (B)

| Cas | Attendu |
|-----|---------|
| Invite au-delà max | 409 `ROOM_FULL` |
| Mute self | 200 + WS |
| 2 devices même user | 1 participant, 2 sessions |
| Kick non-HOST | 403 |
