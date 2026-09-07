# Catalogue Messagerie — tables et attributs

App Django prévue : `apps.messaging`.  
Référence **IAM** (`users`, `devices`) et **Médias** (`media_files`). Pas de duplication de ces tables.

**Légende « Renseigné par »** : User / Système — tables créées à la **phase 3** (module Messagerie).  
**Pas de PostGIS** : type `LOCATION` = GPS dans `encrypted_content` ([CRYPTO-00](../plans/crypto_plans/CRYPTO-00-modele-chiffrement.md)). `lat`/`lng` en JSON clair → **400** `FIELD_FORBIDDEN`.

Index : [INDEX-catalogue.md](INDEX-catalogue.md).

**Hors incrément (non modélisé ici)** : `typing_indicators` (Redis/WS), `scheduled_messages`, ancienne table `message_attachments` (remplacée par `messages.media_id`), `blocked_conversations` (remplacée par `blocked_users`).

---

## Index des tables

| Table | Rôle |
|--------|------|
| `conversations` | Fil de discussion (privé, groupe, IA) |
| `conversation_members` | Appartenance, rôle, unread, épinglage user |
| `messages` | Contenu chiffré, type, métadonnées |
| `message_reads` | Accusés livré / lu par user + device |
| `message_reactions` | Réactions emoji |
| `message_edits` | Historique d’édition |
| `message_deletes` | Suppression pour soi / pour tous |
| `message_forwards` | Lien message source → message forwardé |
| `pinned_messages` | Messages épinglés dans une conversation |
| `message_mentions` | Mentions @user (source relationnelle) |
| `message_polls` | Sondage lié à un message |
| `poll_options` | Options de vote |
| `poll_votes` | Votes utilisateur |
| `blocked_users` | Blocage user ↔ user |
| `reported_messages` | Signalement / modération |
| `message_bookmarks` | Favoris / signets |
| `archived_conversations` | Archivage conversation par user |
| `conversation_settings` | Préférences user sur une conversation |

---

## Relations (ERD)

| De | Vers | Cardinalité | FK |
|----|------|-------------|-----|
| `conversations` | `users` | n → 1 | `owner_id` |
| `conversations` | `messages` | n → 1 | `last_message_id` |
| `conversations` | `media_files` | n → 1 | `avatar_media_id` |
| `conversation_members` | `conversations` | n → 1 | `conversation_id` |
| `conversation_members` | `users` | n → 1 | `user_id` |
| `conversation_members` | `messages` | n → 1 | `last_read_message_id` |
| `messages` | `conversations` | n → 1 | `conversation_id` |
| `messages` | `users` | n → 1 | `sender_id` |
| `messages` | `messages` | n → 1 | `parent_message_id` (fil / réponse) |
| `messages` | `media_files` | n → 1 | `media_id` |
| `messages` | `message_polls` | n → 1 | `poll_id` (dénormalisation) |
| `messages` | — | | `call_id` uuid sans FK (module Appels, phase ultérieure) |
| `message_reads` | `messages` | n → 1 | `message_id` |
| `message_reads` | `users` | n → 1 | `user_id` |
| `message_reads` | `devices` | n → 1 | `device_id` |
| `message_reactions` | `messages` | n → 1 | `message_id` |
| `message_reactions` | `users` | n → 1 | `user_id` |
| `message_edits` | `messages` | n → 1 | `message_id` |
| `message_edits` | `users` | n → 1 | `edited_by_id` |
| `message_deletes` | `messages` | n → 1 | `message_id` |
| `message_deletes` | `users` | n → 1 | `deleted_by_id` |
| `message_forwards` | `messages` | n → 1 | `original_message_id`, `new_message_id` |
| `message_forwards` | `users` | n → 1 | `forwarded_by_id` |
| `pinned_messages` | `conversations` | n → 1 | `conversation_id` |
| `pinned_messages` | `messages` | n → 1 | `message_id` |
| `pinned_messages` | `users` | n → 1 | `pinned_by_id` |
| `message_mentions` | `messages` | n → 1 | `message_id` |
| `message_mentions` | `users` | n → 1 | `mentioned_user_id` |
| `message_polls` | `messages` | 1 → 1 | `message_id` |
| `message_polls` | `users` | n → 1 | `created_by_id` |
| `message_polls` | `devices` | n → 1 | `device_id` |
| `poll_options` | `message_polls` | n → 1 | `poll_id` |
| `poll_votes` | `poll_options` | n → 1 | `poll_option_id` |
| `poll_votes` | `users` | n → 1 | `user_id` |
| `blocked_users` | `users` | n → 1 | `blocker_id`, `blocked_id` |
| `reported_messages` | `messages` | n → 1 | `message_id` |
| `reported_messages` | `users` | n → 1 | `reported_by_id`, `reviewed_by_id` |
| `message_bookmarks` | `messages` | n → 1 | `message_id` |
| `message_bookmarks` | `users` | n → 1 | `user_id` |
| `archived_conversations` | `conversations` | n → 1 | `conversation_id` |
| `archived_conversations` | `users` | n → 1 | `user_id` |
| `conversation_settings` | `conversations` | n → 1 | `conversation_id` |
| `conversation_settings` | `users` | n → 1 | `user_id` |

