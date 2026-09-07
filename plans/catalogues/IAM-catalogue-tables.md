# Catalogue IAM — tables et attributs

App Django `apps.iam`.  
Hors IAM (catalogues dédiés) : **Annuaire** [`ANNUAIRE-catalogue-tables.md`](ANNUAIRE-catalogue-tables.md) · **Médias** [`MEDIA-catalogue-tables.md`](MEDIA-catalogue-tables.md).

**Supprimé :** `user_roles` (rôle unique = `users.role_id`) · `trusted_devices` (confiance = `devices.trusted`).

**Légende « Renseigné par »**

| Valeur | Sens |
|--------|------|
| Seed | `seed_iam` (`USER`, user test) |
| AUTH-A | login local (AUTH-01 … 12) |
| RH / admin | back-office |
| User | app |
| Système | `uuid4`, `now()`, hasher, identity |
| Ticket | AUTH-13, AUTH-19… (hors A) |
| Compte | création user (ligne 1-1 prefs/privacy) |

Enums communs :

- **`login_method`** : `PASSWORD` \| `LDAP` \| `SSO` \| `OTP` \| `REFRESH` \| `DEVICE_LINK` (`SSO` non livré AUTH-B ; `DEVICE_LINK` = AUTH-J)
- **`reset_channel`** : `SMS` \| `EMAIL` \| `APPEL`
- **`users.status`** : `ONLINE` \| `OFFLINE`
- **visibilité privacy** : `EVERYONE` \| `CONTACTS` \| `NOBODY`

---

## Index IAM

| # | Table | AUTH-A (01–12) |
|---|--------|---------|
| 1 | `roles` | seed `USER` |
| 2 | `region` | vide (référentiel RH) |
| 3 | `permissions` | vide |
| 4 | `role_permissions` | vide |
| 5 | `users` | lecture + `last_login` / `first_login` ; `status` / `region_id` inchangés au login. AUTH-B : `ldap_dn` |
| 6 | `user_preferences` | 1 ligne à la création compte (seed) |
| 7 | `privacy_settings` | 1 ligne à la création compte (seed) |
| 8 | `sessions` | INSERT (`device_id`, access + refresh jti) |
| 9 | `login_history` | INSERT |
| 10 | `devices` | upsert AUTH-11 |
| 11 | `refresh_tokens` | INSERT AUTH-10 |
| 12 | `password_history` | vide |
| 13 | `password_reset_tokens` | vide |
| 14 | `otp_secrets` | vide AUTH-A ; écrit **AUTH-C** |
| 15 | `email_verifications` | vide |
| 16 | `audit_logs` | vide |

---

## 1. `roles`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Identifiant | `3f2a…` | FK `users.role_id` | Système |
| `code` | `varchar(32)` | UK, index, NOT NULL | Clé technique JWT / ACL | `USER` | Claim `role` | Seed / RH |
| `name` | `varchar(128)` | NOT NULL | Libellé UI | `Utilisateur` | Affichage | Seed / RH |
| `description` | `text` | NULL ou `''` | Aide admin | `Accès applicatif standard` | Fiche rôle | Seed / RH |
| `level` | `smallint` | NOT NULL, défaut `0` | Rang hiérarchique | `0` USER, `100` ADMIN | Comparer / trier rôles | Seed / RH |
| `is_system` | `boolean` | NOT NULL, défaut `false` | Rôle plateforme | `true` | Interdit suppression | Seed |
| `created_at` | `timestamptz` | NOT NULL | Création | | Audit | Système |
| `updated_at` | `timestamptz` | NOT NULL | MAJ | | Audit | Système |

---

## 2. `region`

