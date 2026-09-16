# Jour 23 — NOTIF-R + NOTIF-A (centre de notifications + push)

**Statut :** clos (2026-09-15).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–22 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 22](00-jour-22-media-r-a.md)). CRYPTO-00 (jour 21) figé : payload 1-to-1 générique.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §5 — *notifications*) :

| Fonction MVP                              | Ticket             | Statut          |
| ------------------------------------------ | ------------------ | --------------- |
| Upload générique de fichiers               | MEDIA-R + MEDIA-A   | **fait** (jour 22) |
| **Centre de notifs + push (in-app + FCM/APNs)** | **NOTIF-R + NOTIF-A** | **ce jour** |
| Clés HTTP (crypto)                         | CRYPTO-R + CRYPTO-A | jour 24         |

**À quoi ça sert (MVP) :** aujourd'hui, un nouvel appareil déclenche juste un `logger.info(...)` (`apps/iam/services/notify_stub.py`) — personne n'est réellement notifié. Ce jour construit le vrai centre de notifications (badge, liste, préférences) et le moteur `emit()` qui poussera plus tard les messages et appels — mais qui, **dès aujourd'hui**, remplace le stub `DEVICE_NEW` par une vraie notification in-app.

**Plan métier (code à coller) :** [NOTIF-R-roles-permissions.md](notif_plans/NOTIF-R-roles-permissions.md) (NOTIF-R01…R04) + [NOTIF-A-in-app-push.md](notif_plans/NOTIF-A-in-app-push.md) (NOTIF-01…17, **hors** hooks Messagerie/Appels — voir §0).  
Chemins lab = ce fichier (nouvelle app `apps/notifications/`).

**Déjà en base / code :**

- `apps/iam/services/notify_stub.py::emit_device_new` : stub `logger.info` déjà branché dans `device_service.on_new_device` (appelé depuis `auth_service.complete_login` quand `created=True`). **C'est lui qu'on remplace.**
- `devices.push_token` : colonne existante (AUTH-E). `devices.voip_push_token` : **n'existe pas encore** — delta AUTH-E 28b de ce jour.
- `UserPreference.timezone` (PROF-B) : c'est le « TZ des prefs IAM » que NOTIF-09 (DND) doit utiliser.
- `RolePermission`/`rbac_catalog.py` : pattern déjà établi (jours 11+) pour seed des permissions self.
- `apps/config` (`SystemSetting`) : pas utilisé ici (pas de plafond runtime pour les notifs).

**Pas encore :** l'app `apps.notifications` **n'existe pas du tout** (ni dans `INSTALLED_APPS`, ni sur disque) — contrairement à IAM/Annuaire/Media dont les tables existaient déjà depuis AUTH-01, ici il faut créer l'app, son `models.py` et sa **première migration**. `apps.messaging` et `apps.calls` n'existent pas non plus (jours 25+ et 29+) : les hooks NOTIF-11/12/13/14/14b ne peuvent physiquement pas être branchés aujourd'hui.

**Objectif du jour :**

