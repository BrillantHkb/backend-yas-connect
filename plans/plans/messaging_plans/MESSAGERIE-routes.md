# Messagerie — Catalogue des routes planifiées

**Produit :** YAS Connect uniquement.  
**Source :** [MESSAGERIE-R](MESSAGERIE-R-roles-permissions.md) · [A](MESSAGERIE-A-inbox-conversations.md) … [G](MESSAGERIE-G-indicateurs-saisie.md).  
**Préfixe HTTP :** `/api/v1` · **WebSocket :** `/ws/v1/messaging/`.  
**Dépendances :** IAM (JWT, devices, privacy), Médias (`media_files`), Notifications (push), Redis, [CRYPTO-A](../crypto_plans/CRYPTO-A-cles.md).

**Permission** = `required_permission` (`HasPermission`).  
**Rôles** = USER / ADMIN après `seed_messaging` + AUTH-R.

**52 routes HTTP** + **1 WebSocket**. Un **ADMIN** a aussi toutes les routes Collaborateur + modération.

**Hors tableau :** jobs (expiration groupe temporaire), `GET /health`, OpenAPI, événements WS typing (plan G).

---

## Pourquoi cet ordre

| Vague | Plan | Pourquoi |
|-------|------|----------|
| **0** | MESSAGERIE-R | Seed `messaging.*` avant toute vue |
| **A** | MESSAGERIE-A | Inbox avant messages |
| **B** | MESSAGERIE-B | CRUD messages |
| **C** | MESSAGERIE-C | Groupes après privé stable |
| **D** | MESSAGERIE-D | WS + accusés après persistance |
| **E** | MESSAGERIE-E | Enrichissements |
| **F** | MESSAGERIE-F | Blocage / modération |
| **G** | MESSAGERIE-G | Typing Redis (WS seulement) |

Portes **AUTH-F** (CGU + wizard) sur toutes les routes JWT.

---

## Vague 0 — RBAC (MESSAGERIE-R)

Hors HTTP : `python manage.py seed_messaging` (18 permissions).

---

## Vague A — Inbox & conversations (MESSAGERIE-A)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 1 | `GET` | `/api/v1/conversations` | Collaborateur | `messaging.conversation.read` | USER, ADMIN | A-04 | Inbox | Keyset `last_message_at`. Filtres archived/pinned/type. |
| 2 | `POST` | `/api/v1/conversations` | Collaborateur | `messaging.conversation.create` | USER, ADMIN | A-02 | Créer privé ou groupe | Body `type` + `participant_id` ou `member_ids`. |
| 3 | `GET` | `/api/v1/conversations/{id}` | Collaborateur | `messaging.conversation.read` | USER, ADMIN | A-11 | Détail fil | 404 si non membre. |
| 4 | `GET` | `/api/v1/conversations/by-uuid/{uuid}` | Collaborateur | `messaging.conversation.read` | USER, ADMIN | A-03 | Deep-link | Même payload que #3. |
| 5 | `POST` | `/api/v1/conversations/{id}/archive` | Collaborateur | `messaging.conversation.archive` | USER, ADMIN | A-07 | Archiver | Upsert `archived_conversations`. |
| 6 | `DELETE` | `/api/v1/conversations/{id}/archive` | Collaborateur | `messaging.conversation.archive` | USER, ADMIN | A-08 | Désarchiver | |
| 7 | `PATCH` | `/api/v1/conversations/{id}/inbox` | Collaborateur | `messaging.conversation.read` | USER, ADMIN | A-09 | Épingler inbox | `{ "pinned": true }`. |
| 8 | `PATCH` | `/api/v1/conversations/{id}/settings` | Collaborateur | `messaging.conversation.read` | USER, ADMIN | A-10 | Muet | `{ "muted": true }`. |
| 9 | `GET` | `/api/v1/conversations/{id}/pinned-messages` | Collaborateur | `messaging.conversation.read` | USER, ADMIN | A-12 | Messages épinglés | |

