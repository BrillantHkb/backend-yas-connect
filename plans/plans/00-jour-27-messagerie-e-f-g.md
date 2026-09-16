# Jour 27 — MESSAGERIE-E (partiel) + F + G (enrichissements, blocage, typing)

**Statut :** à faire.
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.
**Préalable :** jours 0–26 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 26](00-jour-26-messagerie-c-d.md)). Toutes les 18 tables `apps.messaging` et les 18 permissions `messaging.*` existent depuis le jour 25 — ce jour n'en crée aucune de plus.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §7 — *messagerie, enrichissements*) :

| Fonction MVP                                    | Ticket                        | Statut             |
| ------------------------------------------------- | ------------------------------ | ------------------- |
| Groupes, temps réel, accusés                       | MESSAGERIE-C + D               | **fait** (jour 26)  |
| **Réactions, transfert, signets, sondages**        | **MESSAGERIE-E (partiel)**     | **ce jour**         |
| **Blocage utilisateur, signalement**               | **MESSAGERIE-F**               | **ce jour**         |
| **« En train d'écrire… »**                         | **MESSAGERIE-G**               | **ce jour**         |

**À quoi ça sert (MVP) :** dernier jour du module Messagerie proprement dit (jour 28+ = Médias avancés, Appels). Ferme les usages quotidiens attendus d'un chat moderne — réagir, transférer, mettre de côté, sonder un groupe, bloquer un contact gênant, signaler un abus, voir que l'autre est en train d'écrire. `MESSAGERIE-E` est marqué **« partiel »** dans le calendrier parce que le business doc lui-même sépare « MVP » (réactions, transfert, signets, sondages) de « après le MVP » (épingles de message, localisation, type IA) — voir §0.

**Plan métier (code à coller) :** [MESSAGERIE-E-contenu-enrichi.md](messaging_plans/MESSAGERIE-E-contenu-enrichi.md) (MSG-73…88, **hors** MSG-77/78 épingles, MSG-86 localisation, MSG-87 appel, MSG-88 IA — voir §0) + [MESSAGERIE-F-moderation-blocage.md](messaging_plans/MESSAGERIE-F-moderation-blocage.md) (MSG-89…98) + [MESSAGERIE-G-indicateurs-saisie.md](messaging_plans/MESSAGERIE-G-indicateurs-saisie.md) (MSG-99…104). Modèles : déjà tous créés (jour 25).
Chemins lab = ce fichier.

**Déjà en base / code :**

- Les 18 tables `apps.messaging` (jour 25) contiennent déjà `MessageReaction`, `MessageForward`, `MessageBookmark`, `MessagePoll`/`PollOption`/`PollVote`, `BlockedUser`, `ReportedMessage`. **0 nouvelle migration.**
- Les 18 permissions `messaging.*` (jour 25) contiennent déjà `message.react`, `message.forward`, `bookmark.manage`, `poll.vote`, `block.manage`, `report.create`, `report.review`. **0 nouvelle permission.**
- `apps.messaging.services.realtime_service` (jour 26) : `_group_send` générique, prêt pour de nouveaux types d'événements (`reaction.updated`, `typing.updated`).
- `apps.messaging.consumers.MessagingConsumer` (jour 26) : `receive_json` déjà structuré en `if kind == ...` — ce jour y ajoute `typing.start`/`typing.stop`.
- `apps.crypto.services.wrapping.wrap_with_key`/`unwrap_with_key` + `apps.crypto.services.key_service.group_content_key` (jour 26) : réutilisés pour le transfert GROUP→GROUP (§0).
- `apps.iam.models.UserPreference.typing_indicator` + `PrivacySetting.typing_indicator_enabled` : déjà en base (PROF-B/C), jamais lus par Messagerie jusqu'ici.
- `django.core.cache.cache` : déjà l'abstraction Redis/LocMemCache utilisée partout (rate-limit, présence) — réutilisée pour le TTL typing, jamais de client Redis brut.

