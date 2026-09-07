# MESSAGERIE-B — Messages (MSG-21 … 40)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MESSAGERIE-A](MESSAGERIE-A-inbox-conversations.md) + **MEDIA-A** (upload PJ, phase **3a**) + [CRYPTO-A](../crypto_plans/CRYPTO-A-cles.md) (bundles 1-to-1) + [CRYPTO-00](../crypto_plans/CRYPTO-00-modele-chiffrement.md).  
**Models :** [code/messaging_models.py](../code/messaging_models.py).

**Périmètre :** envoi, historique, édition, suppression, réponse, recherche dans un fil, types texte et média de base.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MSG-21** | **Gardé** | Historique paginé `sent_at` DESC | `messages` |
| **MSG-22** | **Gardé** | Envoi texte chiffré | `messages.encrypted_content`, `type=TEXT` |
| **MSG-23** | **Gardé** | Répondre (thread) | `parent_message_id` |
| **MSG-24** | **Gardé** | Éditer message envoyé (fenêtre 15 min configurable) | `message_edits`, `edited=true` |
| **MSG-25** | **Gardé** | Supprimer pour soi | `message_deletes` scope `SELF` |
| **MSG-26** | **Gardé** | Supprimer pour tous (auteur ou admin groupe) | scope `EVERYONE`, `deleted=true` |
| **MSG-27** | **Gardé** | Détail message (membre du fil) | lecture |
| **MSG-28** | **Gardé** | Recherche dans conversation (tags, métadonnées) | GIN `tags` ; texte = client si E2E |
| **MSG-29** | **Gardé** | Pièce jointe image/vidéo/audio/document | `media_id`, `type` adapté |
| **MSG-30** | **Gardé** | Message GIF | `type=GIF` |
| **MSG-31** | **Gardé** | Message système | `type=SYSTEM` (auto join/leave) |
| **MSG-32** | **Gardé** | Priorité / important | `priority` > 0 |
| **MSG-33** | **Gardé** | Incrément `unread_count` destinataires | `conversation_members` |
| **MSG-34** | **Gardé** | Mise à jour `last_message_at` / `last_message_id` | `conversations` |
| **MSG-35** | **Gardé** | Idempotence client `client_message_id` dans `metadata` | anti-doublon |
| **MSG-36** | **Gardé** | Refus envoi si fil `locked` (sauf OWNER/ADMIN) | `conversation_settings` |
| **MSG-37** | **Gardé** | Refus envoi si `READ_ONLY` | rôle membre |
| **MSG-38** | **Gardé** | Scan média `INFECTED` → 422 | `media_files.scan_status` |
| **MSG-39** | **Gardé** | Copier message | **client** (pas de route dédiée) |
| **MSG-40** | **Gardé** | Partager = forward ou deep-link | voir [MESSAGERIE-E](MESSAGERIE-E-contenu-enrichi.md) |

**Hors incrément :** messages planifiés, édition illimitée dans le temps.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Contenu | Pas de `content` clair serveur ; corps dans `encrypted_content` |
| Pagination messages | Keyset `(sent_at, id)` ; `limit` max 100 |
| Édition | Seul `sender_id` ; historique `message_edits.previous_encrypted_content` |
| 1-to-1 | Sender sans identité appareil → **409** `CRYPTO_KEYS_MISSING` ; pair sans bundle → **409** `PEER_KEYS_MISSING` |
| Suppression tous | Auteur ≤ 48 h OU OWNER/ADMIN du groupe |
| SYSTEM | Émis par le service (join, leave, role change) |

---

## Contrat HTTP

### MSG-21 — `GET /api/v1/conversations/{id}/messages`

`messaging.message.read`. Query : `before`, `after`, `limit`, `parent_id` (fil réponses).

### MSG-22 — `POST /api/v1/conversations/{id}/messages`

`messaging.message.send`.

```json
{
  "type": "TEXT",
  "encrypted_content": "<base64>",
  "parent_message_id": null,
  "media_id": null,
  "priority": 0,
  "tags": [],
  "client_message_id": "<uuid>"
}
```

**201** message créé. **409** si `client_message_id` dupliqué.

### MSG-24 — `PATCH /api/v1/messages/{id}`

`messaging.message.update`. Body : `encrypted_content`.

### MSG-25/26 — `DELETE /api/v1/messages/{id}`

`messaging.message.delete`. Query `scope=SELF|EVERYONE`.

### MSG-28 — `GET /api/v1/conversations/{id}/messages/search`

`q` min 2 car. sur `tags` ; mention rows si besoin.

### MSG-27 — `GET /api/v1/messages/{id}`

Détail + flags `edited`, `forwarded`, `pinned`, `deleted` (selon scope visibilité).