Référentiel géographique (Maritime, Plateaux, …). **0 ligne AUTH-01.** Seed / RH plus tard.  
SQL = `region` (singulier, ERD). FK `users.region_id`.

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Identifiant | | FK `users.region_id` | Système |
| `code` | `varchar(50)` | UK, index, NOT NULL | Clé technique | `MARITIME` | Filtre, JWT / annuaire | Seed / RH |
| `name` | `varchar(100)` | UK, NOT NULL | Libellé UI | `Maritime` | Affichage | Seed / RH |
| `created_at` | `timestamptz` | NOT NULL | Création | | Audit | Système |
| `updated_at` | `timestamptz` | NOT NULL | MAJ | | Audit | Système |

---

## 3. `permissions`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Identifiant | | | Système |
| `code` | `varchar(64)` | UK, index, NOT NULL | Clé unique | `msg.send` | Check API | Seed RBAC |
| `name` | `varchar(128)` | NOT NULL | Libellé | `Envoyer un message` | UI admin | Seed RBAC |
| `description` | `text` | NULL ou `''` | Détail | `Envoi 1-1 et groupes` | Doc interne | Seed RBAC |
| `module` | `varchar(64)` | NOT NULL | Domaine | `messaging` | Grouper l’UI | Seed RBAC |
| `action` | `varchar(64)` | NOT NULL | Verbe | `send` | Unique avec `module` | Seed RBAC |
| `is_system` | `boolean` | NOT NULL, défaut `false` | Permission plateforme | `true` | Non supprimable | Seed |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

UK `(module, action)`.

---

## 4. `role_permissions`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `role_id` | `uuid` | FK `roles` CASCADE, NOT NULL | Rôle | | Matrice ACL | Admin |
| `permission_id` | `uuid` | FK `permissions` CASCADE, NOT NULL | Droit | | | Admin |
| `assigned_by_id` | `uuid` | FK `users` SET NULL, NULL | Qui a accordé | | Audit | Admin |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

UK `(role_id, permission_id)`.

---

## 5. `users`

Présence = `status` (`ONLINE` / `OFFLINE`). **Login** = `is_active` / `is_locked` uniquement.  
Thème / last seen / appels → `privacy_settings` + `user_preferences`. Pas de `manager_id` (N+1 = org Annuaire). Pas de `user_roles`.

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Identité | | JWT `sub` | Système |
| `email` | `varchar(254)` | UK, NOT NULL, lower | Login | `jean.dupont@yas.tg` | AUTH-01 / AUTH-13 (lookup, pas de copie AD) | Seed / RH |
| `username` | `varchar(64)` | UK, NOT NULL | Handle | `jdupont` | Mentions | Seed / User |
| `first_name` | `varchar(128)` | défaut `''` | Prénom | `Jean` | Annuaire | RH / User |
| `last_name` | `varchar(128)` | défaut `''` | Nom | `Dupont` | | RH / User |
| `matricule` | `varchar(32)` | UK, NULL | Matricule | `TG2026015` | Recherche | RH |
| `phone` | `varchar(32)` | NULL | E.164 | `+22890…` | Appels / OTP SMS | RH / User |
| `job_title` | `varchar(128)` | défaut `''` | Intitulé actuel | `Ingénieur NOC` | Carte profil | RH |
| `status` | `varchar(16)` | NOT NULL, index, enum `ONLINE`/`OFFLINE`, défaut `OFFLINE` | Présence | `ONLINE` | Liste contacts, pastille | Présence WS / heartbeat |
| `language` | `varchar(8)` | défaut `fr` | Langue profil (peut ≠ prefs) | `fr` | Fallback i18n | RH / User |
| `timezone` | `varchar(64)` | défaut `Africa/Lome` | Fuseau profil (peut ≠ prefs) | | Planning | RH / User |
| `role_id` | `uuid` | FK `roles` PROTECT, NOT NULL | Rôle unique | `USER` | JWT, ACL | Seed / RH |
| `ldap_dn` | `varchar(512)` | UK, NULL | DN AD (lien sync) | `CN=Jean Dupont,OU=…` | AUTH-D02 / AUTH-13 pose si vide ; AUTH-16 sync | AUTH-D02 / AUTH-13 |
| `region_id` | `uuid` | FK `region` SET NULL, NULL | Région géographique | `MARITIME` | Filtre / profil | RH |
| `segment_id` | `uuid` | FK `segments` SET NULL, NULL | Unité courante | | Filtre org | RH (Annuaire) |
| `avatar_id` | `uuid` | FK `media_files` SET NULL, NULL | Photo | | Annuaire | User / Médias |
| `password_hash` | `varchar(255)` | NOT NULL | Hash Argon2id | `argon2$…` | Vérif MDP — **jamais API** | Seed / change MDP |
| `is_active` | `boolean` | défaut `true` | Compte utilisable | `false` | 403 `ACCOUNT_DISABLED` (si pas pending) | RH / AUTH-16 / D05 |
| `pending_approval` | `boolean` | NOT NULL, DEF `false` | Self-register hors AD en attente RH | `true` | 403 `ACCOUNT_PENDING` au login | D03 = true ; D05 approve = false ; D02 / seed / RH = false |
| `is_locked` | `boolean` | défaut `false` | Verrou sécurité | `true` | 403 `ACCOUNT_LOCKED` | Admin |
| `last_login` | `timestamptz` | NULL | Dernier succès login | | Sécurité | **AUTH-01** |
| `first_login` | `timestamptz` | NULL | Premier succès | | Onboarding | **AUTH-01** |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

