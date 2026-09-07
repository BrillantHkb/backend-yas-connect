# MESSAGERIE-G — Indicateurs de saisie (MSG-99 … 104)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MESSAGERIE-D](MESSAGERIE-D-temps-reel.md), **PROF-C** (`typing_indicator_enabled`), prefs **PROF-B** (`typing_indicator`).  
**Infrastructure :** Redis (TTL), WebSocket [MESSAGERIE-D](MESSAGERIE-D-temps-reel.md).

**Périmètre MVP :** « en train d’écrire… » (MSG-99, 103, 104). Vocal / photo / « répond à… » = même mécanisme, livrables avec G.

---

## Cartographie

| ID | Statut | Comportement | Stockage |
|----|--------|--------------|----------|
| **MSG-99** | **Gardé** | « En train d’écrire… » | Redis `typing:{conv}:{user}` TTL 5s |
| **MSG-100** | **Gardé** | « Enregistre un vocal… » | `activity=VOICE` |
| **MSG-101** | **Gardé** | « Capture une image… » | `activity=CAMERA` |
| **MSG-102** | **Gardé** | « Est en train de répondre… » | `reply_to_message_id` |
| **MSG-103** | **Gardé** | Broadcast aux autres membres du fil | WS `typing.updated` |
| **MSG-104** | **Gardé** | Pas d’émission si privacy/prefs désactivés | — |

**Hors incrément :** indicateur « en ligne » (module PRES-A).

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Transport | WS uniquement (pas de REST polling) |
| Client | Envoie `typing.start` / `typing.stop` ; debounce 300 ms |
| TTL | Clé Redis expire 5 s sans refresh |
| Audience | Membres actifs du fil sauf l’émetteur |

---

## Contrat WebSocket

### Client → serveur

```json
{
  "type": "typing.start",
  "conversation_id": "<uuid>",
  "activity": "TEXT",
  "reply_to_message_id": null
}
```

`activity` : `TEXT` | `VOICE` | `CAMERA`.

```json
{ "type": "typing.stop", "conversation_id": "<uuid>" }
```

### Serveur → autres membres

```json
{
  "type": "typing.updated",
  "conversation_id": "<uuid>",
  "user_id": "<uuid>",
  "display_name": "Jean",
  "activity": "TEXT",
  "reply_to_message_id": null,
  "expires_in": 5
}
```

Vérification avant broadcast : `preferences.typing_indicator` **et** `privacy.typing_indicator_enabled` pour l’émetteur.