---

## Vague B — Messages (MESSAGERIE-B)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 10 | `GET` | `/api/v1/conversations/{id}/messages` | Collaborateur | `messaging.message.read` | USER, ADMIN | B-21 | Historique | Keyset `sent_at`. |
| 11 | `POST` | `/api/v1/conversations/{id}/messages` | Collaborateur | `messaging.message.send` | USER, ADMIN | B-22 | Envoyer | `client_message_id` idempotent. |
| 12 | `GET` | `/api/v1/messages/{id}` | Collaborateur | `messaging.message.read` | USER, ADMIN | B-27 | Détail message | |
| 13 | `PATCH` | `/api/v1/messages/{id}` | Collaborateur | `messaging.message.update` | USER, ADMIN | B-24 | Éditer | Auteur seul ; fenêtre 15 min. |
| 14 | `DELETE` | `/api/v1/messages/{id}` | Collaborateur | `messaging.message.delete` | USER, ADMIN | B-25/26 | Supprimer | Query `scope=SELF\|EVERYONE`. |
| 15 | `GET` | `/api/v1/conversations/{id}/messages/search` | Collaborateur | `messaging.message.read` | USER, ADMIN | B-28 | Recherche fil | `q` sur tags. |

---

## Vague C — Groupes (MESSAGERIE-C)

`urls` : routes `members` avant `{user_id}` si conflit.

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 16 | `PATCH` | `/api/v1/conversations/{id}` | Collaborateur | `messaging.conversation.update` | USER, ADMIN | C-42/43 | Titre, description, avatar | GROUP seulement ; OWNER/ADMIN. |
| 17 | `PATCH` | `/api/v1/conversations/{id}/group-settings` | Collaborateur | `messaging.conversation.update` | USER, ADMIN | C-50–53 | Visibilité, locked, max | |
| 18 | `GET` | `/api/v1/conversations/{id}/members` | Collaborateur | `messaging.member.read` | USER, ADMIN | C-44 | Liste membres | Actifs par défaut. |
| 19 | `POST` | `/api/v1/conversations/{id}/members` | Collaborateur | `messaging.member.manage` | USER, ADMIN | C-44 | Ajouter | `allow_group_invites`. |
| 20 | `PATCH` | `/api/v1/conversations/{id}/members/{user_id}` | Collaborateur | `messaging.member.manage` | USER, ADMIN | C-47/48 | Rôle, pseudo | Pas retirer dernier OWNER. |
| 21 | `DELETE` | `/api/v1/conversations/{id}/members/{user_id}` | Collaborateur | `messaging.member.manage` | USER, ADMIN | C-45 | Retirer | |
| 22 | `POST` | `/api/v1/conversations/{id}/leave` | Collaborateur | `messaging.conversation.read` | USER, ADMIN | C-46 | Quitter groupe | OWNER doit transférer avant. |

---

## Vague D — Temps réel & accusés (MESSAGERIE-D)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 23 | `POST` | `/api/v1/messages/{id}/delivered` | Collaborateur | `messaging.receipt.update` | USER, ADMIN | D-61 | Accusé livré | Par device. |
| 24 | `POST` | `/api/v1/messages/{id}/read` | Collaborateur | `messaging.receipt.update` | USER, ADMIN | D-62 | Accusé lu | Privacy accusés. |
| 25 | `POST` | `/api/v1/conversations/{id}/read` | Collaborateur | `messaging.receipt.update` | USER, ADMIN | D-66 | Tout lire jusqu’à id | Reset `unread_count`. |
| 26 | `WS` | `/ws/v1/messaging/` | Collaborateur | JWT + membre fil | USER, ADMIN | D-59–72 | Temps réel | Subscribe par `conversation_id`. |

---

