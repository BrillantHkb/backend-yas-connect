# Jour 25 — MESSAGERIE-R + A + B (inbox, conversations, messages 1-to-1)

**Statut :** clos (2026-09-16).
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.
**Préalable :** jours 0–24 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 24](00-jour-24-crypto-r-a.md)). CRYPTO-00 (jour 21) et CRYPTO-A (jour 24) figés : le sender doit avoir une identité (`require_sender_identity`), et ce jour ajoute une vérification symétrique côté destinataire.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §7 — *messagerie 1-to-1*) :


| Fonction MVP                              | Ticket                   | Statut             |
| ----------------------------------------- | ------------------------ | ------------------ |
| Bundles de clés Signal (par appareil)     | CRYPTO-R + CRYPTO-A      | **fait** (jour 24) |
| **Inbox, conversations, messages 1-to-1** | **MESSAGERIE-R + A + B** | **ce jour**        |
| Groupes + temps réel                      | MESSAGERIE-C, D          | jour 26            |


**À quoi ça sert (MVP) :** premier jour où un utilisateur peut réellement **discuter**. CRYPTO-A (jour 24) a livré le socle X3DH (bundles), NOTIF-A (jour 23) le canal d'alerte, MEDIA-A (jour 22) le stockage de pièces jointes — ce jour les assemble : créer/ouvrir un fil privé, voir son inbox, envoyer/lire/éditer/supprimer/rechercher des messages **1-to-1 chiffrés E2E** (le serveur ne voit jamais le texte en clair, conformément à CRYPTO-00). Sans ce jour, `APPELS-`* (jour 29+) n'a pas de fil où poser un message `type=CALL`/`SYSTEM`, et `MESSAGERIE-C/D` (jour 26) n'ont rien à étendre.

**Plan métier (code à coller) :** [MESSAGERIE-R-roles-permissions.md](messaging_plans/MESSAGERIE-R-roles-permissions.md) (MSG-R01…R05) + [MESSAGERIE-A-inbox-conversations.md](messaging_plans/MESSAGERIE-A-inbox-conversations.md) (MSG-01…20) + [MESSAGERIE-B-messages.md](messaging_plans/MESSAGERIE-B-messages.md) (MSG-21…40, **hors** MSG-29/30/38 pièces jointes avancées et sondages — voir §0). Modèles : [code/messaging_models.py](code/messaging_models.py) (**18 tables**, toutes créées ce jour).
Chemins lab = ce fichier (nouvelle app `apps/messaging/`).

**Déjà en base / code :**

