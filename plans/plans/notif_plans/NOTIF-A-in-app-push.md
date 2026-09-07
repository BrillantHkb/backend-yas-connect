# NOTIF-A — In-app + push (NOTIF-01 … 16)

**Produit :** YAS Connect uniquement.  
**Préalable :** **NOTIF-R** + **AUTH-E** (`devices.push_token`) + [CRYPTO-00](../crypto_plans/CRYPTO-00-modele-chiffrement.md).  
**Attributs :** [NOTIF-catalogue-tables.md](../../catalogues/NOTIF-catalogue-tables.md).  
**Models :** [code/notif_models.py](../code/notif_models.py).

**Périmètre :** centre de notifications, badge unread, push FCM/APNs, événements **message** et **appel**.  
C’est le transverse qui fait **sonner l’app fermée** — pas un 6ᵉ module métier.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **NOTIF-01** | **Gardé** | Inbox paginée (keyset `created_at`) | lecture `notifications` |
| **NOTIF-02** | **Gardé** | Compteur non lus | `read_at IS NULL` |
| **NOTIF-03** | **Gardé** | Marquer une notif lue | `read_at` |
| **NOTIF-04** | **Gardé** | Tout marquer lu | `read_at` en masse |
| **NOTIF-05** | **Gardé** | GET / PATCH préférences | `notification_preferences` |
| **NOTIF-06** | **Gardé** | Seed prefs via `provision_user_rows` (AUTH-A seed, AUTH-D, ADMIN-A) | 1 ligne 1-1 |
| **NOTIF-07** | **Gardé** | `emit(user, type, …)` idempotent par `collapse_key` récent | INSERT ou skip |
| **NOTIF-08** | **Gardé** | Push si `push_enabled` + token non vide + hors DND | `pushed_at` |
| **NOTIF-09** | **Gardé** | DND : `quiet_hours_*` dans le TZ des prefs IAM | skip push (in-app OK) |
| **NOTIF-10** | **Gardé** | Mute fil : `conversation_settings.muted` → pas d’emit message | — |
| **NOTIF-11** | **Gardé** | Event `MESSAGE_NEW` (hook MSG-67) | dest. membres sauf sender |
| **NOTIF-12** | **Gardé** | Event `MESSAGE_MENTION` si `allow_mentions` | dest. mentionné |
| **NOTIF-13** | **Gardé** | Event `CALL_INCOMING` (hook CALL-05 / CALL-44) | dest. callee / invitees |
| **NOTIF-14** | **Gardé** | Event `CALL_MISSED` (timeout / reject) | dest. callee |
| **NOTIF-15** | **Gardé** | Event `DEVICE_NEW` (AUTH-E, remplace stub mail) | dest. owner device |
| **NOTIF-16** | **Gardé** | Payload 1-to-1 **sans plaintext** (CRYPTO-00) | `title`/`body` génériques |

**Hors incrément :** e-mail SMTP de notif, SMS, Web Push navigateur distinct, collapse avancé multi-device, retry outbox dédiée.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Transport push | `devices.platform` : ANDROID/WEB/DESKTOP → **FCM** ; IOS → **APNs** ; OTHER ou token vide → in-app seulement |
| Priorité appel | `CALL_INCOMING` : priorité haute, **ignore DND** si `call_ring_enabled` (sonner quand même) |
| Priorité message | `MESSAGE_*` : DND + mute fil respectés |
| Preview groupe | `message_preview_enabled` : `body` peut contenir un extrait **déchiffré service** (fil GROUP) |
| Preview 1-to-1 | Toujours générique, même si preview enabled |
| Isolation | 404 si `user_id ≠ me` |
| WS | Optionnel : événement `notification.created` sur le socket user (PRES-A / messaging) — pas de WS notif dédié au MVP |
| Lab | `FCM_SERVER_KEY` / `APNS_KEY_PATH` vides → no-op push ; INSERT in-app **quand même** |

---

## Contrat HTTP

Préfixe `/api/v1`. Portes AUTH-F. Permission = tableau [NOTIF-routes](NOTIF-routes.md).

### NOTIF-01 — `GET /api/v1/notifications`

Query : `before` (keyset), `limit` (max 50), `unread_only`.

**200** `{ "results": [ { "id", "type", "title", "body", "payload", "read_at", "created_at" } ], "next_before" }`.

### NOTIF-02 — `GET /api/v1/notifications/unread-count`

**200** `{ "count": 0 }`.

### NOTIF-03 — `POST /api/v1/notifications/{id}/read`

**204**. Idempotent si déjà lu. **404** si pas à soi.

### NOTIF-04 — `POST /api/v1/notifications/read-all`

**204**. Pose `read_at=now()` sur les non lus de `me`.

### NOTIF-05 — `GET` / `PATCH /api/v1/notification-preferences`

GET **200** prefs. PATCH whitelist : `push_enabled`, `in_app_enabled`, `call_ring_enabled`, `message_preview_enabled`, `quiet_hours_enabled`, `quiet_hours_start`, `quiet_hours_end`.

---

## Hooks producteurs (pas d’HTTP)

| Source | Quand | `type` | Destinataires | `payload` (ids seulement) |
|--------|-------|--------|---------------|---------------------------|
| MESSAGERIE-D MSG-67 | Message persisté | `MESSAGE_NEW` | Membres actifs ≠ sender, non mutés | `conversation_id`, `message_id` |
| MESSAGERIE-E | Mention | `MESSAGE_MENTION` | User mentionné si `allow_mentions` | + `mentioned` |
| APPELS-A CALL-05 | → `RINGING` | `CALL_INCOMING` | Invitees | `call_id`, `call_type` |
| APPELS-A CALL-08 | Timeout / miss | `CALL_MISSED` | Callee | `call_id` |
| AUTH-E | Nouvel appareil | `DEVICE_NEW` | Owner | `device_id` |

`collapse_key` : `msg:{conversation_id}` · `call:{call_id}` · `device:{device_id}`. Un push récent (ex. 30 s) avec la même clé **remplace** plutôt que d’empiler.

---

## Tests (minimum)

| Cas | Attendu |
|-----|---------|
| GET inbox autre user (id volé) | 404 |
| MESSAGE_NEW fil PRIVATE | `title` générique ; `payload` sans texte |
| Fil `muted` | 0 INSERT |
| `push_enabled=false` | INSERT in-app, `pushed_at` NULL |
| CALL_INCOMING + DND + `call_ring_enabled` | push quand même |
| `allow_calls=false` | pas d’emit (Appels refuse avant) |
| Sans token FCM (lab) | 201/204 HTTP prefs ; emit in-app OK |

---

## Critères de fin NOTIF-A

- [ ] Seed `seed_notifications` + prefs à la création user
- [ ] 6 routes vertes + isolation
- [ ] Hooks message + appel branchés (ou no-op documenté si module pas encore livré)
- [ ] CRYPTO-00 respecté sur PRIVATE
