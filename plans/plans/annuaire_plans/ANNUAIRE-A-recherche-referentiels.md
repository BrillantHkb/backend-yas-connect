# ANNUAIRE-A — Recherche collègues & référentiels (ANN-01 … 05)

**Produit :** YAS Connect uniquement (pas le SIRH).  
**Préalable :** Phase 0 + **PROF-A** (carte collègue + privacy) + **ADMIN-A** (seed `region`) + **AUTH-R**.  
**Attributs :** [IAM](../../catalogues/IAM-catalogue-tables.md) (`users`, `region`) · [Annuaire](../../catalogues/ANNUAIRE-catalogue-tables.md) · [INDEX](../../catalogues/INDEX-catalogue.md) (GIN trgm).  
**Models :** [code/iam_models.py](../code/iam_models.py) · [code/annuaire_models.py](../code/annuaire_models.py).

**Périmètre :** people-picker (`GET /users`), listes **publiques** régions / types / segments (dropdown inscription AUTH-D), **seed** `segment_types` + segment racine `YAS`.

Écriture RH : [ANNUAIRE-B](ANNUAIRE-B-arbre-segments.md) (types / arbre), [ANNUAIRE-C](ANNUAIRE-C-affectations.md) (historique + sync), [ANNUAIRE-D](ANNUAIRE-D-competences-certifications.md) (skills / certifs).

L’Annuaire **ne duplique pas** `users`. Il pointe vers `users.id` ; le profil reste dans l’IAM.

---

## Cartographie


| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **ANN-01** | **Gardé** | `GET /users` : recherche trgm + filtres org ; privacy PROF-02 par hit | lecture |
| **ANN-02** | **Gardé (délégué)** | Fiche `GET /users/{id}` = **PROF-02** (pas de 2e contrat) | — |
| **ANN-03** | **Gardé** | `GET /directory/regions` public : seed ADMIN-A | lecture |
| **ANN-04** | **Gardé** | `GET /directory/segment-types` + `GET /directory/segments` public, actifs seulement | lecture |
| **ANN-05** | **Gardé** | Seed `segment_types` + segment racine `YAS` (type `DIRECTION`) | Annuaire |


**Hors incrément :** CRUD RH ([ANNUAIRE-B/C/D](ANNUAIRE-B-arbre-segments.md)), organigramme UI, graphe d’amis, recherche experts par skill / certif, synchro SIRH.

---

## Décisions figées


| Sujet | Choix |
|-------|--------|
| Recherche | JWT + `iam.profile.read_other` (même perm que PROF-02) |
| Résultats | Uniquement `is_active=true` **et** `pending_approval=false`. Inactifs = absents (pas de 403) |
| `q` | Obligatoire, **2–64** car. trim. Sinon **400** `QUERY_TOO_SHORT` (évite de dumper l’annuaire) |
| Filtres | `region_id`, `segment_id` optionnels (UUID). Combinés en AND avec `q` |
| Carte hit | Sous-ensemble PROF-02 : `id`, `display_name`, `username`, `job_title`, `avatar_url`, `org.segment` (id/code/name), `status` / `badge` si privacy. **Pas** email / phone / matricule / last_seen / last_login |
| Privacy | `avatar_url` / `status` / `badge` : mêmes règles PROF-23…25 que la fiche |
| CONTACTS | Même `users.segment_id` non NULL (pas de graphe d’amis) |
| Soi | Exclu des `results` (`id ≠ me`) |
| Pagination | `limit` 20 défaut, max 50 ; `offset` |
| Public directory | `AllowAny` **sans JWT** : id, code, name (et `level` / `type_code` / `parent_id`). Pas de `responsable`, pas d’emails. `is_active=true` |
| Pourquoi public | AUTH-D D02/D03 exigent `region_id` / `segment_id` UUID ; le client d’inscription n’a pas de JWT |
| Seed types | `DIRECTION` (level 0), `DEPARTEMENT` (1), `SERVICE` (2) — codes lus par PROF-12…14 |
| Seed segment | `YAS` / « YAS Togo » / type `DIRECTION` / `parent=NULL` / `responsable=NULL`. Idempotent |
| `users.segment_id` | Seed **ne** rattache **pas** jean.dupont. AUTH-D / ADMIN-A posent la FK ; historique `user_segments` = [ANNUAIRE-C](ANNUAIRE-C-affectations.md) |
| Région vs org | `users.region_id` (IAM `region`) ≠ chemin `segments`. **Pas** de `segments.region_id` |
| Manager | `segments.responsable_id` du courant, sinon parents (PROF-13). Pas de `users.manager_id` |
| Portes AUTH-F | `GET /users` **après** CGU + wizard. Directory public : **pas** de porte |

---

## Contrat HTTP

