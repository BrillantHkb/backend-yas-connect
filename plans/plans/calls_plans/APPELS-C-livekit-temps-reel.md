# APPELS-C — LiveKit, tokens & temps réel (CALL-37 … 52)

**Produit :** YAS Connect uniquement.  
**Préalable :** **APPELS-A/B** + infra LiveKit + Redis + Channels + **[NOTIF-A](../notif_plans/NOTIF-A-in-app-push.md)** (CALL-44 `CALL_INCOMING`).  
**Attributs :** `livekit_rooms` ; Redis status/presence.  
**Models :** [code/calls_models.py](../code/calls_models.py).

**Périmètre :** émission tokens LiveKit, webhooks SFU, WS événements appel, présence salle. **Pas de persistence SDP** (`webrtc_sessions` hors MVP).

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **CALL-37** | **Gardé** | Créer room LiveKit à la création appel | `livekit_rooms` |
| **CALL-38** | **Gardé** | Token JWT LiveKit court (TTL ≤ 2 h, renew) | — |
| **CALL-39** | **Gardé** | Token scopes : publish/subscribe selon rôle | — |
| **CALL-40** | **Gardé** | Webhook `room_started` / `room_finished` | `livekit_sid`, `closed_at` |
| **CALL-41** | **Gardé** | Webhook `participant_joined` / `left` | sync sessions |
| **CALL-42** | **Gardé** | Webhook `track_published` / `unpublished` | → plan D |
| **CALL-43** | **Gardé** | WS `/ws/v1/calls/` subscribe `call_id` | — |
| **CALL-44** | **Gardé** | Push notif `CALL_INCOMING` (Notifications) | — |
| **CALL-45** | **Gardé** | Redis `call:{id}:status` | Redis |
| **CALL-46** | **Gardé** | Redis `call_presence:{room_id}` | Redis |
| **CALL-47** | **Gardé** | Fermeture room à `ENDED` | LiveKit API + `closed_at` |
| **CALL-48** | **Gardé** | Signature webhooks LiveKit (HMAC) | middleware |
| **CALL-49** | **Gardé** | Refus token si appel fermé / non participant | **403/409** |
| **CALL-50** | **Gardé** | ICE via STUN/TURN LiveKit (config ops) | — |
| **CALL-51** | **Gardé** | Logs structurés signaling (sans SDP) | logs |
| **CALL-52** | **Gardé** | Option Redis `call:{id}:signaling` TTL 15 min | Redis |

**Hors incrément :** table `webrtc_sessions` PG, mediasoup alternatif, enregistrement côté client pur.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| SFU | **LiveKit** uniquement au MVP |
| SDP/ICE | **Non** en PostgreSQL |
| Auth token | Endpoint Django → JWT LiveKit (API key serveur) |
| Webhooks | Endpoint interne `/api/v1/internal/livekit/webhook` (signature, pas JWT user) |
| WS | Un canal appels séparé de la messagerie |
| Secrets | `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` en env |

---

## Contrat HTTP

### CALL-38 — `POST /api/v1/calls/{id}/token`

`calls.token.create`.

```json
{ "device_id": "<uuid>", "can_publish": true }
```

**200** :

```json
{
  "token": "<jwt>",
  "url": "wss://livekit.example",
  "room_name": "…",
  "expires_at": "…"
}
```

Crée/refresh `call_sessions` si besoin.

### CALL-40…42 — `POST /api/v1/internal/livekit/webhook`

Pas de JWT user. Header signature LiveKit. Idempotent sur `event_id`.

### CALL-43 — WebSocket `GET /ws/v1/calls/`

JWT query/header. Client envoie `{ "action": "subscribe", "call_id": "…" }`.

Événements : ceux de A/B + `ROOM_CLOSED`, `TOKEN_REFRESH_NEEDED`.

---

## Observabilité (sans webrtc_sessions)

| Signal | Source |
|--------|--------|
| Join/leave | Webhook + `call_sessions` |
| Échec connect | Log client `last_error` → Redis signaling optionnel |
| Qualité | Plan F `call_quality_metrics` |

---

## Tests (C)

| Cas | Attendu |
|-----|---------|
| Token participant ACTIVE | 200 JWT |
| Token après ENDED | 409 |
| Webhook signature invalide | 401 |
| Subscribe WS non-membre | close 4403 |