---

## 6. `user_preferences`

1-1 avec `users`. Créée à l’ouverture du compte.

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Id ligne | UUID | PATCH interne | Serveur à création user |
| `language` | `varchar(10)` | NOT NULL, DEF `'fr'` | Langue UI | `fr` | i18n app | Défaut seed ; user PATCH |
| `timezone` | `varchar(100)` | NOT NULL, DEF `'Africa/Lome'` | Fuseau | `Africa/Lome` | Affichage heures | Défaut / user (peut diverger de `users.timezone`) |
| `notification_sound` | `boolean` | DEF `true` | Son notif | `false` | Mute sonore | User |
| `auto_download_media` | `boolean` | DEF `false` | DL auto médias | `true` | Économie data terrain | User |
| `read_receipts` | `boolean` | DEF `true` | Accusés lecture (souhait) | `true` | Messagerie | User |
| `typing_indicator` | `boolean` | DEF `true` | « en train d’écrire » | `true` | Messagerie | User |
| `last_updated` | `timestamptz` | NOT NULL | Dernière MAJ | | Sync multi-device | Serveur à chaque PATCH |
| `user_id` | `uuid` | UK FK `users`, NOT NULL | Propriétaire | UUID | Load au login | Création compte |

---

## 7. `privacy_settings`

1-1 avec `users`. Créée à l’ouverture du compte.

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Id | UUID | PATCH | Serveur à création user |
| `last_seen_visibility` | `varchar(16)` enum | NOT NULL, DEF `EVERYONE` | Qui voit last seen | `NOBODY` | Masquer « vu à … » | User |
| `profile_photo_visibility` | `varchar(16)` enum | NOT NULL, DEF `EVERYONE` | Qui voit avatar | `NOBODY` | Annuaire / chat | User |
| `online_status_visibility` | `varchar(16)` enum | NOT NULL, DEF `EVERYONE` | Qui voit online | `NOBODY` | Liste présence | User |
| `read_receipts_enabled` | `boolean` | DEF `true` | Envoyer/afficher accusés | `false` | Double coche | User |
| `typing_indicator_enabled` | `boolean` | DEF `true` | Envoyer typing | `false` | Indicateur | User |
| `allow_calls` | `boolean` | DEF `true` | Accepter appels | `false` | Rejet appel entrant | User |
| `allow_mentions` | `boolean` | DEF `true` | Autoriser @ | `false` | Filtrer mentions | User / moteur notif |
| `allow_group_invites` | `boolean` | DEF `true` | Invitable en groupe | `false` | Blocage invite | User |
| `updated_at` | `timestamptz` | NOT NULL | MAJ | | Sync | Serveur |
| `user_id` | `uuid` | UK FK `users`, NOT NULL | Propriétaire | UUID | Load privacy check | Création compte |

