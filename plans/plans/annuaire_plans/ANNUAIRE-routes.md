# Annuaire — Catalogue des routes planifiées

**Produit :** YAS Connect uniquement (pas le SIRH).  
**Source :** [ANNUAIRE-A](ANNUAIRE-A-recherche-referentiels.md) … [D](ANNUAIRE-D-competences-certifications.md). Lecture org sur `/me` et `/users/{id}` = [PROF-A](../iam_plans/PROF-A-identite.md). Régions géo = [ADMIN-A](../iam_plans/ADMIN-A-lifecycle-audit.md) (`iam.region.*`, pas `apps.annuaire`).  
**Préfixe :** `/api/v1`.  
**Principe :** l’Annuaire pointe vers `users.id` ; il ne duplique pas le profil IAM.


**Permission** = code `required_permission` (`HasPermission`, un seul code par vue).  
**Rôles** = qui a ce code après `seed_iam` (USER et/ou ADMIN). ADMIN a aussi toutes les perms USER.  
Public = `AllowAny` : pas de JWT, pas de permission.

**38 routes** (dont `GET /me` et `GET /users/{id}` : contrat PROF-A, org lue ici). Un **ADMIN** a aussi les routes Collaborateur (skills / certifs `/me`).

**Hors tableau :** seed `seed_annuaire`, service `sync_users_segment_id`, recherche experts (GIN prêt, pas d’API), CRUD `region` (IAM).

---

## Pourquoi cet ordre

| Vague | Plan | Pourquoi |
|-------|------|----------|
| **A** | ANNUAIRE-A | Dropdowns inscription + people-picker. Tables déjà créées AUTH-A. |
| **B** | ANNUAIRE-B | Arbre avant les affectations (FK segment). |
| **C** | ANNUAIRE-C | Historique + sync `users.segment_id` ; hook AUTH-D / ADMIN-A. |
| **D** | ANNUAIRE-D | Skills / certifs (indépendants de l’arbre, après `/me`). |

Décisions figées : pas de `segments.region_id` ; pas de `users.manager_id` ; CONTACTS = même `segment_id` ; self-service skills/certifs **oui**.

---

## Vague A — Lecture (ANNUAIRE-A + PROF)


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 1 | `GET` | `/api/v1/directory/regions` | Public | `AllowAny` | — | A-03 | Dropdown régions inscription | Actifs. Seed ADMIN-A. `[]` si vide. |
| 2 | `GET` | `/api/v1/directory/segment-types` | Public | `AllowAny` | — | A-04 | Types d’unité | Actifs. Pas de JWT. |
| 3 | `GET` | `/api/v1/directory/segments` | Public | `AllowAny` | — | A-04 | Segments pour `segment_id` | Query `parent_id`. Pas de responsable. |
| 4 | `GET` | `/api/v1/users` | Collaborateur | `iam.profile.read_other` | USER, ADMIN | A-01 | People-picker | `q` 2–64. Pas d’email. Privacy 23–25. Après CGU. |
| 5 | `GET` | `/api/v1/users/{id}` | Collaborateur | `iam.profile.read_other` | USER, ADMIN | A-02 / PROF-02 | Fiche collègue + org | Délégué PROF-A. Self → 400. |
| 6 | `GET` | `/api/v1/me` | Collaborateur | `iam.profile.read` | USER, ADMIN | PROF-A | Org sur sa fiche | Path, manager `responsable_id`. Vue IAM. |

---

## Vague B — Arbre RH (ANNUAIRE-B)

`urls` : `segments/tree` **avant** `segments/{id}`.


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 7 | `GET` | `/api/v1/admin/segment-types` | Admin | `annuaire.segment_type.read` | ADMIN | B-06 | Lister les types | Admin voit inactifs. |
| 8 | `GET` | `/api/v1/admin/segment-types/{id}` | Admin | `annuaire.segment_type.read` | ADMIN | B-06 | Détail type | 404 si absent. |
| 9 | `POST` | `/api/v1/admin/segment-types` | Admin | `annuaire.segment_type.manage` | ADMIN | B-06 | Créer un type | `code` SCREAMING_SNAKE. |
| 10 | `PATCH` | `/api/v1/admin/segment-types/{id}` | Admin | `annuaire.segment_type.manage` | ADMIN | B-06 | Renommer / level / actif | Seed : `code` gelé. |
| 11 | `DELETE` | `/api/v1/admin/segment-types/{id}` | Admin | `annuaire.segment_type.manage` | ADMIN | B-06 | Supprimer | 409 `TYPE_SYSTEM` (3 seed) ou `TYPE_IN_USE`. |
| 12 | `GET` | `/api/v1/admin/segments` | Admin | `annuaire.segment.read` | ADMIN | B-07 | Liste unités | `q`, `parent_id`, `type_id`. |
| 13 | `GET` | `/api/v1/admin/segments/tree` | Admin | `annuaire.segment.read` | ADMIN | B-08 | Organigramme JSON | Profondeur max 16. |
| 14 | `GET` | `/api/v1/admin/segments/{id}` | Admin | `annuaire.segment.read` | ADMIN | B-07 | Fiche + mini-responsable | `children_count`. |
| 15 | `POST` | `/api/v1/admin/segments` | Admin | `annuaire.segment.manage` | ADMIN | B-07 | Créer une unité | Cycle / level / responsable. |
| 16 | `PATCH` | `/api/v1/admin/segments/{id}` | Admin | `annuaire.segment.manage` | ADMIN | B-07 | Déplacer / renommer | `SEGMENT_CYCLE` si boucle. |
| 17 | `DELETE` | `/api/v1/admin/segments/{id}` | Admin | `annuaire.segment.manage` | ADMIN | B-07 | Supprimer | 409 `SEGMENT_IN_USE`. |