### ANN-01 — `GET /api/v1/users`

`required_permission = iam.profile.read_other`. Portes AUTH-F après perm.

| Query | Règle |
|-------|--------|
| `q` | 2–64, `ILIKE` / trgm sur `first_name`, `last_name`, `username`, `matricule` (**pas** l’email) |
| `region_id` | UUID optionnel |
| `segment_id` | UUID optionnel |
| `limit` | 1–50, défaut 20 |
| `offset` | ≥ 0 |

**200**

```json
{
  "count": 1,
  "results": [
    {
      "id": "<uuid>",
      "display_name": "Marie Koevi",
      "username": "mkoevi",
      "job_title": "RH",
      "avatar_url": "https://…",
      "badge": "green",
      "status": "ONLINE",
      "org": {
        "segment": { "id": "<uuid>", "code": "YAS", "name": "YAS Togo" }
      }
    }
  ]
}
```

`org` / `avatar_url` / `status` / `badge` : `null` si absent ou masqué (PROF-C).  
**400** `QUERY_TOO_SHORT`. USER jean **200** (perm self `read_other`).

### ANN-02 — fiche (délégué PROF-A)

`GET /api/v1/users/{id}` : contrat [PROF-02](../iam_plans/PROF-A-identite.md). Org = PROF-12…14. **404** si inactif / pending. Self → **400** (utiliser `GET /me`).

`GET /api/v1/me` : même résolution org, toujours visible pour soi.

### ANN-03 / 04 — directory public

`AllowAny`. Pas de `HasPermission`.

| Méthode | Chemin | Body |
|---------|--------|------|
| GET | `/api/v1/directory/regions` | `[{ "id", "code", "name" }]` tri `name` |
| GET | `/api/v1/directory/segment-types` | `[{ "id", "code", "name", "level" }]` actifs |
| GET | `/api/v1/directory/segments` | query `parent_id` optionnel (UUID ou omis = racines) ; `[{ "id", "code", "name", "type_code", "parent_id" }]` actifs |

**404** jamais sur une liste vide : `[]`.

Admin CRUD régions = [ADMIN-A ADM-08](../iam_plans/ADMIN-A-lifecycle-audit.md) (`iam.region.*`). Write segments = [ANNUAIRE-B](ANNUAIRE-B-arbre-segments.md).

---

## ANN-05 — Seed Annuaire

`seed_annuaire` (idempotent, après `seed_iam`) :

**`segment_types`**

| code | name | level |
|------|------|-------|
| `DIRECTION` | Direction | 0 |
| `DEPARTEMENT` | Département | 1 |
| `SERVICE` | Service | 2 |

**`segments`**

| code | name | type | parent |
|------|------|------|--------|
| `YAS` | YAS Togo | `DIRECTION` | NULL |

Pas de `user_segments`. Pas de skills.

---

## 1. Fichiers

```
apps/iam/views_directory_search.py   # GET /users
apps/annuaire/views_directory.py     # GET /directory/*
apps/annuaire/seed.py                # seed_annuaire
```

`HasPermission` sur `GET /users` seulement.

---

## 2. Tests (acceptation)


| ID | Cas | Attendu |
|----|-----|---------|
| 01 | `q=m` | 400 `QUERY_TOO_SHORT` |
| 01 | `q=koe` USER | 200 ; hits actifs ; pas soi ; pas email |
| 01 | cible `NOBODY` photo | `avatar_url=null` |
| 01 | pending / disabled | absents |
| 02 | `GET /users/{id}` | contrat PROF-02 inchangé |
| 03 | directory regions sans JWT | 200 ; 5 codes TG |
| 04 | directory segments | `YAS` présent |
| 05 | seed 2e fois | pas de doublon UK |
| — | `GET /users` sans JWT | 401 |
| — | sans `iam.profile.read_other` | 403 |


---

## Critères d’acceptation

- [ ] People-picker JWT + trgm ; pas de dump sans `q`
- [ ] Privacy 23–25 sur les hits
- [ ] Directory public pour AUTH-D
- [ ] Seed types + `YAS` ; régions = ADMIN-A
- [ ] Pas de CRUD RH arbre (B/C/D)
- [ ] Spec seulement

---

## Écarts documents liés

- **PROF-A** : recherche n’est plus hors incrément. Fiche `{id}` inchangée. Org lue ici.
- **AUTH-D** : le client d’inscription lit `/directory/*` puis POSTe les UUID.
- **ADMIN-A** : seed + CRUD `region` ; create user exige un `segment_id` (au moins `YAS`).
- **AUTH-R** : `GET /users` déjà `iam.profile.read_other`. Routes directory = **public**.
- **ANNUAIRE-B/C/D** : écriture types, arbre, affectations, skills, certifs.
