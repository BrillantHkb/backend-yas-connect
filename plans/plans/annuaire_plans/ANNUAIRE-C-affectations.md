# ANNUAIRE-C — Affectations user ↔ segment (ANN-09 … 13, ANN-16)

**Produit :** YAS Connect uniquement (pas le SIRH).  
**Préalable :** **ANNUAIRE-B** (segments existent) + **AUTH-D** / **ADMIN-A** (création compte pose déjà `users.segment_id`).  
**Attributs :** [Annuaire](../../catalogues/ANNUAIRE-catalogue-tables.md) (`user_segments`) · [IAM](../../catalogues/IAM-catalogue-tables.md) (`users.segment_id`).  
**Models :** [code/annuaire_models.py](../code/annuaire_models.py) · [code/iam_models.py](../code/iam_models.py).

**Périmètre :** historique RH, sync de la copie courante IAM, validation FK org (région + segment) réutilisée par AUTH-D / ADMIN-A.

`users.job_title` (IAM) ≠ `user_segments.position` (poste dans l’unité).

---

## Cartographie


| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **ANN-09** | **Gardé** | `GET /admin/users/{id}/segments` historique | lecture |
| **ANN-10** | **Gardé** | `POST` nouvelle affectation (mutation si déjà une ouverte) | `user_segments` + sync |
| **ANN-11** | **Gardé** | `PATCH /admin/user-segments/{id}` | dates, position, `is_active` |
| **ANN-12** | **Gardé** | Clôturer (`PATCH end_date`) ou DELETE (correction) | + sync |
| **ANN-13** | **Gardé** | Service `sync_users_segment_id` après chaque write | `users.segment_id` |
| **ANN-16** | **Gardé** | `validate_org_fk(region_id, segment_id)` | — (lecture) |


**Hors incrément :** PATCH `users.segment_id` par le collaborateur, multi-affectations **ouvertes** simultanées, import masse RH.

---

## Décisions figées


| Sujet | Choix |
|-------|--------|
| Double couche | Courant = `users.segment_id` (profil, CONTACTS, picker). Historique = `user_segments` |
| Une ouverte | Au plus **une** ligne `end_date=NULL` et `is_active=true` par user |
| Mutation | POST ouverte **clôture** l’ancienne (`end_date=now()`, `is_active=false`) puis insère. Pas de 409 chevauchement |
| Sync (ANN-13) | Ouverte la plus récente → copie `users.segment_id`. Plus aucune ouverte → `NULL` |
| Création compte | Dès cet incrément : AUTH-D D02/D03 et ADMIN-A ADM-02 appellent `open_assignment` (plus seulement la colonne IAM). `assigned_by` = admin (ADM-02) ou **NULL** (self-register) |
| Comptes déjà créés | Pas de backfill auto. RH pose une affectation si l’historique manque |
| Dates | `start_date` ≤ `end_date` si `end_date` posé. Sinon **400** `ASSIGNMENT_DATE_INVALID` |
| Segment cible | Doit exister et `is_active=true` → **400** `SEGMENT_INVALID` |
| `assigned_by` | Toujours `request.user` sur les vues admin. Non patchable |
| `user_id` | Non patchable (DELETE + POST) |
| Portes | Admin : pas de CGU. Self : **interdit** (pas de `/me/segments`) |
| Audit | `USER_SEGMENT_CREATE` / `UPDATE` / `CLOSE` / `DELETE` |

---

## ANN-13 — Sync

```
def sync_users_segment_id(user):
    row = user_segments.filter(user=user, is_active=True, end_date__isnull=True)
         .order_by("-start_date").first()
    user.segment_id = row.segment_id if row else None
    user.save(update_fields=["segment_id", "updated_at"])
```

Appelé **dans la même transaction** que tout write `user_segments`.

`open_assignment(user, segment, *, assigned_by, start_date=now, position="", position_description="")` : clôture ouverte → INSERT → sync.

---

## ANN-16 — FK org

Utilisé par AUTH-D, ADMIN-A create, POST/PATCH affectation.

