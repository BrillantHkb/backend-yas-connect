# Catalogue des index PostgreSQL

Source de vérité **btree (simple)** vs **GIN** pour tous les modules.  
Les `Meta.indexes` des `plans/code/*_models.py` **doivent** coller à ce fichier.

Django crée déjà : PK, `unique=True`, `unique_together`, `db_index=True`, index des `ForeignKey`.  
Ici : **composites**, **GIN jsonb**, **GIN trigram** (`ILIKE '%…%'`).

## Règle

| Type | Quand | Opérateur PG typique |
|------|--------|----------------------|
| **B-tree** (simple) | égalité, plage de dates, tri, UNIQUE | `=`, `<`, `BETWEEN`, `ORDER BY` |
| **GIN `jsonb_ops`** | colonnes `jsonb` | `@>`, `?`, `?|` |
| **GIN `gin_trgm_ops`** | recherche partielle texte | `ILIKE '%dupont%'` |

**Pas de GIN** sur UUID, booléens, enums courts, IP en égalité — le btree suffit.

**Extensions AUTH-01** (1re opération de `0001` ou migration `0002` **avant** les `AddIndex` GIN trgm) :

```python
from django.contrib.postgres.operations import TrigramExtension

operations = [TrigramExtension(), …]  # CREATE EXTENSION IF NOT EXISTS pg_trgm
```

`INSTALLED_APPS` : `"django.contrib.postgres"` (GinIndex).

---

## IAM (`apps.iam`) — dès AUTH-01

| Table | Index | Type | Pourquoi |
|-------|--------|------|----------|
| `users` | `email`, `username`, `matricule` | btree UNIQUE | login, mentions, RH |
| `users` | `(is_active, is_locked)` | btree | listes admin / 403 |
| `users` | `pending_approval` | btree (`db_index` recommandé) | file d’attente RH AUTH-D |
| `users` | `status` | btree (`db_index`) | présence (PRES-A enum) |
| `users` | `ldap_dn` | btree UNIQUE | AUTH-13 / AUTH-16 |
| `users` | `first_name`, `last_name`, `email`, `username`, `matricule` | **GIN trgm** | annuaire `ILIKE` |
| `roles` / `region` / `permissions` | `code` | btree UNIQUE | lookup (AUTH-R : `permissions.code` 96 car.) |
| `permissions` | `(module, resource, action)` | btree UNIQUE | AUTH-R01 ; remplace `(module, action)` |
| `role_permissions` | `(role, permission)` | btree UNIQUE | AUTH-R04 / R08 |
| `sessions` | `(user, is_active)` | btree | middleware JWT ; AUTH-12 1 active / device |
| `sessions` | `access_jti`, `refresh_jti` | btree UNIQUE | |
| `sessions` | `expires_at` | btree | purge |
| `login_history` | `(user, -created_at)` | btree | historique fiche |
| `login_history` | `(email, -created_at)` | btree | brute-force / SOC |
| `login_history` | `(ip_address, -created_at)` | btree | SOC par IP |
| `login_history` | `success`, `created_at` | btree (`db_index`) | |
| `refresh_tokens` | `jti` UNIQUE ; `(user, expires_at)` ; `expires_at` | btree | AUTH-09, purge |
| `password_reset_tokens` | `expires_at` | btree | purge tokens |
| `devices` | `(user, device_uuid)` UNIQUE ; `last_seen` | btree | AUTH-11 |
| `otp_secrets` | `backup_codes` | **GIN jsonb** | lookup codes secours |
| `audit_logs` | `(user, -created_at)` | btree | timeline user |
| `audit_logs` | `(module, action)` | btree | filtres admin |
| `audit_logs` | `(entity_type, entity_id)` | btree | drill-down |
| `audit_logs` | `created_at` | btree | pagination |
| `audit_logs` | `old_values`, `new_values`, `metadata` | **GIN jsonb** | recherche dans le JSON |

