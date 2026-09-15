# Jour 18 — ANNUAIRE-B (organigramme : types d’unité + arbre)

**Statut :** clos (2026-09-15).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–17 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 17](00-jour-17-annuaire-a.md)).  
**Livré :** CRUD `/api/v1/admin/segment-types` (gardes `TYPE_SYSTEM`/`TYPE_IN_USE`) ; CRUD `/api/v1/admin/segments` (gardes cycle/level/responsable/`SEGMENT_IN_USE`) ; `GET /api/v1/admin/segments/tree`. 17 tests (`test_annuaire_b.py`).  
`SegmentType` / `Segment` **déjà** créés (AUTH-A, 5 tables annuaire). `seed_annuaire` (jour 3) : 3 types + segment `YAS`. Perms `annuaire.segment_type.read/manage`, `annuaire.segment.read/manage` **déjà** dans le catalogue RBAC (jour 11, AUTH-R) — ADMIN les a via `ALL_SYSTEM_CODES`. Directory public (jour 17) et `resolve_org` (PROF-A) lisent déjà `Segment` en écriture seule seed.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §3 — *organigramme*) :

| Fonction MVP                          | Ticket     | Statut                    |
| -------------------------------------- | ---------- | ------------------------- |
| Recherche par nom (people-picker)      | ANNUAIRE-A | **fait** (jour 17)        |
| **Organigramme (types + arbre)**       | **ANNUAIRE-B** | **ce jour**            |
| Mutations / affectations               | ANNUAIRE-C | jour 19                   |
| Compétences / certifications           | ANNUAIRE-D | jour 20                   |

**À quoi ça sert (MVP) :** aujourd’hui, seul `YAS` (créé au seed) existe comme segment. Un admin doit pouvoir créer réellement des unités (Direction, Département, Service, NOC, agence…), les ranger en arbre, et nommer un responsable — pour que la fiche collègue, le picker et `/me` s’appuient sur une organisation réelle plutôt que sur une case texte figée.

**Plan métier (code à coller) :** [ANNUAIRE-B-arbre-segments.md](annuaire_plans/ANNUAIRE-B-arbre-segments.md) (ANN-06 … 08).  
Chemins lab = ce fichier (`views/admin_org.py`, `services/org_tree.py`, `urls/admin_org.py` — **pas** `views_admin_org.py` à plat, comme ANNUAIRE-A).

**Déjà en base / code :**

- `SegmentType` / `Segment` : modèles complets (code, name, level, is_active, segment_type FK, parent_segment FK, responsable FK) depuis AUTH-A. 0 écriture hors seed.
- `seed_annuaire` : `DIRECTION`/`DEPARTEMENT`/`SERVICE` + `YAS` (racine, `parent_segment=NULL`).
- `GET /directory/segment-types` et `GET /directory/segments` (public, jour 17) : lecture actifs seulement, **inchangés** ce jour.
- `resolve_org` (PROF-A) : path/department/direction/manager déjà calculés depuis `Segment` — **ne pas** recoder.
- Perms `annuaire.segment_type.read`, `annuaire.segment_type.manage`, `annuaire.segment.read`, `annuaire.segment.manage` : déjà dans `rbac_catalog.SYSTEM_PERMISSIONS`, déjà accordées à ADMIN.
- Helper audit ADMIN-A (`AuditLog.objects.create(module="ANNUAIRE", ...)`) : pattern réutilisable, pas de nouveau helper.

**Pas encore :** CRUD `/admin/segment-types` ; CRUD `/admin/segments` (create/patch/delete, cycle / level / responsable) ; `GET /admin/segments/tree`.

**Objectif du jour :**

