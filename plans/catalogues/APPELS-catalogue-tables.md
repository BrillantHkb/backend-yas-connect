# Catalogue Appels — tables et attributs

App Django prévue : `apps.calls`.  
Référence **IAM** (`users`, `devices`), **Médias** (`media_files` pour enregistrements), **Messagerie** (`messages.call_id` sans FK inverse).

**Légende « Renseigné par »** : User / Système / LiveKit (webhooks) — phase **5** (module Appels).  
Django **n’achemine pas** l’audio-vidéo : tokens LiveKit + signalisation ; flux via **SFU LiveKit**.

Index : [INDEX-catalogue.md](INDEX-catalogue.md).

**Stack** : LiveKit (SFU) + STUN/TURN ; Redis pour statut live (`call:{id}:status`, présence salle).

---

## Index des tables

| # | Table | Rôle | Migration MVP |
|---|--------|------|---------------|
| 58 | `calls` | Appel / réunion (cycle de vie, type, durée) | Oui |
| 59 | `call_participants` | Participants (rôle, mute, caméra, horaires) | Oui |
| 60 | `call_sessions` | Connexion technique par device (IP, réseau) | Oui |
| 61 | `webrtc_sessions` | SDP / ICE (signalisation WebRTC) | **Non** — hors incrément MVP |
| 62 | `livekit_rooms` | Salle LiveKit (1:1 avec `calls`) | Oui |
| 63 | `media_tracks` | Pistes live publiées (audio / vidéo / écran) | Oui |
| 64 | `recordings` | Fichier enregistré → `media_files` | Oui |
| 65 | `screen_shares` | Épisodes de partage d’écran | Oui |
| 66 | `call_quality_metrics` | Échantillons QoS (latence, pertes…) | Oui |
| 67 | `meeting_history` | Compte-rendu post-appel (transcript, IA) | Oui |

**9 tables** dans la migration initiale `apps.calls` ; `webrtc_sessions` documentée pour extension P2P / audit.

---

## Relations (ERD)

| De | Vers | Cardinalité | FK |
|----|------|-------------|-----|
| `calls` | `users` | n → 1 | `caller_id` |
| `call_participants` | `calls` | n → 1 | `call_id` |
| `call_participants` | `users` | n → 1 | `user_id` |
| `call_sessions` | `calls` | n → 1 | `call_id` |
| `call_sessions` | `users` | n → 1 | `user_id` |
| `call_sessions` | `devices` | n → 1 | `device_id` |
| `webrtc_sessions` | `calls` | n → 1 | `call_id` (hors MVP) |
| `livekit_rooms` | `calls` | 1 → 1 | `call_id` UK |
| `media_tracks` | `calls` | n → 1 | `call_id` |
| `media_tracks` | `users` | n → 1 | `user_id` |
| `recordings` | `calls` | n → 1 | `call_id` |
| `recordings` | `media_files` | n → 1 | `media_id` |
| `screen_shares` | `calls` | n → 1 | `call_id` |
| `screen_shares` | `users` | n → 1 | `user_id` |
| `call_quality_metrics` | `calls` | n → 1 | `call_id` |
| `call_quality_metrics` | `users` | n → 1 | `user_id` |
| `meeting_history` | `calls` | 1 → 1 | `call_id` UK |

**Messagerie (sans FK SQL)** : `messages.call_id` → référence logique `calls.id` quand `type = CALL`.

---

## 1. `calls`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Identifiant appel | | FK messagerie, historique | Système |
| `caller_id` | `uuid` | FK `users` SET NULL, NOT NULL à la création | Initiateur | | `POST /calls` | User |
| `call_type` | `varchar(16)` | NOT NULL | Type d’appel | `VIDEO` | UI, politique réseau | User / Système |
| `room_id` | `varchar(255)` | UK, NOT NULL | Identifiant salle (LiveKit) | `room_abc` | Token join | Système |
| `status` | `varchar(16)` | défaut `CREATED` | Cycle de vie | `ACTIVE` | WS / inbox | Système |
| `started_at` | `timestamptz` | NULL | Début effectif média | | Facturation durée | Système |
| `ended_at` | `timestamptz` | NULL | Fin appel | | Historique | Système |
| `duration_seconds` | `integer` | défaut `0`, CHECK `>= 0` | Durée calculée | `360` | Stats | Système |
| `max_participants` | `smallint` | défaut `2` | Plafond participants | `15` | Réunion / crise | Système |
| `is_recorded` | `boolean` | défaut `false` | Enregistrement actif | | Compliance | User / Admin |
| `created_at` | `timestamptz` | NOT NULL | Création ligne | | Tri historique | Système |

**Enum `call_type`** : `AUDIO`, `VIDEO`, `CONFERENCE`, `CRISIS_ROOM`, `MEETING`.

