# Appels — Catalogue des routes planifiées

**Produit :** YAS Connect uniquement.  
**Source :** [APPELS-R](APPELS-R-roles-permissions.md) · [A](APPELS-A-cycle-vie.md) … [G](APPELS-G-compte-rendu.md).  
**Préfixe HTTP :** `/api/v1` · **WebSocket :** `/ws/v1/calls/` · **Webhook :** `/api/v1/internal/livekit/webhook`.  
**Dépendances :** IAM (JWT, devices, privacy, présence), LiveKit, Redis, Médias (recordings), Messagerie (`type=CALL`).

**Permission** = `required_permission` (`HasPermission`).  
**Rôles** = USER / ADMIN après `seed_calls` + AUTH-R.

**36 routes HTTP** + **1 WebSocket** + **1 webhook interne**. Un **ADMIN** a aussi les routes Collaborateur + admin QoS/recordings.

**Hors tableau :** `GET /health`, OpenAPI, job purge QoS 90 j, workers STT/IA, `webrtc_sessions` (hors MVP).

---

## Pourquoi cet ordre

| Vague | Plan | Pourquoi |
|-------|------|----------|
| **0** | APPELS-R | Seed `calls.*` avant toute vue |
| **A** | APPELS-A | Cycle de vie avant join média |
| **B** | APPELS-B | Participants / sessions |
| **C** | APPELS-C | Tokens LiveKit + WS + webhooks |
| **D** | APPELS-D | Tracks / screen après salle live |
| **E** | APPELS-E | Enregistrements (Médias) |
| **F** | APPELS-F | QoS une fois appels actifs |
| **G** | APPELS-G | CR post-appel |

Portes **AUTH-F** (CGU + wizard) sur toutes les routes JWT user.

---

## Vague 0 — RBAC (APPELS-R)

Hors HTTP : `python manage.py seed_calls` (16 permissions).

---

## Vague A — Cycle de vie (APPELS-A)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 1 | `POST` | `/api/v1/calls` | Collaborateur | `calls.call.create` | USER, ADMIN | A-01/02 | Créer appel | 1-to-1 ou réunion ; LiveKit room. |
| 2 | `GET` | `/api/v1/calls/history` | Collaborateur | `calls.call.read` | USER, ADMIN | A-10 | Historique | Keyset ; filtres status/type/missed. |
| 3 | `GET` | `/api/v1/calls/{id}` | Collaborateur | `calls.call.read` | USER, ADMIN | A-11 | Détail | Participant only. |
| 4 | `POST` | `/api/v1/calls/{id}/accept` | Collaborateur | `calls.call.control` | USER, ADMIN | A-06 | Accepter | → ACTIVE. |
| 5 | `POST` | `/api/v1/calls/{id}/reject` | Collaborateur | `calls.call.control` | USER, ADMIN | A-07 | Rejeter | CALL_MISSED. |
| 6 | `POST` | `/api/v1/calls/{id}/end` | Collaborateur | `calls.call.control` | USER, ADMIN | A-09 | Terminer | Durée + ENDED. |

---

## Vague B — Participants & sessions (APPELS-B)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 7 | `GET` | `/api/v1/calls/{id}/participants` | Collaborateur | `calls.participant.read` | USER, ADMIN | B-21 | Liste | |
| 8 | `POST` | `/api/v1/calls/{id}/participants` | Collaborateur | `calls.participant.manage` | USER, ADMIN | B-22 | Inviter | HOST/MOD. |
| 9 | `PATCH` | `/api/v1/calls/{id}/participants/{user_id}` | Collaborateur | `calls.participant.manage` | USER, ADMIN | B-24 | Rôle | |
| 10 | `DELETE` | `/api/v1/calls/{id}/participants/{user_id}` | Collaborateur | `calls.participant.manage` | USER, ADMIN | B-23 | Kick | |
| 11 | `POST` | `/api/v1/calls/{id}/leave` | Collaborateur | `calls.call.control` | USER, ADMIN | B-leave | Quitter | |
| 12 | `PATCH` | `/api/v1/calls/{id}/me` | Collaborateur | `calls.call.control` | USER, ADMIN | B-25/27 | Mute / caméra | Self. |
| 13 | `POST` | `/api/v1/calls/{id}/sessions` | Collaborateur | `calls.session.manage` | USER, ADMIN | B-28 | Join device | IP serveur. |
| 14 | `POST` | `/api/v1/calls/{id}/sessions/{session_id}/disconnect` | Collaborateur | `calls.session.manage` | USER, ADMIN | B-29 | Fin jambe | |

---

## Vague C — LiveKit & temps réel (APPELS-C)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 15 | `POST` | `/api/v1/calls/{id}/token` | Collaborateur | `calls.token.create` | USER, ADMIN | C-38 | Token SFU | TTL court. |
| 16 | `POST` | `/api/v1/internal/livekit/webhook` | LiveKit | HMAC signature | — | C-40–42 | Sync SFU | Pas JWT user. |
| 17 | `WS` | `/ws/v1/calls/` | Collaborateur | JWT + participant | USER, ADMIN | C-43 | Événements | Subscribe `call_id`. |

---

