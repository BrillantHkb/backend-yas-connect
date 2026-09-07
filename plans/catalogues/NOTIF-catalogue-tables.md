# Catalogue Notifications — tables et attributs

App Django `apps.notifications`.  
Phase **3b** (après MEDIA-A, avant / avec MESSAGERIE-B et APPELS sonnerie).  
Source comportement : [NOTIF-R](../plans/notif_plans/NOTIF-R-roles-permissions.md) · [NOTIF-A](../plans/notif_plans/NOTIF-A-in-app-push.md).

**Légende « Renseigné par »** : Système (service) / User / Seed.

Push tokens : **pas** de table dédiée — `devices.push_token` ([IAM](IAM-catalogue-tables.md) AUTH-E).

---

## Index

| Table | Rôle |
|-------|------|
| `notifications` | Centre de notifs in-app (1 ligne / événement / destinataire) |
| `notification_preferences` | 1-1 user : push, sonnerie appel, DND |

---

## 1. `notifications`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Identifiant | | Deep-link, mark-read | Système |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL, index | Destinataire | | Inbox perso | Système |
| `type` | `varchar(32)` | NOT NULL, index | Famille | `MESSAGE_NEW` | Filtre / collapse | Système |
| `title` | `varchar(255)` | NOT NULL | Titre affiché | `Nouveau message` | In-app + push | Système |
| `body` | `varchar(512)` | défaut `''` | Sous-titre | `Appel manqué` | UI | Système |
| `payload` | `jsonb` | NOT NULL, DEF `{}` | Ids métier | `{"conversation_id":"…"}` | Navigation | Système |
| `collapse_key` | `varchar(128)` | défaut `''`, index | Regroupement FCM | `msg:{conversation_id}` | Remplacer push | Système |
| `read_at` | `timestamptz` | NULL | Lu in-app | | Badge | User (mark-read) / Système |
| `pushed_at` | `timestamptz` | NULL | Push envoyé | | Retry / debug | Système |
| `created_at` | `timestamptz` | NOT NULL, index | Horodatage | | Tri inbox | Système |

`type` enum applicatif : `MESSAGE_NEW` · `MESSAGE_MENTION` · `CALL_INCOMING` · `CALL_MISSED` · `DEVICE_NEW` · `SYSTEM`.

**CRYPTO-00 :** pour `MESSAGE_NEW` / `MESSAGE_MENTION` sur fil `PRIVATE`, `title`/`body`/`payload` **ne contiennent jamais** le plaintext du message.

---

## 2. `notification_preferences`

1-1 avec `users`. Créée à l’ouverture du compte (même moment que `user_preferences`).

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `user_id` | `uuid` | UK FK `users` CASCADE, NOT NULL | Propriétaire | | Load au login | Création compte |
| `push_enabled` | `boolean` | DEF `true` | Push distant | `false` | App fermée | User |
| `in_app_enabled` | `boolean` | DEF `true` | Centre de notifs | `false` | Mute global in-app | User |
| `call_ring_enabled` | `boolean` | DEF `true` | Sonnerie appel | `false` | Silence appels (≠ `allow_calls`) | User |
| `message_preview_enabled` | `boolean` | DEF `true` | Aperçu corps **groupe uniquement** | `false` | Privacy lockscreen | User |
| `quiet_hours_enabled` | `boolean` | DEF `false` | DND horaire | | Terrain / nuit | User |
| `quiet_hours_start` | `time` | NULL | Début DND | `22:00` | Fuseau `user_preferences.timezone` | User |
| `quiet_hours_end` | `time` | NULL | Fin DND | `06:00` | | User |
| `updated_at` | `timestamptz` | NOT NULL | | | Sync multi-device | Système |

Mute **par fil** : `conversation_settings.muted` (Messagerie) — pas dupliqué ici.  
Son UI : `user_preferences.notification_sound` (IAM).  
`call_ring_enabled=false` n’interdit pas l’appel (`privacy_settings.allow_calls`) : ça coupe seulement push/sonnerie.

---

## Hors catalogue

Pas de table `push_receipts` / `notification_templates` au MVP. Retry FCM = logs applicatifs.  
Canaux Social / IA : types futurs, même table.