---

## Annuaire (`apps.annuaire`) — dès AUTH-01 (tables vides)

| Table | Index | Type | Pourquoi |
|-------|--------|------|----------|
| `segments` | `code` UNIQUE ; `(parent_segment, is_active)` | btree | arbre |
| `segments` | `name` | **GIN trgm** | recherche unité |
| `user_segments` | `(user, is_active)` ; `(segment, is_active)` | btree | affectation courante |
| `user_skills` | `(user, skill_name)` | btree UNIQUE recommandé | 1 skill / user |
| `user_skills` | `skill_name` | **GIN trgm** | recherche expert |
| `user_certifications` | `certification_name` | **GIN trgm** | recherche certif |

---

## Médias (`apps.media`) — dès AUTH-01 (0 ligne)

| Table | Index | Type | Pourquoi |
|-------|--------|------|----------|
| `media_files` | `(owner, -created_at)` ; `scan_status` ; `media_type` | btree | quota / galerie ; files scan ; filtres type |
| `media_files` | `checksum` | btree **UNIQUE** | dédup stricte (NULL si inconnu) |
| `media_metadata` | `metadata` | **GIN jsonb** | recherche EXIF / tags |
| `videos` | `transcoding_status` | btree | pipeline transcodage |
| `audio_messages` | `transcription_status` ; `waveform` | btree / **GIN jsonb** | STT ; affichage |
| `voice_transcriptions` | `(audio, -created_at)` | btree | historique STT |
| `documents` | `category` ; `(owner, -created_at)` | btree | GED filtres |
| `document_versions` | `(document, version_number)` UNIQUE ; `media_id` | btree | historique ; blob version |
| `media_access_logs` | `(media, -created_at)` ; `(user, -created_at)` ; `(action, -created_at)` | btree | audit SOC |
| `storage_usage` | `(user, storage_type)` UNIQUE | btree | quota agrégé |

Pas de GIN trgm sur `extracted_text` en AUTH-01 (ticket recherche GED ultérieur).

---

## Config (`apps.config`) — dès AUTH-B

| Table | Index | Type | Pourquoi |
|-------|--------|------|----------|
| `system_settings` | `(category, setting_key)` UNIQUE | btree | lecture clé |
| `system_settings` | `setting_value` | **GIN jsonb** | |
| `scheduled_jobs` | `job_name` UNIQUE ; `(enabled, next_execution)` | btree | runner |
| `feature_flags` | `feature_code` UNIQUE ; `target_roles` | btree / **GIN jsonb** | |

---

## Messagerie (`apps.messaging`) — phase 3

| Table | Index | Type | Pourquoi |
|-------|--------|------|----------|
| `conversations` | `-last_message_at` ; `type` | btree | inbox triée ; filtres |
| `conversation_members` | `(conversation, user)` UNIQUE ; `(user, active, -joined_at)` ; `(conversation, active)` | btree | membership ; inbox user |
| `messages` | `(conversation, -sent_at)` ; `(sender, -sent_at)` ; `type` ; `call_id` | btree | fil chronologique ; historique user ; traces appels |
| `messages` | `mentions`, `tags`, `metadata` | **GIN jsonb** | recherche / filtres |
| `message_reads` | `(message, user, device)` UNIQUE ; `(user, -read_at)` | btree | accusés ; inbox lus |
| `message_reactions` | `(message, user, emoji)` UNIQUE | btree | 1 emoji / user / message |
| `message_edits` | `(message, -edited_at)` | btree | historique |
| `pinned_messages` | `(conversation, message)` UNIQUE | btree | épinglés groupe |
| `message_mentions` | `(mentioned_user, -created_at)` | btree | notifs @ |
| `poll_votes` | `(poll_option, user)` UNIQUE | btree | anti double-vote |
| `blocked_users` | `(blocker, blocked)` UNIQUE | btree | blocage |
| `reported_messages` | `(status, -created_at)` | btree | file modération |
| `message_bookmarks` | `(user, message)` UNIQUE | btree | favoris |
| `archived_conversations` | `(user, conversation)` UNIQUE | btree | archivage |
| `conversation_settings` | `(conversation, user)` UNIQUE ; `custom_settings` | btree / **GIN jsonb** | mute / prefs |

