# APPELS-A — Cycle de vie des appels (CALL-01 … 21)

**Produit :** YAS Connect uniquement.  
**Préalable :** **APPELS-R** + migrations 9 tables + **PROF-C** + **PRES-A** + Messagerie (message `CALL`).  
**Attributs :** [APPELS-catalogue-tables.md](../../catalogues/APPELS-catalogue-tables.md).  
**Models :** [code/calls_models.py](../code/calls_models.py).

**Périmètre :** création, sonnerie, acceptation, rejet, fin, historique, trace messagerie `type=CALL`.

---

## Cartographie


| ID          | Statut    | Comportement                                                           | Écritures                                     |
| ----------- | --------- | ---------------------------------------------------------------------- | --------------------------------------------- |
| **CALL-01** | **Gardé** | Créer appel 1-to-1 (`AUDIO` / `VIDEO`)                                 | `calls`, `call_participants`, `livekit_rooms` |
| **CALL-02** | **Gardé** | Créer conférence / réunion (`CONFERENCE`, `MEETING`) avec `member_ids` | idem                                          |
| **CALL-03** | **Gardé** | Créer salle crise (`CRISIS_ROOM`) — HOST = caller, plafond élevé       | idem                                          |
| **CALL-04** | **Gardé** | `room_id` UNIQUE généré serveur ; synchro `livekit_rooms.room_name`    | `room_id`, LiveKit API                        |
| **CALL-05** | **Gardé** | Status `CREATED` → `RINGING` après invitees notifiés ; push/WS `CALL_INCOMING` + identité | `calls.status`                                |
| **CALL-06** | **Gardé** | Callee accepte → `ACTIVE`, `started_at`                                | participants + status                         |
| **CALL-07** | **Gardé** | Callee rejette → `CANCELLED` (1-to-1) ou participant `left` (groupe)   | status / `left_at`                            |
| **CALL-08** | **Gardé** | Timeout sonnerie (`calls.ring_timeout_seconds`, défaut **45**) → `FAILED` / `CANCELLED` | job / Redis TTL                               |
| **CALL-09** | **Gardé** | Terminer appel (`ENDED`) : `ended_at`, `duration_seconds`              | `calls`                                       |
| **CALL-10** | **Gardé** | Historique perso (initiés + participés)                                | lecture                                       |
| **CALL-11** | **Gardé** | Détail appel (participant seulement)                                   | lecture                                       |
| **CALL-12** | **Gardé** | Message messagerie `type=CALL` + `call_id` + `metadata.event`          | `messages` (sans FK)                          |
| **CALL-13** | **Gardé** | Redis `call:{id}:status` TTL 5 min                                     | Redis                                         |
| **CALL-14** | **Gardé** | Respect `allow_calls` / blocage                                        | —                                             |
| **CALL-15** | **Gardé** | Plafond `max_participants`                                             | refus invite                                  |
| **CALL-16** | **Gardé** | Appel terminé non réouvrable                                           | **409**                                       |
| **CALL-17** | **Gardé** | `IN_MEETING` sur ACTIVE ; clear à ENDED                                | `users.status`                                |
| **CALL-18** | **Gardé** | Pagination historique keyset `created_at`                              | —                                             |
| **CALL-19** | **Gardé** | Filtres historique : status, call_type, missed                         | query                                         |
| **CALL-20** | **Gardé** | Portes AUTH-F                                                          | —                                             |
| **CALL-21** | **Gardé (MOB-PUSH)** | Quitte `RINGING` sans accept → `CALL_CANCELLED` (push+WS) **et** `CALL_MISSED` (inbox+bannière) | — |


**Hors incrément :** planification (`scheduled_calls`), file d’attente salle d’attente, appels PSTN.

**Delta MOB-PUSH (2026-09-11) :** identité appelant sur push **et** WS ; `CALL_CANCELLED` distinct de `CALL_MISSED` ; timeout configurable. Forme des push = [NOTIF-A](../notif_plans/NOTIF-A-in-app-push.md).

---



## Décisions figées