**Enum `status`** : `CREATED`, `RINGING`, `ACTIVE`, `ENDED`, `FAILED`, `CANCELLED`.

Règle : un appel `ENDED` ne repasse pas `ACTIVE` (nouvel appel).

---

## 2. `call_participants`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `call_id` | `uuid` | FK `calls` CASCADE, NOT NULL | Appel | | Liste participants | Système |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | Participant | | | Système |
| `joined_at` | `timestamptz` | NOT NULL | Arrivée | | | Système |
| `left_at` | `timestamptz` | NULL | Départ | | Reconnexion métier | Système |
| `role` | `varchar(16)` | NOT NULL | Rôle dans l’appel | `HOST` | Droits modération | Système |
| `muted` | `boolean` | défaut `false` | Micro coupé | | UI / WS | User |
| `camera_enabled` | `boolean` | défaut `false` | Caméra active | | | User |

UK `(call_id, user_id)`.

**Enum `role`** : `HOST`, `MODERATOR`, `PARTICIPANT`, `GUEST`.

---

## 3. `call_sessions`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Session technique | | Multi-device | Système |
| `call_id` | `uuid` | FK `calls` CASCADE, NOT NULL | Appel | | | Système |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | Utilisateur | | | Système |
| `device_id` | `uuid` | FK `devices` SET NULL, NULL | Appareil | | Push / 4G vs Wi‑Fi | Système |
| `connection_id` | `varchar(255)` | défaut `''` | ID connexion LiveKit / client | | Debug | Système |
| `ip_address` | `inet` | NULL | IP au join | | Support NOC | Système |
| `network_type` | `varchar(16)` | défaut `OTHER` | Réseau | `WIFI` | QoS | Client |
| `connected_at` | `timestamptz` | NOT NULL | Début jambe | | | Système |
| `disconnected_at` | `timestamptz` | NULL | Fin jambe (drop / hangup) | | Reconnexion | Système |

**Enum `network_type`** : `WIFI`, `MOBILE_3G`, `MOBILE_4G`, `MOBILE_5G`, `ETHERNET`, `OTHER`.

Un user peut avoir **plusieurs** `call_sessions` sur le même `call_id` (téléphone + PC).

---

## 4. `webrtc_sessions` — hors incrément MVP

> **Non migrée en phase 5 MVP.** LiveKit gère SDP/ICE côté SFU. Observabilité : webhooks LiveKit + logs structurés ; Redis optionnel `call:{id}:signaling` (TTL 10–15 min, sans SDP complet).  
> Réintroduire en PG si chemin **P2P sans LiveKit** ou audit signalisation obligatoire.

| Attribut | Type PG | Contraintes | Rôle |
|----------|---------|-------------|------|
| `id` | `uuid` | PK | |
| `call_id` | `uuid` | FK `calls` CASCADE, NOT NULL | |
| `peer_id` | `varchar(255)` | défaut `''` | |
| `sdp_offer` | `text` | défaut `''` | Offre SDP |
| `sdp_answer` | `text` | défaut `''` | Réponse SDP |
| `ice_candidates` | `jsonb` | défaut `[]` | Candidats ICE |
| `state` | `varchar(16)` | défaut `NEW` | `NEW`, `CHECKING`, `CONNECTED`, `DISCONNECTED`, `FAILED` |
| `created_at` | `timestamptz` | NOT NULL | |

---

## 5. `livekit_rooms`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `call_id` | `uuid` | FK `calls` CASCADE, UK, NOT NULL | Appel 1:1 | | Une salle / appel | Système |
| `room_name` | `varchar(255)` | UK, NOT NULL | Nom salle LiveKit | | Token API | Système |
| `livekit_sid` | `varchar(255)` | défaut `''` | SID serveur LiveKit | | Webhooks | LiveKit |
| `max_participants` | `smallint` | défaut `2` | Plafond SFU | `15` | | Système |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `closed_at` | `timestamptz` | NULL | Fermeture salle | | | LiveKit |

---

## 6. `media_tracks`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `call_id` | `uuid` | FK `calls` CASCADE, NOT NULL | Appel | | | LiveKit |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | Publieur | | | LiveKit |
| `track_type` | `varchar(16)` | NOT NULL | Type piste | `VIDEO` | Adaptation qualité | LiveKit |
| `codec` | `varchar(50)` | défaut `''` | Codec | `vp8` | | LiveKit |
| `bitrate` | `integer` | défaut `0` | Débit bps | | Stats | LiveKit |
| `resolution` | `varchar(30)` | défaut `''` | ex. `1280x720` | | | LiveKit |
| `active` | `boolean` | défaut `true` | Piste publiée | | | LiveKit |

**Enum `track_type`** : `AUDIO`, `VIDEO`, `SCREEN_SHARE`.