---

## 8. `sessions`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Session | | Révocation | AUTH-01 |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | Titulaire | | | AUTH-01 |
| `device_id` | `uuid` | FK `devices` SET NULL, NOT NULL au login local succès | Terminal | | AUTH-12 | AUTH-A |
| `access_jti` | `uuid` | UK, index, NOT NULL | `jti` JWT access | | Middleware | AUTH-01 |
| `refresh_jti` | `uuid` | UK, NULL | `jti` refresh | | AUTH-10 | AUTH-A |
| `refresh_hash` | `text` | défaut `''` | Hash refresh | | Rotation | AUTH-A |
| `ip_address` | `inet` | NULL | IP | `10.0.0.12` | Audit | AUTH-01 |
| `user_agent` | `text` | défaut `''` | Client | | | AUTH-01 |
| `login_at` | `timestamptz` | auto, NOT NULL | Début | | | Système |
| `last_activity` | `timestamptz` | NOT NULL | Sliding | | Requêtes auth | AUTH-01 + middleware |
| `expires_at` | `timestamptz` | index, NOT NULL | Fin access | now+15 min | | AUTH-01 |
| `is_active` | `boolean` | index, défaut `true` | Pas révoquée | | Logout | AUTH-01 / logout |
| `revoked_at` | `timestamptz` | NULL | Instant révocation | | Audit logout / kill | Logout / admin |
| `revoke_reason` | `varchar(64)` | NULL | Motif | `LOGOUT` / `ADMIN` / `PASSWORD_CHANGE` | SOC | Code |
| `login_method` | `varchar(16)` | NOT NULL, enum `login_method` | Comment connecté | `PASSWORD` | Stats, MFA later | AUTH-01 (`PASSWORD`) |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

Index `(user_id, is_active)`.

---

## 9. `login_history` (append-only)

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `user_id` | `uuid` | FK SET NULL, NULL | User si connu | NULL si email inconnu | Stats | AUTH-01 |
| `device_id` | `uuid` | FK `devices` SET NULL, NULL si échec login | Terminal | | AUTH-11 | AUTH-A (succès) |
| `session_id` | `uuid` | FK `sessions` SET NULL, NULL | Session créée | NULL si échec | Relier historique ↔ session | AUTH-01 (succès) |
| `email` | `varchar(254)` | NOT NULL | Identifiant tenté (email **ou** username) | `jean.dupont@yas.tg` | Corrélation | AUTH-A |
| `ip_address` | `inet` | NULL | | | | AUTH-01 |
| `country` | `varchar(64)` | NULL | Pays | `TG` | Geo IP | GeoIP (async OK) |
| `city` | `varchar(128)` | NULL | Ville | `Lomé` | Geo IP | GeoIP |
| `latitude` | `numeric(9,6)` | NULL | Lat | `6.1378` | Carte sessions | GeoIP / client |
| `longitude` | `numeric(9,6)` | NULL | Lon | `1.2123` | | GeoIP / client |
| `browser` | `varchar(64)` | NULL | Navigateur | `Chrome` | UA parse **au login** | **AUTH-01** (`ua-parser`) |
| `browser_version` | `varchar(32)` | NULL | Version | `128.0` | UA parse **au login** | **AUTH-01** (`ua-parser`) |
| `login_method` | `varchar(16)` | NOT NULL, enum `login_method` | Canal | `PASSWORD` | Stats | AUTH-01 |
| `success` | `boolean` | index, NOT NULL | Issue | `false` | Alertes | AUTH-01 |
| `failure_reason` | `varchar(64)` | NULL | Motif | `ACCOUNT_LOCKED` | | AUTH-01 |
| `created_at` | `timestamptz` | index, auto | Quand | | | Système |

