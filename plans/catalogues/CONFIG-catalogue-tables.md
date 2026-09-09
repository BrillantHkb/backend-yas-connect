# Catalogue Config — tables et attributs

App Django `apps.config`.  
Créée pour **AUTH-B** (URI LDAP, secrets bind, job sync départs / disable / expiration).  
Hors AUTH-A (tables absentes au login local).

**Légende « Renseigné par »** : Seed / Admin / Système (job) / AUTH-B.

---

## Index

| Table | AUTH-B |
|--------|--------|
| `system_settings` | seed `ldap.uri` / bind / search_base |
| `scheduled_jobs` | seed `ldap_sync_users` |
| `feature_flags` | vide (réserve) |

---

## 1. `system_settings`

UK `(category, setting_key)`.

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `category` | `varchar(64)` | NOT NULL | Famille | `ldap` | Grouper l’admin | Seed / Admin |
| `setting_key` | `varchar(128)` | NOT NULL | Clé | `uri` | Lecture service | Seed / Admin |
| `setting_value` | `jsonb` | NOT NULL | Valeur | `"ldaps://dc1.yas.tg:636"` | URI / secret / timeout | Admin |
| `value_type` | `varchar(32)` | NOT NULL | `string`/`bool`/`int`/`json` | `string` | Cast | Seed |
| `is_sensitive` | `boolean` | défaut `false` | Secret | `true` (bind password) | **Jamais** renvoyer en API | Seed |
| `editable` | `boolean` | défaut `true` | Modifiable UI | `false` | Verrouiller | Seed |
| `updated_by_id` | `uuid` | FK `users` SET NULL, NULL | Qui | | Audit | Admin |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

Clés AUTH-B : `ldap.uri`, `ldap.bind_dn`, `ldap.bind_password`, `ldap.search_base`, `ldap.timeout_seconds` — [AUTH-B](../plans/iam_plans/AUTH-B-sso-ldap.md).  
Clé AUTH-E (alternative à `.env`) : `security.block_jailbreak` — [AUTH-E](../plans/iam_plans/AUTH-E-appareils.md).  
Clés AUTH-F : `legal.tos_version`, `legal.tos_url` — [AUTH-F](../plans/iam_plans/AUTH-F-onboarding.md).  
Clés AUTH-G : `security.password_min_length` (et `max`, `require_*`, `password_history_n`, TTL reset) — [AUTH-G](../plans/iam_plans/AUTH-G-mot-de-passe.md).  
Clés AUTH-H : `security.session_idle_seconds`, `session_absolute_seconds`, `session_heartbeat_min_seconds` — [AUTH-H](../plans/iam_plans/AUTH-H-sessions.md).  
Clés AUTH-I : `security.lock_after_failures`, `security.lock_duration_seconds` — [AUTH-I](../plans/iam_plans/AUTH-I-securite.md).  
Clé AUTH-J : `security.device_link_ttl_seconds` (défaut `120`) — [AUTH-J](../plans/iam_plans/AUTH-J-lier-appareil-qr.md).  
Clé PROF-B : `profile.job_title_self_edit` (bool, défaut `false`) — [PROF-B](../plans/iam_plans/PROF-B-edition-preferences.md).  
Clés PRES-A : `presence.heartbeat_seconds`, `redis_ttl_seconds`, `away_after_seconds` — [PRES-A](../plans/iam_plans/PRES-A-presence.md).

Job AUTH-H : `session_reaper` (`*/5 * * * *`) — même table `scheduled_jobs` qu’AUTH-16.  
Job AUTH-I : `account_unlock_reaper` (`*/5 * * * *`).

---

## 2. `scheduled_jobs`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `job_name` | `varchar(128)` | UK, NOT NULL | Nom | `ldap_sync_users` | AUTH-16 | Seed |
| `module` | `varchar(64)` | NOT NULL | | `IAM` | Filtre admin | Seed |
| `cron_expression` | `varchar(64)` | NULL | Cron 5 champs | `0 2 * * *` | Planif | Seed / Admin |
| `interval_seconds` | `int` | NULL | Alternative au cron | `3600` | | Seed / Admin |
| `handler` | `varchar(255)` | NOT NULL | Dotted path | `apps.iam.jobs.sync_ldap_accounts` | Runner | Seed |
| `enabled` | `boolean` | défaut `true` | | | Pause sync | Admin |
| `last_execution` | `timestamptz` | NULL | Dernier run | | | Runner |
| `next_execution` | `timestamptz` | NULL, index | Prochain | | Poll runner | Runner |
| `last_status` | `varchar(32)` | NULL | `OK` / `ERROR` | | Alerting | Runner |
| `last_error` | `text` | défaut `''` | Trace courte | | Debug | Runner |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

Un des deux : `cron_expression` **ou** `interval_seconds`.

---

## 3. `feature_flags`

Réserve. **0 ligne obligatoire AUTH-B.**

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `feature_code` | `varchar(64)` | UK, NOT NULL | | `auth.ldap` | Gate | Seed |
| `feature_name` | `varchar(128)` | NOT NULL | | `LDAP login` | UI | Seed |
| `enabled` | `boolean` | défaut `false` | | | | Admin |
| `rollout_percentage` | `smallint` | défaut `100` | 0–100 | | Canary | Admin |
| `target_roles` | `jsonb` | DEF `[]` | Codes rôles | `["ADMIN"]` | | Admin |
| `target_platforms` | `jsonb` | DEF `[]` | | `["WEB"]` | | Admin |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |
