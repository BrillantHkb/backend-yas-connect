# Jour 26 — MESSAGERIE-C + D (groupes, temps réel, accusés)

**Statut :** clos (2026-09-16).
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.
**Préalable :** jours 0–25 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 25](00-jour-25-messagerie-r-a-b.md)). CRYPTO-A (jour 24) a laissé `ensure_conversation_key` comme hook interne « prêt pour MESSAGERIE-C » — c'est **ce jour** qui le consomme enfin. PRES-A (jour 16) a laissé un WebSocket authentifié JWT (`PresenceConsumer`) — ce jour en écrit un second sur le même modèle.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §7 — *messagerie groupes + temps réel*) :


| Fonction MVP                            | Ticket               | Statut             |
| --------------------------------------- | -------------------- | ------------------ |
| Inbox, conversations, messages 1-to-1   | MESSAGERIE-R + A + B | **fait** (jour 25) |
| **Groupes (CRUD, membres, rôles)**      | **MESSAGERIE-C**     | **ce jour**        |
| **Temps réel (WS) + accusés**           | **MESSAGERIE-D**     | **ce jour**        |
| Réactions, transfert, sondages, blocage | MESSAGERIE-E, F, G   | jour 27            |


**À quoi ça sert (MVP) :** jusqu'ici, seul le 1-to-1 existe. Ce jour ouvre les **groupes** (créer, gérer les membres, transférer la propriété) et rend la messagerie **instantanée** (WebSocket au lieu de polling REST) avec des **accusés livré/lu** par appareil. C'est le jour où `ensure_conversation_key` (CRYPTO-A, jour 24) sert enfin à quelque chose : contrairement au 1-to-1 (E2E Signal, le serveur ne voit jamais le texte), un groupe est un chiffrement **« cloud »** (CRYPTO-00, décision jour 21) — le serveur chiffre au repos avec une clé de fil qu'il gère lui-même, et peut déchiffrer pour servir le contenu à n'importe quel membre autorisé.

**Plan métier (code à coller) :** [MESSAGERIE-C-groupes.md](messaging_plans/MESSAGERIE-C-groupes.md) (MSG-41…58, **hors** MSG-58 groupe temporaire — voir §0) + [MESSAGERIE-D-temps-reel.md](messaging_plans/MESSAGERIE-D-temps-reel.md) (MSG-59…72, **hors** MSG-71 réactions temps réel — jour 27). Modèles : déjà tous créés (jour 25 pour `apps.messaging`, jour 24 pour `ConversationKey`).
Chemins lab = ce fichier.

**Déjà en base / code :**

- Les **18 tables** `apps.messaging` (jour 25) contiennent déjà tous les champs nécessaires : `Conversation.owner`/`avatar_media`, `ConversationMember.role`/`username`/`active`/`left_at`, `ConversationSetting.visibility`/`locked`/`max_members`/`custom_settings`, `MessageRead` (unique `message,user,device`). **0 nouvelle migration ce jour.**
- `apps.crypto.services.key_service.ensure_conversation_key(conversation_id)` (jour 24) : get-or-create la ligne `ConversationKey` (32 octets aléatoires, wrap AES-256-GCM via `CRYPTO_MASTER_KEY`), jamais appelée jusqu'ici.
- `apps.iam.services.rbac_catalog` : les 18 permissions `messaging.*` (jour 25) couvrent **déjà** tout ce jour (`conversation.update`, `member.read`, `member.manage`, `receipt.update`) — **0 nouvelle permission**.
- `apps/realtime/consumers.py::PresenceConsumer` (PRES-A, jour 16) : le patron exact à dupliquer pour le WS messagerie — JWT via `?token=` ou `Authorization`, portes AUTH-F dans le `connect()`, `channel_layer.group_add`/`group_discard`, test via `WebsocketCommunicator`.
- `apps.media.services.upload_service.get_own_media_or_404` (MEDIA-A) : réutilisé pour l'avatar de groupe.
- `apps.iam.models.PrivacySetting` (`allow_group_invites`, `read_receipts_enabled`) : déjà en base, déjà utilisé pour `allow_mentions` au jour 25 (même pattern `get_or_create`).

**Pas encore :** `apps.messaging.consumers` n'existe pas. Aucune route n'appelle jamais `ensure_conversation_key`. `type=GROUP` est refusé par `POST /conversations` (filet de sécurité posé au jour 25, §0 de ce jour-là). Aucun accusé livré/lu n'est jamais posé.