## Vague D — Pistes & écran (APPELS-D)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 18 | `GET` | `/api/v1/calls/{id}/tracks` | Collaborateur | `calls.track.read` | USER, ADMIN | D-60 | Pistes | Query `active`. |
| 19 | `GET` | `/api/v1/calls/{id}/screen-shares` | Collaborateur | `calls.track.read` | USER, ADMIN | D-61 | Shares | |
| 20 | `POST` | `/api/v1/calls/{id}/screen-shares` | Collaborateur | `calls.call.control` | USER, ADMIN | D-57 | Start share | Optionnel si webhook. |
| 21 | `POST` | `/api/v1/calls/{id}/screen-shares/{share_id}/stop` | Collaborateur | `calls.call.control` | USER, ADMIN | D-58 | Stop share | |

---

## Vague E — Enregistrements (APPELS-E)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 22 | `POST` | `/api/v1/calls/{id}/recordings/start` | Collaborateur | `calls.recording.create` | USER, ADMIN | E-65 | Start | HOST/MOD ; 202. |
| 23 | `POST` | `/api/v1/calls/{id}/recordings/stop` | Collaborateur | `calls.recording.create` | USER, ADMIN | E-66 | Stop | |
| 24 | `GET` | `/api/v1/calls/{id}/recordings` | Collaborateur | `calls.recording.read` | USER, ADMIN | E-69 | Liste | |
| 25 | `GET` | `/api/v1/recordings/{id}/download` | Collaborateur | `calls.recording.read` | USER, ADMIN | E-70 | Download | Via Médias. |
| 26 | `GET` | `/api/v1/admin/recordings` | Admin | `calls.recording.manage_all` | ADMIN | E-71 | Admin | |

---

## Vague F — QoS (APPELS-F)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 27 | `POST` | `/api/v1/calls/{id}/metrics` | Collaborateur | `calls.metrics.write` | USER, ADMIN | F-77 | Batch samples | Max 50. |
| 28 | `GET` | `/api/v1/calls/{id}/metrics` | Collaborateur | `calls.metrics.read` | USER, ADMIN | F-81 | Courbe | |
| 29 | `GET` | `/api/v1/calls/{id}/metrics/summary` | Collaborateur | `calls.metrics.read` | USER, ADMIN | F-82 | Agrégats | |
| 30 | `GET` | `/api/v1/admin/calls/metrics` | Admin | `calls.metrics.read_all` | ADMIN | F-83 | NOC | |

---

## Vague G — Compte-rendu (APPELS-G)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 31 | `GET` | `/api/v1/meetings/history` | Collaborateur | `calls.meeting.read` | USER, ADMIN | G-94 | Liste CR | Keyset. |
| 32 | `POST` | `/api/v1/calls/{id}/meeting` | Collaborateur | `calls.meeting.update` | USER, ADMIN | G-89 | Créer CR | Opt-in 1-to-1. |
| 33 | `GET` | `/api/v1/calls/{id}/meeting` | Collaborateur | `calls.meeting.read` | USER, ADMIN | G-93 | Lire CR | |
| 34 | `PATCH` | `/api/v1/calls/{id}/meeting` | Collaborateur | `calls.meeting.update` | USER, ADMIN | G-90 | Titre/notes | HOST. |
| 35 | `POST` | `/api/v1/calls/{id}/meeting/transcribe` | Collaborateur | `calls.meeting.update` | USER, ADMIN | G-91 | STT | 202. |
| 36 | `POST` | `/api/v1/calls/{id}/meeting/summarize` | Collaborateur | `calls.meeting.update` | USER, ADMIN | G-92 | Résumé IA | 202. |

---

## Événements WebSocket (référence)

| Event | Plan | Payload clé |
|-------|------|-------------|
| `CALL_INCOMING` | A | `call_id`, `caller`, `call_type` |
| `CALL_ACCEPTED` / `REJECTED` / `STARTED` / `ENDED` / `FAILED` | A | `call_id`, `status` |
| `PARTICIPANT_JOINED` / `LEFT` / `MUTED` / `CAMERA` | B | `user_id`, flags |
| `ROOM_CLOSED` / `TOKEN_REFRESH_NEEDED` | C | `call_id` |
| `SCREEN_SHARE_STARTED` / `STOPPED` | D | `user_id`, `share_id` |
| `RECORDING_STARTED` / `READY` / `FAILED` | E | `recording_id` |
| `TRANSCRIPTION_READY` / `AI_SUMMARY_READY` | G | `call_id` |

---

## Matrice permissions ↔ routes

| Permission | Routes # |
|------------|----------|
| `calls.call.create` | 1 |
| `calls.call.read` | 2, 3 |
| `calls.call.control` | 4–6, 11–12, 20–21 |
| `calls.participant.read` | 7 |
| `calls.participant.manage` | 8–10 |
| `calls.session.manage` | 13–14 |
| `calls.token.create` | 15 |
| `calls.track.read` | 18–19 |
| `calls.recording.create` | 22–23 |
| `calls.recording.read` | 24–25 |
| `calls.recording.manage_all` | 26 |
| `calls.metrics.write` | 27 |
| `calls.metrics.read` | 28–29 |
| `calls.metrics.read_all` | 30 |
| `calls.meeting.read` | 31, 33 |
| `calls.meeting.update` | 32, 34–36 |
