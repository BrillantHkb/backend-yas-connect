# MESSAGERIE-D — Temps réel & accusés (MSG-59 … 72)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MESSAGERIE-B](MESSAGERIE-B-messages.md), **AUTH-E** (devices), **PRES-A** (Redis), **[NOTIF-A](../notif_plans/NOTIF-A-in-app-push.md)** (MSG-67 push).  
**Models :** [code/messaging_models.py](../code/messaging_models.py).

**Périmètre :** WebSocket, accusés envoyé/livré/lu, sync multi-appareils, file hors ligne côté client, catch-up REST.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MSG-59** | **Gardé** | Diffusion instantanée nouveau message | WS `message.created` |
| **MSG-60** | **Gardé** | Accusé envoyé (serveur a persisté) | `sent_at` + event WS |
| **MSG-61** | **Gardé** | Accusé livré par device | `message_reads.delivered_at` |
| **MSG-62** | **Gardé** | Accusé lu | `message_reads.read_at` |
| **MSG-63** | **Gardé** | Heure lecture par user/device | idem |
| **MSG-64** | **Gardé** | Respect privacy accusés (PROF-C) | pas de `read_at` si désactivé |
| **MSG-65** | **Gardé** | Sync multi-appareils | UK `(message, user, device)` |
| **MSG-66** | **Gardé** | `last_read_message_id` + reset unread | `conversation_members` |
| **MSG-67** | **Gardé** | Notification push nouveau message | module Notifications |
| **MSG-68** | **Gardé** | WS authentifié JWT (même TTL access) | Channels |
| **MSG-69** | **Gardé** | Reconnexion + resubscribe fils | client |
| **MSG-70** | **Gardé** | Catch-up REST après coupure | `GET messages?after=` |
| **MSG-71** | **Gardé** | Événements edit/delete/reaction en temps réel | WS |
| **MSG-72** | **Gardé** | Heartbeat WS (idle disconnect 5 min) | — |

**Hors incrément :** présence « en ligne dans le chat » (réutilise PRES-A).

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Endpoint WS | `/ws/v1/messaging/` |
| Auth WS | Query `?token=` access JWT ou header (phase 3 : query) |
| Rooms | `conversation:{id}` — join si membre actif |
| Livré | Premier device du destinataire qui ACK |
| Lu | Tous devices ou policy « lu si un device » (défaut : par device, agrégé UI) |
| Offline | Client queue locale ; serveur idempotent via `client_message_id` |

---

## Contrat WebSocket

### Connexion

Client envoie après open :

```json
{ "type": "subscribe", "conversation_ids": ["<uuid>", "..."] }
```

Serveur :

```json
{ "type": "message.created", "conversation_id": "...", "message": { ... } }
{ "type": "message.updated", ... }
{ "type": "message.deleted", ... }
{ "type": "reaction.updated", ... }
{ "type": "receipt.updated", "message_id": "...", "user_id": "...", "delivered_at": "...", "read_at": "..." }
```

### REST accusés

| Route | Perm | Body |
|-------|------|------|
| `POST /api/v1/messages/{id}/delivered` | `messaging.receipt.update` | `{ "device_id": "..." }` |
| `POST /api/v1/messages/{id}/read` | `messaging.receipt.update` | `{ "device_id": "..." }` |
| `POST /api/v1/conversations/{id}/read` | `messaging.receipt.update` | `{ "last_read_message_id": "..." }` |

Marque tous les messages ≤ id comme lus pour le user courant.