1. `apps/annuaire/services/org_tree.py` : `validate_level`, `detect_cycle` (max 16), `serialize_segment`, `serialize_tree`, audit `SEGMENT_TYPE_*` / `SEGMENT_*`.
2. CRUD `/api/v1/admin/segment-types` (list/detail/create/patch/delete). Garde `TYPE_SYSTEM` (409, les 3 seed) et `TYPE_IN_USE` (409, un segment pointe encore).
3. CRUD `/api/v1/admin/segments` (list/detail/create/patch/delete). Gardes `SEGMENT_PARENT_SELF`, `SEGMENT_CYCLE`, `SEGMENT_LEVEL_INVALID`, `RESPONSABLE_INVALID`, `SEGMENT_IN_USE` (DELETE si enfant / `users.segment_id` / `user_segments`).
4. `GET /api/v1/admin/segments/tree` : nœuds imbriqués `children[]`, `root_id` optionnel, `include_inactive` défaut `false`, profondeur max 16.
5. Ne rien casser : directory public (actifs seulement), `resolve_org`, `seed_annuaire`.

**Hors jour 18 :** ANNUAIRE-C (affectations / mutations), ANNUAIRE-D (skills / certifs), organigramme UI drag-and-drop, import SIRH, `segments.region_id`, recherche trgm admin (liste `q` suffit), recoder `resolve_org` / directory public / PROF-A.

---

## Pourquoi ce jour (après ANNUAIRE-A)

Le picker et la fiche collègue savent déjà **lire** un segment (jour 17), mais un admin ne peut encore rien créer d’autre que le `YAS` du seed — impossible de représenter une vraie organisation. ANNUAIRE-C (mutations, jour 19) a besoin que des segments réels existent d’abord ; ANNUAIRE-D (skills, jour 20) est indépendant de l’arbre.

```text
JWT + HasPermission (pas de porte CGU/wizard — vues admin, comme ADMIN-A)
    GET/POST   /admin/segment-types              annuaire.segment_type.read / manage
    GET/PATCH/DELETE /admin/segment-types/{id}    annuaire.segment_type.read / manage
    GET/POST   /admin/segments                    annuaire.segment.read / manage
    GET/PATCH/DELETE /admin/segments/{id}         annuaire.segment.read / manage
    GET        /admin/segments/tree               annuaire.segment.read (AVANT {id})

Déjà là (ne pas casser)
    GET /directory/segment-types   public, actifs (jour 17)
    GET /directory/segments        public, actifs, parent_id (jour 17)
    GET /users?q=                  org.segment mini (jour 17)
    GET /me, GET /users/{id}       org path/department/direction/manager (PROF-A resolve_org)
    seed_annuaire                  types + YAS (jour 3)
```

---

## Paliers (figés pour ce jour)

| Sujet | Choix jour 18 | Plus tard |
| ----- | ------------- | --------- |
| Auth | JWT + `HasPermission`. **Pas** de porte CGU/wizard (vues admin, comme ADMIN-A) | — |
| Codes | `segment_types.code` / `segments.code` : `SCREAMING_SNAKE` 2–64, UK | — |
| Types seed | `DIRECTION`/`DEPARTEMENT`/`SERVICE` : `code` non patchable, DELETE **409** `TYPE_SYSTEM`. Pas de colonne `is_system` : liste close en dur (les 3 codes seed) | — |
| Types custom | POST libre (`NOC`, `AGENCE`…). DELETE **409** `TYPE_IN_USE` si un segment pointe encore | — |
| Arbre | `parent_segment_id` NULL = racine. Self-parent → **400** `SEGMENT_PARENT_SELF`. Cycle (max 16 sauts) → **400** `SEGMENT_CYCLE` | — |
| Level | Si parent **et** enfant ont un type : `child.level > parent.level` sinon **400** `SEGMENT_LEVEL_INVALID`. Parent sans type : pas de check | — |
| Responsable | `responsable_id` = user **actif** existant, ou `null`. Inactif / inconnu → **400** `RESPONSABLE_INVALID` | — |
| Actifs | Admin voit inactifs (`is_active=false` inclus). Directory public (jour 17) = actifs seulement, **inchangé** | — |
| DELETE segment | **409** `SEGMENT_IN_USE` si enfant, `users.segment_id`, ou `user_segments` (table 0 ligne avant ANNUAIRE-C : seul `users.segment_id` compte ce jour) | — |
| Soft vs hard | Pas de soft-delete dédié. `is_active=false` pour masquer (directory / PROF org ignorent l’inactif) | — |
| URL tree | `GET /admin/segments/tree` **avant** `{id}` dans `urls/admin_org.py` | — |
| Audit | `module=ANNUAIRE` ; actions `SEGMENT_TYPE_CREATE/UPDATE/DELETE`, `SEGMENT_CREATE/UPDATE/DELETE`. Jamais de secret | — |
| Enveloppe | `{success, data: {count, results}}` pour les listes, `{success, data: {...}}` pour détail/tree — comme admin IAM (ADMIN-A) | — |