| Sujet           | Choix                                                                                                 |
| --------------- | ----------------------------------------------------------------------------------------------------- |
| Machine d’états | `CREATED` → `RINGING` → `ACTIVE` → `ENDED` ; branches `CANCELLED` / `FAILED`                          |
| 1-to-1          | Caller = HOST ; callee = PARTICIPANT à l’accept                                                       |
| Groupe          | Caller = HOST ; invités = PARTICIPANT jusqu’à promote                                                 |
| Durée           | `duration_seconds = ended_at - started_at` (0 si jamais ACTIVE)                                       |
| Timeout sonnerie | `system_settings` `calls.ring_timeout_seconds` (int, défaut **45**). Seuil produit : p95 latence push **> 15 s** (spike MOB-PUSH-00) → revoir la valeur |
| Identité appelant | Push **et** WS `CALL_INCOMING` / `CALL_CANCELLED` : `caller_id`, `caller_name`, `caller_avatar_id` optionnel. Obligatoire iOS (CallKit synchrone, pas de fetch réseau) |
| `CALL_CANCELLED` | Émis dès que l’appel quitte `RINGING` **sans** accept (raccroché caller, reject, timeout). Push `data` seul — **coupe** la sonnerie. Pas d’INSERT inbox. Même `collapse_key` `call:{id}` que incoming |
| `CALL_MISSED`   | Timeout, reject callee, **ou** raccroché caller tant que RINGING. Pose la bannière. `collapse_key` **`missed:{id}`** — **jamais** `call:{id}` (un cancel ne doit pas manger le manqué) |
| Messagerie      | À RINGING : `CALL_STARTED` / `CALL_INCOMING` ; à ENDED : `CALL_ENDED` + durée ; rejet / miss : `CALL_MISSED` |
| Idempotence     | `Idempotency-Key` optionnel sur `POST /calls`                                                         |
| LiveKit         | Création room API LiveKit dans la même transaction métier (rollback si échec SFU)                     |


---



## Contrat HTTP



### CALL-01/02 — `POST /api/v1/calls`

`required_permission = calls.call.create`.

**1-to-1**

```json
{
  "call_type": "VIDEO",
  "callee_id": "<uuid>",
  "conversation_id": "<uuid optionnel>"
}
```

**Groupe / réunion**

```json
{
  "call_type": "MEETING",
  "member_ids": ["<uuid>", "..."],
  "max_participants": 15,
  "title": "Stand-up NOC"
}
```

**201** : `{ id, room_id, status, call_type, livekit: { room_name }, participants[] }`.


| Erreur                     | Code                      |
| -------------------------- | ------------------------- |
| Callee `allow_calls=false` | **403** `CALLS_DISABLED`  |
| Blocage                    | **403** `USER_BLOCKED`    |
| Trop d’appels actifs       | **429** `TOO_MANY_CALLS`  |
| LiveKit down               | **503** `SFU_UNAVAILABLE` |




### CALL-06 — `POST /api/v1/calls/{id}/accept`

`calls.call.control`. Body optionnel `{ "device_id": "..." }`.  
**200** → `ACTIVE` + token join (ou redirect token endpoint).

### CALL-07 — `POST /api/v1/calls/{id}/reject`

`calls.call.control`. 1-to-1 → `CANCELLED` + message `CALL_MISSED`.  
Hooks NOTIF : `CALL_CANCELLED` **et** `CALL_MISSED` (clés distinctes).

### CALL-08 — Timeout sonnerie

Job / Redis TTL = `calls.ring_timeout_seconds` (défaut 45). Status `FAILED` ou `CANCELLED`.  
Même couple d’événements : `CALL_CANCELLED` + `CALL_MISSED`.

### CALL-09 — `POST /api/v1/calls/{id}/end`

`calls.call.control` — HOST ou dernier participant.  
Calcule durée, ferme LiveKit room, clear `IN_MEETING`, message `CALL_ENDED`.  
Si status encore `RINGING` (raccroché appelant) : **pas** `CALL_ENDED` métier sonnant — emit `CALL_CANCELLED` + `CALL_MISSED` (l’appel n’a jamais été ACTIVE).

### CALL-10 — `GET /api/v1/calls/history`

`calls.call.read`. Query : `status`, `call_type`, `missed=true`, `limit` 1–50, `cursor`.

### CALL-11 — `GET /api/v1/calls/{id}`

Détail + participants + room LiveKit (sans secrets). **404** si non participant.

---



## Événements WS (aperçu → plan C)

`CALL_INCOMING`, `CALL_CANCELLED`, `CALL_ACCEPTED`, `CALL_REJECTED`, `CALL_STARTED`, `CALL_ENDED`, `CALL_FAILED`.

Payload `CALL_INCOMING` / `CALL_CANCELLED` :

```json
{
  "call_id": "<uuid>",
  "call_type": "VIDEO",
  "caller_id": "<uuid>",
  "caller_name": "Jean Dupont",
  "caller_avatar_id": "<uuid|null>"
}
```

Même bloc sur le push ([NOTIF-A](../notif_plans/NOTIF-A-in-app-push.md) NOTIF-13 / 14b). Le chemin premier plan n’a **pas** de code identité séparé.

---



## Tests (A)


| Cas                 | Attendu                                         |
| ------------------- | ----------------------------------------------- |
| Create VIDEO 1-to-1 | 201, RINGING, 2 participants, livekit_rooms 1:1 |
| allow_calls=false   | 403                                             |
| Accept              | ACTIVE + started_at                             |
| End                 | ENDED + duration + message CALL                 |
| Re-end              | 409 CALL_CLOSED                                 |
| End tant que RINGING | `CALL_CANCELLED` + `CALL_MISSED` (pas sonnerie orpheline) |
| Timeout             | status fermé ; cancel **et** missed émis        |