**Mentions** : `message_mentions` = source relationnelle (notifications, requêtes) ; `messages.mentions` jsonb = snapshot dénormalisé pour affichage.

---

## 1. `conversations`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Identifiant interne | | | Système |
| `conversation_uuid` | `uuid` | UK, NOT NULL | ID public / deep-link | | Partage, API | Système |
| `type` | `varchar(16)` | NOT NULL | `PRIVATE` / `GROUP` / `AI` | `GROUP` | Type de fil | Système |
| `title` | `varchar(255)` | défaut `''` | Nom affiché (groupes) | `Équipe NOC` | Liste conversations | User / Système |
| `description` | `text` | défaut `''` | Description groupe | | Profil groupe | User |
| `encrypted` | `boolean` | NOT NULL | E2E fil | `true` si `PRIVATE` | CRYPTO-00 | Système à création |
| `last_message_at` | `timestamptz` | NULL | Tri inbox | | Liste triée | Système |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |
| `last_message_id` | `uuid` | FK `messages` SET NULL, NULL | Dernier message | | Aperçu inbox | Système |
| `avatar_media_id` | `uuid` | FK `media_files` SET NULL, NULL | Avatar groupe | | Affichage | User |
| `owner_id` | `uuid` | FK `users` SET NULL, NULL | Créateur / propriétaire | | Groupe | User |

---

## 2. `conversation_members`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `username` | `varchar(100)` | défaut `''` | Pseudo affiché dans le groupe | `jdupont` | Groupes | User |
| `role` | `varchar(16)` | NOT NULL | `OWNER` / `ADMIN` / `MEMBER` / `READ_ONLY` | `MEMBER` | Droits groupe | Système / admin groupe |
| `unread_count` | `integer` | défaut `0` | Compteur non lus | `3` | Badge | Système |
| `left_at` | `timestamptz` | NULL | Quitte le groupe | | Historique | User |
| `active` | `boolean` | défaut `true` | Membre actif | | Filtre participants | Système |
| `archived` | `boolean` | défaut `false` | Masqué inbox user | | Archivage léger | User |
| `pinned` | `boolean` | défaut `false` | Épinglé inbox user | | Tri | User |
| `joined_at` | `timestamptz` | NOT NULL | Date d’entrée | | | Système |
| `conversation_id` | `uuid` | FK `conversations` CASCADE, NOT NULL | | | | Système |
| `last_read_message_id` | `uuid` | FK `messages` SET NULL, NULL | Dernier lu | | Accusés / unread | Système |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | | | | Système |

UK `(conversation_id, user_id)`.

---

## 3. `messages`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `type` | `varchar(16)` | NOT NULL | Voir enum ci-dessous | `TEXT` | Rendu UI | User / Système |
| `encrypted_content` | `bytea` | NULL | Corps chiffré | | Stockage | Système |
| `mentions` | `jsonb` | défaut `[]` | Snapshot @users | | Affichage rapide | Système |
| `tags` | `jsonb` | défaut `[]` | Hashtags / labels | | Recherche | User |
| `forwarded` | `boolean` | défaut `false` | Message forwardé | | | Système |
| `edited` | `boolean` | défaut `false` | A été modifié | | Badge « édité » | Système |
| `deleted` | `boolean` | défaut `false` | Soft-delete global | | Masquage | Système |
| `pinned` | `boolean` | défaut `false` | Épinglé dans le fil | | | User / admin |
| `priority` | `smallint` | défaut `0` | Priorité affichage | | Urgent | User |
| `ai_generated` | `boolean` | défaut `false` | Contenu IA | | Transparence | Système |
| `metadata` | `jsonb` | défaut `{}` | Données type-spécifiques | | Extensibilité | Système |
| `sent_at` | `timestamptz` | NOT NULL | Horodatage envoi | | Tri fil | Système |
| `created_at` | `timestamptz` | NOT NULL | Insertion BDD | | Audit | Système |
| `media_id` | `uuid` | FK `media_files` SET NULL, NULL | Pièce jointe | | IMAGE, DOC… | User |
| `conversation_id` | `uuid` | FK `conversations` CASCADE, NOT NULL | | | | Système |
| `parent_message_id` | `uuid` | FK self SET NULL, NULL | Réponse / fil | | Thread | User |
| `poll_id` | `uuid` | FK `message_polls` SET NULL, NULL | Lien sondage | | type POLL | Système |
| `call_id` | `uuid` | NULL, sans FK | Réf. appel (module Appels) | | type CALL | Système |
| `sender_id` | `uuid` | FK `users` SET NULL, NULL | Auteur | | | User |