`failure_reason` : `INVALID_CREDENTIALS` \| `ACCOUNT_DISABLED` \| `ACCOUNT_LOCKED` \| `RATE_LIMITED` \| `DIRECTORY_UNAVAILABLE` (AUTH-13) \| `MFA_INVALID` \| `MFA_CHALLENGE_EXPIRED` (AUTH-C). Succès → NULL.  
**UA :** `browser` / `browser_version` extraits **immédiatement** du header (`ua-parser`). NULL seulement si header absent ou famille `Other`.  
**Geo** (`country` / `city` / lat-lng) : plus tard (MaxMind) ; NULL en AUTH-01.

---

## 10. `devices`

**Upsert AUTH-11** (login local). Confiance = colonne `trusted` (AUTH-27, pas cet incrément).

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | AUTH-11 |
| `user_id` | `uuid` | FK CASCADE, NOT NULL | Propriétaire | | | AUTH-11 |
| `device_uuid` | `varchar(128)` | unique avec user | ID install | | Push | App |
| `device_name` | `varchar(128)` | défaut `''` | Nom affiché | `iPhone de Jean` | Liste appareils | App / User |
| `model` | `varchar(128)` | défaut `''` | Modèle | `Pixel 8` | Support | App |
| `platform` | `varchar(16)` | `IOS/ANDROID/WEB/DESKTOP/OTHER` | OS famille | `ANDROID` | | App |
| `os_version` | `varchar(64)` | défaut `''` | Version OS | `14` | Compat | App |
| `app_version` | `varchar(32)` | défaut `''` | Build app | `1.4.2` | Force update | App |
| `device_fingerprint` | `varchar(255)` | NULL | Empreinte | hash | Anti-fraude | App |
| `push_token` | `text` | défaut `''` | Token push | FCM ou APNs selon `platform` | NOTIF-A | App |
| `ip_address` | `inet` | NULL | Dernière IP device | | SOC | App / login |
| `last_location` | `varchar(255)` | NULL | Libellé lieu | `Lomé` | UI « dernière localisation » | App / GeoIP |
| `trusted` | `boolean` | défaut `false` | Appareil de confiance | | **Non lu AUTH-C** (pas de skip MFA) | — |
| `compromised` | `boolean` | défaut `false` | Signalement | | Ban sessions | SOC |
| `jailbreak` | `boolean` | défaut `false` | Root / jailbreak | | Politique sécu | App (attest) |
| `last_seen` | `timestamptz` | NULL | Dernière vue device | | Liste appareils | Heartbeat app |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

UK `(user_id, device_uuid)`.  
Routage push (NOTIF-A) : `ANDROID` / `WEB` / `DESKTOP` → **FCM** ; `IOS` → **APNs** ; `OTHER` ou token vide → in-app seulement.

---

## 11. `refresh_tokens`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | Rotation | AUTH-A |
| `session_id` | `uuid` | FK `sessions` CASCADE, NOT NULL | | | | AUTH-A |
| `user_id` | `uuid` | FK CASCADE, NOT NULL | | | | AUTH-A |
| `token_hash` | `text` | NOT NULL | Hash opaque | | Compare | AUTH-A |
| `jti` | `uuid` | UK, NOT NULL | Id token | | | AUTH-A |
| `issued_at` | `timestamptz` | NOT NULL | Émission | | Audit | AUTH-A |
| `expires_at` | `timestamptz` | NOT NULL | Fin de vie | | | AUTH-A |
| `rotated_at` | `timestamptz` | NULL | Rotation | | Chaîne refresh | AUTH-A (`/refresh`) |
| `revoked_at` | `timestamptz` | NULL | Révocation | | Logout / reuse detect | AUTH-A |
| `revoked_reason` | `varchar(64)` | NULL | Motif | `ROTATED` / `REUSE` / `NEW_LOGIN_SAME_DEVICE` | SOC | AUTH-A |
| `created_ip` | `inet` | NULL | IP à l’émission | | Fraude | AUTH-09 |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

