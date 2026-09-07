# ANNUAIRE-D — Compétences & certifications (ANN-14, 15, 17, 18)

**Produit :** YAS Connect uniquement (pas le SIRH).  
**Préalable :** **AUTH-R** (perms `annuaire.skill*` / `annuaire.user_skill*` / certifs) + **PROF-A** (portes AUTH-F pour le self) + table `media_files`.  
**Attributs :** [Annuaire](../../catalogues/ANNUAIRE-catalogue-tables.md) · [Médias](../../catalogues/MEDIA-catalogue-tables.md) (`document_id`).  
**Models :** [code/annuaire_models.py](../code/annuaire_models.py).

**Périmètre :** CRUD compétences et certifications, **admin** (n’importe quel user) **et self-service** (`/me/…`). Catalogue : « User / RH ».

Recherche experts par `skill_name` / certif (index GIN déjà là) : **hors incrément**.

---

## Cartographie


| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **ANN-14** | **Gardé** | CRUD admin `/admin/users/{id}/skills` + `/admin/user-skills/{id}` | `user_skills` |
| **ANN-15** | **Gardé** | CRUD admin certifications | `user_certifications` |
| **ANN-17** | **Gardé** | Self `/me/skills` | `user_skills` |
| **ANN-18** | **Gardé** | Self `/me/certifications` | `user_certifications` |


**Hors incrément :** people-picker filtré par skill, workflow validation RH d’une skill user, upload binaire dans cet incrément (l’upload fichier = module Médias ; ici on **référence** un `document_id` déjà créé).

---

## Décisions figées


| Sujet | Choix |
|-------|--------|
| Self-service | **Oui** (catalogue User/RH). Routes `/me/skills` et `/me/certifications` |
| Admin | Peut CRUD les lignes de **n’importe quel** user. Perms distinctes (`user_skill` vs `skill`) |
| UK skill | `(user_id, skill_name)` — **409** `SKILL_TAKEN` (case-insensitive trim ; stocker tel que saisi après trim) |
| `level` | Entier **1–5**. 0 ou hors plage → **400** `SKILL_LEVEL_INVALID`. Défaut POST = `1` |
| Certif | Pas d’UK nom. Plusieurs « CCNA » possibles (renouvellement) |
| `document_id` | Optionnel. Si posé : `media_files` existe, `owner_id` = **le user cible**, `scan_status` ∈ {`CLEAN`,`SKIPPED`} sinon **400** `CERT_DOCUMENT_INVALID` |
| Self vs admin | Self : `user` = `request.user`. Id d’une ligne d’autrui → **404** (pas de 403 qui confirme) |
| Portes AUTH-F | Self **après** CGU/wizard. Admin : pas de porte |
| Audit | `USER_SKILL_*` / `USER_CERTIFICATION_*`. Self et admin même action, `user_id` = acteur |
| PATCH | Whitelist. Skill : `skill_name`, `level`. Certif : `certification_name`, `issued_at`, `document_id` |

---

## Contrat HTTP

Préfixe `/api/v1`. JWT.

### ANN-17 / 14 — skills

| Méthode | Chemin | Perm | Acteur |
|---------|--------|------|--------|
| GET | `/me/skills` | `annuaire.skill.read` | Collaborateur |
| POST | `/me/skills` | `annuaire.skill.manage` | Collaborateur |
| PATCH | `/me/skills/{id}` | `annuaire.skill.manage` | Collaborateur |
| DELETE | `/me/skills/{id}` | `annuaire.skill.manage` | Collaborateur |
| GET | `/admin/users/{user_id}/skills` | `annuaire.user_skill.read` | Admin |
| POST | `/admin/users/{user_id}/skills` | `annuaire.user_skill.manage` | Admin |
| PATCH | `/admin/user-skills/{id}` | `annuaire.user_skill.manage` | Admin |
| DELETE | `/admin/user-skills/{id}` | `annuaire.user_skill.manage` | Admin |

POST `{ "skill_name": "Fibre", "level": 4 }`  
**201** `{ "id", "skill_name", "level" }`.  
GET liste : tri `skill_name`. Pas de pagination (volume faible) ; max **50** lignes / user — au-delà POST **400** `SKILL_LIMIT`.

### ANN-18 / 15 — certifications

| Méthode | Chemin | Perm | Acteur |
|---------|--------|------|--------|
| GET | `/me/certifications` | `annuaire.certification.read` | Collaborateur |
| POST | `/me/certifications` | `annuaire.certification.manage` | Collaborateur |
| PATCH | `/me/certifications/{id}` | `annuaire.certification.manage` | Collaborateur |
| DELETE | `/me/certifications/{id}` | `annuaire.certification.manage` | Collaborateur |
| GET | `/admin/users/{user_id}/certifications` | `annuaire.user_certification.read` | Admin |
| POST | `/admin/users/{user_id}/certifications` | `annuaire.user_certification.manage` | Admin |
| PATCH | `/admin/user-certifications/{id}` | `annuaire.user_certification.manage` | Admin |
| DELETE | `/admin/user-certifications/{id}` | `annuaire.user_certification.manage` | Admin |

POST `{ "certification_name": "CCNA", "issued_at": "2024-06-01", "document_id": null }`  
`issued_at` date ISO optionnelle, pas dans le futur → **400** `CERT_DATE_INVALID`.  
Carte : + `document` `{ id, url? }` si scan OK, sinon `document_id` seul.  
Max **30** certifs / user → **400** `CERT_LIMIT`.

DELETE **204**. Fichier média **conservé** (comme avatar PROF-04).

---

## 1. Fichiers

```
apps/annuaire/views_skills.py
apps/annuaire/views_certifications.py
apps/annuaire/services/media_ref.py   # CERT_DOCUMENT_INVALID
```

Self et admin partagent le même serializer ; la vue fixe `user`.

---

## 2. Tests (acceptation)


| ID | Cas | Attendu |
|----|-----|---------|
| 17 | jean POST Fibre level 4 | 201 ; GET liste 1 |
| 17 | POST Fibre 2e fois | 409 `SKILL_TAKEN` |
| 17 | level 9 | 400 `SKILL_LEVEL_INVALID` |
| 17 | PATCH skill d’un autre | 404 |
| 14 | admin POST skill sur marie | 201 |
| 18 | document d’un autre owner | 400 `CERT_DOCUMENT_INVALID` |
| 18 | `issued_at` demain | 400 |
| 15 | jean GET admin certifs | 403 |
| — | self sans CGU | 403 `TOS_REQUIRED` |


---

## Critères d’acceptation

- [ ] Self + admin skills / certifs ; UK skill ; plage level
- [ ] `document_id` owner + scan
- [ ] Pas de recherche expert
- [ ] Seed 4 perms self + 4 admin (voir AUTH-R)
- [ ] Spec seulement

---

## Écarts documents liés

- **Catalogue** : « User / RH » → self-service **figé ici** (lacune fermée).
- **Médias** : upload hors incrément ; référence seulement.
- **ANNUAIRE-A** : picker **ne** filtre **pas** sur skill.
- **AUTH-R** : `annuaire.skill.*` / `certification.*` (self) et `annuaire.user_skill.*` / `user_certification.*` (admin).