Perms déjà seedées (jour 11) : `annuaire.segment_type.read/manage`, `annuaire.segment.read/manage`. ADMIN uniquement (USER ne les a pas dans `SELF_PERMISSION_CODES`).

---

## 1. Tables

**0 migration.** `SegmentType` / `Segment` existent depuis AUTH-A (5 tables annuaire). Ce jour = écritures HTTP sur des tables déjà là, pas de nouveau champ.  
**Interdit :** `docker compose down -v`. Pas de `user_segments` (ANNUAIRE-C), pas de `user_skills` / `user_certifications` (ANNUAIRE-D).

---

## 2. HTTP

Arborescence `views/` / `urls/admin_org.py`, montée en **plus** de `apps.iam.urls.admin` sous le même préfixe `/api/v1/admin/` (`config/urls.py` : deuxième `include()`). `path("segments/tree")` **avant** `path("segments/<uuid:pk>")`.

| Fichier | Rôle |
| ------- | ---- |
| `apps/annuaire/services/org_tree.py` | **nouveau.** cycle, level, tree, audit |
| `apps/annuaire/views/admin_org.py` | **nouveau.** `AdminSegmentTypeListCreateView` + `AdminSegmentTypeDetailView` + `AdminSegmentListCreateView` + `AdminSegmentDetailView` + `AdminSegmentTreeView` |
| `apps/annuaire/serializers/admin_org.py` | **nouveau.** query OpenAPI + enveloppes |
| `apps/annuaire/urls/admin_org.py` | **nouveau.** `segments/tree` avant `segments/<uuid:pk>` |
| `apps/iam/tests/test_annuaire_b.py` | **nouveau.** |

| Méthode | Chemin | Perm |
| ------- | ------ | ---- |
| GET, POST | `/api/v1/admin/segment-types` | `annuaire.segment_type.read` / `.manage` |
| GET, PATCH, DELETE | `/api/v1/admin/segment-types/{id}` | `annuaire.segment_type.read` / `.manage` |
| GET, POST | `/api/v1/admin/segments` | `annuaire.segment.read` / `.manage` |
| GET | `/api/v1/admin/segments/tree` | `annuaire.segment.read` |
| GET, PATCH, DELETE | `/api/v1/admin/segments/{id}` | `annuaire.segment.read` / `.manage` |

Query liste `segment-types` : `q` (code/name), `is_active`, `limit` 1–100 défaut 50, `offset`.  
Query liste `segments` : `q` (code/name trgm), `parent_id` (UUID ou `null`), `type_id`, `is_active`, pagination.

POST/PATCH `segment-types` : `{ "code", "name", "level", "description?" }`. `code` gelé sur les 3 seed.  
POST/PATCH `segments` :

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

Fiche `GET {id}` segment : champs + `type` `{id,code,name,level}` + `parent` mini + `responsable` mini-user (`id`, `display_name`, `username`) + `children_count`.  
`GET /admin/segments/tree` : mêmes champs, `children_count` remplacé par `children[]` imbriqués. Query `root_id` optionnel (défaut = toutes les racines), `include_inactive` défaut `false`.