**Enum `type`** : `TEXT`, `IMAGE`, `VIDEO`, `AUDIO`, `DOCUMENT`, `GIF`, `LOCATION`, `POLL`, `SYSTEM`, `CALL`, `AI`.

Pas de colonne `content` en clair : déchiffrement côté client / service.

---

## 4. `message_reads`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `delivered_at` | `timestamptz` | NULL | Accusé livré | | ✓✓ gris | Système |
| `read_at` | `timestamptz` | NULL | Accusé lu | | ✓✓ bleu | User |
| `message_id` | `uuid` | FK `messages` CASCADE, NOT NULL | | | | Système |
| `device_id` | `uuid` | FK `devices` SET NULL, NULL | Appareil | | Multi-device | Système |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | | | | Système |

UK `(message_id, user_id, device_id)` — `device_id` NULL traité comme un seul slot « web » par user (contrainte partielle ou COALESCE en app).

---

## 5. `message_reactions`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `emoji` | `varchar(20)` | NOT NULL | Réaction | `👍` | | User |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `message_id` | `uuid` | FK `messages` CASCADE, NOT NULL | | | | Système |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | | | | User |

UK `(message_id, user_id, emoji)` recommandé.

---

## 6. `message_edits`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `previous_encrypted_content` | `bytea` | NOT NULL | Ancien corps (même régime que le fil) | | Historique | Système |
| `edited_at` | `timestamptz` | NOT NULL | | | | Système |
| `message_id` | `uuid` | FK `messages` CASCADE, NOT NULL | | | | Système |
| `edited_by_id` | `uuid` | FK `users` SET NULL, NULL | | | | User |

---

## 7. `message_deletes`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `delete_scope` | `varchar(16)` | NOT NULL | `SELF` / `EVERYONE` | `SELF` | Supprimer pour moi / tous | User |
| `deleted_at` | `timestamptz` | NOT NULL | | | | Système |
| `message_id` | `uuid` | FK `messages` CASCADE, NOT NULL | | | | Système |
| `deleted_by_id` | `uuid` | FK `users` SET NULL, NULL | | | | User |

---

## 8. `message_forwards`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `original_message_id` | `uuid` | FK `messages` CASCADE, NOT NULL | Message source | | Traçabilité | Système |
| `new_message_id` | `uuid` | FK `messages` CASCADE, NOT NULL | Copie forwardée | | | Système |
| `forwarded_by_id` | `uuid` | FK `users` SET NULL, NULL | | | | User |

---

## 9. `pinned_messages`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `pinned_at` | `timestamptz` | NOT NULL | | | | Système |
| `conversation_id` | `uuid` | FK `conversations` CASCADE, NOT NULL | | | | Système |
| `message_id` | `uuid` | FK `messages` CASCADE, NOT NULL | | | | User |
| `pinned_by_id` | `uuid` | FK `users` SET NULL, NULL | | | | User |

UK `(conversation_id, message_id)`.

---

## 10. `message_mentions`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `created_at` | `timestamptz` | NOT NULL | | | Notifications | Système |
| `message_id` | `uuid` | FK `messages` CASCADE, NOT NULL | | | | Système |
| `mentioned_user_id` | `uuid` | FK `users` CASCADE, NOT NULL | User @mentionné | | Notif + privacy | Système |

UK `(message_id, mentioned_user_id)`.

---