---

## 12. `password_history`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Change MDP |
| `user_id` | `uuid` | FK CASCADE, NOT NULL | | | Interdire réemploi | Politique MDP |
| `password_hash` | `text` | NOT NULL | Ancien hash | | | Système |
| `created_at` | `timestamptz` | append-only | | | | Système |

---

## 13. `password_reset_tokens`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | Forgot password | Ticket reset |
| `user_id` | `uuid` | FK CASCADE, NOT NULL | | | | |
| `token_hash` | `text` | NOT NULL | Lien / code | | | Système |
| `reset_channel` | `varchar(16)` | NOT NULL, enum `SMS`/`EMAIL`/`APPEL` | Canal | `EMAIL` | Choix UX | User / API |
| `requested_ip` | `inet` | NULL | IP demande | | Fraude | Requête |
| `user_agent` | `text` | défaut `''` | Client | | | Requête |
| `expires_at` | `timestamptz` | NOT NULL | TTL | | | Système |
| `used_at` | `timestamptz` | NULL | One-shot | | | Système |
| `revoked_at` | `timestamptz` | NULL | Annulé | | Nouveau reset invalide l’ancien | Système |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

---

## 14. `otp_secrets`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | AUTH-19 |
| `user_id` | `uuid` | UK 1-1 CASCADE, NOT NULL | | | TOTP | User (enroll) |
| `secret` | `bytea` | NOT NULL | Secret TOTP | | | Système (chiffré appli) |
| `algorithm` | `varchar(16)` | NOT NULL, DEF `'SHA1'` | Algo TOTP | `SHA1` | RFC 6238 | AUTH-19 |
| `digits` | `smallint` | NOT NULL, DEF `6` | Longueur code | `6` | | AUTH-19 |
| `period` | `smallint` | NOT NULL, DEF `30` | Période secondes | `30` | | AUTH-19 |
| `issuer` | `varchar(64)` | NOT NULL, DEF `'YAS Connect'` | Issuer QR | `YAS Connect` | App authenticator | AUTH-19 |
| `backup_codes` | `jsonb` | DEF `[]` | Hash SHA-256 des codes secours | | Verify AUTH-22 ; **jamais** le clair | AUTH-20 / 23 |
| `enabled` | `boolean` | DEF `false` | Enroll terminé | `true` | Toujours avec `verified_at` (MFA obligatoire, pas une option) | AUTH-20 |
| `verified_at` | `timestamptz` | NULL | 1er TOTP OK | | Enroll fini | AUTH-20 |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

---

## 15. `email_verifications`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Inscription / change mail |
| `user_id` | `uuid` | FK CASCADE, NOT NULL | | | | |
| `email` | `varchar(254)` | NOT NULL | Adresse à confirmer | | | User |
| `token_hash` | `text` | NOT NULL | Lien | | | Système |
| `verified_at` | `timestamptz` | NULL | Confirmé | | | Clic lien |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

---