**409** `SEGMENT_TYPE_CODE_TAKEN` / `NAME_TAKEN` / `TYPE_SYSTEM` / `TYPE_IN_USE` / `SEGMENT_CODE_TAKEN` / `SEGMENT_IN_USE`.  
**400** `INVALID_TYPE_CODE` / `INVALID_SEGMENT_CODE` / `SEGMENT_PARENT_SELF` / `SEGMENT_CYCLE` / `SEGMENT_LEVEL_INVALID` / `RESPONSABLE_INVALID` / `TYPE_INVALID`.  
**401** sans JWT. **403** `FORBIDDEN` sans la perm (pas de porte CGU/wizard, comme ADMIN-A).

---

## 3. Flux cycle (`detect_cycle`)

```text
cur = parent
seen = {self.id}
pour _ in range(16):
    si cur is None: ok
    si cur.id in seen: SEGMENT_CYCLE
    seen.add(cur.id)
    cur = cur.parent_segment
sinon: SEGMENT_CYCLE
```

Appliqué sur POST (parent fourni) et PATCH (si `parent_segment_id` change).

---

## 4. Impact tests existants

| Fichier | Adapter |
| ------- | ------- |
| `test_annuaire_a.py` | `GET /directory/segment-types|segments` inchangés (actifs seulement) ; pas de régression |
| `test_prof_a.py` | `resolve_org` (path/department/direction/manager) inchangé — lit toujours `Segment` directement |
| `test_admin_a.py` | `/admin/users` **pas** ce contrat ; pas de collision de route avec `/admin/segments*` |
| `test_auth_d.py` | `test_directory_public` inchangé |

Portes : vues admin **sans** CGU/wizard (comme ADMIN-A) — pas de régression AUTH-F sur ces routes.

---

## 5. Tests nouveaux (`test_annuaire_b.py`)

| ID | Cas | Attendu |
| -- | --- | ------- |
| 06 | USER (pas ADMIN) GET `/admin/segment-types` | 403 `FORBIDDEN` |
| 06 | POST `code=DIRECTION` (déjà seed) | 409 `SEGMENT_TYPE_CODE_TAKEN` |
| 06 | DELETE `SERVICE` (seed, 0 segment) | 409 `TYPE_SYSTEM` |
| 06 | POST `AGENCE` level 3, puis DELETE (0 usage) | 201 puis 204 |
| 06 | DELETE type encore utilisé par un segment | 409 `TYPE_IN_USE` |
| 07 | POST segment enfant de `YAS`, type `DEPARTEMENT` | 201 ; `parent_segment_id` = YAS |
| 07 | POST enfant type `DIRECTION` sous `YAS` (level 0 ≯ 0) | 400 `SEGMENT_LEVEL_INVALID` |
| 07 | PATCH `parent_segment_id` = self | 400 `SEGMENT_PARENT_SELF` |
| 07 | Cycle A→B→A (PATCH B.parent = A puis A.parent = B) | 400 `SEGMENT_CYCLE` |
| 07 | POST avec `responsable_id` inactif | 400 `RESPONSABLE_INVALID` |
| 07 | DELETE `YAS` alors qu’un `users.segment_id` pointe dessus | 409 `SEGMENT_IN_USE` |
| 08 | `GET /admin/segments/tree` | `YAS` racine ; enfants imbriqués ; profondeur correcte |
| 08 | `tree?include_inactive=false` | segment inactif absent |
| — | Directory public (jour 17) après création d’un segment | toujours actifs seulement, inchangé |
| — | `resolve_org` (`/me`) après ANNUAIRE-B | path/department/direction/manager toujours corrects |
| — | sans JWT | 401 |
| — | `/api/schema/` | contient `/api/v1/admin/segments/tree` |

Helper MFA : `login_until_jwt`. Fixture `admin` : rôle `ADMIN` (comme `test_admin_a.py`).

---

## 6. Vérif manuelle

```powershell
python manage.py check
pytest apps/iam/tests/test_annuaire_b.py apps/iam/tests/test_annuaire_a.py apps/iam/tests/test_prof_a.py apps/iam/tests/test_admin_a.py --reuse-db
```

