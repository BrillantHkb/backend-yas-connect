# Jour 19 — ANNUAIRE-C (affectations / mutations)

**Statut :** clos (2026-09-15).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–18 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 18](00-jour-18-annuaire-b.md)).  
**Livré :** `open_assignment`/`sync_users_segment_id`/`validate_org_fk` ; CRUD `/api/v1/admin/users/{id}/segments` + `/api/v1/admin/user-segments/{id}` ; delta AUTH-D (`register_ad`/`register_local`) et ADMIN-A (`create_local_user`) ; `ANNUAIRE-B` `SEGMENT_IN_USE` vérifie aussi `user_segments`. 13 tests (`test_annuaire_c.py`).  
`user_segments` **déjà** créée (AUTH-A, 5 tables annuaire), 0 ligne. Segments réels utilisables **depuis** ANNUAIRE-B (jour 18). Perms `annuaire.user_segment.read/manage` **déjà** dans le catalogue RBAC (jour 11, AUTH-R) — ADMIN les a via `ALL_SYSTEM_CODES`.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §3 — *muter quelqu'un / historique d'affectation*) :

| Fonction MVP                          | Ticket     | Statut                    |
| -------------------------------------- | ---------- | ------------------------- |
| Organigramme (types + arbre)           | ANNUAIRE-B | **fait** (jour 18)        |
| **Mutations / affectations**           | **ANNUAIRE-C** | **ce jour**            |
| Compétences / certifications           | ANNUAIRE-D | jour 20                   |

**À quoi ça sert (MVP) :** aujourd'hui, `users.segment_id` est posé une fois à l'inscription (AUTH-D) ou à la création RH (ADMIN-A) et n'a **aucun historique** — si Jean change de service, personne ne peut dire depuis quand ni ce qu'il faisait avant. ANNUAIRE-C ajoute la table historique (`user_segments`) et fait en sorte que `users.segment_id` (lu partout : fiche, picker, présence) reste **toujours** synchronisé avec l'affectation ouverte la plus récente.

**Plan métier (code à coller) :** [ANNUAIRE-C-affectations.md](annuaire_plans/ANNUAIRE-C-affectations.md) (ANN-09 … 13, ANN-16).  
Chemins lab = ce fichier (`services/assignment.py`, `views/admin_assignments.py`, `urls/admin_assignments.py`).

**Déjà en base / code :**

- `UserSegment` : modèle complet (`user`, `segment`, `assigned_by`, `start_date`, `end_date`, `position`, `position_description`, `is_active`) depuis AUTH-A. 0 ligne.
- `users.segment_id` : posé directement dans `User.objects.create_user(...)` par `register_ad` / `register_local` ([apps/iam/services/register_service.py](../../apps/iam/services/register_service.py) lignes ~161–178 et ~226–243) et par `create_local_user` ([apps/iam/services/admin_user_service.py](../../apps/iam/services/admin_user_service.py) lignes ~244–259) — **sans** trace historique.
- `_validate_region_segment(region_id, segment_id)` : déjà utilisé par ces 3 fonctions, résout déjà l'objet `segment` — **réutiliser**, ne pas re-fetch.
- Segments réels (arbre, responsable) : disponibles depuis ANNUAIRE-B (jour 18).
- Perms `annuaire.user_segment.read`, `annuaire.user_segment.manage` : déjà dans `rbac_catalog.SYSTEM_PERMISSIONS`, déjà accordées à ADMIN.

**Pas encore :** `GET /admin/users/{id}/segments` (historique) ; `POST` nouvelle affectation (mutation) ; `PATCH`/`DELETE /admin/user-segments/{id}` ; `sync_users_segment_id` ; hook `open_assignment` sur AUTH-D / ADMIN-A.

**Objectif du jour :**