**Pas encore :** aucune route de gestion de blocage (`blocked_users` était déjà lisible/vérifiée depuis le jour 25 mais jamais peuplée par HTTP). Aucune route de signalement. Aucune réaction/transfert/signet/sondage. Aucun événement `typing.*`.

**Objectif du jour :**

1. **MESSAGERIE-E (partiel)** : réactions (2 routes), transfert (1 route), signets (3 routes), sondages (2 routes + extension de `POST .../messages` pour `type=POLL`).
2. **MESSAGERIE-F** : blocage (3 routes sous `/me/`), signalement (1 route + 2 routes admin).
3. **MESSAGERIE-G** : `typing.start`/`typing.stop`/`typing.updated` sur le WS existant, dédup TTL 5 s via `cache`.
4. Ne rien casser : MESSAGERIE-A/B/C/D (jours 25-26), CRYPTO-A, NOTIF-A.

**Hors jour 27 :** épingles de message (MSG-77/78 — le business doc les marque lui-même « après le MVP » ; `GET .../pinned-messages` reste câblé depuis le jour 25, toujours vide) ; localisation `type=LOCATION` (idem, « après le MVP ») ; référence appel `type=CALL` (module Appels, jour 29+) ; message IA `type=AI`, `ai_generated` (toujours pas de compte bot) ; modération réelle (masquer un message, suspendre un compte — MSG-97 le dit lui-même « hors scope », lien ADMIN-A) ; `run_scheduled_jobs`/anti-spam distribué (MSG-98 implémenté en comptage DB simple, pas Redis).

---

## 0. Corrections apportées au plan métier (avant de coder)

