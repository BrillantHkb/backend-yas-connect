# Catalogue Annuaire — tables et attributs

App Django prévue : `apps.annuaire` (pas `apps.iam`).  
`users` reste dans l’IAM ; l’annuaire **pointe** vers `users.id`.

**Légende « Renseigné par »** : RH / User / Système — **jamais AUTH-A en écriture** (tables créées dès AUTH-A). Seed **ANNUAIRE-A** : 3 `segment_types` + 1 segment `YAS`. CRUD arbre = [ANNUAIRE-B](../plans/annuaire_plans/ANNUAIRE-B-arbre-segments.md) ; affectations = [ANNUAIRE-C](../plans/annuaire_plans/ANNUAIRE-C-affectations.md) ; skills / certifs = [ANNUAIRE-D](../plans/annuaire_plans/ANNUAIRE-D-competences-certifications.md) (self-service **oui**).

Index : [INDEX-catalogue.md](INDEX-catalogue.md).

---

## Index

| Table | Rôle |
|--------|------|
| `segment_types` | Types d’unité (Direction, Service…) |
| `segments` | Unités org (arbre) |
| `user_segments` | Affectations user ↔ segment (historique) |
| `user_skills` | Compétences |
| `user_certifications` | Certifications |

---

## Relations (ERD)

| De | Vers | Cardinalité | FK |
|----|------|-------------|-----|
| `segments` | `segment_types` | n → 1 | `segment_type_id` |
| `segments` | `segments` | n → 1 | `parent_segment_id` (auto-référence) |
| `segments` | `users` | n → 1 | `responsable_id` (N+1 d’unité ; pas de `users.manager_id`) |
| `user_segments` | `segments` | n → 1 | `segment_id` |
| `user_segments` | `users` | n → 1 | `user_id` |
| `user_segments` | `users` | n → 1 | `assigned_by_id` |
| `user_skills` | `users` | n → 1 | `user_id` |
| `user_certifications` | `users` | n → 1 | `user_id` |
| `user_certifications` | `media_files` | n → 1 | `document_id` |

`users` (IAM) : PK `uuid`. L’annuaire ne possède pas la table `users` ; `users.segment_id` (IAM) = copie dénormalisée de l’affectation courante.

---

## 1. `segment_types`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Identifiant | | FK `segments.segment_type_id` | Système |
| `code` | `varchar(50)` | UK, NOT NULL | Clé | `DIRECTION` | | RH |
| `name` | `varchar(200)` | UK, NOT NULL | Libellé | `Direction` | | RH |
| `level` | `smallint` | NOT NULL, défaut `0` | Profondeur type | `1` | Arbre | RH |
| `description` | `text` | défaut `''` | | | | RH |
| `is_active` | `boolean` | défaut `true` | | | | RH |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

---

## 2. `segments`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Unité | | `users.segment_id` (copie courante IAM) | Système |
| `code` | `varchar(50)` | UK, index, NOT NULL | | `NOC-LOME` | | RH |
| `name` | `varchar(200)` | NOT NULL | | `NOC Lomé` | Organigramme | RH |
| `description` | `text` | défaut `''` | | | | RH |
| `is_active` | `boolean` | défaut `true` | | | | RH |
| `segment_type_id` | `uuid` | FK `segment_types` SET NULL, NULL | Type | | | RH |
| `parent_segment_id` | `uuid` | FK self SET NULL, NULL | Parent | | Hiérarchie | RH |
| `responsable_id` | `uuid` | FK `users` SET NULL, NULL | Chef d’unité | | Escalade org (remplace `users.manager_id`) | RH |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

---

## 3. `user_segments`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `is_active` | `boolean` | défaut `true` | Affectation en cours | | | RH |
| `start_date` | `timestamptz` | NOT NULL | Début | | | RH |
| `end_date` | `timestamptz` | NULL | Fin | | Mutation | RH |
| `position` | `varchar(100)` | défaut `''` | Poste dans l’unité | `Chef équipe` | Historique vs `users.job_title` | RH |
| `position_description` | `varchar(255)` | défaut `''` | | | | RH |
| `segment_id` | `uuid` | FK `segments` CASCADE, NOT NULL | Unité | | | RH |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | Collaborateur | | | RH |
| `assigned_by_id` | `uuid` | FK `users` SET NULL, NULL | Qui a affecté | | Audit | RH |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

`users.segment_id` (IAM) et `user_segments` **coexistent**. Copie courante = lecture rapide (profil, filtres, CONTACTS) ; cette table = historique (`start_date` / `end_date`, `position`).  
Règle d’écriture RH ([ANNUAIRE-C](../plans/annuaire_plans/ANNUAIRE-C-affectations.md)) : une affectation ouverte (`end_date` NULL) **met à jour** `users.segment_id` ; clôture de la dernière ouverte → `users.segment_id = NULL`. Création compte (AUTH-D / ADMIN-A) : `open_assignment` dès C.

---

## 4. `user_skills`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `skill_name` | `varchar(150)` | NOT NULL | | `Fibre` | Recherche expert | User / RH |
| `level` | `smallint` | défaut `0`, CHECK 1–5 | Niveau | `4` | | User / RH |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | | | | User / RH |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

UK `(user_id, skill_name)`. GIN trgm sur `skill_name` : [INDEX-catalogue.md](INDEX-catalogue.md). Self-service + RH : [ANNUAIRE-D](../plans/annuaire_plans/ANNUAIRE-D-competences-certifications.md). Recherche expert par skill : hors incrément.

---

## 5. `user_certifications`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `certification_name` | `varchar(150)` | NOT NULL | | `CCNA` | Profil | RH / User |
| `issued_at` | `date` | NULL | Obtention | | | RH / User |
| `document_id` | `uuid` | FK `media_files` SET NULL, NULL | Scan | | Module Médias | Médias |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | | | | RH / User |

---

## Seed ANNUAIRE-A

Idempotent (`seed_annuaire`) : types `DIRECTION` / `DEPARTEMENT` / `SERVICE` + segment racine `YAS` (DIRECTION, parent NULL). Régions géo = seed IAM [ADMIN-A](../plans/iam_plans/ADMIN-A-lifecycle-audit.md).  
Plans : [ANNUAIRE-A](../plans/annuaire_plans/ANNUAIRE-A-recherche-referentiels.md) … [D](../plans/annuaire_plans/ANNUAIRE-D-competences-certifications.md). Routes : [ANNUAIRE-routes.md](../plans/annuaire_plans/ANNUAIRE-routes.md).  
Pas de `segments.region_id` (région géo ≠ organigramme).
