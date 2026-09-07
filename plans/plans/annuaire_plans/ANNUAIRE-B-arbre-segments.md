# ANNUAIRE-B — Types d’unité & arbre organisationnel (ANN-06 … 08)

**Produit :** YAS Connect uniquement (pas le SIRH).  
**Préalable :** Phase 0 + **ANNUAIRE-A** (seed types + `YAS`) + **AUTH-R** (perms `annuaire.segment*`) + **ADMIN-A** (audit, portes admin absentes).  
**Attributs :** [Annuaire](../../catalogues/ANNUAIRE-catalogue-tables.md) (`segment_types`, `segments`).  
**Models :** [code/annuaire_models.py](../code/annuaire_models.py).

**Périmètre :** CRUD admin des **types** et des **segments** (arbre), vue arbre enrichie. Pas d’affectations ( [ANNUAIRE-C](ANNUAIRE-C-affectations.md) ), pas de skills ( [ANNUAIRE-D](ANNUAIRE-D-competences-certifications.md) ).

`users.region_id` reste IAM. **Pas** de colonne `segments.region_id` (deux axes distincts : géo vs org).

---

## Cartographie


| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **ANN-06** | **Gardé** | CRUD `/admin/segment-types` | `segment_types` ; audit |
| **ANN-07** | **Gardé** | CRUD `/admin/segments` | `segments` ; audit |
| **ANN-08** | **Gardé** | `GET /admin/segments/tree` (hiérarchie + mini-responsable) | lecture |


**Hors incrément :** organigramme UI drag-and-drop, import SIRH, `segments.region_id`, recherche trgm admin (liste `q` suffit).

---

## Décisions figées


| Sujet | Choix |
|-------|--------|
| Auth | JWT + `HasPermission`. **Pas** de porte CGU/wizard (vues admin) |
| Codes | `segment_types.code` et `segments.code` : `SCREAMING_SNAKE` 2–64, UK |
| Types seed | `DIRECTION` / `DEPARTEMENT` / `SERVICE` : `code` non patchable, DELETE **409** `TYPE_SYSTEM` (comme rôles `is_system`). Pas de colonne SQL `is_system` : liste close seed |
| Types custom | POST libre (`NOC`, `AGENCE`…). DELETE **409** `TYPE_IN_USE` si un segment pointe encore |
| Arbre | `parent_segment_id` NULL = racine. Self-parent → **400** `SEGMENT_PARENT_SELF`. Cycle (max 16) → **400** `SEGMENT_CYCLE` |
| Level | Si parent **et** enfant ont un type : `child.level > parent.level` sinon **400** `SEGMENT_LEVEL_INVALID`. Parent sans type : pas de check |
| Responsable | `responsable_id` = user **actif** existant, ou NULL. Inactif / inconnu → **400** `RESPONSABLE_INVALID` |
| Actifs | Admin voit inactifs. Directory public ANNUAIRE-A = actifs seulement |
| DELETE segment | **409** `SEGMENT_IN_USE` si enfant, `users.segment_id`, ou `user_segments` |
| Soft vs hard | Pas de soft-delete. `is_active=false` pour masquer (directory / PROF org ignore l’inactif) |
| URL tree | `GET /admin/segments/tree` **avant** `{id}` dans `urls.py` |
| Audit | `module=ANNUAIRE` ; `SEGMENT_TYPE_*` / `SEGMENT_*`. Jamais de secrets |

---

## Contrat HTTP

Préfixe `/api/v1`. JWT.

### ANN-06 — types

| Méthode | Chemin | Perm |
|---------|--------|------|
| GET | `/admin/segment-types` | `annuaire.segment_type.read` |
| GET | `/admin/segment-types/{id}` | `annuaire.segment_type.read` |
| POST | `/admin/segment-types` | `annuaire.segment_type.manage` |
| PATCH | `/admin/segment-types/{id}` | `annuaire.segment_type.manage` |
| DELETE | `/admin/segment-types/{id}` | `annuaire.segment_type.manage` |

GET liste : query `q` (code/name), `is_active`, `limit` 1–100 défaut 50, `offset`.  
POST `{ "code", "name", "level", "description?" }`. `level` entier ≥ 0.  
PATCH : `name`, `level`, `description`, `is_active`. `code` gelé sur les 3 seed.  
DELETE **204**. **404** si absent.