| Écart trouvé | Correction |
|---|---|
| MSG-75 « Transférer : crée message dans fil cible » — body `{"conversation_id"}` seul | Le business doc ne dit pas comment le contenu traverse deux domaines de chiffrement différents (`PRIVATE` = blob E2E opaque que le serveur ne peut **jamais** lire ; `GROUP` = clé de fil serveur). Tranché : `encrypted_content` devient un champ **optionnel** du corps — **obligatoire** dès que la source **ou** la cible est `PRIVATE` (le client, qui a déchiffré l'original, doit re-chiffrer lui-même pour la cible) ; **auto-recopié côté serveur** uniquement si source **et** cible sont `GROUP` (déchiffrement avec la clé du fil source, re-chiffrement avec celle du fil cible, transparent pour le client). |
| MSG-81 sondage : body `POST .../messages` avec `poll: {...}` | Confirmé implémentable tel quel — extension de `send_message` (jour 25/26), pas de nouvelle route. `type=POLL` interdit `encrypted_content` (les options sont en clair, MSG-81) ; `PRIVATE` → **400** `POLL_PRIVATE_FORBIDDEN` (déjà le message d'erreur nommé par le business doc). |
| MSG-82 vote : comportement single-choice non précisé (remplace ou cumule ?) | Tranché : chaque `POST /polls/{id}/votes` **remplace** l'intégralité du vote de l'appelant pour ce sondage (idempotent) — si `multiple_choices=false`, `option_ids` doit contenir exactement 1 id (400 sinon) ; si `true`, la liste envoyée remplace toutes les options précédemment votées par cet appelant. |
| MSG-98 « anti-spam signalements, max 10/user/jour » | Comptage direct sur `ReportedMessage.objects.filter(reported_by=user, created_at__gte=...).count()` (fenêtre glissante 24 h) — pas de compteur Redis dédié, cohérent avec l'échelle lab et le pattern déjà utilisé ailleurs (pas de sur-ingénierie). |
| MSG-99/103 « Redis `typing:{conv}:{user}` TTL 5 s » | Le TTL sert de **dédup** (ignorer un second `typing.start` du même user dans la fenêtre), pas de déclencheur d'auto-`typing.stop` (ça demanderait des notifications Redis keyspace, hors scope). Implémenté via `django.core.cache.cache` (déjà l'abstraction Redis/LocMem du projet), jamais un client Redis brut. Le client reste responsable d'envoyer `typing.stop` ou de laisser expirer côté UI avec `expires_in`. |
| Routes `/me/blocked-users` et `/me/message-bookmarks` | Nouveau fichier `apps/messaging/urls_me.py`, monté sur `api/v1/me/` — même pattern que `apps.annuaire.urls.me_competences` (chaque app contribue ses propres sous-routes `/me/`, pas de duplication dans `apps.iam.urls.me`). |
| Routes admin signalements | Nouveau fichier `apps/messaging/urls_admin.py`, monté sur `api/v1/admin/` — même pattern que les autres `admin_*.py` de `apps.iam`. |

---

## Pourquoi ce jour (dernier jour Messagerie avant Médias avancés / Appels)

Tout ce qui reste du module Messagerie tient dans les tables déjà créées au jour 25 et jamais exploitées : `message_reactions`, `message_forwards`, `message_bookmarks`, `message_polls`/`poll_options`/`poll_votes`, `blocked_users`, `reported_messages`. Rien de nouveau côté modèle ou RBAC — uniquement des routes et, pour le typing, un nouvel événement WS sur le consumer déjà livré au jour 26. C'est délibérément le jour le plus « léger » en risque architectural de tout le module, pour clore proprement avant d'attaquer Médias avancés (jour 28) et Appels (jour 29-30).

```text
JWT + HasPermission + portes AUTH-F. Appareil = request.auth.session.device_id (jamais le body).

Vague E (partiel) — Réactions, transfert, signets, sondages
    POST   /messages/{id}/reactions                   messaging.message.react
    DELETE /messages/{id}/reactions                    messaging.message.react
    POST   /messages/{id}/forward                       messaging.message.forward
    POST   /messages/{id}/bookmarks                      messaging.bookmark.manage
    DELETE /messages/{id}/bookmarks                       messaging.bookmark.manage
    GET    /me/message-bookmarks                          messaging.bookmark.manage
    POST   /polls/{id}/votes                               messaging.poll.vote
    POST   /polls/{id}/close                                messaging.poll.vote
    (extension) POST /conversations/{id}/messages type=POLL   messaging.message.send

Vague F — Blocage, signalement
    GET    /me/blocked-users                            messaging.block.manage
    POST   /me/blocked-users                              messaging.block.manage
    DELETE /me/blocked-users/{user_id}                      messaging.block.manage
    POST   /messages/{id}/reports                            messaging.report.create
    GET    /admin/reported-messages                            messaging.report.review
    PATCH  /admin/reported-messages/{id}                         messaging.report.review

Vague G — Typing (WS uniquement, pas de REST)
    typing.start / typing.stop   (client → serveur)
    typing.updated                (serveur → autres membres actifs, jamais l'émetteur)

Hors jour 27
    Épingles message, localisation, type=CALL/AI, modération réelle (masquer/suspendre)
```

---

## Paliers (figés pour ce jour)

| Sujet | Choix jour 27 | Plus tard |
| ----- | ------------- | --------- |
| Réactions | `MessageReaction` unique `(message,user,emoji)` ; `POST` idempotent (rejouer le même emoji = pas de doublon, 200) ; `DELETE` query `emoji` | — |
| Transfert | Appelant membre actif **source et cible** (404 sinon). `encrypted_content` du corps obligatoire si source **ou** cible `PRIVATE` ; auto-recopié si les deux sont `GROUP` (déchiffre avec la clé source, re-chiffre avec la clé cible). `MessageForward` + nouveau `Message(forwarded=True)` dans le fil cible, mêmes règles d'envoi que MSG-22 (locked/read-only/etc.) | — |
| Signets | `MessageBookmark` unique `(user,message)` ; `POST` upsert la `note` ; `GET /me/message-bookmarks` toutes conversations confondues (juste besoin d'être resté membre du fil au moment de la lecture — sinon filtré) | — |
| Sondage | Body `POST .../messages` : `{"type":"POLL","poll":{"question","multiple_choices","options":[...]}}`. `PRIVATE` → 400 `POLL_PRIVATE_FORBIDDEN`. `encrypted_content` doit être absent/vide pour `POLL` (question et options toujours en clair, MSG-81) | — |
| Vote | `POST /polls/{id}/votes {"option_ids":[...]}` **remplace** tout le vote de l'appelant sur ce sondage. `multiple_choices=false` + `len(option_ids) != 1` → 400. Membre actif du **groupe** requis. Sondage `closed_at` déjà posé → 403 `POLL_CLOSED` | — |
| Clôture sondage | `POST /polls/{id}/close` : créateur du sondage **ou** `OWNER`/`ADMIN` du groupe. Idempotent (rejouer = pas d'erreur) | — |
| Blocage | `BlockedUser` unique `(blocker,blocked)`. Se bloquer soi-même → 400. Déjà bloqué → 409 `ALREADY_BLOCKED`. Bloquer **n'affecte jamais** les groupes existants (seulement la création de nouveaux fils `PRIVATE`, déjà vérifié depuis le jour 25) | Effet sur Appels : jour 29+ |
| Signalement | `ReportedMessage(status=PENDING)`. `reason` obligatoire (400 sinon). Max **10/jour/utilisateur** (comptage DB, §0). Membre du fil du message requis (404 sinon) | — |
| Modération admin | `GET /admin/reported-messages?status=` (défaut `PENDING`). `PATCH` `{"status":"REVIEWED"\|"DISMISSED","note"?}` → `reviewed_by`, `reviewed_at`. **Aucune** action sur le message lui-même (MSG-97 hors scope) | Masquer message / suspendre user : lien ADMIN-A, hors MVP |
| Typing | WS uniquement. Émission bloquée si `UserPreference.typing_indicator=false` **ou** `PrivacySetting.typing_indicator_enabled=false` chez l'émetteur (silencieux, pas d'erreur). `cache.set(f"typing:{conv}:{user}", True, timeout=5)` en dédup ; diffusion à `conversation.{id}` sauf l'émetteur lui-même (filtré dans le consumer, pas dans `realtime_service`) | — |
| Portes AUTH-F | Toutes les routes REST + WS (déjà vérifiées au `connect()`, jour 26) | — |

---

## 1. Tables

**Aucune migration ce jour.** Toutes les tables nécessaires existent depuis le jour 25.

---

## 2. Fichiers

| Fichier | Rôle |
| ------- | ---- |
| `apps/messaging/services/reaction_service.py` | **nouveau.** `add_reaction`, `remove_reaction` |
| `apps/messaging/services/forward_service.py` | **nouveau.** `forward_message` |
| `apps/messaging/services/bookmark_service.py` | **nouveau.** `add_bookmark`, `remove_bookmark`, `list_bookmarks` |
| `apps/messaging/services/poll_service.py` | **nouveau.** `create_poll_message` (appelé par `message_service.send_message`), `vote`, `close_poll` |
| `apps/messaging/services/block_service.py` | **nouveau.** `list_blocked`, `block_user`, `unblock_user` |
| `apps/messaging/services/report_service.py` | **nouveau.** `create_report`, `list_reports` (admin), `review_report` (admin) |
| `apps/messaging/services/typing_service.py` | **nouveau.** `should_emit(user)`, `mark_typing(conversation_id, user)` (dédup cache) |
| `apps/messaging/services/message_service.py` | **delta.** `send_message` délègue à `poll_service.create_poll_message` si `type=POLL` |
| `apps/messaging/services/realtime_service.py` | **delta.** `broadcast_reaction_updated`, `broadcast_typing_updated` |
| `apps/messaging/consumers.py` | **delta.** `receive_json` gère `typing.start`/`typing.stop` ; méthode `typing_updated` (skip si `event["user_id"] == str(self.user.id)`) |
| `apps/messaging/serializers/reactions.py`, `serializers/forward.py`, `serializers/bookmarks.py`, `serializers/polls.py`, `serializers/blocking.py`, `serializers/reports.py` | **nouveau.** shapes DRF |
| `apps/messaging/views/reactions.py`, `views/forward.py`, `views/bookmarks.py`, `views/polls.py`, `views/blocking.py`, `views/reports.py` | **nouveau.** vues |
| `apps/messaging/urls.py` | **delta.** + routes réactions/forward/pins-bookmarks/polls |
| `apps/messaging/urls_me.py` | **nouveau.** blocage + signets, monté sur `api/v1/me/` |
| `apps/messaging/urls_admin.py` | **nouveau.** signalements admin, monté sur `api/v1/admin/` |
| `config/urls.py` | **delta.** 2 nouveaux `include()` |
| `apps/iam/tests/test_messaging_e.py`, `test_messaging_f.py`, `test_messaging_g.py` | **nouveau.** |

---

## 3. Contrat HTTP

Préfixe `/api/v1`. JWT + portes AUTH-F. **401** sans JWT, **403** `FORBIDDEN`/`TOS_REQUIRED`/`ONBOARDING_REQUIRED` (toutes les routes, non répété ci-dessous). Appareil = session courante (jamais un `device_id` du corps).

### 3.1 Vague E — Réactions, transfert, signets, sondages

| # | Route | Perm | Requête | Flux serveur | Réponse | Erreurs spécifiques |
|---|-------|------|---------|---------------|---------|----------------------|
| E1 | `POST /messages/{id}/reactions` (MSG-73) | `messaging.message.react` | `{ "emoji": "👍" }` | Membre actif du fil requis (404 sinon). `MessageReaction.objects.get_or_create(message,user,emoji)`. Diffuse `reaction.updated`. | **201** `{ "emoji", "user_id" }` | 400 `VALIDATION_ERROR`, 404 |
| E2 | `DELETE /messages/{id}/reactions` (MSG-74) | `messaging.message.react` | Query `emoji` | Membre actif requis. Supprime la ligne si présente (idempotent). Diffuse `reaction.updated`. | **200** `{ "removed": true }` | 400, 404 |
| E3 | `POST /messages/{id}/forward` (MSG-75/76) | `messaging.message.forward` | `{ "conversation_id", "encrypted_content"? }` | 1. Membre actif source **et** cible requis (404 sinon).<br>2. Source `PRIVATE` ou cible `PRIVATE` → `encrypted_content` obligatoire (400 sinon, §0) ; sinon (GROUP→GROUP) auto-recopié via déchiffre+re-chiffre.<br>3. `Message.objects.create(conversation=cible, forwarded=True, ...)` + `MessageForward(original, new)`. Mêmes gardes que MSG-22 (locked/read-only) sur la cible. Diffuse `message.created` sur la cible. | **201** — shape message (jour 25) | 400, 403 `CONVERSATION_LOCKED`/`READ_ONLY_MEMBER`, 404 |
| E4 | `POST /messages/{id}/bookmarks` (MSG-79) | `messaging.bookmark.manage` | `{ "note": "" }` | Membre actif requis. `MessageBookmark.objects.update_or_create(user,message,defaults={"note":...})`. | **201** `{ "message_id", "note" }` | 404 |
| E5 | `DELETE /messages/{id}/bookmarks` (MSG-79) | `messaging.bookmark.manage` | — | Supprime si présent (idempotent). | **200** `{ "removed": true }` | 404 |
| E6 | `GET /me/message-bookmarks` (MSG-80) | `messaging.bookmark.manage` | Query `limit`/`before` | Liste les signets de l'appelant, tri `-created_at`, filtre ceux dont il n'est plus membre du fil. | **200** `{ "results": [{ message_id, conversation_id, note, created_at }] }` | — |
| E7 | `POST /polls/{id}/votes` (MSG-82) | `messaging.poll.vote` | `{ "option_ids": ["<uuid>", ...] }` | 1. Membre actif du **groupe** du sondage requis (404 sinon).<br>2. `closed_at` déjà posé → 403 `POLL_CLOSED`.<br>3. `multiple_choices=false` et `len(option_ids) != 1` → 400.<br>4. Remplace tout le vote de l'appelant (supprime ses `PollVote` existants sur ce sondage, recrée pour `option_ids`), recalcule `vote_count` des options touchées. | **200** `{ "option_ids": [...] }` | 400, 403 `POLL_CLOSED`, 404 |
| E8 | `POST /polls/{id}/close` (MSG-83) | `messaging.poll.vote` | — | Créateur du sondage **ou** `OWNER`/`ADMIN` du groupe requis (403 sinon). `closed_at=now()` (idempotent). | **200** `{ "closed_at": "..." }` | 403, 404 |
| E9 | `POST /conversations/{id}/messages` `type=POLL` (MSG-81, delta) | `messaging.message.send` | `{ "type": "POLL", "poll": { "question", "multiple_choices", "options": ["...", ...] } }` | 1. `conversation.type != GROUP` → 400 `POLL_PRIVATE_FORBIDDEN`.<br>2. `encrypted_content` présent → 400 (question/options toujours en clair).<br>3. `question` non vide, `options` ≥ 2 → sinon 400.<br>4. `Message.objects.create(type=POLL)` + `MessagePoll` + `PollOption` par option, dans la transaction d'envoi (jour 25/26 inchangée sinon). | **201** — shape message + `poll: { id, question, multiple_choices, options: [{id,label,vote_count}] }` | 400 `POLL_PRIVATE_FORBIDDEN`/`VALIDATION_ERROR` |

### 3.2 Vague F — Blocage, signalement

| # | Route | Perm | Requête | Flux serveur | Réponse | Erreurs spécifiques |
|---|-------|------|---------|---------------|---------|----------------------|
| F1 | `GET /me/blocked-users` (MSG-91) | `messaging.block.manage` | — | Liste `BlockedUser(blocker=appelant)`. | **200** `{ "results": [{ user_id, reason, created_at }] }` | — |
| F2 | `POST /me/blocked-users` (MSG-89) | `messaging.block.manage` | `{ "user_id", "reason": "" }` | `user_id == appelant` → 400. Déjà bloqué → 409 `ALREADY_BLOCKED`. `BlockedUser.objects.create(...)`. | **201** `{ "user_id", "reason" }` | 400, 404, 409 `ALREADY_BLOCKED` |
| F3 | `DELETE /me/blocked-users/{user_id}` (MSG-90) | `messaging.block.manage` | — | Supprime si présent (idempotent). | **200** `{ "unblocked": true }` | — |
| F4 | `POST /messages/{id}/reports` (MSG-93/94/98) | `messaging.report.create` | `{ "reason": "..." }` | Membre actif du fil requis (404 sinon). `reason` non vide (400 sinon). ≥ 10 signalements par l'appelant sur les dernières 24h → 429 `REPORT_RATE_LIMITED`. `ReportedMessage(status=PENDING)`. | **201** `{ "id", "status" }` | 400, 404, 429 `REPORT_RATE_LIMITED` |
| F5 | `GET /admin/reported-messages` (MSG-95) | `messaging.report.review` | Query `status` (défaut `PENDING`) | Liste filtrée, tri `-created_at`. | **200** `{ "results": [{ id, message_id, reason, status, reported_by, created_at }] }` | — |
| F6 | `PATCH /admin/reported-messages/{id}` (MSG-96) | `messaging.report.review` | `{ "status": "REVIEWED"\|"DISMISSED", "note"? }` | `reviewed_by=appelant`, `reviewed_at=now()`. | **200** `{ "id", "status", "reviewed_at" }` | 400, 404 |

### 3.3 WebSocket — Vague G (typing, MSG-99…104)

Même consumer que MESSAGERIE-D (`/ws/v1/messaging/`), même souscription (`subscribe` par `conversation_id`).

**Client → serveur**

```json
{ "type": "typing.start", "conversation_id": "<uuid>", "activity": "TEXT", "reply_to_message_id": null }
{ "type": "typing.stop", "conversation_id": "<uuid>" }
```

`activity` ∈ `{TEXT, VOICE, CAMERA}`. Émetteur doit être membre actif du fil (silencieux sinon, comme `subscribe`).

**Serveur → autres membres actifs (jamais l'émetteur)**

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

**Silencieux (aucun événement) si :** émetteur non membre actif ; `UserPreference.typing_indicator=false` ; `PrivacySetting.typing_indicator_enabled=false` ; dédup `cache` actif (déjà émis il y a < 5 s pour ce `(conversation,user)`, `typing.start` répété sans effet — `typing.stop` n'est jamais dédupliqué).

---

## 4. Tests nouveaux

### `test_messaging_e.py`

| Cas | Attendu |
| --- | ------- |
| POST reaction, rejouer le même emoji | 201 puis 201 idempotent, 1 seule ligne `MessageReaction` |
| DELETE reaction absente | 200 idempotent |
| POST forward GROUP→GROUP sans `encrypted_content` | 201, contenu recopié et re-déchiffrable dans le fil cible |
| POST forward PRIVATE→GROUP sans `encrypted_content` | 400 `VALIDATION_ERROR` |
| POST forward avec `encrypted_content` fourni | 201, contenu du corps utilisé tel quel (pas de recopie serveur) |
| POST bookmark puis GET /me/message-bookmarks | signet présent |
| DELETE bookmark | retiré de la liste |
| POST message type=POLL sur PRIVATE | 400 `POLL_PRIVATE_FORBIDDEN` |
| POST message type=POLL sur GROUP | 201, `MessagePoll` + `PollOption` créées |
| POST poll vote, multiple_choices=false, 2 options | 400 `VALIDATION_ERROR` |
| POST poll vote puis revote pour une autre option | ancien vote supprimé, nouveau compté, `vote_count` à jour |
| POST poll vote sur sondage clos | 403 `POLL_CLOSED` |
| POST poll close par non-créateur/non-admin | 403 |
| POST poll close par OWNER du groupe | 200, `closed_at` posé |
| `/api/schema/` | contient `/api/v1/polls/{id}/votes` |

### `test_messaging_f.py`

| Cas | Attendu |
| --- | ------- |
| POST blocked-users vers soi-même | 400 |
| POST blocked-users, rejouer | 409 `ALREADY_BLOCKED` |
| GET blocked-users | liste correcte |
| DELETE blocked-users | débloqué, un nouveau fil PRIVATE redevient possible |
| POST reports, `reason` vide | 400 |
| POST reports ×11 en 24h | la 11ᵉ → 429 `REPORT_RATE_LIMITED` |
| GET admin/reported-messages sans perm review | 403 `FORBIDDEN` |
| GET admin/reported-messages?status=PENDING | liste filtrée |
| PATCH admin/reported-messages | `status`/`reviewed_by`/`reviewed_at` posés |

### `test_messaging_g.py`

| Cas | Attendu |
| --- | ------- |
| WS typing.start → autre membre reçoit typing.updated | via `WebsocketCommunicator` |
| WS typing.start → émetteur ne reçoit pas son propre événement | `receive_nothing` sur la connexion émettrice |
| WS typing.start répété < 5s | un seul `typing.updated` reçu (dédup cache) |
| WS typing.start, `typing_indicator=false` (prefs) | rien émis |
| WS typing.start, `typing_indicator_enabled=false` (privacy) | rien émis |
| WS typing.stop | `typing.updated` reçu (jamais dédupliqué) |

---

## 5. Vérif manuelle

```powershell
python manage.py check
pytest apps/iam/tests/test_messaging_e.py apps/iam/tests/test_messaging_f.py apps/iam/tests/test_messaging_g.py apps/iam/tests/test_messaging_a.py apps/iam/tests/test_messaging_b.py apps/iam/tests/test_messaging_c.py apps/iam/tests/test_messaging_d.py --reuse-db
```

---

## Checklist jour 27

- [ ] Réactions (2 routes), idempotent
- [ ] Transfert (règle cross-chiffrement §0 respectée : PRIVATE ⇒ corps obligatoire, GROUP→GROUP ⇒ recopie serveur)
- [ ] Signets (3 routes)
- [ ] Sondages : `send_message` étendu (`type=POLL`, GROUP only) + vote (remplace) + close (créateur/admin)
- [ ] Blocage (3 routes sous `/me/`)
- [ ] Signalement (1 route + 2 admin), anti-spam 10/jour
- [ ] Typing WS (`typing.start`/`stop`/`updated`), dédup `cache` 5s, respecte prefs + privacy, jamais d'echo à l'émetteur
- [ ] `test_messaging_e/f/g.py`
- [ ] 0 régression MESSAGERIE-A/B/C/D, CRYPTO-A, NOTIF-A
- [ ] 0 nouvelle migration, 0 nouvelle permission
- [ ] SIRH non modifié

---

## Interdits

- Épingles de message (MSG-77/78), localisation (MSG-86), `type=CALL`/`AI` (MSG-87/88) — hors MVP ou modules pas encore livrés
- Modération réelle (masquer un message, suspendre un compte, MSG-97) — hors scope, lien ADMIN-A
- Client Redis brut pour le typing — toujours `django.core.cache.cache`
- `docker compose down -v`
- Changer le SIRH

---

## Après le jour 27

Jour 28 : **MEDIA-B, C, D, E** — album/galerie images, transcodage vidéo, transcription audio, GED documents. Premier jour Médias avancés depuis MEDIA-A (jour 22). Lab pas encore écrit.

---

## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour**. Le jour 2 (admin + Swagger) est un extra déjà clos.

| Jours  | Plan                                           | Ticket MVP                            |
| ------ | ----------------------------------------------- | -------------------------------------- |
| 0      | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health`    |
| 1–2    | AUTH-A ; admin + Swagger                        | Connexion locale ; lab admin           |
| 3–11   | D+B … AUTH-R                                    | §1 entrer + droits HTTP                |
| 12     | ADMIN-A                                         | §9 comptes                             |
| 13     | PROF-A                                          | §2 ma fiche / photo                    |
| 14     | PROF-B                                          | Préférences                            |
| 15     | PROF-C                                          | §2 visibilité                          |
| 16     | PRES-A                                          | §2 statut en ligne                     |
| 17     | ANNUAIRE-A                                      | §3 recherche collègue                  |
| 18     | ANNUAIRE-B                                      | §3 organigramme (types + arbre)        |
| 19     | ANNUAIRE-C                                      | §3 mutations / affectations            |
| 20     | ANNUAIRE-D                                      | §3 compétences / certifications        |
| 21     | CRYPTO-00                                       | §6 décision E2E                        |
| 22     | MEDIA-R + MEDIA-A                               | §4 upload (plafonds ; pas de reprise)  |
| 23     | NOTIF-R + NOTIF-A                               | §5 alertes + MOB-PUSH (VoIP / worker)  |
| 24     | CRYPTO-R + CRYPTO-A                             | Clés HTTP                              |
| 25     | MESSAGERIE-R, A, B                              | §7 1-to-1                              |
| 26     | MESSAGERIE-C, D                                 | §7 groupes + temps réel                |
| **27** | **MESSAGERIE-E (partiel), F, G** (ce plan)      | §7 enrichissements                     |
| 28     | MEDIA-B, C, D, E                                | §4 album / vocal / coffre              |
| 29     | APPELS-R, A, B, C                               | §8 appel 1-1 + `CALL_CANCELLED`        |
| 30     | APPELS-D, E, G                                  | §8 écran / CR                          |

**Total : 31 plans (jours 0 à 30).**
Déjà clos : **27** (0–26). Restant : **4** (27–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.