**Objectif du jour :**

1. **MESSAGERIE-C** : `POST /conversations` accepte `type=GROUP` ; 7 nouvelles routes (métadonnées, réglages, membres, quitter).
2. Chiffrement de fil GROUP : `ensure_conversation_key` appelé à la création ; nouvelles primitives `wrap_with_key`/`unwrap_with_key` (`apps/crypto/services/wrapping.py`) pour chiffrer/déchiffrer le **contenu des messages** GROUP avec la clé de fil (pas la master key directement).
3. `message_service.send_message` : branchement par type — `PRIVATE` inchangé (gardes crypto par appareil) ; `GROUP` chiffre/déchiffre via la clé de fil, **aucune** garde `CRYPTO_KEYS_MISSING`/`PEER_KEYS_MISSING` (ça n'a pas de sens pour un chiffrement serveur).
4. **MESSAGERIE-D** : `apps/messaging/consumers.py::MessagingConsumer` (WS `/ws/v1/messaging/`, sur le patron `PresenceConsumer`) + 3 routes REST d'accusés + delta `after=` sur l'historique (catch-up, MSG-70).
5. Ne rien casser : MESSAGERIE-A/B (jour 25), CRYPTO-A (jour 24), PRES-A (jour 16, même `channel_layer`).

**Hors jour 26 :** `type=AI` (toujours pas de compte bot) ; `GET /conversations/discoverable` (business doc : « optionnel phase 3b ») ; groupe temporaire + job de clôture (MSG-58 — dépendrait de `run_scheduled_jobs`, déjà noté comme sans verrou distribué, explicitement laissé de côté) ; messages `SYSTEM` auto (join/leave/transfert — `Message.Type.SYSTEM` existe, mais MSG-54 le marque lui-même « optionnel », différé pour contenir le scope déjà chargé) ; `GET /crypto/conversations/{id}/key` (CRY-10 — le serveur déchiffre lui-même pour servir le contenu, aucune route n'a besoin d'exposer la clé de fil à un client) ; réactions/transfert temps réel (MSG-71 — jour 27, MESSAGERIE-E) ; indicateurs de saisie (jour 27, MESSAGERIE-G).

---



## 0. Corrections apportées au plan métier (avant de coder)


| Écart trouvé                                                                                                                | Correction                                                                                                                                                                                                                                                                                                                                                                                                      |
| --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MESSAGERIE-D : accusés body `{"device_id": "..."}`                                                                          | Comme partout depuis CRYPTO-A/MESSAGERIE-B : **jamais** un `device_id` du corps — toujours `current_device(request)` (session courante). Le corps de `delivered`/`read` est ignoré.                                                                                                                                                                                                                             |
| MESSAGERIE-C : « `conversation_settings` ligne owner **ou** table dédiée groupe » (formulation ambiguë)                     | Tranché : toujours la ligne du membre `OWNER` qui fait foi pour `visibility`/`locked`/`max_members`/`custom_settings`. Corrige au passage le garde `locked` posé au jour 25 dans `message_service.send_message`, qui utilisait provisoirement « n'importe quelle ligne » faute de `group-settings` — devient « la ligne de l'OWNER ».                                                                           |
| MSG-58 « groupe temporaire, job clôture »                                                                                   | Différé (§ Hors jour 26) — dépend de `run_scheduled_jobs`, déjà identifié comme non prêt pour un vrai scheduler (audit scaling du 2026-09-16).                                                                                                                                                                                                                                                                  |
| MSG-54 « message d'accueil + SYSTEM optionnel »                                                                             | Stockage (`custom_settings.welcome_message`) gardé ; génération du message `SYSTEM` **différée** (le mot « optionnel » est du business doc lui-même) pour contenir le scope.                                                                                                                                                                                                                                    |
| CRY-10 (`GET /crypto/conversations/{id}/key`) toujours listé « hors jour 24, jour 26 MESSAGERIE-C » dans le plan du jour 24 | En fait jamais nécessaire : le modèle « cloud » (CRYPTO-00) veut que le **serveur** déchiffre pour servir le contenu — un client n'a jamais besoin de récupérer la clé de fil brute. `ensure_conversation_key` est consommé **en interne**, aucune route ne l'expose. CRY-10 reste un hook mort, sans route, pour de bon (sauf futur besoin de vrai chiffrement E2E groupe, hors MVP).                          |
| `wrapping.wrap`/`unwrap` (CRYPTO-A) figés sur `CRYPTO_MASTER_KEY`                                                           | Nouvelles fonctions `wrap_with_key(key, plaintext)`/`unwrap_with_key(key, blob)` — même format `nonce(12o) || ciphertext+tag`, mais paramétrées par une clé arbitraire (la clé de fil déjà déwrappée), pour chiffrer le **contenu par message** sans reformater la clé de fil à chaque fois.                                                                                                                    |
| Ajout membre / invitation refusée / bloqué                                                                                  | Business doc ne précise pas le comportement exact. Choix : **skip silencieux** (comme les mentions au jour 25) plutôt que 403 bloquant toute la requête — cohérent avec le pattern déjà établi. 0 membre valide après filtrage → 400 `VALIDATION_ERROR`.                                                                                                                                                        |
| Retrait/rôle membre : hiérarchie non précisée par le business doc                                                           | Tranché : **OWNER** peut tout faire (promouvoir/rétrograder ADMIN, transférer, retirer qui que ce soit sauf lui-même). **ADMIN** peut ajouter/retirer/changer le rôle d'un `MEMBER`/`READ_ONLY`, mais ne touche jamais à un `OWNER` ni à un autre `ADMIN`. Retirer un membre = `active=False`+`left_at` (jamais de suppression de ligne, cohérent avec la règle « jamais DELETE » déjà appliquée aux `Device`). |


---



## Pourquoi ce jour (après MESSAGERIE-B, avant MESSAGERIE-E/F/G)

Le 1-to-1 (jour 25) est le cas le plus simple ; les groupes ajoutent la notion de **membres multiples avec rôles**, ce que `ConversationMember.role` portait déjà en base sans jamais être exploité (jour 25 ne créait que des `MEMBER`). Le temps réel (D) arrive **après** que la persistance (A/B) et les groupes (C) soient stables, exactement comme PRES-A (jour 16) est arrivé après que le modèle `User`/`Device` soit stable — un WebSocket ne fait que pousser en direct ce que les routes REST font déjà, il ne doit rien réinventer.

```text
JWT + HasPermission + portes AUTH-F. Appareil = request.auth.session.device_id (jamais le body).

Vague C — Groupes (toutes les perms déjà seedées au jour 25)
    POST   /conversations (type=GROUP)                messaging.conversation.create
    PATCH  /conversations/{id}                          messaging.conversation.update
    PATCH  /conversations/{id}/group-settings            messaging.conversation.update
    GET    /conversations/{id}/members                    messaging.member.read
    POST   /conversations/{id}/members                    messaging.member.manage
    PATCH  /conversations/{id}/members/{user_id}            messaging.member.manage
    DELETE /conversations/{id}/members/{user_id}            messaging.member.manage
    POST   /conversations/{id}/leave                        messaging.conversation.read

Vague D — Temps réel & accusés
    WS     /ws/v1/messaging/                            JWT + membre du fil (par subscribe)
    POST   /messages/{id}/delivered                      messaging.receipt.update
    POST   /messages/{id}/read                            messaging.receipt.update
    POST   /conversations/{id}/read                       messaging.receipt.update
    GET    /conversations/{id}/messages?after=            messaging.message.read (delta MSG-70)

Delta CRYPTO-A (hook enfin consommé)
    ensure_conversation_key(conversation_id)   → appelé à la création GROUP
    wrap_with_key / unwrap_with_key (nouveau)  → chiffrement du contenu par message GROUP

Hors jour 26
    type=AI, discoverable, groupe temporaire, SYSTEM auto, CRY-10, réactions/typing temps réel
```

---



## Paliers (figés pour ce jour)


| Sujet                           | Choix jour 26                                                                                                                                                                                                                                                                                   | Plus tard                    |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| Création groupe                 | `POST /conversations {"type":"GROUP","title","member_ids":[...],"visibility":"PRIVATE"}` ; créateur = `OWNER` ; autres `member_ids` valides = `MEMBER` ; `encrypted=False` (GROUP, CRYPTO-00)                                                                                                   | —                            |
| Filtrage membres à la création  | Par `member_id` : user inconnu/inactif, `allow_group_invites=false`, ou relation `BlockedUser` (les 2 sens) → **skip silencieux**. 0 membre valide restant → 400 `VALIDATION_ERROR`                                                                                                             | —                            |
| Clé de fil                      | `ensure_conversation_key(conversation.id)` appelé **une fois**, juste après la création, dans la même transaction                                                                                                                                                                               | Rotation : hors MVP          |
| Chiffrement contenu GROUP       | Serveur : `raw_key = unwrap(conv_key.wrapped_key)` (master key) puis `wrap_with_key(raw_key, plaintext)` à l'écriture, symétrique à la lecture. Le champ `encrypted_content` reste le même nom de colonne, mais pour GROUP il contient un blob chiffré par la **clé de fil**, pas par le client | —                            |
| Garde crypto envoi              | `PRIVATE` : inchangé (`require_sender_identity` + `require_peer_ready`). `GROUP` : **aucune** garde par appareil — la confidentialité est gérée par la clé de fil serveur, pas par Signal                                                                                                       | —                            |
| Rôles / hiérarchie              | `OWNER` (1 seul, transfert via PATCH role) > `ADMIN` (plusieurs) > `MEMBER` > `READ_ONLY` (lecture seule, MSG-49). ADMIN ne touche jamais OWNER/ADMIN                                                                                                                                           | —                            |
| Retrait / leave                 | Jamais de suppression de `ConversationMember` — `active=False`, `left_at=now()`. `OWNER` ne peut pas quitter sans transférer d'abord (403)                                                                                                                                                      | —                            |
| `group-settings`                | Une seule ligne `ConversationSetting` fait foi : celle du membre `OWNER`. `PATCH` (OWNER/ADMIN) écrit toujours cette ligne, même si c'est un ADMIN qui appelle                                                                                                                                  | —                            |
| `max_members`                   | Vérifié à `POST .../members` uniquement (pas à la création) ; `None` = illimité                                                                                                                                                                                                                 | —                            |
| Accusés                         | Corps ignoré, appareil = session (`current_device`). `delivered`/`read` = upsert `MessageRead(message,user,device)`. `read` respecte `read_receipts_enabled` (si `false`, **200** silencieux, `read_at` jamais posé)                                                                            | —                            |
| `POST /conversations/{id}/read` | `{"last_read_message_id"}` → marque lu tous les messages `sent_at ≤` celui-ci pour l'appelant, reset `unread_count=0`, `last_read_message` mis à jour                                                                                                                                           | —                            |
| WS                              | `/ws/v1/messaging/`, JWT `?token=` (même patron que PRES-A). Client envoie `{"type":"subscribe","conversation_ids":[...]}` ; le serveur ne rejoint que les fils où l'appelant est membre actif (silencieux sur les autres, pas de fuite d'existence)                                            | —                            |
| Événements WS                   | `message.created`/`message.updated`/`message.deleted`/`receipt.updated`, diffusés au groupe `conversation.{id}` par `channel_layer.group_send` depuis les services REST existants (pas de duplication de logique métier dans le consumer)                                                       | `reaction.updated` : jour 27 |
| Catch-up                        | `GET /conversations/{id}/messages?after=<iso>` (nouveau, en plus de `before` existant) — tri ascendant, pour rattraper après coupure WS                                                                                                                                                         | —                            |
| Portes AUTH-F                   | Toutes les routes REST + le `connect()` WS                                                                                                                                                                                                                                                      | —                            |