Pas de GIN trgm sur le corps message (contenu chiffré `bytea`). **Pas de PostGIS** messagerie : GPS dans `encrypted_content` (CRYPTO-00).

---

## Crypto (`apps.crypto`) — phase 3c

| Table | Index | Type | Pourquoi |
|-------|--------|------|----------|
| `identity_keys` | `device_id` UNIQUE | btree | 1 identité / appareil |
| `signed_prekeys` | `(device_id, key_id)` UNIQUE ; `(device_id, -created_at)` | btree | rotation ; bundle = plus récente |
| `one_time_prekeys` | `(device_id, key_id)` UNIQUE ; `device_id` WHERE `consumed_at IS NULL` | btree | recharge ; OTPK disponibles |
| `conversation_keys` | `(conversation_id, version)` UNIQUE ; `conversation_id` | btree | clé cloud par fil |

Pas de GIN (pas de jsonb métier).

---

## Notifications (`apps.notifications`) — phase 3b

| Table | Index | Type | Pourquoi |
|-------|--------|------|----------|
| `notifications` | `(user_id, -created_at)` ; `(user_id, read_at)` ; `collapse_key` | btree | inbox ; badge ; collapse FCM |
| `notifications` | `payload` | **GIN jsonb** | filtre ids métier |
| `notification_preferences` | `user_id` UNIQUE | btree | 1-1 load login |

---

## Appels (`apps.calls`) — phase 5

| Table | Index | Type | Pourquoi |
|-------|--------|------|----------|
| `calls` | `(caller, -created_at)` ; `status` ; `-created_at` | btree | historique initiateur ; files actives ; tri |
| `call_participants` | `(call, user)` UNIQUE ; `(call, joined_at)` | btree | 1 participation / user ; timeline |
| `call_sessions` | `(call, user)` ; `(device, -connected_at)` | btree | multi-device ; support |
| `livekit_rooms` | `call_id` UK ; `room_name` UK | btree UNIQUE | 1 salle / appel |
| `media_tracks` | `(call, active)` | btree | pistes live |
| `recordings` | `(call, -created_at)` | btree | historique enregistrements |
| `screen_shares` | `(call, -started_at)` | btree | épisodes partage |
| `call_quality_metrics` | `(call, -created_at)` ; `(user, -created_at)` ; `created_at` | btree | courbes QoS ; purge rétention |
| `meeting_history` | `call_id` UK ; `transcript` | btree UNIQUE / **GIN trgm** | 1 CR / appel ; recherche STT |

`webrtc_sessions` : **pas de migration MVP** (pas d’index PG).  
`messages.call_id` (Messagerie) : btree `call_id` pour fil `type=CALL`.

Partition `call_quality_metrics` : ticket post-MVP si volume > ~100k lignes/jour.

---

## Modules futurs (même règle à la 1re migration du module)

| Module | B-tree | GIN |
|--------|--------|-----|
| Social | `(author_id, created_at)` posts | **GIN trgm / tsvector** contenu |
| Canaux / Télécom | `(site_id, created_at)` WO | **GIN jsonb** metadata ticket |
| IA / RAG | `(document_id, chunk_index)` | **GIN** vecteur (pgvector) **ou** tsvector chunks — ticket IA, pas AUTH-01 |

---

## AUTH-A — rappel

Le login a besoin des btree `users.email` / `username` (UNIQUE), `sessions (user, is_active)` / `access_jti`, et UK `devices (user, device_uuid)`.  
Les GIN sont **créés dès `0001`**.
