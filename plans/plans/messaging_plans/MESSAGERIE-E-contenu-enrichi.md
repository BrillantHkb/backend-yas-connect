# MESSAGERIE-E — Contenu enrichi (MSG-73 … 88)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MESSAGERIE-B](MESSAGERIE-B-messages.md), **MEDIA-A**, [CRYPTO-00](../crypto_plans/CRYPTO-00-modele-chiffrement.md).  
**Models :** [code/messaging_models.py](../code/messaging_models.py).

**Périmètre MVP :** réactions emoji, transfert, favoris, sondages.  
**Après le MVP :** épingles dans le fil, mentions, localisation, type IA. (Appel `type=CALL` = module Appels.)

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MSG-73** | **Gardé** | Réaction emoji | `message_reactions` UK (message,user,emoji) |
| **MSG-74** | **Gardé** | Retirer réaction | DELETE |
| **MSG-75** | **Gardé** | Transférer message | `message_forwards` + nouveau message |
| **MSG-76** | **Gardé** | Partager (forward + lien) | `conversation_uuid` |
| **MSG-77** | **Gardé** | Épingler message dans fil | `pinned_messages` |
| **MSG-78** | **Gardé** | Désépingler | DELETE pin |
| **MSG-79** | **Gardé** | Signet / favori avec note | `message_bookmarks` |
| **MSG-80** | **Gardé** | Liste signets user | `GET /me/message-bookmarks` |
| **MSG-81** | **Gardé** | Sondage | `message_polls`, `poll_options`, `type=POLL` |
| **MSG-82** | **Gardé** | Vote simple / multiple | `poll_votes` |
| **MSG-83** | **Gardé** | Clôturer sondage | `closed_at` |
| **MSG-84** | **Gardé** | Mention @user | `message_mentions` + snapshot `mentions` jsonb |
| **MSG-85** | **Gardé** | Hashtags | `messages.tags` |
| **MSG-86** | **Gardé** | Localisation | `type=LOCATION` ; GPS dans `encrypted_content` (pas de colonne) |
| **MSG-87** | **Gardé** | Référence appel | `type=CALL`, `call_id` sans FK — voir [APPELS-A](../calls_plans/APPELS-A-cycle-vie.md) |
| **MSG-88** | **Gardé** | Message IA | `ai_generated=true`, fil `type=AI` |

**Hors incrément :** stickers pack, GIF tenor API.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Forward | Crée message dans fil cible ; `forwarded=true` |
| Poll | Une option = un vote sauf `multiple_choices=true` |
| Mentions | Notif push si `allow_mentions` OK |
| Location | WGS84 dans le blob ; `latitude`/`longitude` JSON clair → **400** `FIELD_FORBIDDEN` |

---

## Contrat HTTP

### Réactions

- `POST /api/v1/messages/{id}/reactions` — `{ "emoji": "👍" }` — `messaging.message.react`
- `DELETE /api/v1/messages/{id}/reactions` — query `emoji` — idem

### Forward

`POST /api/v1/messages/{id}/forward` — `{ "conversation_id": "..." }` — `messaging.message.forward`

### Épingles

- `POST /api/v1/conversations/{id}/pins` — `{ "message_id": "..." }`
- `DELETE /api/v1/conversations/{id}/pins/{message_id}`

### Signets

- `POST /api/v1/messages/{id}/bookmarks` — `{ "note": "" }`
- `DELETE /api/v1/messages/{id}/bookmarks`
- `GET /api/v1/me/message-bookmarks`

### Sondage

Envoi via `POST .../messages` :

```json
{
  "type": "POLL",
  "encrypted_content": null,
  "poll": {
    "question": "Qui vient ?",
    "multiple_choices": false,
    "options": ["Oui", "Non"]
  }
}
```

- `POST /api/v1/polls/{id}/votes` — `{ "option_ids": ["..."] }` — `messaging.poll.vote`
- `POST /api/v1/polls/{id}/close` — créateur ou admin groupe

### Localisation

```json
{ "type": "LOCATION", "encrypted_content": "<base64>" }
```

Pas de `latitude` / `longitude` en clair (CRYPTO-00). Tracking live hors incrément.
