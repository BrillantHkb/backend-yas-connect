# Jour 17 — ANNUAIRE-A (people-picker + directory)

**Statut :** clos (2026-09-15).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–16 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 16](00-jour-16-pres-a.md)).  
**Livré :** `GET /api/v1/users` (picker, `q` 2–64, filtres `region_id`/`segment_id`, pagination, privacy 23–25) ; `GET /api/v1/directory/segment-types` ; `GET /api/v1/directory/segments` enrichi (`type_code`, `parent_id`). 17 tests (`test_annuaire_a.py`).  
Fiche collègue **déjà** `GET /users/{id}` (PROF-A). Dropdowns inscription **déjà** `GET /directory/regions|segments` (AUTH-D). Seed types + `YAS` **déjà** `seed_annuaire` (jour 3). Perm `iam.profile.read_other` **déjà** seedée (jour 11). Index GIN trgm `users` **déjà** AUTH-A.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §3 — *trouver un collègue*) :


| Fonction MVP                         | Ticket     | Statut                                     |
| ------------------------------------ | ---------- | ------------------------------------------ |
| Fiche collègue + masques + pastille  | PROF-A/C, PRES-A | **fait** (jours 13, 15, 16)          |
| **Recherche par nom (people-picker)** | **ANNUAIRE-A** | **ce jour**                           |
| Listes région / service inscription  | ANNUAIRE-A | **delta** (segment-types + `parent_id`)    |
| Arbre RH / mutations / skills        | B / C / D  | dans le MVP, jours 18–20 (A→Z §4.1)         |


**À quoi ça sert (MVP) :** jean tape `koe` → marie apparaît (nom, photo si visible, pastille, service) **sans** e-mail. Il ouvre un chat / un appel plus tard sans connaître le matricule. L’inscription hors JWT lit encore `/directory/*`.

**Plan métier (code à coller) :** [ANNUAIRE-A-recherche-referentiels.md](annuaire_plans/ANNUAIRE-A-recherche-referentiels.md) (ANN-01 … 05).  
Chemins lab = ce fichier (`views/users.py` liste + `{id}`, `services/search_service.py`, `apps/annuaire/views/directory.py` — **pas** `views_directory_search.py` à la racine IAM).

**Déjà en base / code :**

- `GET /api/v1/users/{uuid}` : fiche PROF-02, privacy 23–25, self → 400, inactif/pending → 404
- `GET /api/v1/users` **liste : 404** (pas de `path("")`)
- `GET /directory/regions` : public, enveloppe `{success, data}` ; tri **`code`** (AUTH-D : `MARITIME` en premier)
- `GET /directory/segments` : public, tous les actifs (`id`, `code`, `name`) ; **pas** `parent_id` / `type_code`
- **Pas** de `GET /directory/segment-types`
- `seed_annuaire` : `DIRECTION` / `DEPARTEMENT` / `SERVICE` + `YAS` ; **ne** rattache **pas** jean
- GIN trgm : `first_name`, `last_name`, `username`, `matricule` (et `email` — **ne pas** s’en servir ici)
- USER a déjà `iam.profile.read_other`
- Listes IAM : enveloppe `{success, data: {count, results}}` (admin users)

**Pas encore :** people-picker `GET /users?q=` ; `GET /directory/segment-types` ; query `parent_id` sur segments.

**Objectif du jour :**

1. `GET /api/v1/users` : `q` obligatoire 2–64, actifs non pending, **pas soi**, **pas d’e-mail** (ni filtre ni JSON). Privacy 23–25 sur `avatar_url` / `status` / `badge`.
2. Filtres optionnels `region_id` / `segment_id` (AND). Pagination `limit` 20 défaut, max 50.
3. Directory : **ajouter** `segment-types` ; **enrichir** segments (`type_code`, `parent_id`, filtre `parent_id`, omis = **racines**). Régions **inchangées** (régression AUTH-D).
4. Seed : **rejouer** `seed_annuaire` (idempotent). 0 table nouvelle. 0 CRUD RH.

**Hors jour 17 :** ANNUAIRE-B/C/D, organigramme admin, graphe d’amis, recherche par skill, recoder PROF-A fiche / PRES-A / AUTH-D register, `GET /admin/users` (e-mail RH).

---



## Pourquoi ce jour (après PRES-A)

La fiche `{id}` existe, mais le front ne peut pas **trouver** l’UUID sans le connaître. Sans `q` obligatoire on dumperait l’annuaire. Les dropdowns AUTH-D existent mais il manque les types et le filtrage parent (inscription / org).