1. Créer l'app `apps/notifications/` (`Notification`, `NotificationPreference` — [code/notif_models.py](code/notif_models.py)), l'ajouter à `INSTALLED_APPS`, migration `0001_initial`.
2. **NOTIF-R** : 3 permissions `notifications.*` dans `rbac_catalog.py` (self, USER+ADMIN via le mécanisme existant).
3. **Delta AUTH-E 28b** : `devices.voip_push_token` (migration `apps/iam`), whitelist PATCH `/me/devices/current` séparée de `push_token`.
4. `apps/notifications/services/notification_service.py` : `emit()` (idempotence 30 s), `ensure_preferences()`, inbox (liste/unread-count/mark-read/read-all), préférences (get/patch), DND.
5. `apps/notifications/services/push_worker.py` : routage stub iOS alert/VoIP vs FCM — toujours `not_configured` en lab (`FCM_SERVER_KEY`/`APNS_KEY_PATH` vides).
6. 6 routes inbox/prefs + `POST /me/devices/current/push-test` (NOTIF-17, rate-limit 1/30 s).
7. Remplacer `notify_stub.emit_device_new` par un vrai `emit(type=DEVICE_NEW)`. Provisionner `NotificationPreference` à la création de compte (`register_ad`/`register_local`/`create_local_user` — 4ᵉ fois qu'on rouvre ces fonctions, après ANNUAIRE-C).
8. Ne rien casser : login (AUTH-A/D), appareils (AUTH-E), présence, tout le reste.

**Hors jour 23 :** hooks `MESSAGE_NEW`/`MESSAGE_MENTION` (Messagerie n'existe pas, jour 25+) ; hooks `CALL_INCOMING`/`CALL_MISSED`/`CALL_CANCELLED` (Appels n'existe pas, jour 29+) ; mute de fil NOTIF-10 (`conversation_settings` n'existe pas) ; vrai FCM/APNs (SDK, certificats — restera `not_configured` bien au-delà du MVP lab) ; WebSocket `notification.created` (optionnel, non fait) ; email/SMS/Web Push.

---

## 0. Corrections apportées au plan métier (avant de coder)

| Écart trouvé | Correction |
|---|---|
| NOTIF-R dit « Commande `python manage.py seed_notifications` » | Pas de nouvelle commande : même convention que AUTH-R/MEDIA-R = ajouter les 3 codes à `rbac_catalog.py` (`_SELF`), `ensure_system_matrix()` les distribue. |
| NOTIF-A liste des tests sur `MESSAGE_NEW`, `CALL_INCOMING`, `CALL_CANCELLED`, mute fil | Ces hooks réels sont **impossibles** aujourd'hui (tables inexistantes). On teste le moteur `emit()` **directement** (il est agnostique du type — appeler `emit(type=Notification.Type.CALL_INCOMING, ...)` en test valide la logique DND/priorité **sans** qu'un vrai appel existe). Mute fil (NOTIF-10) reste totalement non câblé, sans test, faute de table. |
| « `collapse_key` et type récent (ex. 30 s) remplace » | Interprétation figée ici : fenêtre **30 s fixe**, on **met à jour** la ligne existante (title/body/payload, `pushed_at` remis à `NULL` pour retenter le push) plutôt que d'insérer, indépendamment de `read_at`. |

---

## Pourquoi ce jour (après MEDIA-A, avant CRYPTO-A / MESSAGERIE)

NOTIF-A est un **transverse** : Messagerie (jour 25+) et Appels (jour 29+) auront besoin d'appeler `NotificationService.emit()` dès leur premier jour. Le construire maintenant — avec le seul hook réellement disponible aujourd'hui (`DEVICE_NEW`, AUTH-E) — évite de le improviser plus tard en pleine implémentation Messagerie. C'est aussi la première fois qu'une **nouvelle app Django** est créée depuis la phase 0 (toutes les précédentes réutilisaient les tables d'AUTH-01).

```text
JWT + HasPermission + portes AUTH-F
    GET  /notifications                        notifications.inbox.read
    GET  /notifications/unread-count           notifications.inbox.read
    POST /notifications/{id}/read              notifications.inbox.update
    POST /notifications/read-all               notifications.inbox.update
    GET  /notification-preferences             notifications.preferences.manage
    PATCH /notification-preferences            notifications.preferences.manage
    POST /me/devices/current/push-test         iam.device.update (existant)

Hook réel (aujourd'hui)
    AUTH-A/D login → device_service.on_new_device → emit(DEVICE_NEW)  [remplace notify_stub]

Hooks futurs (pas aujourd'hui, table absente)
    MESSAGERIE-D MSG-67 → emit(MESSAGE_NEW / MESSAGE_MENTION)   [jour 25+]
    APPELS-A CALL-05/07/08/09 → emit(CALL_INCOMING/MISSED/CANCELLED)  [jour 29+]
```

---

## Paliers (figés pour ce jour)

| Sujet | Choix jour 23 | Plus tard |
| ----- | ------------- | --------- |
| Nouvelle app | `apps/notifications` créée ce jour, migration `0001_initial` | — |
| `voip_push_token` | Ajouté à `Device` (migration `apps/iam`), whitelist PATCH séparée (`push_token` inchangé si seul `voip_push_token` posé) | — |
| Idempotence `emit()` | Fenêtre **30 s** fixe sur `(user, type, collapse_key)` → **update** en place, pas d'INSERT dupliqué | — |
| DND | `quiet_hours_*` comparés dans `UserPreference.timezone`. Bloque le **push** seulement (in-app toujours inséré) | — |
| Priorité appel | `CALL_INCOMING`/`CALL_CANCELLED` **ignorent** le DND si `call_ring_enabled=true` (testé via `emit()` direct, pas de vrai appel) | — |
| Preview 1-to-1 | `emit()` ne reçoit **jamais** de texte réel pour `MESSAGE_NEW` — c'est l'appelant (futur Messagerie) qui doit passer un `title`/`body` générique. Rien à coder ici, juste **documenté** (CRYPTO-00) | Vérifié réellement au jour 25 |
| Worker push | Stub pur : `FCM_SERVER_KEY`/`APNS_KEY_PATH` vides (nouveaux settings, défaut `""`) → **toujours** `not_configured`. Routage (quel jeton, quelle forme) codé et testable, **envoi réel jamais tenté** | Vrai SDK FCM/APNs post-MVP |
| `pushed_at` | Posé **uniquement** si le worker renvoie `status="sent"` — donc reste `NULL` en lab pour tout push réel (mais **pas** pour `CALL_CANCELLED`/`PUSH_TEST`, jamais en inbox) | — |
| `CALL_CANCELLED` / `PUSH_TEST` | **Jamais** d'INSERT `notifications` (push/WS seulement, ou diagnostic seul) | — |
| `NotificationPreference` | Provisionnée à la création de compte (`register_ad`, `register_local`, `create_local_user`) via `ensure_preferences(user)`. **Pas** de backfill pour les comptes déjà créés (jean/marie des jours précédents) | RH pose la ligne manuellement si besoin |
| Push-test | `POST /me/devices/current/push-test`, `iam.device.update` (perm existante, **pas** `notifications.*`). Rate-limit **1/30 s** par appareil courant → 429 `RATE_LIMITED`. **200** toujours (jamais 204) | — |
| Portes AUTH-F | Toutes les routes `/notifications*` et `/notification-preferences` sous JWT + CGU/wizard (comme tout `/me/*`/self) | — |
| Audit | `module=NOTIFICATIONS` ; pas de nouvelle action `AuditLog` pour chaque `emit()` (bruyant) — seul `DEVICE_NEW` reste aussi audité côté IAM (déjà fait par `on_new_device`) | — |

---

## 1. Tables (nouvelle app + delta IAM)

**2 migrations** (première fois depuis la phase 0 qu'un jour en a besoin — les jours précédents ne faisaient que réutiliser AUTH-01) :

- `apps/notifications/migrations/0001_initial.py` : `notifications`, `notification_preferences` (0 ligne).
- `apps/iam/migrations/0008_notif_a_voip_push_token.py` : `devices.voip_push_token` (`TextField`, blank/default `""`).

**Interdit :** `docker compose down -v`.

---

## 2. Fichiers

| Fichier | Rôle |
| ------- | ---- |
| `apps/notifications/__init__.py`, `apps.py`, `migrations/` | **nouveau.** Scaffolding app |
| `apps/notifications/models.py` | **nouveau.** `Notification`, `NotificationPreference` (coller [code/notif_models.py](code/notif_models.py)) |
| `apps/notifications/services/notification_service.py` | **nouveau.** `emit`, `ensure_preferences`, `list_inbox`, `unread_count`, `mark_read`, `mark_all_read`, `get_preferences`, `patch_preferences`, DND |
| `apps/notifications/services/push_worker.py` | **nouveau.** `send_push(device, type, title, body, payload)` — routage stub |
| `apps/notifications/serializers/notifications.py` | **nouveau.** `NotificationOutSerializer`, `PreferencesPatchSerializer` |
| `apps/notifications/views/inbox.py` | **nouveau.** `NotificationListView`, `UnreadCountView`, `NotificationReadView`, `ReadAllView` |
| `apps/notifications/views/preferences.py` | **nouveau.** `NotificationPreferencesView` |
| `apps/notifications/urls.py` | **nouveau.** monté sous `/api/v1/` (`notifications`, `notification-preferences`) |
| `apps/iam/models.py` | **delta.** `Device.voip_push_token` |
| `apps/iam/serializers/devices.py` | **delta.** `DeviceCurrentPatchSerializer` + `voip_push_token` |
| `apps/iam/services/device_service.py` | **delta.** `patch_current_device` gère `voip_push_token` ; `on_new_device` appelle `emit()` au lieu du stub |
| `apps/iam/services/notify_stub.py` | **delta.** `emit_device_new` supprimée (remplacée) |
| `apps/iam/services/rate_limit_service.py` | **delta.** `is_push_test_limited` / `push_test_hit` (1/30 s) |
| `apps/iam/services/register_service.py` | **delta.** `register_ad`/`register_local` appellent `ensure_preferences(user)` |
| `apps/iam/services/admin_user_service.py` | **delta.** `create_local_user` idem |
| `apps/iam/views/devices.py` | **delta.** `DevicePushTestView` (NOTIF-17) |
| `apps/iam/urls/me.py` | **delta.** + route push-test |
| `apps/iam/services/rbac_catalog.py` | **delta.** + 3 permissions `notifications.*` |
| `config/settings.py` | **delta.** `INSTALLED_APPS` + `FCM_SERVER_KEY`/`APNS_KEY_PATH` (défaut `""`) |
| `apps/iam/tests/test_notif_a.py` | **nouveau.** |

---

## 3. Contrat HTTP

### Inbox / préférences (NOTIF-01…06)

| Méthode | Chemin | Perm |
|---------|--------|------|
| GET | `/api/v1/notifications` | `notifications.inbox.read` |
| GET | `/api/v1/notifications/unread-count` | `notifications.inbox.read` |
| POST | `/api/v1/notifications/{id}/read` | `notifications.inbox.update` |
| POST | `/api/v1/notifications/read-all` | `notifications.inbox.update` |
| GET | `/api/v1/notification-preferences` | `notifications.preferences.manage` |
| PATCH | `/api/v1/notification-preferences` | `notifications.preferences.manage` |

`GET /notifications` : query `before` (keyset ISO datetime), `limit` (défaut 20, max 50), `unread_only`. **200** `{ "results": [...], "next_before" }`.  
`GET /unread-count` : **200** `{ "count" }`.  
`POST /{id}/read` : **204**, idempotent, **404** si pas à soi.  
`POST /read-all` : **204**.  
`PATCH /notification-preferences` whitelist : `push_enabled`, `in_app_enabled`, `call_ring_enabled`, `message_preview_enabled`, `quiet_hours_enabled`, `quiet_hours_start`, `quiet_hours_end`.

### `POST /api/v1/me/devices/current/push-test` (NOTIF-17)

`iam.device.update`. Query `channel=alert|voip|both` (défaut `both`). Rate-limit 1/30 s → **429** `RATE_LIMITED`.  
**200** (jamais 204) `{ "emitted_at", "channels": [{ "channel", "status" }] }`. `status` ∈ `sent|skipped_no_token|not_configured` — toujours `not_configured` en lab (aucune clé FCM/APNs configurée). Aucune ligne `notifications` créée.

**401** sans JWT. **403** `FORBIDDEN` sans la perm / `TOS_REQUIRED` / `ONBOARDING_REQUIRED`.

---

## 4. `emit()` — moteur (NOTIF-07…09, 16)

```text
def emit(user, type, *, title, body="", payload=None, collapse_key="", ignore_dnd=False):
    recent = Notification.objects.filter(
        user=user, type=type, collapse_key=collapse_key,
        created_at__gte=now()-30s,
    ).first() if collapse_key else None
    if recent:
        recent.title, recent.body, recent.payload = title, body, payload or {}
        recent.pushed_at = None
        recent.save(...)
        row = recent
    elif type not in (CALL_CANCELLED, PUSH_TEST):  # pas d'inbox pour ceux-là
        row = Notification.objects.create(user=user, type=type, title=title, body=body,
                                            payload=payload or {}, collapse_key=collapse_key)
    else:
        row = None

    prefs = ensure_preferences(user)
    if not prefs.push_enabled and not ignore_dnd:
        return row
    if _in_quiet_hours(prefs) and not ignore_dnd:
        return row
    for device in user.devices.exclude(push_token="", voip_push_token=""):
        result = push_worker.send_push(device, type, title, body, payload)
        if row and result["status"] == "sent":
            row.pushed_at = now(); row.save(update_fields=["pushed_at"])
    return row
```

`ignore_dnd=True` passé par les futurs appels `CALL_INCOMING`/`CALL_CANCELLED` si `call_ring_enabled` (logique dans l'appelant, pas dans `emit()` — reste simple et testable directement).

---

## 5. Tests nouveaux (`test_notif_a.py`)

| ID | Cas | Attendu |
| -- | --- | ------- |
| 01 | `emit()` deux fois même `collapse_key`+`type` sous 30 s | 1 seule ligne, mise à jour |
| — | `GET /notifications` autre user (id volé dans payload) | 404 sur `/read` |
| 03 | `POST /{id}/read` idempotent | 204 deux fois |
| 04 | `POST /read-all` | tous `read_at` posés |
| 02 | `GET /unread-count` | compte correct après lecture partielle |
| 06 | Compte créé (`register_local`) | `NotificationPreference` existe (1 ligne, defaults) |
| 08 | `push_enabled=false` | INSERT in-app ; `pushed_at` NULL |
| 09 | DND actif (`quiet_hours`) type `MESSAGE_NEW` | in-app inséré ; pas de push tenté au-delà du stub |
| — | `emit(CALL_INCOMING, ignore_dnd=True)` avec DND actif | push stub quand même tenté |
| — | `DEVICE_NEW` réel (login nouvel appareil) | 1 ligne `notifications` `type=DEVICE_NEW` (stub supprimé) |
| 17 | `POST push-test` sans jeton | 200 `not_configured` ou `skipped_no_token`, jamais 500 |
| 17 | `POST push-test` 2 fois en < 30 s | 429 `RATE_LIMITED` |
| 17 | `PUSH_TEST` | 0 ligne `notifications` |
| — | PATCH `voip_push_token` seul | `push_token` inchangé (AUTH-E 28b) |
| — | sans JWT | 401 |
| — | sans la permission | 403 `FORBIDDEN` |
| — | self sans CGU | 403 `TOS_REQUIRED` |
| — | `/api/schema/` | contient `/api/v1/notifications` et `/api/v1/me/devices/current/push-test` |

---

## 6. Vérif manuelle

```powershell
python manage.py makemigrations notifications iam
python manage.py migrate
python manage.py check
pytest apps/iam/tests/test_notif_a.py apps/iam/tests/test_auth_e.py apps/iam/tests/test_auth_a.py --reuse-db
```

Login jean (nouvel appareil) → `GET /api/v1/notifications` → une notif `DEVICE_NEW` apparaît. `POST /api/v1/me/devices/current/push-test` → `200` avec `not_configured` (aucune clé configurée en lab).

---

## Checklist jour 23

- [x] App `apps.notifications` créée, migration `0001_initial`
- [x] `devices.voip_push_token` (migration `apps.iam`), PATCH séparée de `push_token`
- [x] 3 permissions `notifications.*` seedées
- [x] `emit()` : idempotence 30 s, DND, `ignore_dnd`, pas d'inbox pour `CALL_CANCELLED`/`PUSH_TEST`
- [x] 6 routes inbox/prefs + isolation 404
- [x] `NotificationPreference` provisionnée à la création de compte (3 endroits)
- [x] `DEVICE_NEW` réel remplace le stub `notify_stub.emit_device_new`
- [x] `push_worker` stub : routage codé, toujours `not_configured` en lab
- [x] `POST push-test` : rate-limit 1/30 s, 200 diagnostique, 0 inbox
- [x] `test_notif_a.py` (19 tests) + régression complète (0 régression, seul échec pré-existant test_cache_down_falls_back_sql)
- [x] SIRH non modifié

**Note de clôture :** la migration `apps/iam/migrations/0008_notif_a_voip_push_token.py` générée par `makemigrations` embarquait aussi une dérive pré-existante (`AlterField EmailVerification.purpose`, inerte, sans rapport avec ce jour) — retirée manuellement du fichier pour ne pas l'attribuer à NOTIF-A.

---

## Interdits

- Hooks `MESSAGE_NEW`/`MESSAGE_MENTION` (Messagerie n'existe pas) — jour 25+
- Hooks `CALL_INCOMING`/`CALL_MISSED`/`CALL_CANCELLED` (Appels n'existe pas) — jour 29+
- Mute de fil NOTIF-10 (`conversation_settings` n'existe pas)
- Vrai SDK FCM/APNs (stub uniquement, `not_configured` assumé)
- WebSocket `notification.created` (optionnel, pas fait)
- Email / SMS / Web Push navigateur
- `docker compose down -v`
- Changer le SIRH

---

## Après le jour 23

Jour 24 : [00-jour-24-crypto-r-a.md](00-jour-24-crypto-r-a.md) — **CRYPTO-R + CRYPTO-A** (bundles de clés Signal par appareil, `ensure_conversation_key` en hook interne).

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
| **23** | **NOTIF-R + NOTIF-A** (ce plan)                 | §5 alertes + MOB-PUSH (VoIP / worker)  |
| 24     | CRYPTO-R + CRYPTO-A                             | Clés HTTP                              |
| 25     | MESSAGERIE-R, A, B                              | §7 1-to-1                              |
| 26     | MESSAGERIE-C, D                                 | §7 groupes + temps réel                |
| 27     | MESSAGERIE-E (partiel), F, G                    | §7 enrichissements                     |
| 28     | MEDIA-B, C, D, E                                | §4 album / vocal / coffre              |
| 29     | APPELS-R, A, B, C                               | §8 appel 1-1 + `CALL_CANCELLED`        |
| 30     | APPELS-D, E, G                                  | §8 écran / CR                          |

**Total : 31 plans (jours 0 à 30).**  
Déjà clos : **23** (0–22). Restant : **8** (23–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.