État live : préférer webhooks LiveKit ; PG = historique post-appel ou support.

---

## 7. `recordings`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `call_id` | `uuid` | FK `calls` CASCADE, NOT NULL | Appel source | | | Système |
| `media_id` | `uuid` | FK `media_files` SET NULL, NULL | Fichier MinIO | | Lecture | Système |
| `duration_seconds` | `integer` | défaut `0` | Durée fichier | | | Système |
| `format` | `varchar(30)` | défaut `''` | `mp4`, `webm` | | | Système |
| `encrypted` | `boolean` | défaut `false` | Chiffrement au repos | | | Système |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

---

## 8. `screen_shares`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `call_id` | `uuid` | FK `calls` CASCADE, NOT NULL | Appel | | | LiveKit |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | Partageur | | | LiveKit |
| `started_at` | `timestamptz` | NOT NULL | Début partage | | | LiveKit |
| `ended_at` | `timestamptz` | NULL | Fin partage | | | LiveKit |
| `active` | `boolean` | défaut `true` | En cours | | | LiveKit |

Plusieurs lignes par user / appel (stop puis re-share).

---

## 9. `call_quality_metrics`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `bigint` | PK BIGSERIAL | Échantillon | | Série temporelle | Client / LiveKit |
| `call_id` | `uuid` | FK `calls` CASCADE, NOT NULL | Appel | | Courbe qualité | Système |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | Participant | | | Système |
| `latency_ms` | `integer` | NULL | RTT | `45` | Grafana | Client |
| `jitter_ms` | `integer` | NULL | Gigue | | | Client |
| `packet_loss` | `decimal(6,3)` | NULL, CHECK 0–100 | Perte paquets % | `0.052` | NOC | Client |
| `bitrate` | `integer` | NULL | Débit bps | | | Client |
| `fps` | `integer` | NULL | Images/s vidéo | `30` | | Client |
| `cpu_usage` | `integer` | NULL | Charge CPU client % | | | Client |
| `network_type` | `varchar(20)` | défaut `''` | Contexte réseau | `4G` | | Client |
| `created_at` | `timestamptz` | NOT NULL | Horodatage échantillon | | Partition / purge | Système |

**INSERT only** — pas d’UPDATE métier. Rétention MVP : job `DELETE` > 90 jours. Partition mensuelle **après** montée en charge (~100k+ lignes/jour).

---

## 10. `meeting_history`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `call_id` | `uuid` | FK `calls` CASCADE, UK, NOT NULL | Appel 1:1 | | Un CR par appel | Système |
| `title` | `varchar(255)` | défaut `''` | Titre réunion | | UI | User |
| `summary` | `text` | défaut `''` | Notes humaines | | | User |
| `transcript` | `text` | défaut `''` | Transcription STT | | Recherche | Système / IA |
| `ai_summary` | `text` | défaut `''` | Résumé IA | | | Système / IA |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

Recherche plein texte : **GIN trgm** sur `transcript` (ticket post-MVP si volumineux).

---

## Lien Messagerie (`messages.type = CALL`)

| Champ messagerie | Usage |
|------------------|--------|
| `messages.call_id` | UUID **sans FK** — référence logique `calls.id` |
| `messages.metadata` | Événement : `{"event": "CALL_STARTED" \| "CALL_ENDED" \| "CALL_MISSED", "duration_seconds": …}` |

Validation applicative : `type = CALL` ⇒ `call_id` NOT NULL. Pas de FK cross-module (déploiements indépendants). Suppression / anonymisation appel : ne pas CASCADE le message ; conserver la trace ou anonymiser `metadata`.

---

## Hors modèle transactionnel (Redis / WS)

| Besoin | Stockage |
|--------|----------|
| Statut live appel | Redis `call:{id}:status` (TTL ~5 min) |
| Présence en salle | Redis `call_presence:{room_id}` |
| Signalisation éphémère | WebSocket + webhooks LiveKit |
| `webrtc_sessions` | **Pas de PG au MVP** (voir §4) |

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| SFU | **LiveKit** — Django = auth, salle, tokens, webhooks |
| `webrtc_sessions` | **Hors migration MVP** — logs LiveKit + Redis optionnel |
| `call_quality_metrics` | Table PG simple MVP ; partition mensuelle si volume élevé ; rétention 90 j |
| `packet_loss` | `decimal(6,3)` + CHECK `0 <= x <= 100` (pourcentage) |
| PK | `uuid` partout sauf `call_quality_metrics.id` (`bigint` BIGSERIAL) |
| Messagerie | `messages.call_id` sans FK ; validation `CALL` ⇒ `call_id` requis |
| `livekit_rooms` / `meeting_history` | Relation **1:1** avec `calls` (`call_id` UK) |
| Enregistrements | Fichier dans **Médias** (`recordings.media_id` → `media_files`) |