```text
JWT + HasPermission + portes AUTH-F (après CGU + wizard)
    GET /users                         iam.profile.read_other

AllowAny (pas de porte)
    GET /directory/regions             déjà
    GET /directory/segment-types       nouveau
    GET /directory/segments            delta parent_id

Déjà là (ne pas casser)
    GET /users/{id} contrat PROF-02
    GET /me org_resolver
    GET /directory/regions (MARITIME d’abord)
    seed_annuaire YAS
    GET /admin/users (e-mail, pending — autre contrat)
```

---



## Paliers (figés pour ce jour)


| Sujet | Choix jour 17 | Plus tard |
| ----- | ------------- | --------- |
| Enveloppe picker | `{success, data: {count, results}}` comme admin listes. **Pas** le JSON nu du ticket | — |
| Enveloppe directory | **Garder** `{success, data: […]}` (AUTH-D). Pas un tableau racine | — |
| `q` | Obligatoire, trim, **2–64**. Manquant / 1 car. / 65+ → 400 `QUERY_TOO_SHORT` | — |
| Match | `icontains` (ILIKE) sur `first_name`, `last_name`, `username`, `matricule`. **Pas** `email` | similarité trgm score |
| Tri | `last_name`, `first_name`, `id` | ranking trgm |
| Soi | Exclu (`id ≠ me`) | — |
| Population | `is_active=true` **et** `pending_approval=false`. Inactifs **absents** (pas 403) | — |
| Hit | `id`, `display_name`, `username`, `job_title`, `avatar_url`, `org.segment` `{id,code,name}`, `status`, `badge`. **Pas** email / phone / matricule / last_seen / last_login / connection / availability / `status_message` | — |
| Privacy | Mêmes `_visible` / `colleague_presence` que PROF-A/C / PRES-A. `org.segment` **toujours** si segment (pas un masque) | — |
| `org` | `null` si pas de `segment_id` / segment inactif ; sinon `{segment: {id, code, name}}` seulement (pas path / manager) | — |
| Fiche `{id}` | **Inchangée** (délégué PROF-02) | — |
| `path("")` | **Avant** `path("<uuid:pk>")` dans `urls/users.py` | — |
| Régions | **Ne pas** changer tri (`code`) ni champs. AUTH-D `MARITIME` | ticket disait `name` |
| Segments `parent_id` omis | **Racines** (`parent_segment IS NULL`) + `is_active`. YAS reste visible | lister tout = `parent_id` absent **avant** ce jour |
| Segments champs | Ajouter `type_code`, `parent_id` (null si racine). Garder `id/code/name` | responsable = B |
| `segment-types` | Actifs ; `{id, code, name, level}` ; tri `level`, `code` | inactifs = B |
| Liste vide directory | **200** `data: []` jamais 404 | — |
| UUID filtre cassé | 400 `VALIDATION_ERROR` (`region_id` / `segment_id` / `parent_id`) | — |
| `parent_id` inconnu | 200 `[]` | — |
| Seed | Commande **existante**. 2e run sans doublon. Pas de `users.segment_id` | C |
| Migration | **0** | — |
| Portes | `GET /users` après CGU + wizard. Directory **sans** JWT | — |


Perm déjà seedée : `iam.profile.read_other` (self USER). Directory = `AllowAny`.

---



## 1. Tables

**0 migration.** Index trgm déjà là. `seed_annuaire` déjà là (ANN-05).  
**Interdit :** `docker compose down -v`. Pas de `user_segments` / skills.

---



## 2. HTTP

Arborescence `views/` / `urls/users.py`. `path("")` **avant** `path("<uuid:pk>")`.


| Fichier | Rôle |
| ------- | ---- |
| `apps/iam/services/search_service.py` | **nouveau.** parse `q` / filtres / page ; serialize hit |
| `apps/iam/views/users.py` | **delta.** `UserSearchView` GET liste + `UserPublicView` inchangé |
| `apps/iam/serializers/search.py` | query OpenAPI + envelope hits |
| `apps/annuaire/views/directory.py` | **delta.** `DirectorySegmentTypesView` + segments `parent_id` |
| `apps/annuaire/urls/directory.py` | `segment-types` **avant** tout catch-all |
| `apps/iam/tests/test_annuaire_a.py` | **nouveau.** |


| Méthode | Chemin | Perm |
| ------- | ------ | ---- |
| GET | `/api/v1/users` | `iam.profile.read_other` |
| GET | `/api/v1/users/{id}` | déjà PROF-A |
| GET | `/api/v1/directory/regions` | AllowAny (déjà) |
| GET | `/api/v1/directory/segment-types` | AllowAny |
| GET | `/api/v1/directory/segments` | AllowAny |

**GET `/users?q=` 200** — `data.count` = total filtré ; `data.results` = page.

**400** `QUERY_TOO_SHORT` si `q` absent / trop court / trop long.  
**401** sans JWT. **403** `TOS_REQUIRED` / `ONBOARDING_REQUIRED` / `FORBIDDEN`.

