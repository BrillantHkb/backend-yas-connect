# NOTIF-A — In-app + push (NOTIF-01 … 17)

**Produit :** YAS Connect uniquement.  
**Préalable :** **NOTIF-R** + **AUTH-E** (`devices.push_token` + **`voip_push_token`**) + [CRYPTO-00](../crypto_plans/CRYPTO-00-modele-chiffrement.md).  
**Attributs :** [NOTIF-catalogue-tables.md](../../catalogues/NOTIF-catalogue-tables.md).  
**Models :** [code/notif_models.py](../code/notif_models.py).  
**Delta MOB-PUSH (2026-09-11) :** routage iOS alert/VoIP, forme FCM, identité appelant, `CALL_CANCELLED`, `emitted_at`, `PUSH_TEST`. Reporté post-MVP : retrait notif lue ailleurs (`unread_count` plutôt qu’un dismiss silencieux iOS).

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
| **NOTIF-07** | **Gardé** | `emit(user, type, …)` idempotent par `collapse_key` **et type** récent | INSERT ou skip |
| **NOTIF-08** | **Gardé** | Push si `push_enabled` + jeton adéquat + hors DND (sauf sonnerie) | `pushed_at` |
| **NOTIF-09** | **Gardé** | DND : `quiet_hours_*` dans le TZ des prefs IAM | skip push (in-app OK) |
| **NOTIF-10** | **Gardé** | Mute fil : `conversation_settings.muted` → pas d’emit message | — |
| **NOTIF-11** | **Gardé** | Event `MESSAGE_NEW` (hook MSG-67) | dest. membres sauf sender |
| **NOTIF-12** | **Gardé** | Event `MESSAGE_MENTION` si `allow_mentions` | dest. mentionné |
| **NOTIF-13** | **Gardé** | Event `CALL_INCOMING` (hook CALL-05 / CALL-44) + identité appelant | dest. callee / invitees |
| **NOTIF-14** | **Gardé** | Event `CALL_MISSED` (timeout / reject / raccroché RINGING) | dest. callee |
| **NOTIF-14b** | **Gardé** | Event `CALL_CANCELLED` — **push + WS seulement**, pas d’INSERT inbox | dest. callee / invitees |
| **NOTIF-15** | **Gardé** | Event `DEVICE_NEW` (AUTH-E, remplace stub mail) | dest. owner device |
| **NOTIF-16** | **Gardé** | Payload 1-to-1 **sans plaintext** (CRYPTO-00) | `title`/`body` génériques |
| **NOTIF-17** | **Gardé** | `POST /me/devices/current/push-test` — type `PUSH_TEST`, pas d’inbox | — |

**Hors incrément :** e-mail SMTP de notif, SMS, Web Push navigateur distinct, `NOTIFICATION_DISMISS` / `unread_count` multi-appareils (post-MVP), retry outbox dédiée.