## Vague E — Contenu enrichi (MESSAGERIE-E)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 27 | `POST` | `/api/v1/messages/{id}/reactions` | Collaborateur | `messaging.message.react` | USER, ADMIN | E-73 | Ajouter emoji | |
| 28 | `DELETE` | `/api/v1/messages/{id}/reactions` | Collaborateur | `messaging.message.react` | USER, ADMIN | E-74 | Retirer | Query `emoji`. |
| 29 | `POST` | `/api/v1/messages/{id}/forward` | Collaborateur | `messaging.message.forward` | USER, ADMIN | E-75 | Transférer | |
| 30 | `POST` | `/api/v1/conversations/{id}/pins` | Collaborateur | `messaging.message.update` | USER, ADMIN | E-77 | Épingler message | OWNER/ADMIN/MEMBER selon policy. |
| 31 | `DELETE` | `/api/v1/conversations/{id}/pins/{message_id}` | Collaborateur | `messaging.message.update` | USER, ADMIN | E-78 | Désépingler | |
| 32 | `POST` | `/api/v1/messages/{id}/bookmarks` | Collaborateur | `messaging.bookmark.manage` | USER, ADMIN | E-79 | Signet | |
| 33 | `DELETE` | `/api/v1/messages/{id}/bookmarks` | Collaborateur | `messaging.bookmark.manage` | USER, ADMIN | E-79 | Retirer signet | |
| 34 | `GET` | `/api/v1/me/message-bookmarks` | Collaborateur | `messaging.bookmark.manage` | USER, ADMIN | E-80 | Liste signets | |
| 35 | `POST` | `/api/v1/polls/{id}/votes` | Collaborateur | `messaging.poll.vote` | USER, ADMIN | E-82 | Voter | |
| 36 | `POST` | `/api/v1/polls/{id}/close` | Collaborateur | `messaging.poll.vote` | USER, ADMIN | E-83 | Clôturer sondage | Créateur ou admin groupe. |

---

## Vague F — Blocage & modération (MESSAGERIE-F)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 37 | `GET` | `/api/v1/me/blocked-users` | Collaborateur | `messaging.block.manage` | USER, ADMIN | F-91 | Liste bloqués | |
| 38 | `POST` | `/api/v1/me/blocked-users` | Collaborateur | `messaging.block.manage` | USER, ADMIN | F-89 | Bloquer | |
| 39 | `DELETE` | `/api/v1/me/blocked-users/{user_id}` | Collaborateur | `messaging.block.manage` | USER, ADMIN | F-90 | Débloquer | |
| 40 | `POST` | `/api/v1/messages/{id}/reports` | Collaborateur | `messaging.report.create` | USER, ADMIN | F-93 | Signaler | |
| 41 | `GET` | `/api/v1/admin/reported-messages` | Admin | `messaging.report.review` | ADMIN | F-95 | File modération | `?status=PENDING`. |
| 42 | `PATCH` | `/api/v1/admin/reported-messages/{id}` | Admin | `messaging.report.review` | ADMIN | F-96 | Traiter | |

---

## Index par acteur

| Acteur | Combien | Qui |
|--------|---------|-----|
| **Collaborateur** | 40 | Inbox, messages, groupes, accusés, enrichi, blocage |
| **Admin** | +2 | Modération signalements (#41–42) |
| **WebSocket** | 1 | Temps réel + typing (plan G) |

Upload médias = module [Médias](../media_plans/MEDIA-routes.md) (`POST /media/...`), référencé par `media_id` à l’envoi message.

---

## Mapping fonctionnalités produit → routes

| Fonctionnalité produit (module 3) | Routes / plan |
|-----------------------------------|---------------|
| Chat 1-to-1, création, historique | #2, #10–12, A, B |
| Suppression / édition / réponse | #13–14, B |
| Réactions, copier, transférer, partager, important, épingler | #27–31, E |
| Recherche conversation, archiver, bloquer, signaler | #5–6, #15, #37–40 |
| Groupes (CRUD, membres, admins, règles, annonce, public/privé) | #2, #16–22, C |
| Temps réel, accusés, sync, offline | #23–26, D |
| Indicateurs saisie | WS plan G |
