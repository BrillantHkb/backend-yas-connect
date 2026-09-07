# Catalogue Crypto — tables et attributs

App Django `apps.crypto`.  
Phase **3c** (après NOTIF-A, **avant** MESSAGERIE-B).  
Comportement : [CRYPTO-00](../plans/crypto_plans/CRYPTO-00-modele-chiffrement.md) · [CRYPTO-A](../plans/crypto_plans/CRYPTO-A-cles.md).

Le serveur **ne stocke jamais** de clé privée Signal. Les blobs 1-to-1 restent opaques.

**Légende « Renseigné par »** : Client / Système.

---

## Index

| Table | Rôle |
|-------|------|
| `identity_keys` | Clé d’identité **publique** Signal, 1 ligne / appareil |
| `signed_prekeys` | Signed prekey courante (rotation) |
| `one_time_prekeys` | One-time prekeys ; consommées à la lecture du bundle |
| `conversation_keys` | Clé de fil **cloud** (GROUP / AI) wrappée at-rest |

`conversation_id` : UUID **sans FK** (même pattern que `messages.call_id`) — le fil vit dans Messagerie.

---

## 1. `identity_keys`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | Propriétaire | | Bundle | Système |
| `device_id` | `uuid` | FK `devices` CASCADE, NOT NULL | Appareil | | Multi-device | Système |
| `registration_id` | `integer` | NOT NULL | Signal registration id | `12345` | Session ratchet | Client |
| `identity_public_key` | `bytea` | NOT NULL | Clé publique identité | 32–33 o | Vérif / X3DH | Client |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | Rotation rare | Système |

UK `(device_id)`. Un appareil = une identité.

---

## 2. `signed_prekeys`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `device_id` | `uuid` | FK `devices` CASCADE, NOT NULL | | | | Système |
| `key_id` | `integer` | NOT NULL | Id Signal | `1` | Bundle | Client |
| `public_key` | `bytea` | NOT NULL | SPK publique | | X3DH | Client |
| `signature` | `bytea` | NOT NULL | Signée par identité | | Vérif client | Client |
| `created_at` | `timestamptz` | NOT NULL | | | Rotation | Système |

UK `(device_id, key_id)`. Le bundle expose la **plus récente** (`created_at` DESC).

---

## 3. `one_time_prekeys`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `device_id` | `uuid` | FK `devices` CASCADE, NOT NULL | | | | Système |
| `key_id` | `integer` | NOT NULL | Id Signal | `42` | Bundle | Client |
| `public_key` | `bytea` | NOT NULL | OTPK publique | | X3DH 1-shot | Client |
| `consumed_at` | `timestamptz` | NULL | Consommée | | Anti-reuse | Système au GET bundle |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

UK `(device_id, key_id)`. Index `(device_id)` WHERE `consumed_at IS NULL` (prekeys disponibles).

---

## 4. `conversation_keys`

Clé de chiffrement **plateforme** pour `GROUP` / `AI`. **Pas** de ligne pour `PRIVATE` (E2E : clés seulement sur les clients).

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `conversation_id` | `uuid` | NOT NULL, index | Fil Messagerie | | Lookup | Système (hook GROUP) |
| `version` | `integer` | NOT NULL, DEF `1` | Rotation | `1` | Re-wrap | Système |
| `algorithm` | `varchar(32)` | NOT NULL, DEF `AES-256-GCM` | Algo fil | | Clients | Seed |
| `wrapped_key` | `bytea` | NOT NULL | Clé wrappée | | At-rest | Système |
| `is_current` | `boolean` | DEF `true` | Version active | | GET | Système |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

UK `(conversation_id, version)`. Wrap : AES-GCM avec `CRYPTO_MASTER_KEY` (env, **≠** `DJANGO_SECRET_KEY`).  
Le GET membre renvoie la clé **déwrappée** en TLS. Le serveur la déwrappe aussi pour modération groupe (CRYPTO-00).

---

## Hors catalogue

Pas de table de sessions ratchet (Double Ratchet **côté client**). Pas de backup seed. Pas de sender-key E2E groupe.