**Ordre de portage worker :** AUTH-28b (`voip_push_token`) **puis** routage iOS (#5) ; ensuite forme FCM + identité + `CALL_CANCELLED` + `emitted_at` ; puis NOTIF-17 ; timeout sonnerie = [APPELS-A](../calls_plans/APPELS-A-cycle-vie.md) CALL-08.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Transport | `ANDROID` / `WEB` / `DESKTOP` → **FCM** (`push_token`) ; `IOS` → **deux** sujets APNs ; `OTHER` ou jeton vide pour le canal visé → in-app seulement |
| iOS alert | Sujet `<bundle-id>` + `push_token`. Messages, mentions, manqué, device, test |
| iOS VoIP | Sujet **`<bundle-id>.voip`** + `voip_push_token`. **Uniquement** `CALL_INCOMING` et `CALL_CANCELLED` (`data` sans `alert`). Un VoIP pour un message = faute iOS (terminaison) |
| Priorité appel | `CALL_INCOMING` / `CALL_CANCELLED` : priorité haute, **ignore DND** si `call_ring_enabled` |
| Priorité message | `MESSAGE_*` : DND + mute fil respectés |
| Preview groupe | `message_preview_enabled` : `body` peut contenir un extrait **déchiffré service** (fil GROUP) |
| Preview 1-to-1 | Toujours générique, même si preview enabled |
| Identité appelant | `CALL_INCOMING` **et** `CALL_CANCELLED` (push **et** WS) : `caller_id`, `caller_name` (`display_name`), `caller_avatar_id` optionnel. CRYPTO-00 n’interdit pas : signalisation d’appel hors modèle E2E |
| `CALL_CANCELLED` vs `CALL_MISSED` | **Deux événements.** Cancel **coupe** la sonnerie (`data` seul, pas d’inbox). Missed **pose** une bannière (`notification`+`data` + INSERT). Un cancel **ne supprime jamais** un manqué |
| `collapse_key` | `msg:{conversation_id}` · `call:{call_id}` (incoming **et** cancel) · `missed:{call_id}` (missed **seul**) · `device:{device_id}` · `test:{device_id}`. **Ne pas** partager `call:{id}` avec `CALL_MISSED` (R4). **Ne pas** promettre l’ordre d’arrivée |
| `emitted_at` | ISO-8601 UTC sur **tous** les push. Latence client = réception − émission : utile en p50/p95 parc, **pas** mesure absolue (horloge appareil) |
| Isolation | 404 si `user_id ≠ me` |
| WS notif | Optionnel : `notification.created` sur le socket user — pas de WS notif dédié au MVP. Identité appel = WS `/ws/v1/calls/` ([APPELS-A](../calls_plans/APPELS-A-cycle-vie.md)) |
| Lab emit inbox | `FCM_SERVER_KEY` / `APNS_KEY_PATH` vides → no-op push ; INSERT in-app **quand même** (sauf `CALL_CANCELLED` / `PUSH_TEST`) |
| Lab push-test | **Pas** de 204 muet : **200** + statut `not_configured` par canal |

---

## Matrice de routage du worker

| Plateforme | Événement | Destination | Forme |
|------------|-----------|-------------|--------|
| **IOS** | `CALL_INCOMING`, `CALL_CANCELLED` | APNs **`.voip`** + `voip_push_token` | **`data` seul** |
| **IOS** | message, mention, manqué, device, test | APNs **alert** + `push_token` | `alert` + `data` |
| ANDROID / WEB / DESKTOP | `CALL_INCOMING`, `CALL_CANCELLED` | FCM + `push_token` | **`data` seul, priorité haute** |
| ANDROID / WEB / DESKTOP | le reste | FCM + `push_token` | `notification` + `data` + `android_channel_id` |
| Jeton vide pour le canal / `OTHER` | tout | — | in-app seulement (si le type INSERT) |

**Canaux FCM `android_channel_id` :** `messages` · `mentions` · `calls_missed` · `security`.  
Les canaux clients `calls` / `ongoing_call` (plein écran, FGS) **ne sont pas** posés par le worker : chemin `data` seul.

| Événement | Forme FCM / APNs alert | Canal Android | Inbox |
|-----------|------------------------|---------------|-------|
| `MESSAGE_NEW` | `notification` + `data` | `messages` | INSERT |
| `MESSAGE_MENTION` | `notification` + `data` | `mentions` | INSERT |
| `CALL_MISSED` | `notification` + `data` | `calls_missed` | INSERT |
| `DEVICE_NEW` | `notification` + `data` | `security` | INSERT |
| `PUSH_TEST` | `notification` + `data` (alert iOS / FCM) | `security` | **pas d’INSERT** |
| `CALL_INCOMING` | **`data` seul**, priorité haute | — | INSERT (centre) |
| `CALL_CANCELLED` | **`data` seul**, priorité haute | — | **pas d’INSERT** |

---

## Contrat HTTP

Préfixe `/api/v1`. Portes AUTH-F. Permission = tableau [NOTIF-routes](NOTIF-routes.md) (inbox) et [IAM-routes](../iam_plans/IAM-routes.md) #87 (push-test).

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

### NOTIF-17 — `POST /api/v1/me/devices/current/push-test`

`required_permission = iam.device.update`. JWT, appareil de **session**. Rate-limit **1 / 30 s** (429 `RATE_LIMITED`).

Query optionnelle : `channel=alert|voip|both` (défaut **`both`**). ANDROID/WEB/DESKTOP : un envoi FCM (ignore `channel`). IOS : `alert` → `push_token` ; `voip` → `voip_push_token` ; `both` → les deux **indépendamment** (un jeton manquant ne fait pas échouer l’autre).

Type **`PUSH_TEST` uniquement** — **interdit** de réutiliser `DEVICE_NEW` (fausse alerte sécu, mauvais deep-link, accoutumance). **Pas d’INSERT** inbox.

**200** (jamais 204) :

```json
{
  "success": true,
  "data": {
    "emitted_at": "2026-09-11T16:05:00Z",
    "channels": [
      { "channel": "apns_alert", "status": "sent" },
      { "channel": "apns_voip", "status": "skipped_no_token" }
    ]
  }
}
```

Android / Web / Desktop : une ligne `{ "channel": "fcm", "status": "…" }`.

| `status` | Sens |
|----------|------|
| `sent` | Dispatché vers FCM / APNs |
| `skipped_no_token` | Jeton vide pour ce canal |
| `not_configured` | `FCM_SERVER_KEY` / `APNS_KEY_PATH` vides (lab) |

---

## Hooks producteurs (pas d’HTTP)

| Source | Quand | `type` | Destinataires | `payload` | Inbox | `collapse_key` |
|--------|-------|--------|---------------|-----------|-------|----------------|
| MESSAGERIE-D MSG-67 | Message persisté | `MESSAGE_NEW` | Membres actifs ≠ sender, non mutés | `conversation_id`, `message_id` | oui | `msg:{conversation_id}` |
| MESSAGERIE-E | Mention | `MESSAGE_MENTION` | User mentionné si `allow_mentions` | + `mentioned` | oui | `msg:{conversation_id}` |
| APPELS-A CALL-05 | → `RINGING` | `CALL_INCOMING` | Invitees | `call_id`, `call_type`, `caller_id`, `caller_name`, `caller_avatar_id`? | oui | `call:{call_id}` |
| APPELS-A | Quitte `RINGING` sans accept | `CALL_CANCELLED` | Invitees | **même identité** que incoming | **non** | `call:{call_id}` |
| APPELS-A CALL-07/08/09 | Timeout, reject callee, ou raccroché caller tant que RINGING | `CALL_MISSED` | Callee | `call_id` (+ identité si déjà calculée) | oui | **`missed:{call_id}`** |
| AUTH-E | Nouvel appareil | `DEVICE_NEW` | Owner (autres appareils) | `device_id` | oui | `device:{device_id}` |
| NOTIF-17 | Push-test | `PUSH_TEST` | Appareil courant | `device_id` | **non** | `test:{device_id}` |

Tous les push portent aussi `emitted_at`.

`CALL_CANCELLED` et `CALL_MISSED` **partent tous les deux** dès que l’appel quitte `RINGING` sans accept. L’ordre d’arrivée n’est **pas** un contrat. Clés distinctes → un cancel `data` ne peut pas écraser la bannière manquée.

Un push récent (ex. 30 s) avec la **même** `collapse_key` **et le même** `type` **remplace** plutôt que d’empiler (inbox). Incoming puis cancel partagent `call:{id}` **côté gateway** (le cancel remplace la sonnerie) mais pas le même `type` inbox (cancel n’INSERT pas).

---

## Tests (minimum)

| Cas | Attendu |
|-----|---------|
| GET inbox autre user (id volé) | 404 |
| MESSAGE_NEW fil PRIVATE | `title` générique ; `payload` sans texte |
| Fil `muted` | 0 INSERT |
| `push_enabled=false` | INSERT in-app, `pushed_at` NULL |
| CALL_INCOMING + DND + `call_ring_enabled` | push quand même (VoIP iOS / data FCM) |
| `allow_calls=false` | pas d’emit (Appels refuse avant) |
| Sans token FCM (lab) | emit inbox OK ; push-test **200** `not_configured` |
| CALL_INCOMING payload | `caller_id` + `caller_name` présents |
| CALL_CANCELLED | 0 INSERT inbox ; même identité ; iOS → VoIP |
| Timeout RINGING | emit cancel **et** missed ; clés `call:{id}` ≠ `missed:{id}` |
| PUSH_TEST | 0 ligne `DEVICE_NEW` ; 0 INSERT `PUSH_TEST` |
| PUSH_TEST iOS `both`, voip vide | `apns_alert=sent` (ou `not_configured`), `apns_voip=skipped_no_token` |
| PATCH current voip seul | `push_token` inchangé ([AUTH-E](../iam_plans/AUTH-E-appareils.md) 28b) |

---

## Critères de fin NOTIF-A

- [ ] Seed `seed_notifications` + prefs à la création user
- [ ] 6 routes inbox vertes + isolation
- [ ] Migration `devices.voip_push_token` + heartbeat / revoke ([AUTH-E](../iam_plans/AUTH-E-appareils.md) 28b)
- [ ] Worker : matrice iOS alert/VoIP + FCM `notification`/`data` + canaux
- [ ] Hooks message + appel branchés (ou no-op documenté si module pas encore livré)
- [ ] `CALL_INCOMING` / `CALL_CANCELLED` : identité appelant ; missed : `collapse_key` distincte
- [ ] NOTIF-17 `PUSH_TEST` : 200 diagnostique, deux canaux iOS, pas d’inbox
- [ ] `emitted_at` sur tous les push
- [ ] CRYPTO-00 respecté sur PRIVATE