## 11. `message_polls`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `question` | `text` | NOT NULL | Question du sondage | `Qui vient ?` | | User |
| `multiple_choices` | `boolean` | défaut `false` | Vote multiple | | | User |
| `closed_at` | `timestamptz` | NULL | Clôture votes | | | User / Système |
| `message_id` | `uuid` | FK `messages` CASCADE, UK, NOT NULL | Message parent | | type POLL | Système |
| `device_id` | `uuid` | FK `devices` SET NULL, NULL | Appareil créateur | | | Système |
| `created_by_id` | `uuid` | FK `users` SET NULL, NULL | | | | User |

---

## 12. `poll_options`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `label` | `text` | NOT NULL | Libellé option | `Oui` | | User |
| `vote_count` | `integer` | défaut `0` | Dénormalisation compteur | | Affichage | Système |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `poll_id` | `uuid` | FK `message_polls` CASCADE, NOT NULL | | | | Système |

---

## 13. `poll_votes`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `poll_option_id` | `uuid` | FK `poll_options` CASCADE, NOT NULL | Option choisie | | | User |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | Votant | | | User |

UK `(poll_option_id, user_id)` si une option = un vote ; pour choix multiples, UK `(user_id, poll_option_id)` identique.

---

## 14. `blocked_users`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `reason` | `text` | défaut `''` | Motif | | Modération | User |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `blocked_id` | `uuid` | FK `users` CASCADE, NOT NULL | User bloqué | | | User |
| `blocker_id` | `uuid` | FK `users` CASCADE, NOT NULL | Qui bloque | | | User |

UK `(blocker_id, blocked_id)`.

---

## 15. `reported_messages`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `reason` | `text` | NOT NULL | Motif signalement | | Modération | User |
| `status` | `varchar(16)` | défaut `PENDING` | `PENDING` / `REVIEWED` / `DISMISSED` | | File admin | Système |
| `reviewed_at` | `timestamptz` | NULL | Traité le | | | Admin |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `message_id` | `uuid` | FK `messages` CASCADE, NOT NULL | | | | Système |
| `reviewed_by_id` | `uuid` | FK `users` SET NULL, NULL | Modérateur | | | Admin |
| `reported_by_id` | `uuid` | FK `users` SET NULL, NULL | Signaleur | | | User |

---

## 16. `message_bookmarks`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `note` | `text` | défaut `''` | Note personnelle | | Favoris | User |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `message_id` | `uuid` | FK `messages` CASCADE, NOT NULL | | | | User |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | | | | User |

UK `(user_id, message_id)`.

---

## 17. `archived_conversations`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `created_at` | `timestamptz` | NOT NULL | Date archivage | | Inbox | User |
| `conversation_id` | `uuid` | FK `conversations` CASCADE, NOT NULL | | | | User |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | | | | User |

UK `(user_id, conversation_id)`.

---

## 18. `conversation_settings`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `muted` | `boolean` | défaut `false` | Notifications coupées | | | User |
| `visibility` | `varchar(16)` | défaut `PRIVATE` | `PRIVATE` / `PUBLIC` | | Découverte groupe | Owner |
| `locked` | `boolean` | défaut `false` | Fil verrouillé (plus de messages) | | Modération | Admin |
| `max_members` | `integer` | NULL | Plafond membres | `256` | Groupes | Owner |
| `custom_settings` | `jsonb` | défaut `{}` | Extensions | | | User |
| `conversation_id` | `uuid` | FK `conversations` CASCADE, NOT NULL | | | | Système |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | Préférences **par user** | | Mute perso | User |

UK `(conversation_id, user_id)`. `visibility` / `locked` / `max_members` : éditables par OWNER/ADMIN ; `muted` par le titulaire.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Contenu message | `encrypted_content` uniquement (pas de `content` clair) |
| Édition | `message_edits.previous_encrypted_content` (`bytea`) — pas de `previous_content` clair |
| Localisation | `type=LOCATION` ; GPS **dans le blob** ; pas de colonne geography |
| `conversations.encrypted` | `PRIVATE` → **toujours `true`** ; `GROUP`/`AI` → **`false`** ([CRYPTO-00](../plans/crypto_plans/CRYPTO-00-modele-chiffrement.md)) |
| Pièces jointes | FK directe `messages.media_id` (pas de `message_attachments`) |
| Archivage | `archived_conversations` + flag `conversation_members.archived` |
| Blocage | `blocked_users` (user ↔ user), pas par conversation |
| Typing / planifiés | Hors BDD transactionnelle (Redis / ticket ultérieur) |
| `call_id` | UUID **sans FK** — référence logique `calls.id` ; `type=CALL` ⇒ obligatoire ; pas de FK cross-module |
| PK externes | `uuid` partout (IAM, Médias, Devices) |