---



## 3. Hit picker (serialize)

Réutiliser `avatar_url()`, `_visible` photo, `colleague_presence` (status + badge). **Ne pas** appeler `serialize_colleague` (trop de champs).

`job_title` : string éventuellement `""`.  
`status` / `badge` : `null` si PROF-25 masque (comme la fiche).

---



## 4. Impact tests existants


| Fichier | Adapter |
| ------- | ------- |
| `test_auth_d.py` `test_directory_public` | **200** ; `YAS` encore dans `data` (racine). Champs extra OK |
| `test_prof_a.py` | `GET /users/{id}` inchangé ; `GET /users` sans `q` → 400 (pas 404) |
| `test_pres_a.py` | collègue `{id}` inchangé |
| `test_admin_a.py` | `/admin/users` **pas** ce contrat |


Portes : picker **fermées** comme `/users/{id}`.

---



## 5. Tests nouveaux (`test_annuaire_a.py`)


| ID | Cas | Attendu |
| -- | --- | ------- |
| 01 | `q=m` / sans `q` / `q` 65 car. | 400 `QUERY_TOO_SHORT` |
| 01 | `q=koe` USER | 200 ; marie dans `results` ; **pas** jean ; **pas** de clé `email` |
| 01 | cible photo `NOBODY` | `avatar_url` null ; `status` encore visible si online EVERYONE |
| 01 | cible online `NOBODY` | `status`/`badge` null |
| 01 | pending / `is_active=false` | absents |
| 01 | `region_id` / `segment_id` AND | hors filtre → 0 hit |
| 01 | `limit`/`offset` | page ; `count` = total |
| 02 | `GET /users/{id}` | contrat PROF-02 (régression courte) |
| 03 | directory regions sans JWT | 200 ; premier `code=MARITIME` |
| 04 | `GET /directory/segment-types` sans JWT | 200 ; `DIRECTION` level 0 |
| 04 | segments sans `parent_id` | racines ; `YAS` ; `parent_id` null ; `type_code=DIRECTION` |
| 04 | `parent_id=<YAS>` | enfants (vide au seed) ; 200 `[]` OK |
| 05 | `seed_annuaire` 2e fois | pas d’intégrité UK |
| — | `GET /users` sans JWT | 401 |
| — | sans `iam.profile.read_other` | 403 `FORBIDDEN` |
| — | avant wizard | 403 TOS puis `ONBOARDING_REQUIRED` |
| — | `/api/schema/` | contient `/api/v1/users` **et** `segment-types` |


Helper MFA : `login_until_jwt`. Portes : `close_gates`. Seed types via `call_command("seed_annuaire")` ou `get_or_create` comme AUTH-D.

---



## 6. Vérif manuelle

```powershell
python manage.py check
python manage.py seed_annuaire
pytest apps/iam/tests/test_annuaire_a.py apps/iam/tests/test_auth_d.py apps/iam/tests/test_prof_a.py --reuse-db
```

Login jean → `GET /api/v1/users?q=koe` → marie, **sans** e-mail.  
Sans Bearer : directory 200 ; picker 401.  
`/admin/` cookie : **pas** ces routes.

---



## Checklist jour 17

- [x] `GET /users` `q` 2–64 + trgm/ILIKE ; soi / pending / disabled exclus
- [x] Hit sans e-mail ; privacy 23–25 ; `org.segment` mini
- [x] `path("")` avant `{id}` ; fiche PROF-02 intacte
- [x] `GET /directory/segment-types` ; segments racines + `parent_id`
- [x] Régions AUTH-D inchangées
- [x] `seed_annuaire` idempotent ; 0 migration ; 0 `down -v`
- [x] `test_annuaire_a.py` + régression D / PROF-A
- [x] SIRH non modifié

---



## Interdits

- Recoder `serialize_colleague` / `org_resolver` / PRES-A / register AUTH-D
- Chercher ou renvoyer l’**e-mail** sur le picker
- Dump sans `q` / `q` d’1 caractère
- CRUD `segment-types` / `segments` admin (ANNUAIRE-B)
- `user_segments`, skills, certifs (C/D)
- Confondre avec `GET /admin/users`
- `docker compose down -v`
- Changer le SIRH

---



## Après le jour 17

Jour 18 : **ANNUAIRE-B** — types d'unité + arbre organisationnel ([ANNUAIRE-B-arbre-segments.md](annuaire_plans/ANNUAIRE-B-arbre-segments.md)). Lab pas encore écrit.

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
| **17** | **ANNUAIRE-A** (ce plan)                       | §3 recherche collègue               |
| 18     | ANNUAIRE-B                                     | §3 organigramme (types + arbre)     |
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
Déjà clos : **17** (0–16). Restant : **14** (17–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.