---

## Vague C — Affectations (ANNUAIRE-C)


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 18 | `GET` | `/api/v1/admin/users/{id}/segments` | Admin | `annuaire.user_segment.read` | ADMIN | C-09 | Historique d’affectations | Distinct de `users.job_title`. |
| 19 | `POST` | `/api/v1/admin/users/{id}/segments` | Admin | `annuaire.user_segment.manage` | ADMIN | C-10 | Affecter / muter | Clôture l’ouverte ; sync `users.segment_id`. |
| 20 | `GET` | `/api/v1/admin/user-segments/{id}` | Admin | `annuaire.user_segment.read` | ADMIN | C-09 | Détail d’une ligne | 404 si absent. |
| 21 | `PATCH` | `/api/v1/admin/user-segments/{id}` | Admin | `annuaire.user_segment.manage` | ADMIN | C-11 | Dates, poste, clôture | `user_id` non patchable. |
| 22 | `DELETE` | `/api/v1/admin/user-segments/{id}` | Admin | `annuaire.user_segment.manage` | ADMIN | C-12 | Correction (hard delete) | Puis sync. Pas de `/me/segments`. |

Hors HTTP : `open_assignment` branché sur AUTH-D / ADMIN-A create ; `validate_org_fk` (ANN-16).

---

## Vague D — Compétences & certifications (ANNUAIRE-D)

### Self (USER)


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 23 | `GET` | `/api/v1/me/skills` | Collaborateur | `annuaire.skill.read` | USER, ADMIN | D-17 | Lister ses compétences | Après CGU/wizard. |
| 24 | `POST` | `/api/v1/me/skills` | Collaborateur | `annuaire.skill.manage` | USER, ADMIN | D-17 | Déclarer une compétence | UK `(user, skill_name)`. `level` 1–5. |
| 25 | `PATCH` | `/api/v1/me/skills/{id}` | Collaborateur | `annuaire.skill.manage` | USER, ADMIN | D-17 | Modifier | 404 si pas à soi. |
| 26 | `DELETE` | `/api/v1/me/skills/{id}` | Collaborateur | `annuaire.skill.manage` | USER, ADMIN | D-17 | Retirer | Max 50 / user. |
| 27 | `GET` | `/api/v1/me/certifications` | Collaborateur | `annuaire.certification.read` | USER, ADMIN | D-18 | Lister ses certifs | |
| 28 | `POST` | `/api/v1/me/certifications` | Collaborateur | `annuaire.certification.manage` | USER, ADMIN | D-18 | Ajouter | `document_id` optionnel, owner + scan. |
| 29 | `PATCH` | `/api/v1/me/certifications/{id}` | Collaborateur | `annuaire.certification.manage` | USER, ADMIN | D-18 | Modifier | Date pas dans le futur. |
| 30 | `DELETE` | `/api/v1/me/certifications/{id}` | Collaborateur | `annuaire.certification.manage` | USER, ADMIN | D-18 | Retirer | Fichier média conservé. |

### Admin


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 31 | `GET` | `/api/v1/admin/users/{id}/skills` | Admin | `annuaire.user_skill.read` | ADMIN | D-14 | Skills d’un user | |
| 32 | `POST` | `/api/v1/admin/users/{id}/skills` | Admin | `annuaire.user_skill.manage` | ADMIN | D-14 | Ajouter pour un user | Même UK. |
| 33 | `PATCH` | `/api/v1/admin/user-skills/{id}` | Admin | `annuaire.user_skill.manage` | ADMIN | D-14 | Modifier n’importe quelle ligne | |
| 34 | `DELETE` | `/api/v1/admin/user-skills/{id}` | Admin | `annuaire.user_skill.manage` | ADMIN | D-14 | Supprimer | |
| 35 | `GET` | `/api/v1/admin/users/{id}/certifications` | Admin | `annuaire.user_certification.read` | ADMIN | D-15 | Certifs d’un user | |
| 36 | `POST` | `/api/v1/admin/users/{id}/certifications` | Admin | `annuaire.user_certification.manage` | ADMIN | D-15 | Ajouter | `document_id` owner = **cible**. |
| 37 | `PATCH` | `/api/v1/admin/user-certifications/{id}` | Admin | `annuaire.user_certification.manage` | ADMIN | D-15 | Modifier | |
| 38 | `DELETE` | `/api/v1/admin/user-certifications/{id}` | Admin | `annuaire.user_certification.manage` | ADMIN | D-15 | Supprimer | |

---

## Index par acteur


| Acteur | Combien | Qui |
|--------|---------|-----|
| **Public** | 3 | Dropdowns `/directory/*` (inscription AUTH-D) |
| **Collaborateur** | 13 | Picker, fiche, `/me` org, skills/certifs self |
| **Admin** | 22 | Types, arbre, affectations, skills/certifs d’autrui |

CRUD `/admin/regions` = IAM (ADMIN-A), pas compté ici.