Login admin → POST `/admin/segment-types` `AGENCE` → POST `/admin/segments` `NOC-LOME` (parent `YAS`) → `GET /admin/segments/tree` → `NOC-LOME` sous `YAS`.  
Directory public (`/directory/segments`) : toujours actifs seulement, sans changement de contrat.

---

## Checklist jour 18

- [x] CRUD `/admin/segment-types` + gardes `TYPE_SYSTEM` / `TYPE_IN_USE`
- [x] CRUD `/admin/segments` + gardes cycle / level / responsable / `SEGMENT_IN_USE`
- [x] `GET /admin/segments/tree` avant `{id}` ; profondeur max 16
- [x] Directory public (jour 17) inchangé ; `resolve_org` (PROF-A) inchangé
- [x] Audit `SEGMENT_TYPE_*` / `SEGMENT_*`
- [x] `test_annuaire_b.py` + régression A / PROF-A / ADMIN-A / AUTH-D
- [x] 0 migration ; 0 `docker compose down -v`
- [x] SIRH non modifié

---

## Interdits

- Recoder `resolve_org` / directory public / le picker (jour 17)
- CRUD `user_segments` (ANNUAIRE-C, jour 19)
- CRUD `user_skills` / `user_certifications` (ANNUAIRE-D, jour 20)
- `segments.region_id` (axes géo vs org restent distincts)
- Organigramme UI drag-and-drop, import SIRH
- `docker compose down -v`
- Changer le SIRH

---

## Après le jour 18

Jour 19 : **ANNUAIRE-C** — affectations / mutations (`user_segments` + sync `users.segment_id`) ([ANNUAIRE-C-affectations.md](annuaire_plans/ANNUAIRE-C-affectations.md)). Delta AUTH-D (D02/D03) et ADMIN-A (ADM-02) : appeler `open_assignment` (déjà noté dans ces plans). Lab pas encore écrit.

---

## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour**. Le jour 2 (admin + Swagger) est un extra déjà clos.

| Jours  | Plan                                           | Ticket MVP                          |
| ------ | ---------------------------------------------- | ----------------------------------- |
| 0      | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health` |
| 1–2    | AUTH-A ; admin + Swagger                       | Connexion locale ; lab admin        |
| 3–11   | D+B … AUTH-R                                   | §1 entrer + droits HTTP             |
| 12     | ADMIN-A                                        | §9 comptes                          |
| 13     | PROF-A                                         | §2 ma fiche / photo                 |
| 14     | PROF-B                                         | Préférences                         |
| 15     | PROF-C                                         | §2 visibilité                       |
| 16     | PRES-A                                         | §2 statut en ligne                  |
| 17     | ANNUAIRE-A                                     | §3 recherche collègue               |
| **18** | **ANNUAIRE-B** (ce plan)                       | §3 organigramme (types + arbre)     |
| 19     | ANNUAIRE-C                                     | §3 mutations / affectations         |
| 20     | ANNUAIRE-D                                     | §3 compétences / certifications     |
| 21     | CRYPTO-00                                      | §6 décision E2E                     |
| 22     | MEDIA-R + MEDIA-A                              | §4 upload (plafonds ; pas de reprise) |
| 23     | NOTIF-R + NOTIF-A                              | §5 alertes + MOB-PUSH (VoIP / worker) |
| 24     | CRYPTO-R + CRYPTO-A                            | Clés HTTP                           |
| 25     | MESSAGERIE-R, A, B                             | §7 1-to-1                           |
| 26     | MESSAGERIE-C, D                                | §7 groupes + temps réel             |
| 27     | MESSAGERIE-E (partiel), F, G                   | §7 enrichissements                  |
| 28     | MEDIA-B, C, D, E                               | §4 album / vocal / coffre           |
| 29     | APPELS-R, A, B, C                              | §8 appel 1-1 + `CALL_CANCELLED`     |
| 30     | APPELS-D, E, G                                 | §8 écran / CR                       |

**Total : 31 plans (jours 0 à 30).**  
Déjà clos : **18** (0–17). Restant : **13** (18–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.