- `apps.crypto` (jour 24) : `require_sender_identity(device)` (409 `CRYPTO_KEYS_MISSING`) déjà écrit et testé comme hook — ce jour l'appelle enfin depuis une vraie route (`POST .../messages`).
- `apps.media` (jour 22) : `upload_service.get_own_media_or_404(user, pk)` réutilisable tel quel pour valider un `media_id` de pièce jointe (scope = fichiers de l'expéditeur uniquement).
- `apps.notifications` (jour 23) : `emit()` déjà générique (`type_`, `title`, `body`, `payload`, `collapse_key`) — prêt à recevoir `MESSAGE_NEW`/`MESSAGE_MENTION` (hooks déjà réservés dans le docstring NOTIF-A, jamais appelés faute de Messagerie).
- `User` (IAM, PROF-C) : `allow_mentions`, `allow_group_invites`, `read_receipts_enabled`, `typing_indicator_enabled` déjà en base (`apps/iam/models.py`).
- `apps.iam.services.device_service.current_device(request)` : source de vérité « appareil courant » (jamais un champ du body), déjà promue en fonction publique (CRYPTO-A).

**Pas encore :** l'app `apps.messaging` **n'existe pas du tout** (3ᵉ fois après `apps.notifications` et `apps.crypto` qu'un jour crée une app de zéro). Aucun compte de service « bot IA » n'existe (ticket infra non fait) : `type=AI` reste hors scope. Aucune gestion de membres de groupe n'existe (jour 26) : `type=GROUP` reste hors scope. Le WebSocket temps réel n'existe pas (jour 26, MESSAGERIE-D) : accusés livré/lu, typing sont hors scope.

**Objectif du jour :**

1. Créer l'app `apps/messaging/` (18 modèles, coller [code/messaging_models.py](code/messaging_models.py) tel quel), migration `0001_initial`.
2. **MESSAGERIE-R** : 18 permissions `messaging.`* dans `rbac_catalog.py` (17 self + 1 admin) — seedées en bloc comme AUTH-R/MEDIA-R/NOTIF-R/CRYPTO-R, même si seules 7 sont branchées à une route ce jour (le reste sert C/D/E/F, jours 26-27).
3. **MESSAGERIE-A** : 9 routes — inbox, création/réouverture fil privé, détail, deep-link, archive/désarchive, épingler inbox, muet, messages épinglés du fil.
4. **MESSAGERIE-B** : 6 routes — historique, envoi (texte + PJ simple), détail, édition (fenêtre 15 min), suppression (SELF/EVERYONE), recherche par tags.
5. Delta `apps/crypto/services/key_service.py` : `require_peer_ready(target_user)` — vérification d'existence (pas de consommation d'OTPK) pour la garde `PEER_KEYS_MISSING` à l'envoi (§0).
6. Ne rien casser : CRYPTO-A (bundles, hooks), NOTIF-A, MEDIA-A, tout le reste.

**Hors jour 25 :** `type=GROUP`/`AI` (création, membres, rôles — jour 26 MESSAGERIE-C) ; WebSocket temps réel, accusés livré/lu (jour 26 MESSAGERIE-D) ; réactions, transfert, épinglage de message, signets, sondages (jour 27 MESSAGERIE-E) ; blocage/signalement (jour 27 MESSAGERIE-F, la table `blocked_users` existe déjà en base mais aucune route ne la peuple ce jour — testée directement par l'ORM) ; indicateurs de saisie (jour 27 MESSAGERIE-G) ; messages `type=GIF`/`LOCATION`/`POLL`/`CALL`/`AI` (aucun producteur encore) ; `emit()` réellement branché sur l'envoi de message (§0, corrigé en hook direct cette fois — pas différé comme NOTIF-A/CRYPTO-A).

---



## 0. Corrections apportées au plan métier (avant de coder)


| Écart trouvé                                                                                                                                                        | Correction                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| MESSAGERIE-R dit « Commande `python manage.py seed_messaging` »                                                                                                     | Même correction que AUTH-R/MEDIA-R/NOTIF-R/CRYPTO-R : 18 codes ajoutés à `rbac_catalog.py`, pas de nouvelle commande.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| MESSAGERIE-B (MSG-21…40) inclut PJ image/vidéo/audio/document (MSG-29), GIF (MSG-30), scan `INFECTED`→422 (MSG-38), messages `SYSTEM` (MSG-31), `priority` (MSG-32) | Gardés en partie : un `media_id` **simple** (déjà scanné, `get_own_media_or_404`) est accepté à l'envoi avec le `type` calculé depuis `media.media_type` (§3.2) et **422** si `scan_status=INFECTED` — mais **pas** de galerie/album, pas de GIF picker, pas de génération de `SYSTEM` (aucun événement join/leave possible sans groupes). `priority` accepté tel quel (champ simple, pas de logique métier supplémentaire ce jour).                                                                                                                                                                                           |
| MESSAGERIE-A dit MSG-13 « conversation IA `type=AI` » gardé                                                                                                         | **Différé** : `owner_id=user` + « second membre = service account bot (ticket infra) » suppose un compte système qui n'existe pas. `POST /conversations` avec `type=AI` → **400** `VALIDATION_ERROR` (`extra.field="type"`) ce jour. Prêt dès que le ticket infra du bot existe.                                                                                                                                                                                                                                                                                                                                               |
| `POST /conversations` (routes.md) : « Body `type` + `participant_id` **ou** `member_ids` » (sous-entend GROUP possible ce jour)                                     | Le calendrier MVP situe explicitement les groupes au jour 26 (MESSAGERIE-C, gestion de membres). `type=GROUP` sans route de membres n'a aucun sens opérationnel → **400** `VALIDATION_ERROR` ce jour. Seul `type=PRIVATE` (+ `participant_id`) est accepté.                                                                                                                                                                                                                                                                                                                                                                    |
| MESSAGERIE-B décisions : « pair sans bundle → 409 `PEER_KEYS_MISSING` » à l'envoi de message                                                                        | Appeler `key_service.get_bundles()` à **chaque envoi** consommerait une OTPK à **chaque message** — contresens total (les bundles ne se consomment qu'à l'amorçage X3DH, côté client, via `GET /crypto/users/{id}/bundles`, jour 24). Nouvelle fonction non consommatrice `apps/crypto/services/key_service.py::require_peer_ready(target_user)` : vérifie l'**existence** d'au moins un appareil `IdentityKey` + `SignedPreKey` chez le destinataire, lève `PEER_KEYS_MISSING` sinon, **sans toucher aux OTPK**.                                                                                                              |
| MESSAGERIE-A pagination inbox « keyset `last_message_at` + id » ; MESSAGERIE-B « keyset `(sent_at, id)` »                                                           | Même simplification qu'à NOTIF-A (`list_inbox`) : curseur `before` (timestamp) + `limit+1` trick pour savoir s'il reste une page, pas de curseur composite encodé. Suffisant tant qu'il n'y a pas d'égalités de timestamp à la microseconde près en pratique lab.                                                                                                                                                                                                                                                                                                                                                              |
| MESSAGERIE-B « Recherche `q` sur `tags` »                                                                                                                           | Le contenu (`encrypted_content`) est E2E, le serveur ne peut indexer que ce que le client expose volontairement dans `tags` (JSON liste de chaînes, non sensible, fourni par le client à l'envoi). Recherche = `tags__icontains=q` (substring simple sur la représentation JSON), pas de full-text ranking. Documenté comme choix pragmatique lab, pas une vraie recherche.                                                                                                                                                                                                                                                    |
| `emit()` (NOTIF-A) réservait des hooks `MESSAGE_NEW`/`MESSAGE_MENTION` non branchés faute de Messagerie                                                             | **Branchés ce jour** (contrairement à CRY-10/AI qui restent différés) : `POST .../messages` appelle `emit()` pour chaque **autre** membre actif du fil, titre/corps **génériques** (jamais le contenu déchiffré — cohérent avec la discussion E2E notifications de la session précédente), `collapse_key=f"message:{conversation_id}"`. Mentions (`MESSAGE_MENTION`) : seulement si `allow_mentions=true` chez le mentionné (MSG-R05) — champ `mentions` du body accepté et persisté (`MessageMention`), mais la résolution `@pseudo → user_id` reste **côté client** (pas de parsing serveur de texte, le texte est chiffré). |
| MESSAGERIE-B « suppression tous : auteur ≤48h OU OWNER/ADMIN du groupe »                                                                                            | Seul `PRIVATE` existe ce jour → la clause OWNER/ADMIN groupe ne peut jamais s'appliquer en pratique ; codée quand même (générique, lit `ConversationMember.role`) pour ne pas être à refaire au jour 26.                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Table `blocked_users` (MSG-19, « refus création si `blocked_users` »)                                                                                               | Aucune route ne peuple cette table ce jour (MESSAGERIE-F, jour 27) — la vérification est codée et **testée en créant la ligne directement par l'ORM** (comme `Device` dans les tests CRYPTO-A), pas via HTTP.                                                                                                                                                                                                                                                                                                                                                                                                                  |




---



## Pourquoi ce jour (après CRYPTO-A, avant MESSAGERIE-C/D)

CRYPTO-A (jour 24) a livré le socle de clés mais **rien ne le consomme encore** : `require_sender_identity` n'était appelé par aucune route, `get_bundles` n'était appelé que par le client directement. Ce jour est le premier **vrai consommateur serveur** de CRYPTO-A, exactement comme NOTIF-A (jour 23) attendait Messagerie/Appels pour ses hooks `MESSAGE_NEW`/`CALL_`* — sauf que cette fois le hook `MESSAGE_NEW` **peut** être branché immédiatement (contrairement à `CALL_`*, toujours hors scope). Construire l'inbox + les messages avant les groupes (jour 26) permet de stabiliser le cas 1-to-1 (le plus simple, le plus utilisé) avant d'ajouter la complexité multi-membres.

```text
JWT + HasPermission + portes AUTH-F. Appareil = request.auth.session.device_id (jamais le body).

Vague A — Inbox & conversations
    GET    /conversations                          messaging.conversation.read
    POST   /conversations                           messaging.conversation.create
    GET    /conversations/{id}                       messaging.conversation.read
    GET    /conversations/by-uuid/{uuid}              messaging.conversation.read
    POST   /conversations/{id}/archive                messaging.conversation.archive
    DELETE /conversations/{id}/archive                messaging.conversation.archive
    PATCH  /conversations/{id}/inbox                  messaging.conversation.read
    PATCH  /conversations/{id}/settings               messaging.conversation.read
    GET    /conversations/{id}/pinned-messages         messaging.conversation.read

Vague B — Messages
    GET    /conversations/{id}/messages               messaging.message.read
    POST   /conversations/{id}/messages                messaging.message.send
    GET    /messages/{id}                              messaging.message.read
    PATCH  /messages/{id}                              messaging.message.update
    DELETE /messages/{id}                              messaging.message.delete
    GET    /conversations/{id}/messages/search          messaging.message.read

Delta CRYPTO-A (hook consommé, pas différé)
    require_sender_identity(device)   → 409 CRYPTO_KEYS_MISSING (envoi)
    require_peer_ready(target_user)   → 409 PEER_KEYS_MISSING (envoi, nouveau, non consommateur)

Hors jour 25 (table/service absent)
    GROUP/AI, membres, rôles          → jour 26 MESSAGERIE-C
    WS, accusés livré/lu               → jour 26 MESSAGERIE-D
    réactions/transfert/épingle msg/signets/sondages → jour 27 MESSAGERIE-E
    blocage/signalement (routes)       → jour 27 MESSAGERIE-F
    typing                             → jour 27 MESSAGERIE-G
```

---



## Paliers (figés pour ce jour)


| Sujet                           | Choix jour 25                                                                                                                                                                                                         | Plus tard                                                       |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Nouvelle app                    | `apps/messaging` créée ce jour, migration `0001_initial`, **18 tables** (toutes, même celles non utilisées avant C/D/E/F)                                                                                             | —                                                               |
| Type conversation créable       | `PRIVATE` **uniquement** ce jour (`GROUP`/`AI` → 400 `VALIDATION_ERROR`)                                                                                                                                              | GROUP jour 26, AI quand le bot existe                           |
| Idempotence privé               | `POST /conversations {"type":"PRIVATE","participant_id":<uuid>}` → **200** + fil existant si la paire a déjà un `PRIVATE` actif (recherche par `ConversationMember` croisé, pas de nouvelle table UK) ; sinon **201** | —                                                               |
| `encrypted`                     | `PRIVATE` ⇒ `encrypted=true` toujours (CRYPTO-00), non modifiable par le client                                                                                                                                       | —                                                               |
| Contenu message                 | `encrypted_content` = **exactement** le blob base64 décodé envoyé par le client (Double Ratchet côté client) ; le serveur ne le déchiffre, ne le wrap, ni ne le touche jamais pour `PRIVATE`                          | GROUP/AI : wrap serveur via `ensure_conversation_key` (jour 26) |
| Garde crypto envoi              | `require_sender_identity(device)` (existant) + `require_peer_ready(target_user)` (nouveau, non consommateur) — dans cet ordre, avant toute écriture                                                                   | —                                                               |
| Pagination                      | Curseur `before` (timestamp) + `limit+1` trick, comme `list_inbox` NOTIF-A. Inbox `limit` max 50, messages `limit` max 100                                                                                            | —                                                               |
| Édition message                 | Auteur **seul**, fenêtre **15 min** depuis `sent_at`. Au-delà → 403 `EDIT_WINDOW_EXPIRED`                                                                                                                             | Configurable par org (hors MVP)                                 |
| Suppression EVERYONE            | Auteur ≤ 48h **OU** `ConversationMember.role in (OWNER, ADMIN)` (générique, inatteignable en pratique tant que PRIVATE seul existe) ; au-delà → 403 `DELETE_WINDOW_EXPIRED`                                           | —                                                               |
| Suppression SELF                | Crée `MessageDelete(scope=SELF)` pour l'appelant uniquement ; le message reste visible pour l'autre membre ; masqué des lectures futures de l'appelant (filtre à la lecture)                                          | —                                                               |
| PJ (media_id)                   | `get_own_media_or_404(sender, media_id)` ; `INFECTED` → **422** `MEDIA_INFECTED` ; `type` du message dérivé de `media.media_type` (IMAGE/VIDEO/AUDIO/DOCUMENT)                                                        | Galerie/album/GIF picker : MEDIA-B..E, MESSAGERIE-E             |
| `client_message_id`             | Unicité par `(conversation, sender, metadata->>'client_message_id')` ; doublon → **409** `DUPLICATE_MESSAGE` (pas de nouvelle écriture, renvoie le message existant en `data`)                                        | —                                                               |
| Notification                    | `emit(type_=MESSAGE_NEW, title générique, body générique, collapse_key=f"message:{conversation_id}", payload={conversation_id, message_id})` pour chaque autre membre actif, `ignore_dnd=False`                       | Aperçu enrichi hors MVP (E2E)                                   |
| Blocage (lecture seule ce jour) | `BlockedUser.objects.filter(blocker=participant, blocked=requester).exists()` (et inverse) vérifié à la création `PRIVATE` → 403 `USER_BLOCKED`                                                                       | Routes de gestion : jour 27 MESSAGERIE-F                        |
| Recherche                       | `messages/search?q=` : `q` ≥ 2 caractères, `tags__icontains=q`, membre du fil uniquement                                                                                                                              | —                                                               |
| Portes AUTH-F                   | Toutes les routes `/conversations*`, `/messages*` sous JWT + CGU/wizard (comme tout `/api/v1/*`)                                                                                                                      | —                                                               |
| Audit                           | `module=MESSAGING` sur create/archive/delete-everyone (pas sur chaque envoi — trop bruyant, cohérent avec le choix « pas de ligne par clé publiée » de CRYPTO-A)                                                      | —                                                               |


---



## 1. Tables (nouvelle app)

**1 migration** : `apps/messaging/migrations/0001_initial.py` — les **18 tables** de [code/messaging_models.py](code/messaging_models.py) (`conversations`, `conversation_members`, `messages`, `message_reads`, `message_reactions`, `message_edits`, `message_deletes`, `message_forwards`, `pinned_messages`, `message_mentions`, `message_polls`, `poll_options`, `poll_votes`, `blocked_users`, `reported_messages`, `message_bookmarks`, `archived_conversations`, `conversation_settings`), 0 ligne.
Dépend de `iam` (users, devices) et `media` (media_files) — vérifier l'ordre des dépendances de migration généré (`iam`, `media` avant `messaging`).
**Interdit :** `docker compose down -v`.

---



## 2. Fichiers


| Fichier                                                                  | Rôle                                                                                                                                 |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `apps/messaging/__init__.py`, `apps.py`, `migrations/`                   | **nouveau.** Scaffolding app                                                                                                         |
| `apps/messaging/models.py`                                               | **nouveau.** 18 modèles (coller [code/messaging_models.py](code/messaging_models.py))                                                |
| `apps/messaging/services/conversation_service.py`                        | **nouveau.** inbox, create/find-private, detail, archive/unarchive, pin, mute, pinned-messages                                       |
| `apps/messaging/services/message_service.py`                             | **nouveau.** history, send, detail, edit, delete, search                                                                             |
| `apps/messaging/serializers/conversations.py`, `serializers/messages.py` | **nouveau.** shapes DRF                                                                                                              |
| `apps/messaging/views/conversations.py`, `views/messages.py`             | **nouveau.** 15 vues                                                                                                                 |
| `apps/messaging/urls.py`                                                 | **nouveau.** monté sous `/api/v1/` (`conversations`, `messages` — pas de préfixe `messaging/`, cohérent avec `MESSAGERIE-routes.md`) |
| `apps/crypto/services/key_service.py`                                    | **delta.** + `require_peer_ready(target_user)` (§0)                                                                                  |
| `apps/iam/services/rbac_catalog.py`                                      | **delta.** + 18 permissions `messaging.`* (17 self + 1 admin)                                                                        |
| `config/urls.py`, `config/settings.py`                                   | **delta.** `INSTALLED_APPS += "apps.messaging"`, include des urls                                                                    |
| `apps/iam/tests/test_messaging_a.py`, `test_messaging_b.py`              | **nouveau.** (scindés vu le volume, comme le reste du projet colocalise tous les tests API sous `apps/iam/tests/`)                   |


---



## 3. Contrat HTTP

Préfixe `/api/v1`. JWT + portes AUTH-F. Appareil = session courante (jamais un `device_id` du corps). **401** sans JWT (toutes les routes). **403** `FORBIDDEN` sans la perm / `TOS_REQUIRED` / `ONBOARDING_REQUIRED` (toutes les routes, non répété par ligne ci-dessous).

### 3.1 Vague A — Inbox & conversations


| #   | Route                                                     | Perm                                             | Requête                                                                                                                                        | Flux serveur                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Réponse                                                                                                                                                                           | Erreurs spécifiques                                                                       |
| --- | --------------------------------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| A1  | `GET /conversations` (MSG-04, inbox)                      | `messaging.conversation.read`                    | Query : `archived` (`true`/`false`, défaut `false`), `pinned` (`true` opt.), `type` (opt.), `limit` (1-50, défaut 20), `before` (ISO datetime) | 1. `conversation_service.list_inbox(user, archived, pinned, type_, limit, before)`. 2. `ConversationMember.objects.filter(user=user, active=True, archived=archived)` (+ `pinned=True` si demandé, + `conversation__type=type_` si fourni), `select_related("conversation")`, tri `-conversation__last_message_at`, trick `limit+1`.                                                                                                                                                                                                          | **200** `{ "results": [{ id, conversation_uuid, type, title, encrypted, last_message_at, unread_count, pinned, archived, muted, avatar_url, peer_summary? }], "next_before": <iso | null> }`.` peer_summary`(nom + avatar du pair) uniquement pour`PRIVATE`.                  |
| A2  | `POST /conversations` (MSG-01/02/19, créer/rouvrir privé) | `messaging.conversation.create`                  | `{ "type": "PRIVATE", "participant_id": "<uuid>" }`                                                                                            | 1. Serializer valide `type ∈ {PRIVATE}` (sinon 400, §0) et `participant_id` (UUID). 2. `participant_id == request.user.id` → 400. 3. `User.objects.get(pk=participant_id)` inconnu/inactif → 404. 4. `BlockedUser` (les 2 sens) → 403 `USER_BLOCKED`. 5. `find_or_create_private(user, participant)` : cherche un `Conversation(type=PRIVATE)` avec les 2 comme `ConversationMember(active=True)` (jointure croisée) → trouvé = réouverture ; sinon crée `Conversation(encrypted=True)` + 2 `ConversationMember(role=MEMBER)` en transaction. | **200** si réouverture, **201** si création — même shape que A3                                                                                                                   | 400 `VALIDATION_ERROR` (type non supporté, soi-même), 403 `USER_BLOCKED`, 404 `NOT_FOUND` |
| A3  | `GET /conversations/{id}` (MSG-11, détail)                | `messaging.conversation.read`                    | —                                                                                                                                              | 1. `ConversationMember.objects.get(conversation_id=id, user=request.user, active=True)` absent → 404 (MSG-18, pas de fuite d'existence).                                                                                                                                                                                                                                                                                                                                                                                                      | **200** `{ id, conversation_uuid, type, title, description, encrypted, avatar_url, created_at, settings: { muted, pinned, role, joined_at } }`                                    | 404 `NOT_FOUND`                                                                           |
| A4  | `GET /conversations/by-uuid/{uuid}` (MSG-03, deep-link)   | `messaging.conversation.read`                    | —                                                                                                                                              | Même flux que A3, résolution par `conversation_uuid` au lieu de `id`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | identique à A3                                                                                                                                                                    | 404 `NOT_FOUND`                                                                           |
| A5  | `POST /conversations/{id}/archive` (MSG-07)               | `messaging.conversation.archive`                 | —                                                                                                                                              | 1. Membre actif requis (404 sinon). 2. `ArchivedConversation.objects.get_or_create(conversation, user)` + `ConversationMember.archived=True`. Idempotent.                                                                                                                                                                                                                                                                                                                                                                                     | **200** `{ "archived": true }`                                                                                                                                                    | 404 `NOT_FOUND`                                                                           |
| A6  | `DELETE /conversations/{id}/archive` (MSG-08)             | `messaging.conversation.archive`                 | —                                                                                                                                              | 1. Membre actif requis (404 sinon). 2. Supprime la ligne `ArchivedConversation` + `archived=False`. Idempotent.                                                                                                                                                                                                                                                                                                                                                                                                                               | **200** `{ "archived": false }`                                                                                                                                                   | 404 `NOT_FOUND`                                                                           |
| A7  | `PATCH /conversations/{id}/inbox` (MSG-09, épingler)      | `messaging.conversation.read` (préférence perso) | `{ "pinned": true }`                                                                                                                           | 1. Membre actif requis (404 sinon). 2. `ConversationMember.pinned = payload["pinned"]`.                                                                                                                                                                                                                                                                                                                                                                                                                                                       | **200** `{ "pinned": true                                                                                                                                                         | false }`                                                                                  |
| A8  | `PATCH /conversations/{id}/settings` (MSG-10, muet)       | `messaging.conversation.read`                    | `{ "muted": true }`                                                                                                                            | 1. Membre actif requis (404 sinon). 2. `ConversationSetting.objects.update_or_create(conversation, user, defaults={"muted": ...})`.                                                                                                                                                                                                                                                                                                                                                                                                           | **200** `{ "muted": true                                                                                                                                                          | false }`                                                                                  |
| A9  | `GET /conversations/{id}/pinned-messages` (MSG-12)        | `messaging.conversation.read`                    | —                                                                                                                                              | 1. Membre actif requis (404 sinon). 2. `PinnedMessage.objects.filter(conversation_id=id).order_by("-pinned_at")` — liste vide ce jour (rien ne peuple `PinnedMessage`, réservé MESSAGERIE-E jour 27), endpoint câblé pour ne pas être à refaire.                                                                                                                                                                                                                                                                                              | **200** `{ "results": [{ message_id, pinned_at, pinned_by }] }`                                                                                                                   | 404 `NOT_FOUND`                                                                           |




### 3.2 Vague B — Messages


| #   | Route                                                                | Perm                       | Requête                                                                                                                                                                      | Flux serveur                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Réponse                                                                                                                                                                                                                                                                                                                                                                                                                      | Erreurs spécifiques                                                                                                                                                            |
| --- | -------------------------------------------------------------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| B1  | `GET /conversations/{id}/messages` (MSG-21, historique)              | `messaging.message.read`   | Query : `before`, `limit` (1-100, défaut 30), `parent_id` (opt., fil de réponses)                                                                                            | 1. Membre actif requis (404 sinon). 2. `Message.objects.filter(conversation_id=id, deleted=False)` moins celles avec `MessageDelete(scope=SELF, deleted_by=request.user)` (exclude), `+ parent_message_id=parent_id` si fourni, tri `-sent_at`, trick `limit+1`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | **200** `{ "results": [{ id, type, encrypted_content: "", sender_id, parent_message_id, media_id, priority, tags, mentions, edited, forwarded, pinned, sent_at }], "next_before": <iso                                                                                                                                                                                                                                       | null> }`                                                                                                                                                                       |
| B2  | `POST /conversations/{id}/messages` (MSG-22/29/32/33/34/35, envoyer) | `messaging.message.send`   | `{ "type": "TEXT", "encrypted_content": "<base64>", "parent_message_id": null, "media_id": null, "priority": 0, "tags": [], "mentions": [], "client_message_id": "<uuid>" }` | 1. Membre actif requis (404 sinon) ; `conversation.type != PRIVATE` → 400 (filet, aucun GROUP n'existe). 2. `locked=True` sans OWNER/ADMIN → 403 `CONVERSATION_LOCKED` (MSG-36) ; rôle `READ_ONLY` → 403 `READ_ONLY_MEMBER` (MSG-37). 3. `client_message_id` déjà vu `(conversation, sender)` → 409 `DUPLICATE_MESSAGE`, renvoie le message existant. 4. `device = current_device(request)` ; `require_sender_identity(device)` → 409 `CRYPTO_KEYS_MISSING`. 5. `require_peer_ready(target_user=peer)` → 409 `PEER_KEYS_MISSING` (nouveau, §0, non consommateur d'OTPK). 6. Si `media_id` : `get_own_media_or_404(user, media_id)` (404 si pas à soi), `INFECTED` → 422 `MEDIA_INFECTED`, `type` dérivé de `media.media_type` si `TEXT`/absent. 7. Décode `encrypted_content` base64 → bytes (400 si invalide et pas de `media_id`) ; stocke tel quel, **aucun** wrap serveur (§0). 8. `Message.objects.create(sent_at=now())` en transaction : incrémente `unread_count` des autres membres actifs, met à jour `conversation.last_message_at`/`last_message`. 9. Mentions : pour chaque `user_id` membre actif **et** `allow_mentions=true`, crée `MessageMention`. 10. `emit()` par autre membre actif (`MESSAGE_NEW`, titre/corps génériques, `collapse_key=f"message:{id}"`) + `MESSAGE_MENTION` séparé par mentionné (`ignore_dnd=True`). | **201** `{ id, type, encrypted_content: "<base64>", sender_id, sent_at, ... }` (même shape que B1, un élément)                                                                                                                                                                                                                                                                                                               | 400 `VALIDATION_ERROR`, 403 `CONVERSATION_LOCKED`/`READ_ONLY_MEMBER`, 404 `NOT_FOUND`, 409 `DUPLICATE_MESSAGE`/`CRYPTO_KEYS_MISSING`/`PEER_KEYS_MISSING`, 422 `MEDIA_INFECTED` |
| B3  | `GET /messages/{id}` (MSG-27, détail)                                | `messaging.message.read`   | —                                                                                                                                                                            | 1. Membre actif du fil du message requis (404 sinon, y compris fil quitté).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | **200** — même shape que B1 + flags `edited`, `forwarded`, `pinned`, `deleted`                                                                                                                                                                                                                                                                                                                                               | 404 `NOT_FOUND`                                                                                                                                                                |
| B4  | `PATCH /messages/{id}` (MSG-24, éditer)                              | `messaging.message.update` | `{ "encrypted_content": "<base64>" }`                                                                                                                                        | 1. `message.sender != request.user` → 403 `FORBIDDEN` ; `now() - sent_at > 15min` → 403 `EDIT_WINDOW_EXPIRED`. 2. `MessageEdit.objects.create(message, previous_encrypted_content=message.encrypted_content, edited_by=user, edited_at=now())`. 3. `message.encrypted_content = <nouveau>` ; `edited=True`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | **200** — shape B1 mise à jour                                                                                                                                                                                                                                                                                                                                                                                               | 400 `VALIDATION_ERROR`, 403 `FORBIDDEN`/`EDIT_WINDOW_EXPIRED`, 404 `NOT_FOUND`                                                                                                 |
| B5  | `DELETE /messages/{id}` (MSG-25/26, supprimer)                       | `messaging.message.delete` | Query `scope=SELF                                                                                                                                                            | EVERYONE`(défaut`SELF`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | 1. Membre actif requis (404 sinon). 2. `scope=SELF` : `MessageDelete.objects.get_or_create(message, deleted_by=user, delete_scope=SELF, deleted_at=now())`. Idempotent. 3. `scope=EVERYONE` : `sender != user` **et** `role not in (OWNER, ADMIN)` → 403 `FORBIDDEN` ; `sender == user` et `> 48h` → 403 `DELETE_WINDOW_EXPIRED` ; sinon `MessageDelete(EVERYONE)` + `deleted=True`, `encrypted_content=b""` (purge réelle). | **200** `{ "deleted": true, "scope": "SELF"                                                                                                                                    |
| B6  | `GET /conversations/{id}/messages/search` (MSG-28)                   | `messaging.message.read`   | Query `q` (≥ 2 caractères)                                                                                                                                                   | 1. Membre actif requis (404 sinon) ; `len(q) < 2` → 400 `VALIDATION_ERROR`. 2. `Message.objects.filter(conversation_id=id, deleted=False, tags__icontains=q)` (moins `MessageDelete(SELF)` de l'appelant), tri `-sent_at`, `limit` max 50.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | **200** `{ "results": [...] }` (shape B1)                                                                                                                                                                                                                                                                                                                                                                                    | 400 `VALIDATION_ERROR`, 404 `NOT_FOUND`                                                                                                                                        |




---



## 4. Tests nouveaux



### `test_messaging_a.py`


| Cas                                                      | Attendu                                           |
| -------------------------------------------------------- | ------------------------------------------------- |
| POST conversations PRIVATE, 2 users                      | 201, `encrypted=true`, 2 `ConversationMember`     |
| POST conversations, même paire rejouée                   | 200, même `conversation.id`, pas de doublon       |
| POST conversations `type=GROUP`/`AI`                     | 400 `VALIDATION_ERROR`                            |
| POST conversations vers soi-même                         | 400 `VALIDATION_ERROR`                            |
| POST conversations, `participant_id` bloqué (ORM direct) | 403 `USER_BLOCKED`                                |
| POST conversations, participant inconnu                  | 404 `NOT_FOUND`                                   |
| GET conversations (inbox)                                | tri `-last_message_at`, pagination `limit+before` |
| GET conversations `archived=true`                        | seulement les archivés                            |
| GET conversations/{id}, non membre                       | 404                                               |
| GET conversations/by-uuid/{uuid}                         | même payload que par id                           |
| POST puis DELETE archive                                 | idempotent, reflété dans l'inbox                  |
| PATCH inbox `{pinned:true}`                              | reflété                                           |
| PATCH settings `{muted:true}`                            | `ConversationSetting` upsert                      |
| GET pinned-messages                                      | 200 liste vide (rien ne peuple encore)            |
| sans JWT / sans perm / self sans CGU                     | 401 / 403 `FORBIDDEN` / 403 `TOS_REQUIRED`        |
| `/api/schema/`                                           | contient `/api/v1/conversations`                  |




### `test_messaging_b.py`


| Cas                                                                  | Attendu                                                                                                             |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| POST messages, sender sans identité crypto                           | 409 `CRYPTO_KEYS_MISSING`                                                                                           |
| POST messages, peer sans identité/SPK                                | 409 `PEER_KEYS_MISSING`, **aucune** OTPK consommée (assert count inchangé)                                          |
| POST messages, les deux prêts                                        | 201, `unread_count` du pair incrémenté, `last_message_at` mis à jour, notification `MESSAGE_NEW` émise pour le pair |
| POST messages, `client_message_id` rejoué                            | 409 `DUPLICATE_MESSAGE`, renvoie le message existant, pas de doublon en base                                        |
| POST messages avec `media_id` à soi, `scan_status=CLEAN`             | 201, `type` dérivé du `media_type`                                                                                  |
| POST messages avec `media_id` `INFECTED`                             | 422 `MEDIA_INFECTED`                                                                                                |
| POST messages avec `media_id` d'un autre user                        | 404                                                                                                                 |
| POST messages avec mention, `allow_mentions=false` chez le mentionné | pas de `MessageMention` créée, pas de `MESSAGE_MENTION` émis                                                        |
| GET messages (historique)                                            | pagination, tri `-sent_at`                                                                                          |
| GET messages/{id}, non membre du fil                                 | 404                                                                                                                 |
| PATCH messages/{id}, éditeur ≠ auteur                                | 403 `FORBIDDEN`                                                                                                     |
| PATCH messages/{id}, > 15 min (monkeypatch `sent_at`)                | 403 `EDIT_WINDOW_EXPIRED`                                                                                           |
| PATCH messages/{id}, auteur < 15 min                                 | 200, `MessageEdit` créée, `edited=true`                                                                             |
| DELETE messages/{id}?scope=SELF                                      | invisible pour l'appelant, visible pour l'autre membre                                                              |
| DELETE messages/{id}?scope=EVERYONE, non-auteur                      | 403 `FORBIDDEN`                                                                                                     |
| DELETE messages/{id}?scope=EVERYONE, auteur < 48h                    | 200, `deleted=true`, `encrypted_content` purgé                                                                      |
| GET messages/search `q` < 2 car                                      | 400 `VALIDATION_ERROR`                                                                                              |
| GET messages/search `q` match tag                                    | 200, résultat trouvé                                                                                                |
| sans JWT / sans perm / self sans CGU                                 | 401 / 403 `FORBIDDEN` / 403 `TOS_REQUIRED`                                                                          |
| `/api/schema/`                                                       | contient `/api/v1/conversations/{id}/messages`                                                                      |




### Delta crypto


| Cas                                                              | Attendu                                |
| ---------------------------------------------------------------- | -------------------------------------- |
| `require_peer_ready(target_user)`, target avec identity+SPK      | ne lève rien                           |
| `require_peer_ready(target_user)`, target sans SPK               | lève `PEER_KEYS_MISSING`               |
| `require_peer_ready` n'altère jamais `OneTimePreKey.consumed_at` | assert count OTPK inchangé avant/après |


---



## 5. Vérif manuelle

```powershell
python manage.py makemigrations messaging
python manage.py migrate
python manage.py check
pytest apps/iam/tests/test_messaging_a.py apps/iam/tests/test_messaging_b.py apps/iam/tests/test_crypto_a.py apps/iam/tests/test_notif_a.py --reuse-db
```

---



## Checklist jour 25

- [x] App `apps.messaging` créée, 18 tables, migration `0001_initial`
- [x] 18 permissions `messaging.*` seedées (17 self + 1 admin)
- [x] 9 routes MESSAGERIE-A vertes (inbox, création/réouverture privé, détail, deep-link, archive, pin, mute, pinned-messages)
- [x] 6 routes MESSAGERIE-B vertes (historique, envoi, détail, édition, suppression, recherche)
- [x] `require_peer_ready` ajouté à `apps/crypto` (non consommateur d'OTPK) et branché à l'envoi
- [x] `require_sender_identity` réellement appelé (plus un hook orphelin)
- [x] `emit()` réellement appelé pour `MESSAGE_NEW`/`MESSAGE_MENTION`
- [x] Blocage vérifié à la création (test ORM direct, pas de route de gestion)
- [x] `test_messaging_a.py` + `test_messaging_b.py` + régression CRYPTO-A/NOTIF-A
- [x] 0 régression MEDIA-A (get_own_media_or_404)
- [x] SIRH non modifié

---



## Interdits

- `type=GROUP`/`AI` en création — jour 26 (MESSAGERIE-C) / bot infra
- WebSocket, accusés livré/lu, typing — jour 26/27 (MESSAGERIE-D/G)
- Réactions, transfert, épingle message, signets, sondages — jour 27 (MESSAGERIE-E)
- Routes de gestion blocage/signalement — jour 27 (MESSAGERIE-F)
- Appeler `key_service.get_bundles()` depuis l'envoi de message (consommation OTPK, §0)
- Wrap/déchiffrement serveur du contenu `PRIVATE` (CRYPTO-00)
- `docker compose down -v`
- Changer le SIRH

---



## Après le jour 25

Jour 26 : **MESSAGERIE-C, D** — groupes (CRUD, membres, rôles) + temps réel (WebSocket, accusés livré/lu), premier vrai consommateur de `ensure_conversation_key` (CRYPTO-A) et de `channels_redis` (si `REDIS_URL` toujours vide en lab, `InMemoryChannelLayer` suffira pour les tests). Lab pas encore écrit.

---



## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour**. Le jour 2 (admin + Swagger) est un extra déjà clos.


| Jours  | Plan                                           | Ticket MVP                            |
| ------ | ---------------------------------------------- | ------------------------------------- |
| 0      | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health`   |
| 1–2    | AUTH-A ; admin + Swagger                       | Connexion locale ; lab admin          |
| 3–11   | D+B … AUTH-R                                   | §1 entrer + droits HTTP               |
| 12     | ADMIN-A                                        | §9 comptes                            |
| 13     | PROF-A                                         | §2 ma fiche / photo                   |
| 14     | PROF-B                                         | Préférences                           |
| 15     | PROF-C                                         | §2 visibilité                         |
| 16     | PRES-A                                         | §2 statut en ligne                    |
| 17     | ANNUAIRE-A                                     | §3 recherche collègue                 |
| 18     | ANNUAIRE-B                                     | §3 organigramme (types + arbre)       |
| 19     | ANNUAIRE-C                                     | §3 mutations / affectations           |
| 20     | ANNUAIRE-D                                     | §3 compétences / certifications       |
| 21     | CRYPTO-00                                      | §6 décision E2E                       |
| 22     | MEDIA-R + MEDIA-A                              | §4 upload (plafonds ; pas de reprise) |
| 23     | NOTIF-R + NOTIF-A                              | §5 alertes + MOB-PUSH (VoIP / worker) |
| 24     | CRYPTO-R + CRYPTO-A                            | Clés HTTP                             |
| **25** | **MESSAGERIE-R, A, B** (ce plan)               | §7 1-to-1                             |
| 26     | MESSAGERIE-C, D                                | §7 groupes + temps réel               |
| 27     | MESSAGERIE-E (partiel), F, G                   | §7 enrichissements                    |
| 28     | MEDIA-B, C, D, E                               | §4 album / vocal / coffre             |
| 29     | APPELS-R, A, B, C                              | §8 appel 1-1 + `CALL_CANCELLED`       |
| 30     | APPELS-D, E, G                                 | §8 écran / CR                         |


**Total : 31 plans (jours 0 à 30).**
Déjà clos : **26** (0–25). Restant : **5** (26–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.