## 16. `audit_logs`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `bigint` | PK (BIGSERIAL / identity) | Id séquentiel haute volumétrie | `9845123` | Export, pagination | Auto-increment |
| `trace_id` | `uuid` | NOT NULL | Corrélation requête | UUID | Suivre un flux multi-actions | Middleware (header / généré) |
| `module` | `varchar(80)` | NOT NULL | Domaine | `IAM` / `CHAT` / `NOC` | Filtres admin | Code applicatif |
| `action` | `varchar(120)` | NOT NULL | Action | `USER_DISABLE` / `ROLE_PERM_ADD` | Recherche | Code |
| `entity_type` | `varchar(80)` | NULL | Type cible | `users` / `roles` | Drill-down | Code |
| `entity_id` | `uuid` | NULL | Id cible | UUID | Fiche entité | Code |
| `old_values` | `jsonb` | NULL | Avant | `{ "is_active": true }` | Diff audit | Couche service (snapshot) |
| `new_values` | `jsonb` | NULL | Après | `{ "is_active": false }` | Diff audit | Idem |
| `metadata` | `jsonb` | NULL | Contexte | `{ "reason": "…" }` | Enrichissement | Code |
| `ip_address` | `inet` | NULL | IP acteur | `196.x` | Investigation | Requête HTTP |
| `severity` | `varchar(30)` | NOT NULL | Gravité | `INFO` / `WARNING` / `CRITICAL` | Alerting | Code selon action |
| `success` | `boolean` | NOT NULL | Succès op | `true` | Échecs aussi audités | Fin de traitement |
| `created_at` | `timestamptz` | NOT NULL | Horodatage | | Tri, partitions | Serveur |
| `device_id` | `uuid` | FK `devices`, NULL | Appareil | UUID | Contexte device | Session courante |
| `user_id` | `uuid` | FK `users`, NULL | Acteur | UUID | Qui a fait quoi | JWT (NULL si système/job) |

---

## Rappel AUTH-A (01–12)

Écritures login **succès** : `users.last_login` (+ `first_login` si vide), upsert `devices`, révocation sessions du même appareil, 1 `sessions` (`device_id`, `login_method=PASSWORD`, refresh jti/hash), 1 `refresh_tokens` (hash), 1 `login_history` (UA parsé, `session_id` + `device_id`).  
Échecs : `login_history` seulement (pas de device).  
Seed : 1 `user_preferences` + 1 `privacy_settings` + 1 `notification_preferences` (NOTIF-06, dès phase 3b ; avant : skip si table absente). Pas d’INSERT MFA / `region` / annuaire / médias.

Index btree / GIN : [INDEX-catalogue.md](INDEX-catalogue.md).

## Rappel AUTH-B (13 + 16)

Login LDAP : bind AD, user YAS **déjà** en base (RH / seed / **AUTH-D register/ad**), `ldap_dn` si vide, session `login_method=LDAP`. MDP applicatif **reste** valide. Sync : `is_active=false` si `ldap_dn` absent d’AD **ou** compte AD non loggable (`userAccountControl` bits bloquants / `accountExpires`). Attributs AD **non** copiés sur `users` au login (inscription AD = UPN / sAMAccountName / DN seulement). Config : [CONFIG-catalogue-tables.md](CONFIG-catalogue-tables.md).

## Rappel AUTH-C (19–24)

TOTP Google Authenticator **obligatoire** à chaque `POST /login` et `/login/ldap`. JWT seulement après `POST /mfa/verify`. Codes de secours affichés **une fois** (jamais mail/SMS). Pas de skip `devices.trusted` ni politique par rôle. Reset = admin. Plan : [AUTH-C-mfa-otp.md](../plans/iam_plans/AUTH-C-mfa-otp.md).

Lier un 2ᵉ appareil par QR (`yasconnect://device-link/…`) **puis** TOTP Authenticator : [AUTH-J](../plans/iam_plans/AUTH-J-lier-appareil-qr.md). Session `login_method=DEVICE_LINK`. Ce QR n’est pas l’enroll `otpauth://`.

## Rappel AUTH-D (inscription)

Self-register AD : UPN / sAMAccountName / `ldap_dn` + MDP **app** + MFA.  
Self-register hors AD : `pending_approval=true`, `is_active=false` ; email (D04) **sans** activer ; RH approve (D05).  
Login : `pending_approval` → 403 `ACCOUNT_PENDING`. Plan : [AUTH-D-inscription.md](../plans/AUTH-D-inscription.md).