---



## 1. Tables

**Aucune migration ce jour.** Les 18 tables `apps.messaging` (jour 25) et `conversation_keys` (`apps.crypto`, jour 24) portent déjà tous les champs nécessaires.

---



## 2. Fichiers


| Fichier                                                     | Rôle                                                                                                                                                                                                                               |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `apps/crypto/services/wrapping.py`                          | **delta.** `wrap_with_key`, `unwrap_with_key`                                                                                                                                                                                      |
| `apps/messaging/services/conversation_service.py`           | **delta.** `find_or_create_private` → renommé en interne pour couvrir GROUP (`create_group`), `update_conversation`, `update_group_settings`, `list_members`, `add_member`, `update_member`, `remove_member`, `leave_conversation` |
| `apps/messaging/services/message_service.py`                | **delta.** branchement PRIVATE/GROUP dans `send_message`, `_serialize_message` group-aware, `after=` dans `list_messages`                                                                                                          |
| `apps/messaging/services/receipt_service.py`                | **nouveau.** `mark_delivered`, `mark_read`, `mark_conversation_read`                                                                                                                                                               |
| `apps/messaging/services/realtime_service.py`               | **nouveau.** `broadcast_message_created/updated/deleted`, `broadcast_receipt_updated` (wrap `channel_layer.group_send`, no-op si layer absent)                                                                                     |
| `apps/messaging/consumers.py`                               | **nouveau.** `MessagingConsumer` (patron `PresenceConsumer`)                                                                                                                                                                       |
| `apps/messaging/serializers/conversations.py`               | **delta.** `GroupCreateSerializer`, `ConversationUpdateSerializer`, `GroupSettingsSerializer`, `MemberAddSerializer`, `MemberUpdateSerializer`                                                                                     |
| `apps/messaging/serializers/messages.py`                    | inchangé (même shape d'envoi)                                                                                                                                                                                                      |
| `apps/messaging/views/conversations.py`                     | **delta.** 7 nouvelles vues (membres, settings, leave) ; `ConversationListCreateView.post` accepte `GROUP`                                                                                                                         |
| `apps/messaging/views/messages.py`                          | **delta.** 3 vues accusés, `after=` sur l'historique                                                                                                                                                                               |
| `apps/messaging/urls.py`                                    | **delta.** + 10 routes                                                                                                                                                                                                             |
| `apps/realtime/routing.py`                                  | **delta.** + `path("ws/v1/messaging/", MessagingConsumer.as_asgi())`                                                                                                                                                               |
| `apps/iam/tests/test_messaging_c.py`, `test_messaging_d.py` | **nouveau.**                                                                                                                                                                                                                       |


---



## 3. Contrat HTTP

Préfixe `/api/v1`. JWT + portes AUTH-F. **401** sans JWT, **403** `FORBIDDEN`/`TOS_REQUIRED`/`ONBOARDING_REQUIRED` (toutes les routes, non répété ci-dessous). Appareil = session courante (jamais un `device_id` du corps).

### 3.1 Vague C — Groupes


| #   | Route                                                        | Perm                            | Requête                                                                                       | Flux serveur                                                                                                                                                                                                                                                                                                                                                                                                | Réponse                                                                    | Erreurs spécifiques    |
| --- | ------------------------------------------------------------ | ------------------------------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ---------------------- |
| C1  | `POST /conversations` (MSG-41, `type=GROUP`)                 | `messaging.conversation.create` | `{ "type": "GROUP", "title": "...", "member_ids": ["<uuid>", ...], "visibility": "PRIVATE" }` | 1. `title` non vide (400 sinon). 2. Pour chaque `member_id` : filtre inconnu/inactif/`allow_group_invites=false`/bloqué → skip silencieux. 0 restant → 400. 3. Transaction : `Conversation.objects.create(type=GROUP, encrypted=False, owner=user)` ; `ConversationMember(role=OWNER)` pour le créateur ; `ConversationMember(role=MEMBER)` par membre valide ; `ensure_conversation_key(conversation.id)`. | **201** — shape détail (3.3, MESSAGERIE-A)                                 | 400 `VALIDATION_ERROR` |
| C2  | `PATCH /conversations/{id}` (MSG-42/43)                      | `messaging.conversation.update` | `{ "title"?, "description"?, "avatar_media_id"? }`                                            | 1. `conversation.type != GROUP` → 400. 2. Appelant `OWNER`/`ADMIN` requis, sinon 403. 3. `avatar_media_id` fourni → `get_own_media_or_404(user, id)` (doit être à soi).                                                                                                                                                                                                                                     | **200** — détail à jour                                                    | 400/403/404            |
| C3  | `PATCH /conversations/{id}/group-settings`                   | `messaging.conversation.update` | `{ "visibility"?, "locked"?, "max_members"?, "welcome_message"?, "rules"? }`                  | 1. `OWNER`/`ADMIN` requis. 2. `ConversationSetting.objects.update_or_create(conversation, user=<OWNER du fil>, defaults={...})` — toujours la ligne de l'OWNER (§0), `welcome_message`/`rules` dans `custom_settings`.                                                                                                                                                                                      | **200** `{ visibility, locked, max_members, welcome_message, rules }`      | 400/403/404            |
| C4  | `GET /conversations/{id}/members` (MSG-44)                   | `messaging.member.read`         | Query `active` (défaut `true`)                                                                | Membre actif requis (404 sinon). Liste `ConversationMember` du fil.                                                                                                                                                                                                                                                                                                                                         | **200** `{ "results": [{ user_id, username, role, joined_at, left_at }] }` | 404                    |
| C5  | `POST /conversations/{id}/members` (MSG-44)                  | `messaging.member.manage`       | `{ "user_id", "role": "MEMBER" }`                                                             | 1. Appelant `OWNER`/`ADMIN` requis. 2. `role` ∈ `{MEMBER, READ_ONLY}` seulement (un ADMIN ne peut pas ajouter un co-OWNER/ADMIN directement, §0). 3. `allow_group_invites=false` ou bloqué → 403 `USER_BLOCKED`/`INVITE_REFUSED`. 4. `max_members` atteint → 409 `GROUP_FULL`. 5. Déjà membre actif → 409 `ALREADY_MEMBER`.                                                                                 | **201** `{ user_id, role, joined_at }`                                     | 400/403/404/409        |
| C6  | `PATCH /conversations/{id}/members/{user_id}` (MSG-47/48/56) | `messaging.member.manage`       | `{ "role"?, "username"? }`                                                                    | 1. `role=OWNER` → **transfert** : seul l'`OWNER` actuel peut le faire (403 sinon), ancien `OWNER` devient `ADMIN`. 2. Autre changement de rôle : `OWNER` illimité ; `ADMIN` seulement sur `MEMBER`/`READ_ONLY` (jamais sur `OWNER`/`ADMIN`, 403). 3. `username` : soi-même ou `OWNER`/`ADMIN`.                                                                                                              | **200** `{ user_id, role, username }`                                      | 400/403/404            |
| C7  | `DELETE /conversations/{id}/members/{user_id}` (MSG-45)      | `messaging.member.manage`       | —                                                                                             | `OWNER`/`ADMIN` requis ; cible `OWNER` → 403 (transfert d'abord) ; `ADMIN` ne retire pas un autre `ADMIN` (403). `active=False`, `left_at=now()` (jamais de suppression de ligne).                                                                                                                                                                                                                          | **200** `{ "removed": true }`                                              | 403/404                |
| C8  | `POST /conversations/{id}/leave` (MSG-46)                    | `messaging.conversation.read`   | —                                                                                             | Appelant `OWNER` → 403 `OWNER_MUST_TRANSFER`. Sinon `active=False`, `left_at=now()`.                                                                                                                                                                                                                                                                                                                        | **200** `{ "left": true }`                                                 | 403/404                |




### 3.2 Vague D — Accusés (REST)


| #   | Route                                                     | Perm                                     | Requête                      | Flux serveur                                                                                                                                                                                     | Réponse                             | Erreurs spécifiques |
| --- | --------------------------------------------------------- | ---------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------- | ------------------- |
| D1  | `POST /messages/{id}/delivered` (MSG-61)                  | `messaging.receipt.update`               | — (corps ignoré, §0)         | Membre actif du fil requis (404 sinon). `MessageRead.objects.update_or_create(message, user, device=current_device(request), defaults={"delivered_at": now()})`. Diffuse `receipt.updated` (WS). | **200** `{ "delivered_at": "..." }` | 404                 |
| D2  | `POST /messages/{id}/read` (MSG-62/63/64)                 | `messaging.receipt.update`               | —                            | Membre actif requis. Si `read_receipts_enabled=false` (privacy appelant) → **200** silencieux, `read_at` **non** posé. Sinon upsert `read_at=now()`, diffuse `receipt.updated`.                  | **200** `{ "read_at": "..."|null }` | 404                 |
| D3  | `POST /conversations/{id}/read` (MSG-66)                  | `messaging.receipt.update`               | `{ "last_read_message_id" }` | Membre actif requis. Marque lu (si privacy autorise) tous les messages `sent_at ≤` celui visé, `ConversationMember.unread_count=0`, `last_read_message=<id>`.                                    | **200** `{ "unread_count": 0 }`     | 400/404             |
| D4  | `GET /conversations/{id}/messages?after=` (MSG-70, delta) | `messaging.message.read` (déjà existant) | Query `after` (ISO datetime) | Même vue que l'historique (jour 25), tri **ascendant** `sent_at` quand `after` est fourni (vs `before` = descendant).                                                                            | **200** — shape historique jour 25  | 404                 |




### 3.3 WebSocket — `/ws/v1/messaging/` (MSG-59/60/65/68/69/71/72)

Même patron que `PresenceConsumer` (PRES-A) : JWT via `?token=` (ou `Authorization: Bearer`), portes AUTH-F et permission `messaging.conversation.read` vérifiées dans `connect()` (fermeture `4401`/`4403` sinon, comme PRES-A).

**Client → serveur**

```json
{ "type": "subscribe", "conversation_ids": ["<uuid>", "..."] }
{ "type": "unsubscribe", "conversation_ids": ["<uuid>", "..."] }
{ "type": "PING" }
```

`subscribe` : pour chaque id, `group_add("conversation.{id}", channel_name)` **seulement** si l'appelant est `ConversationMember(active=True)` de ce fil — les autres ids sont silencieusement ignorés (pas de fuite d'existence, cohérent avec le 404 REST).

**Serveur → client** (poussés par `realtime_service.py` depuis les services REST existants — le consumer ne réimplémente aucune logique métier)

```json
{ "type": "message.created", "conversation_id": "...", "message": { ... } }
{ "type": "message.updated", "conversation_id": "...", "message": { ... } }
{ "type": "message.deleted", "conversation_id": "...", "message_id": "...", "scope": "SELF|EVERYONE" }
{ "type": "receipt.updated", "message_id": "...", "user_id": "...", "delivered_at": "...", "read_at": "..." }
{ "type": "PONG" }
```

**Erreurs :** `4401` (JWT absent/invalide), `4403` (`TOS_REQUIRED`/`ONBOARDING_REQUIRED`/`FORBIDDEN`, message d'erreur JSON envoyé avant fermeture, comme PRES-A).

---



## 4. Tests nouveaux



### `test_messaging_c.py`


| Cas                                                               | Attendu                                                                                                                                        |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| POST conversations GROUP, 2 membres valides                       | 201, `owner=créateur`, 1 `OWNER` + 2 `MEMBER`, `ConversationKey` créée                                                                         |
| POST conversations GROUP, membre avec `allow_group_invites=false` | skip silencieux, groupe créé quand même avec les membres restants                                                                              |
| POST conversations GROUP, tous les membres invalides              | 400 `VALIDATION_ERROR`                                                                                                                         |
| PATCH conversation (titre), par MEMBER                            | 403                                                                                                                                            |
| PATCH conversation (titre), par ADMIN                             | 200                                                                                                                                            |
| PATCH group-settings `locked=true`, puis envoi par MEMBER         | 403 `CONVERSATION_LOCKED` (régression delta message_service)                                                                                   |
| GET members                                                       | liste correcte, rôles corrects                                                                                                                 |
| POST members, `max_members` atteint                               | 409 `GROUP_FULL`                                                                                                                               |
| POST members, déjà membre                                         | 409 `ALREADY_MEMBER`                                                                                                                           |
| PATCH member role=OWNER, appelant = OWNER actuel                  | transfert, ancien OWNER devient ADMIN                                                                                                          |
| PATCH member role=OWNER, appelant = ADMIN                         | 403                                                                                                                                            |
| DELETE member (cible OWNER)                                       | 403                                                                                                                                            |
| DELETE member par ADMIN sur un autre ADMIN                        | 403                                                                                                                                            |
| POST leave, appelant OWNER                                        | 403 `OWNER_MUST_TRANSFER`                                                                                                                      |
| POST leave, MEMBER                                                | 200, `active=False`, `left_at` posé, historique toujours lisible (MSG-57)                                                                      |
| POST .../messages sur un GROUP                                    | 201, `encrypted_content` déchiffrable via la clé de fil, **aucune** garde crypto par appareil (sender sans identité Signal → passe quand même) |
| GET message d'un GROUP                                            | contenu redonné en clair (déchiffré serveur), pas le blob chiffré brut                                                                         |
| `/api/schema/`                                                    | contient `/api/v1/conversations/{id}/members`                                                                                                  |




### `test_messaging_d.py`


| Cas                                                                                 | Attendu                                                           |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| POST delivered                                                                      | `MessageRead.delivered_at` posé, device = session (corps ignoré)  |
| POST read, `read_receipts_enabled=true`                                             | `read_at` posé                                                    |
| POST read, `read_receipts_enabled=false`                                            | 200, `read_at` reste `null`                                       |
| POST conversations/{id}/read                                                        | `unread_count=0`, `MessageRead` créés pour les messages concernés |
| GET messages `after=`                                                               | tri ascendant, ne renvoie que les messages postérieurs            |
| WS connect sans JWT                                                                 | fermeture `4401`                                                  |
| WS connect, self sans CGU                                                           | fermeture `4403`                                                  |
| WS subscribe à un fil dont on n'est pas membre                                      | pas d'erreur, mais aucun événement reçu pour ce fil (silencieux)  |
| WS : `POST .../messages` déclenche `message.created` reçu par l'autre membre abonné | via `WebsocketCommunicator` (patron `test_pres_a.py`)             |
| WS : `POST .../delivered` déclenche `receipt.updated`                               | idem                                                              |
| PING/PONG                                                                           | round-trip                                                        |


---



## 5. Vérif manuelle

```powershell
python manage.py check
pytest apps/iam/tests/test_messaging_c.py apps/iam/tests/test_messaging_d.py apps/iam/tests/test_messaging_a.py apps/iam/tests/test_messaging_b.py apps/iam/tests/test_crypto_a.py apps/iam/tests/test_pres_a.py --reuse-db
```

---



## Checklist jour 26

- [x] `POST /conversations` accepte `type=GROUP` (filtrage membres, `ensure_conversation_key`)
- [x] `wrap_with_key`/`unwrap_with_key` ajoutés à `apps/crypto/services/wrapping.py`
- [x] `send_message` : branchement PRIVATE (inchangé) / GROUP (chiffrement clé de fil, aucune garde par appareil)
- [x] 7 routes MESSAGERIE-C vertes (metadata, group-settings, membres ×4, leave)
- [x] Garde `locked` de jour 25 corrigée (ligne OWNER, pas « n'importe quelle ligne »)
- [x] `MessagingConsumer` (WS) sur le patron `PresenceConsumer`, subscribe filtré par membership
- [x] 3 routes REST accusés + `after=` catch-up
- [x] `realtime_service.py` diffuse `message.created/updated/deleted`/`receipt.updated` depuis les services REST existants
- [x] `test_messaging_c.py` + `test_messaging_d.py`
- [x] 0 régression MESSAGERIE-A/B, CRYPTO-A, PRES-A
- [x] 0 nouvelle migration, 0 nouvelle permission
- [x] SIRH non modifié

---



## Interdits

- `type=AI` — toujours pas de compte bot
- `GET /conversations/discoverable` — hors MVP (business doc : optionnel phase 3b)
- Groupe temporaire + job de clôture (MSG-58) — `run_scheduled_jobs` pas prêt pour un vrai scheduler
- Messages `SYSTEM` auto join/leave/transfert — différé (MSG-54 le dit optionnel)
- `GET /crypto/conversations/{id}/key` (CRY-10) — jamais nécessaire dans ce modèle (serveur déchiffre pour servir)
- Réactions/typing en temps réel — jour 27 (MESSAGERIE-E/G)
- `docker compose down -v`
- Changer le SIRH

---



## Après le jour 26

Jour 27 : **MESSAGERIE-E (partiel), F, G** — réactions, transfert, épinglage de message, signets, sondages (GROUP only), blocage/signalement (routes de gestion — `blocked_users` déjà peuplée manuellement en jour 25/26 pour les tests), indicateurs de saisie (Redis, WS). Lab pas encore écrit.

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
| 25     | MESSAGERIE-R, A, B                             | §7 1-to-1                             |
| **26** | **MESSAGERIE-C, D** (ce plan)                  | §7 groupes + temps réel               |
| 27     | MESSAGERIE-E (partiel), F, G                   | §7 enrichissements                    |
| 28     | MEDIA-B, C, D, E                               | §4 album / vocal / coffre             |
| 29     | APPELS-R, A, B, C                              | §8 appel 1-1 + `CALL_CANCELLED`       |
| 30     | APPELS-D, E, G                                 | §8 écran / CR                         |


**Total : 31 plans (jours 0 à 30).**
Déjà clos : **27** (0–26). Restant : **4** (27–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.