1. `apps/annuaire/services/assignment.py` : `open_assignment(user, segment, *, assigned_by, start_date=None, position="", position_description="")` (clôture l'ouverte existante, insère, sync) ; `sync_users_segment_id(user)` ; `validate_org_fk(region_id, segment_id)` (déjà utilisée ailleurs sous une autre forme — **ANN-16 la formalise en fonction partagée**).
2. CRUD historique : `GET`/`POST /admin/users/{id}/segments`, `GET`/`PATCH`/`DELETE /admin/user-segments/{id}`. Gardes `ASSIGNMENT_DATE_INVALID`, `SEGMENT_INVALID`.
3. **Delta AUTH-D / ADMIN-A** (jours 3 et 12, **déjà clos**, à rouvrir) : appeler `open_assignment(...)` juste après `User.objects.create_user(...)` dans les 3 endroits déjà repérés :
   - `register_service.py::register_ad` (~L172, `assigned_by=None`)
   - `register_service.py::register_local` (~L237, `assigned_by=None`)
   - `admin_user_service.py::create_local_user` (~L254, `assigned_by=actor`)
   Le `segment` est déjà résolu par `_validate_region_segment` dans ces 3 fonctions — le passer tel quel à `open_assignment`, **pas** de nouvelle requête.
4. Ne rien casser : `resolve_org`, directory public, picker, `GET /admin/users` (ADMIN-A), fiche PROF-A.

**Hors jour 19 :** ANNUAIRE-D (skills/certifs), `/me/segments` (self interdit), backfill des comptes déjà créés avant ce jour (RH pose une affectation manuellement si l'historique manque), import RH en masse.

---

## Pourquoi ce jour (après ANNUAIRE-B)

L'arbre existe (jour 18), mais `users.segment_id` reste une simple colonne posée une fois — sans lui, ANNUAIRE-D (skills, indépendant) pourrait déjà être fait, mais l'esprit RH du produit (« muter quelqu'un ») a besoin de cet historique **avant** de clore le chapitre Annuaire. C'est aussi la seule brique qui **rouvre du code déjà livré** (AUTH-D jour 3, ADMIN-A jour 12) — annoncé dès leur écriture.

```text
JWT + HasPermission (pas de porte CGU/wizard — vues admin, comme ADMIN-A/ANNUAIRE-B)
    GET  /admin/users/{user_id}/segments      annuaire.user_segment.read
    POST /admin/users/{user_id}/segments      annuaire.user_segment.manage
    GET/PATCH/DELETE /admin/user-segments/{id} annuaire.user_segment.read / manage

Delta (jours déjà clos, à rouvrir)
    AUTH-D  register_ad / register_local       + open_assignment(assigned_by=None)
    ADMIN-A create_local_user                  + open_assignment(assigned_by=actor)

Déjà là (ne pas casser)
    GET /directory/segment-types|segments      public, actifs (jour 17)
    GET /users?q=, GET /me, GET /users/{id}    org.segment / resolve_org (jour 17, PROF-A)
    CRUD /admin/segment-types|segments|tree    ANNUAIRE-B (jour 18)
```

---

## Paliers (figés pour ce jour)

| Sujet | Choix jour 19 | Plus tard |
| ----- | ------------- | --------- |
| Double couche | Courant = `users.segment_id` (profil, CONTACTS, picker, présence). Historique = `user_segments` | — |
| Une ouverte | Au plus **une** ligne `end_date=NULL` et `is_active=true` par user | — |
| Mutation | `POST` ouverte **clôture** l'ancienne (`end_date=now()`, `is_active=false`) puis insère. **Pas** de 409 chevauchement | — |
| Sync | Ouverte la plus récente (`-start_date`) → copie `users.segment_id`. Plus aucune ouverte → `NULL` | — |
| Création compte | Dès ce jour : AUTH-D (D02/D03) et ADMIN-A (ADM-02) appellent `open_assignment` en plus de la colonne IAM | — |
| Comptes déjà créés | **Pas** de backfill auto (jean/marie des jours précédents restent sans historique). RH pose une affectation si besoin | — |
| Dates | `start_date` défaut `now()`. Si `end_date` fourni : `start_date` ≤ `end_date` sinon **400** `ASSIGNMENT_DATE_INVALID` | — |
| Segment cible | Doit exister et `is_active=true` sinon **400** `SEGMENT_INVALID` | — |
| `assigned_by` | Toujours `request.user` sur les vues admin ; `None` pour `open_assignment` appelé depuis AUTH-D (self-register) | — |
| `user_id` | Non patchable sur `PATCH /admin/user-segments/{id}` (DELETE + POST pour changer d'user) | — |
| Portes | Admin : pas de CGU/wizard. **Interdit** en self (pas de `/me/segments`) | — |
| Audit | `module=ANNUAIRE` ; `USER_SEGMENT_CREATE` / `UPDATE` / `CLOSE` / `DELETE` | — |
| DELETE | Suppression physique (correction d'erreur de saisie), puis sync. **Pas** de soft-delete | — |

Perms déjà seedées (jour 11) : `annuaire.user_segment.read/manage`. ADMIN uniquement.

---

## 1. Tables

**0 migration.** `user_segments` existe depuis AUTH-A (5 tables annuaire), 0 ligne jusqu'ici.  
**Interdit :** `docker compose down -v`. Pas de `user_skills` / `user_certifications` (ANNUAIRE-D).

---

## 2. HTTP

| Fichier | Rôle |
| ------- | ---- |
| `apps/annuaire/services/assignment.py` | **nouveau.** `open_assignment`, `sync_users_segment_id`, `validate_org_fk`, audit |
| `apps/annuaire/views/admin_assignments.py` | **nouveau.** `AdminUserSegmentListCreateView` + `AdminUserSegmentDetailView` |
| `apps/annuaire/urls/admin_assignments.py` | **nouveau.** monté sous `/api/v1/admin/` (`config/urls.py` : 3ᵉ `include()`) |
| `apps/iam/services/register_service.py` | **delta.** `register_ad` / `register_local` appellent `open_assignment` |
| `apps/iam/services/admin_user_service.py` | **delta.** `create_local_user` appelle `open_assignment` |
| `apps/iam/tests/test_annuaire_c.py` | **nouveau.** |

| Méthode | Chemin | Perm |
| ------- | ------ | ---- |
| GET | `/api/v1/admin/users/{user_id}/segments` | `annuaire.user_segment.read` |
| POST | `/api/v1/admin/users/{user_id}/segments` | `annuaire.user_segment.manage` |
| GET | `/api/v1/admin/user-segments/{id}` | `annuaire.user_segment.read` |
| PATCH | `/api/v1/admin/user-segments/{id}` | `annuaire.user_segment.manage` |
| DELETE | `/api/v1/admin/user-segments/{id}` | `annuaire.user_segment.manage` |

`user_id` inconnu → **404** (comme `GET /admin/users/{id}`).

**GET liste** (`include_closed` défaut `true`, tri `-start_date`) : `id`, `segment` `{id,code,name}`, `start_date`, `end_date`, `is_active`, `position`, `position_description`, `assigned_by` mini-user ou `null`.

**POST** body :

```json
{
  "segment_id": "<uuid>",
  "start_date": "2026-09-15T00:00:00Z",
  "end_date": null,
  "position": "Chef équipe",
  "position_description": ""
}
```

`start_date` défaut `now()`. `end_date` omis = ouverte (déclenche la mutation : clôture l'ancienne). `end_date` fourni = saisie rétroactive déjà close, **pas** de clôture de l'ouverte existante, **pas** de sync si une autre reste ouverte. **201**. Audit `USER_SEGMENT_CREATE` (+ `CLOSE` de l'ancienne si mutation).

**PATCH** whitelist : `segment_id`, `start_date`, `end_date`, `position`, `position_description`, `is_active`. Clôturer : `{ "end_date": "<iso>", "is_active": false }` → sync. Audit `USER_SEGMENT_CLOSE` si transition ouvert → fermé, sinon `USER_SEGMENT_UPDATE`.

**DELETE** : suppression physique (correction), puis sync. **204**. Audit `USER_SEGMENT_DELETE`.

**400** `ASSIGNMENT_DATE_INVALID` / `SEGMENT_INVALID` / `VALIDATION_ERROR`. **401** sans JWT. **403** `FORBIDDEN` sans la perm.

---

## 3. Sync (`sync_users_segment_id`, ANN-13)

```text
def sync_users_segment_id(user):
    row = user_segments.filter(user=user, is_active=True, end_date__isnull=True)
         .order_by("-start_date").first()
    user.segment_id = row.segment_id if row else None
    user.save(update_fields=["segment_id", "updated_at"])
```

Appelé **dans la même transaction** que tout write `user_segments`.  
`open_assignment(user, segment, *, assigned_by, start_date=now, position="", position_description="")` : clôture l'ouverte existante (si présente) → INSERT → sync.

---

## 4. FK org partagée (`validate_org_fk`, ANN-16)

Utilisée par AUTH-D, ADMIN-A create, et ce POST/PATCH d'affectation.

| Champ | Règle | Erreur |
|-------|--------|--------|
| `region_id` | UUID existant, `region.is_active` n/a (pas de colonne) — existant seulement | **400** `REGION_INVALID` |
| `segment_id` | UUID existant, `segments.is_active=true` | **400** `SEGMENT_INVALID` |

`_validate_region_segment` (déjà dans `register_service.py`) devient un appel à cette fonction partagée, **sans changer son contrat** (mêmes erreurs, même signature d'appel côté AUTH-D/ADMIN-A).

---

## 5. Impact tests existants

| Fichier | Adapter |
| ------- | ------- |
| `test_auth_d.py` | D02/D03 créent désormais **aussi** une ligne `user_segments` ouverte — ajouter une assertion, ne pas casser le contrat HTTP existant |
| `test_admin_a.py` | ADM-02 idem (`assigned_by` = l'admin acteur) |
| `test_annuaire_b.py` | CRUD segments inchangé ; `SEGMENT_IN_USE` sur DELETE doit maintenant aussi vérifier `user_segments` (pas seulement `users.segment_id`) |
| `test_prof_a.py` / `test_annuaire_a.py` | `resolve_org` / picker lisent toujours `users.segment_id` (inchangé, juste maintenant historisé) |

---

## 6. Tests nouveaux (`test_annuaire_c.py`)

| ID | Cas | Attendu |
| -- | --- | ------- |
| 09 | historique 2 lignes (1 close + 1 ouverte) | 200 ; tri `-start_date` |
| 10 | POST ouverte alors qu'une ouverte existe | ancienne `end_date` posé ; `users.segment_id` = nouveau segment |
| 10 | `segment_id` inactif | 400 `SEGMENT_INVALID` |
| 11 | PATCH `end_date` < `start_date` | 400 `ASSIGNMENT_DATE_INVALID` |
| 12 | DELETE la dernière ouverte | `users.segment_id` → `NULL` après sync |
| 13 | `register_local` (AUTH-D) | 1 ligne `user_segments` ouverte, `assigned_by=None` ; `users.segment_id` posé |
| 13 | `create_local_user` (ADMIN-A) | 1 ligne ouverte, `assigned_by=` l'admin |
| 16 | `region_id` inconnu à la création | 400 `REGION_INVALID` (régression AUTH-D/ADMIN-A) |
| — | `GET /admin/users/{id}/segments` sans la perm | 403 `FORBIDDEN` |
| — | `PATCH user_id` (tentative) | ignoré / `FIELD_FORBIDDEN` |
| — | sans JWT | 401 |
| — | `/api/schema/` | contient `/api/v1/admin/user-segments/{id}` |

Helper MFA : `login_until_jwt`. Fixture `admin` : rôle `ADMIN` (comme `test_admin_a.py` / `test_annuaire_b.py`).

---

## 7. Vérif manuelle

```powershell
python manage.py check
pytest apps/iam/tests/test_annuaire_c.py apps/iam/tests/test_annuaire_b.py apps/iam/tests/test_auth_d.py apps/iam/tests/test_admin_a.py apps/iam/tests/test_prof_a.py --reuse-db
```

Inscription locale (AUTH-D) d'un nouvel utilisateur → vérifier qu'une ligne `user_segments` ouverte existe. POST une mutation vers un autre segment → l'ancienne se ferme, `users.segment_id` change, la fiche `/me` reflète le nouveau segment immédiatement.

---

## Checklist jour 19

- [x] `open_assignment` + `sync_users_segment_id` + `validate_org_fk`
- [x] CRUD historique `/admin/users/{id}/segments` + `/admin/user-segments/{id}`
- [x] Une affectation ouverte max ; mutation clôture l'ancienne
- [x] Delta AUTH-D (`register_ad`/`register_local`) + ADMIN-A (`create_local_user`) : hook `open_assignment`
- [x] `ANNUAIRE-B` : `SEGMENT_IN_USE` DELETE vérifie aussi `user_segments`
- [x] Audit `USER_SEGMENT_*`
- [x] `test_annuaire_c.py` + régression B / AUTH-D / ADMIN-A / PROF-A
- [x] 0 migration ; 0 `docker compose down -v`
- [x] SIRH non modifié

---

## Interdits

- `/me/segments` (self-service interdit, catalogue = admin seulement)
- Backfill automatique des comptes déjà créés (jean/marie des jours précédents)
- CRUD `user_skills` / `user_certifications` (ANNUAIRE-D, jour 20)
- Import RH en masse
- Recoder `resolve_org` / directory public / le picker / le CRUD segments (ANNUAIRE-B)
- `docker compose down -v`
- Changer le SIRH

---

## Après le jour 19

Jour 20 : **ANNUAIRE-D** — compétences / certifications (self `/me/skills`, `/me/certifications` + admin) ([ANNUAIRE-D-competences-certifications.md](annuaire_plans/ANNUAIRE-D-competences-certifications.md)). Indépendant de l'arbre. `document_id` référence `media_files` (déjà créée, upload réel = phase 3a / jour 22). Lab pas encore écrit.

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
| 18     | ANNUAIRE-B                                     | §3 organigramme (types + arbre)     |
| **19** | **ANNUAIRE-C** (ce plan)                       | §3 mutations / affectations         |
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
Déjà clos : **19** (0–18). Restant : **12** (19–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.
