# MESSAGERIE-A — Inbox & conversations (MSG-01 … 20)

**Produit :** YAS Connect uniquement.  
**Préalable :** **MESSAGERIE-R** + migrations 18 tables + **PROF-A** (avatar URL) + **PRES-A** (statut optionnel inbox) + [CRYPTO-00](../crypto_plans/CRYPTO-00-modele-chiffrement.md) (`PRIVATE` ⇒ `encrypted=true`).  
**Attributs :** [MESSAGERIE-catalogue-tables.md](../../catalogues/MESSAGERIE-catalogue-tables.md).  
**Models :** [code/messaging_models.py](../code/messaging_models.py).

**Périmètre :** inbox, création fil privé, détail, archivage, épinglage inbox, mute, liste messages épinglés dans le fil.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MSG-01** | **Gardé** | Chat 1-to-1 : `type=PRIVATE`, exactement 2 membres actifs | `conversations`, `conversation_members` |
| **MSG-02** | **Gardé** | Création ou réouverture fil privé existant (UK logique paire users) | idem |
| **MSG-03** | **Gardé** | `conversation_uuid` public pour deep-link | `conversations.conversation_uuid` |
| **MSG-04** | **Gardé** | Inbox triée `last_message_at` DESC | lecture |
| **MSG-05** | **Gardé** | Aperçu dernier message (type, auteur, date) sans déchiffrer côté serveur si E2E | `last_message_id` |
| **MSG-06** | **Gardé** | Badge `unread_count` par fil | `conversation_members.unread_count` |
| **MSG-07** | **Gardé** | Archiver pour soi | `archived_conversations` + `members.archived` |
| **MSG-08** | **Gardé** | Désarchiver | DELETE archive |
| **MSG-09** | **Gardé** | Épingler conversation dans l’inbox | `members.pinned` |
| **MSG-10** | **Gardé** | Muet (notifications) par fil | `conversation_settings.muted` |
| **MSG-11** | **Gardé** | Détail conversation + réglages perso | lecture |
| **MSG-12** | **Gardé** | Liste messages épinglés du fil | `pinned_messages` |
| **MSG-13** | **Gardé** | Conversation IA `type=AI` (fil bot) | `conversations.type=AI` |
| **MSG-14** | **Gardé** | Flag `encrypted` sur le fil (E2E) | `conversations.encrypted` |
| **MSG-15** | **Gardé** | Filtre inbox : actifs / archivés / épinglés | query |
| **MSG-16** | **Gardé** | Pagination inbox `limit` max 50 | — |
| **MSG-17** | **Gardé** | Exclure fils où seul membre actif | `active=true` |
| **MSG-18** | **Gardé** | 404 si non membre | — |
| **MSG-19** | **Gardé** | Création privée refuse si `blocked_users` | — |
| **MSG-20** | **Gardé** | Portes AUTH-F après perm | — |

**Hors incrément :** recherche globale tous fils (MSG-78), dossiers personnalisés.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Idempotence privé | `POST /conversations` body `{ "type": "PRIVATE", "participant_id": "<uuid>" }` → retourne fil existant si paire déjà ouverte |
| Deep-link | `GET /conversations/by-uuid/{conversation_uuid}` même perm que détail par id |
| Archive | N’efface pas les messages ; masque de l’inbox par défaut |
| Mute | Crée `conversation_settings` si absent (user, conversation) |
| `encrypted` | `type=PRIVATE` → `encrypted=true` obligatoire ; `GROUP`/`AI` → `false` (CRYPTO-00) |
| AI | `owner_id` = user ; second membre = service account bot (ticket infra) |

---

## Contrat HTTP

### MSG-04 — `GET /api/v1/conversations`

`required_permission = messaging.conversation.read`.

| Query | Règle |
|-------|--------|
| `archived` | `true` / `false` / omis (= false) |
| `pinned` | `true` optionnel |
| `type` | `PRIVATE` \| `GROUP` \| `AI` optionnel |
| `limit` | 1–50, défaut 20 |
| `cursor` | `last_message_at` + id (pagination keyset) |

**200** : liste `{ id, conversation_uuid, type, title, encrypted, last_message_at, unread_count, pinned, archived, muted, avatar_url, peer_summary? }`.

### MSG-02 — `POST /api/v1/conversations`

`required_permission = messaging.conversation.create`.

**Privé**

```json
{ "type": "PRIVATE", "participant_id": "<uuid>" }
```

**201** ou **200** si fil existant. **403** `USER_BLOCKED`. **404** participant inconnu/inactif.

### MSG-11 — `GET /api/v1/conversations/{id}`

Détail + `settings` { muted, pinned, role, joined_at }.

### MSG-07/08 — Archivage

- `POST /api/v1/conversations/{id}/archive` → `messaging.conversation.archive`
- `DELETE /api/v1/conversations/{id}/archive` → désarchive

### MSG-09 — `PATCH /api/v1/conversations/{id}/inbox`

```json
{ "pinned": true }
```

`messaging.conversation.read` (préférence perso membre).

### MSG-10 — `PATCH /api/v1/conversations/{id}/settings`

```json
{ "muted": true }
```

Upsert `conversation_settings`.

### MSG-12 — `GET /api/v1/conversations/{id}/pinned-messages`

Liste `{ message_id, pinned_at, pinned_by }` — contenu via MSG-B lecture message.