**409** `SEGMENT_TYPE_CODE_TAKEN` / `NAME_TAKEN`. **400** `INVALID_TYPE_CODE`.

### ANN-07 — segments

| Méthode | Chemin | Perm |
|---------|--------|------|
| GET | `/admin/segments` | `annuaire.segment.read` |
| GET | `/admin/segments/{id}` | `annuaire.segment.read` |
| POST | `/admin/segments` | `annuaire.segment.manage` |
| PATCH | `/admin/segments/{id}` | `annuaire.segment.manage` |
| DELETE | `/admin/segments/{id}` | `annuaire.segment.manage` |

GET liste : `q` (code/name trgm), `parent_id` (UUID ou `null`), `type_id`, `is_active`, pagination.

POST / PATCH body :

```json
{
  "code": "NOC-LOME",
  "name": "NOC Lomé",
  "description": "",
  "segment_type_id": "<uuid>",
  "parent_segment_id": "<uuid-YAS>",
  "responsable_id": "<uuid-user>",
  "is_active": true
}
```

`segment_type_id` / `parent_segment_id` / `responsable_id` nullable.  
Fiche GET : champs + `type` `{id,code,name,level}` + `parent` mini + `responsable` mini-user (`id`, `display_name`, `username`) + `children_count`.

**409** `SEGMENT_CODE_TAKEN`. **400** `INVALID_SEGMENT_CODE` / `SEGMENT_PARENT_SELF` / `SEGMENT_CYCLE` / `SEGMENT_LEVEL_INVALID` / `RESPONSABLE_INVALID` / `TYPE_INVALID`.  
DELETE **204** ou **409** `SEGMENT_IN_USE`.

### ANN-08 — arbre

`GET /api/v1/admin/segments/tree` — `annuaire.segment.read`.

Query `root_id` optionnel (défaut = toutes les racines). `include_inactive` défaut `false`.

**200** nœuds imbriqués `children[]`, même carte que GET `{id}` sans `children_count` (remplacé par `children`). Profondeur max 16.

---

## Flux cycle

```
cur = parent
seen = {self.id}
pour _ in range(16):
    si cur is None: ok
    si cur.id in seen: SEGMENT_CYCLE
    seen.add(cur.id)
    cur = cur.parent_segment
sinon: SEGMENT_CYCLE
```

---

## 1. Fichiers

```
apps/annuaire/views_admin_org.py
apps/annuaire/serializers_org.py
apps/annuaire/services/org_tree.py      # cycle, level, tree
apps/annuaire/urls.py
```

Audit via le helper ADMIN-A (`audit_logs`).

---

## 2. Tests (acceptation)


| ID | Cas | Attendu |
|----|-----|---------|
| 06 | USER jean GET types | 403 |
| 06 | POST `DIRECTION` | 409 code pris |
| 06 | DELETE `SERVICE` (seed, 0 segment) | 409 `TYPE_SYSTEM` |
| 06 | POST `AGENCE` level 3 + DELETE 0 usage | 201 puis 204 |
| 07 | POST enfant de `YAS` type `DEPARTEMENT` | 201 |
| 07 | POST enfant type `DIRECTION` sous `YAS` (level 0≯0) | 400 `SEGMENT_LEVEL_INVALID` |
| 07 | PATCH parent = self | 400 `SEGMENT_PARENT_SELF` |
| 07 | cycle A→B→A | 400 `SEGMENT_CYCLE` |
| 07 | DELETE `YAS` avec users.segment_id | 409 `SEGMENT_IN_USE` |
| 07 | responsable inactif | 400 |
| 08 | tree | `YAS` racine ; enfants imbriqués |
| — | sans JWT | 401 |


---

## Critères d’acceptation

- [ ] CRUD types + gardes seed / in-use
- [ ] CRUD segments + cycle / level / responsable
- [ ] Tree admin ; directory public inchangé (actifs)
- [ ] Audit `SEGMENT_*`
- [ ] Spec seulement

---

## Écarts documents liés

- **ANNUAIRE-A** : lecture publique inchangée (actifs, pas de responsable).
- **PROF-A** : path / manager suivent le nouvel arbre.
- **ANNUAIRE-C** : DELETE segment bloqué si `user_segments`.
- **AUTH-R** : 4 perms `annuaire.segment_type.*` / `annuaire.segment.*`.