| Champ | Règle | Erreur |
|-------|--------|--------|
| `region_id` | UUID existant, `region.is_active=true` | **400** `REGION_INVALID` |
| `segment_id` | UUID existant, `segments.is_active=true` | **400** `SEGMENT_INVALID` |

Les deux restent **obligatoires** à l’inscription / create RH (inchangé AUTH-D / ADMIN-A).

---

## Contrat HTTP

Préfixe `/api/v1`. JWT.

| Méthode | Chemin | Perm |
|---------|--------|------|
| GET | `/admin/users/{user_id}/segments` | `annuaire.user_segment.read` |
| POST | `/admin/users/{user_id}/segments` | `annuaire.user_segment.manage` |
| GET | `/admin/user-segments/{id}` | `annuaire.user_segment.read` |
| PATCH | `/admin/user-segments/{id}` | `annuaire.user_segment.manage` |
| DELETE | `/admin/user-segments/{id}` | `annuaire.user_segment.manage` |

User inconnu → **404** (comme ADM-01).

### ANN-09 — liste

Query `include_closed` défaut `true`. Tri `-start_date`.  
Carte : `id`, `segment` `{id,code,name}`, `start_date`, `end_date`, `is_active`, `position`, `position_description`, `assigned_by` mini-user ou null.

### ANN-10 — POST

```json
{
  "segment_id": "<uuid>",
  "start_date": "2026-09-01T00:00:00Z",
  "end_date": null,
  "position": "Chef équipe",
  "position_description": ""
}
```

`start_date` défaut = now. `end_date` omis = ouverte (mutation).  
Si `end_date` fourni (affectation déjà close, saisie rétro) : **pas** de clôture d’une ouverte existante ; **pas** de sync si une autre reste ouverte.  
**201** ligne. Audit `USER_SEGMENT_CREATE` (+ `CLOSE` de l’ancienne si mutation).

### ANN-11 / 12 — PATCH / DELETE

PATCH whitelist : `segment_id`, `start_date`, `end_date`, `position`, `position_description`, `is_active`.  
Clôturer : `{ "end_date": "<iso>", "is_active": false }`. Puis sync. Audit `USER_SEGMENT_CLOSE` si passage ouvert → fermé.

DELETE : suppression physique (correction). Puis sync. **204**. Audit `USER_SEGMENT_DELETE`.

---

## 1. Fichiers

```
apps/annuaire/services/assignment.py   # open_assignment, sync, validate_org_fk
apps/annuaire/views_admin_assignments.py
```

AUTH-D D02/D03 et ADMIN-A ADM-02 : après INSERT user, `open_assignment(...)` dans la même transaction.

---

## 2. Tests (acceptation)


| ID | Cas | Attendu |
|----|-----|---------|
| 09 | historique 2 lignes | 200 ; tri |
| 10 | POST ouverte alors qu’une ouverte existe | ancienne `end_date` posé ; `users.segment_id` = nouveau |
| 10 | segment inactif | 400 `SEGMENT_INVALID` |
| 11 | `end_date` < `start_date` | 400 `ASSIGNMENT_DATE_INVALID` |
| 12 | DELETE dernière ouverte | `users.segment_id` NULL |
| 13 | AUTH-D register (hook) | 1 `user_segments` ouverte + `users.segment_id` |
| 16 | region inconnue à ADM-02 | 400 `REGION_INVALID` |
| — | jean GET `/admin/users/…/segments` | 403 |


---

## Critères d’acceptation

- [ ] Une affectation ouverte max ; mutation clôture l’ancienne
- [ ] `users.segment_id` toujours aligné (ANN-13)
- [ ] AUTH-D / ADMIN-A créent l’historique
- [ ] ANN-16 partagé
- [ ] Pas de self-service affectation
- [ ] Spec seulement

---

## Écarts documents liés

- **Catalogue Annuaire** : règle d’écriture déjà posée ; ce plan la contracte en HTTP.
- **AUTH-D / ADMIN-A** : delta — appeler `open_assignment` (plus seulement `users.segment_id`).
- **PROF-A / PROF-C** : CONTACTS suit `users.segment_id` après sync.
- **ANNUAIRE-B** : DELETE segment 409 si `user_segments`.
