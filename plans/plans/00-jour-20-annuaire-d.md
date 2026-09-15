# Jour 20 — ANNUAIRE-D (compétences / certifications)

**Statut :** clos (2026-09-15).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–19 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 19](00-jour-19-annuaire-c.md)).  
`UserSkill` / `UserCertification` **déjà** créés (AUTH-A, 5 tables annuaire), 0 ligne. Perms self `annuaire.skill.read/manage`, `annuaire.certification.read/manage` **déjà** accordées à USER (`SELF_PERMISSION_CODES`). Perms admin `annuaire.user_skill.read/manage`, `annuaire.user_certification.read/manage` **déjà** accordées à ADMIN (`ADMIN_PERMISSION_CODES`). Table `media_files` existe (AUTH-A) — upload réel = MEDIA-A (jour 22).

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §3 — *déclarer ses compétences / certifications*) :


| Fonction MVP                     | Ticket         | Statut             |
| -------------------------------- | -------------- | ------------------ |
| Organigramme (types + arbre)     | ANNUAIRE-B     | **fait** (jour 18) |
| Mutations / affectations         | ANNUAIRE-C     | **fait** (jour 19) |
| **Compétences / certifications** | **ANNUAIRE-D** | **ce jour**        |


**À quoi ça sert (MVP) :** un collaborateur déclare lui-même ses compétences (« Fibre optique », niveau 4) et ses certifications (« CCNA », avec éventuellement un justificatif déjà uploadé) — pour que l'équipe sache qui sait faire quoi. Un admin peut aussi le faire pour n'importe quel user (onboarding RH, correction). C'est la **dernière** brique du chapitre Annuaire (§3) avant de passer aux briques transverses (crypto, media, notif).

**Plan métier (code à coller) :** [ANNUAIRE-D-competences-certifications.md](annuaire_plans/ANNUAIRE-D-competences-certifications.md) (ANN-14, 15, 17, 18).  
Chemins lab = ce fichier (`services/competences.py`, `views/competences.py`, `urls/me_competences.py`, `urls/admin_competences.py`).

**Déjà en base / code :**

- `UserSkill` (`skill_name`, `level`, `user`) et `UserCertification` (`certification_name`, `issued_at`, `document` FK `media.MediaFile`, `user`) : modèles complets depuis AUTH-A. 0 ligne.
- Perms self `annuaire.skill.read`, `annuaire.skill.manage`, `annuaire.certification.read`, `annuaire.certification.manage` : déjà dans `rbac_catalog._SELF` → USER les a via `ensure_system_matrix`.
- Perms admin `annuaire.user_skill.read`, `annuaire.user_skill.manage`, `annuaire.user_certification.read`, `annuaire.user_certification.manage` : déjà dans `rbac_catalog._ADMIN` → ADMIN les a.
- `MediaFile.ScanStatus.CLEAN` / `.SKIPPED` ([apps/media/services/avatar_service.py](../../apps/media/services/avatar_service.py) `_VISIBLE`) : déjà le pattern de statuts « visibles » à réutiliser pour valider `document_id`.
- Portes AUTH-F (`ComplianceGates`) : déjà globales sur tout `/api/v1/*` hors allowlist — `/me/skills` et `/me/certifications` hériteront automatiquement de la porte CGU/wizard, **aucune config à ajouter**. Les routes `/admin/`* restent hors porte (déjà allowlistées).

**Pas encore :** `GET`/`POST`/`PATCH`/`DELETE /me/skills(/{id})` et `/me/certifications(/{id})` ; mêmes verbes côté admin sous `/admin/users/{id}/skills` + `/admin/user-skills/{id}` et équivalent certifs.

**Objectif du jour :**

1. `apps/annuaire/services/competences.py` : CRUD skills (`SKILL_TAKEN` UK `(user, skill_name)`, `SKILL_LEVEL_INVALID` hors 1–5, `SKILL_LIMIT` à 50) + CRUD certifications (`CERT_DATE_INVALID` si `issued_at` futur, `CERT_LIMIT` à 30, `CERT_DOCUMENT_INVALID` si `document_id` invalide/owner faux/scan pas CLEAN ou SKIPPED). Audit `USER_SKILL_*` / `USER_CERTIFICATION_*`.
2. Vues self `/me/skills(/{id})`, `/me/certifications(/{id})` : `user = request.user`, ligne d'autrui → **404** (pas 403, ne pas confirmer l'existence).
3. Vues admin `/admin/users/{id}/skills`, `/admin/user-skills/{id}`, `/admin/users/{id}/certifications`, `/admin/user-certifications/{id}` : `user` = cible de l'URL, `owner` du document = la cible (pas l'admin).
4. Ne rien casser : avatar (`/me/avatar`), directory, picker, organigramme (ANNUAIRE-B), affectations (ANNUAIRE-C).

**Hors jour 20 :** recherche experts par skill/certif (index GIN déjà prêt, pas d'API), workflow de validation RH d'une compétence déclarée, upload binaire dans cet incrément (`document_id` référence un `media_files` **déjà créé** — l'upload réel arrive à MEDIA-A, jour 22).

---



## Pourquoi ce jour (après ANNUAIRE-C)

Skills/certifs sont **indépendants** de l'arbre (ANNUAIRE-B) et des affectations (ANNUAIRE-C) — ils auraient pu être faits n'importe quand après AUTH-R/PROF-A. Ils ferment ici le chapitre Annuaire (§3) proprement avant de basculer sur les briques transverses (CRYPTO-00, MEDIA-A, NOTIF-A) qui débloquent la messagerie.

```text
JWT + HasPermission + portes AUTH-F (self, comme tout /me/*)
    GET/POST   /me/skills                      annuaire.skill.read / manage
    GET/PATCH/DELETE /me/skills/{id}            annuaire.skill.read / manage
    GET/POST   /me/certifications               annuaire.certification.read / manage
    GET/PATCH/DELETE /me/certifications/{id}    annuaire.certification.read / manage

JWT + HasPermission (pas de porte CGU/wizard — vues admin, comme ADMIN-A/ANNUAIRE-B/C)
    GET/POST   /admin/users/{id}/skills             annuaire.user_skill.read / manage
    GET/PATCH/DELETE /admin/user-skills/{id}        annuaire.user_skill.read / manage
    GET/POST   /admin/users/{id}/certifications     annuaire.user_certification.read / manage
    GET/PATCH/DELETE /admin/user-certifications/{id} annuaire.user_certification.read / manage

Déjà là (ne pas casser)
    CRUD /admin/segment-types|segments|tree     ANNUAIRE-B (jour 18)
    CRUD /admin/users/{id}/segments             ANNUAIRE-C (jour 19)
    GET /me/avatar, /me/preferences, /me/privacy  PROF-A/B/C
```

---



## Paliers (figés pour ce jour)


| Sujet         | Choix jour 20                                                                                                                                                              | Plus tard |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| Self-service  | **Oui**, catalogue « User / RH » déjà tranché. Routes `/me/skills` et `/me/certifications`                                                                                 | —         |
| Admin         | Peut CRUD les lignes de **n'importe quel** user. Perms distinctes (`user_skill`/`user_certification` vs `skill`/`certification`)                                           | —         |
| UK skill      | `(user_id, skill_name)` — **409** `SKILL_TAKEN` (case-insensitive trim ; stocké tel que saisi après trim)                                                                  | —         |
| `level`       | Entier **1–5**. 0 ou hors plage → **400** `SKILL_LEVEL_INVALID`. Défaut POST = `1`                                                                                         | —         |
| Certif        | **Pas** d'UK sur le nom — plusieurs « CCNA » possibles (renouvellement)                                                                                                    | —         |
| `document_id` | Optionnel. Si posé : `media_files` doit exister, `owner_id` = **le user cible** (self ou admin), `scan_status` ∈ {`CLEAN`,`SKIPPED`}, `media_type` = `DOCUMENT` sinon **400** `CERT_DOCUMENT_INVALID` | —         |
| Self vs admin | Self : `user` = `request.user`. Id d'une ligne d'autrui → **404** (pas de 403 qui confirme l'existence)                                                                    | —         |
| Portes AUTH-F | Self **après** CGU/wizard (automatique, `ComplianceGates` global). Admin : pas de porte                                                                                    | —         |
| Limites       | `SKILL_LIMIT` 50 lignes / user. `CERT_LIMIT` 30 lignes / user                                                                                                              | —         |
| Date certif   | `issued_at` optionnelle, pas dans le futur → **400** `CERT_DATE_INVALID`                                                                                                   | —         |
| DELETE        | Suppression physique. Fichier média **conservé** (comme avatar PROF-04)                                                                                                    | —         |
| Audit         | `module=ANNUAIRE` ; `USER_SKILL_CREATE/UPDATE/DELETE`, `USER_CERTIFICATION_CREATE/UPDATE/DELETE`. `user_id` = l'acteur réel (self ou admin)                                | —         |
| PATCH         | Whitelist. Skill : `skill_name`, `level`. Certif : `certification_name`, `issued_at`, `document_id`                                                                        | —         |


Perms déjà seedées (jour 11) : self `annuaire.skill.*`/`annuaire.certification.*` (USER) ; admin `annuaire.user_skill.*`/`annuaire.user_certification.*` (ADMIN).

---



## 1. Tables

**0 migration.** `user_skills` / `user_certifications` existent depuis AUTH-A (5 tables annuaire), 0 ligne jusqu'ici.  
**Interdit :** `docker compose down -v`.

---



## 2. HTTP


| Fichier                                    | Rôle                                                                              |
| ------------------------------------------ | --------------------------------------------------------------------------------- |
| `apps/annuaire/services/competences.py`    | **nouveau.** CRUD skills + certifs, self et admin, `CERT_DOCUMENT_INVALID`, audit |
| `apps/annuaire/views/competences.py`       | **nouveau.** vues self + admin, service partagé, `user` fixé par la vue           |
| `apps/annuaire/serializers/competences.py` | **nouveau.** shape DRF (POST/PATCH)                                               |
| `apps/annuaire/urls/me_competences.py`     | **nouveau.** monté sous `/api/v1/me/` (`config/urls.py` : 2ᵉ `include()`)         |
| `apps/annuaire/urls/admin_competences.py`  | **nouveau.** monté sous `/api/v1/admin/` (`config/urls.py` : 4ᵉ `include()`)      |
| `apps/iam/tests/test_annuaire_d.py`        | **nouveau.**                                                                      |




### Self


| Méthode            | Chemin                           | Perm                                      |
| ------------------ | -------------------------------- | ----------------------------------------- |
| GET, POST          | `/api/v1/me/skills`              | `annuaire.skill.read` / `.manage`         |
| GET, PATCH, DELETE | `/api/v1/me/skills/{id}`         | `annuaire.skill.read` / `.manage`         |
| GET, POST          | `/api/v1/me/certifications`      | `annuaire.certification.read` / `.manage` |
| GET, PATCH, DELETE | `/api/v1/me/certifications/{id}` | `annuaire.certification.read` / `.manage` |




### Admin


| Méthode            | Chemin                                         | Perm                                           |
| ------------------ | ---------------------------------------------- | ---------------------------------------------- |
| GET, POST          | `/api/v1/admin/users/{user_id}/skills`         | `annuaire.user_skill.read` / `.manage`         |
| GET, PATCH, DELETE | `/api/v1/admin/user-skills/{id}`               | `annuaire.user_skill.read` / `.manage`         |
| GET, POST          | `/api/v1/admin/users/{user_id}/certifications` | `annuaire.user_certification.read` / `.manage` |
| GET, PATCH, DELETE | `/api/v1/admin/user-certifications/{id}`       | `annuaire.user_certification.read` / `.manage` |


**POST skill** `{ "skill_name": "Fibre", "level": 4 }` → **201** `{ "id", "skill_name", "level" }`.  
**GET liste skills** : tri `skill_name`. Pas de pagination (volume faible) ; au-delà de 50 → **400** `SKILL_LIMIT`.

**POST certif** `{ "certification_name": "CCNA", "issued_at": "2024-06-01", "document_id": null }`.  
Carte : + `document` `{ id, url? }` si scan OK, sinon `document_id` seul. Au-delà de 30 → **400** `CERT_LIMIT`.

**400** `SKILL_LEVEL_INVALID` / `SKILL_LIMIT` / `CERT_DATE_INVALID` / `CERT_LIMIT` / `CERT_DOCUMENT_INVALID` / `VALIDATION_ERROR`.  
**409** `SKILL_TAKEN`. **404** ligne d'autrui en self. **401** sans JWT. **403** `FORBIDDEN` sans la perm / `TOS_REQUIRED` / `ONBOARDING_REQUIRED` (self uniquement).

---



## 3. Impact tests existants


| Fichier                                     | Adapter                                                                                                                                     |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_prof_a.py`                            | Avatar (`/me/avatar`) inchangé ; `document` d'une certif est un `MediaFile` distinct de l'avatar, pas de collision                          |
| `test_annuaire_b.py` / `test_annuaire_c.py` | CRUD segments / affectations inchangés ; aucune route ne collisionne (`skills`/`certifications` ≠ `segments`)                               |
| `test_auth_f.py` (portes)                   | `/me/skills` et `/me/certifications` doivent suivre la même règle TOS/onboarding que les autres `/me/*` (pas de régression sur l'allowlist) |


---



## 4. Tests nouveaux (`test_annuaire_d.py`)


| ID  | Cas                                               | Attendu                                                                  |
| --- | ------------------------------------------------- | ------------------------------------------------------------------------ |
| 17  | jean POST `skill_name=Fibre level=4`              | 201 ; `GET /me/skills` liste 1                                           |
| 17  | POST `Fibre` une 2ᵉ fois                          | 409 `SKILL_TAKEN`                                                        |
| 17  | `level=9`                                         | 400 `SKILL_LEVEL_INVALID`                                                |
| 17  | PATCH skill d'un autre user (id trouvé par admin) | self → 404                                                               |
| 17  | 51ᵉ skill                                         | 400 `SKILL_LIMIT`                                                        |
| 14  | admin POST skill sur marie                        | 201                                                                      |
| 14  | jean (pas admin) GET `/admin/users/{id}/skills`   | 403 `FORBIDDEN`                                                          |
| 18  | `document_id` d'un autre owner                    | 400 `CERT_DOCUMENT_INVALID`                                              |
| 18  | `document_id` scan `PENDING`                      | 400 `CERT_DOCUMENT_INVALID`                                              |
| 18  | `issued_at` demain                                | 400 `CERT_DATE_INVALID`                                                  |
| 18  | DELETE certif                                     | 204 ; `MediaFile` référencé conservé                                     |
| 15  | admin GET certifs de jean                         | 200                                                                      |
| —   | self sans CGU                                     | 403 `TOS_REQUIRED`                                                       |
| —   | sans JWT                                          | 401                                                                      |
| —   | `/api/schema/`                                    | contient `/api/v1/me/skills` et `/api/v1/admin/user-certifications/{id}` |


Helper MFA : `login_until_jwt`. Fixture `admin` : rôle `ADMIN` (comme `test_admin_a.py`).

---



## 5. Vérif manuelle

```powershell
python manage.py check
pytest apps/iam/tests/test_annuaire_d.py apps/iam/tests/test_prof_a.py apps/iam/tests/test_annuaire_b.py apps/iam/tests/test_annuaire_c.py --reuse-db
```

Login jean → `POST /api/v1/me/skills {"skill_name": "Fibre", "level": 4}` → `GET /api/v1/me/skills` → la ligne apparaît. Login admin → `GET /api/v1/admin/users/{jean.id}/skills` → même ligne visible côté admin.

---



## Checklist jour 20

- [x] CRUD self `/me/skills` + `/me/certifications`
- [x] CRUD admin `/admin/users/{id}/skills` + `/admin/users/{id}/certifications` + détails
- [x] `SKILL_TAKEN` / `SKILL_LEVEL_INVALID` / `SKILL_LIMIT`
- [x] `CERT_DATE_INVALID` / `CERT_LIMIT` / `CERT_DOCUMENT_INVALID` (+ `media_type` = `DOCUMENT`)
- [x] Self → 404 sur ligne d'autrui ; portes AUTH-F héritées automatiquement
- [x] Audit `USER_SKILL_*` / `USER_CERTIFICATION_*`
- [x] `test_annuaire_d.py` + régression PROF-A / ANNUAIRE-B / ANNUAIRE-C
- [x] 0 migration ; 0 `docker compose down -v`
- [x] SIRH non modifié

---



## Interdits

- Recherche experts par skill/certif (index GIN prêt, pas d'API ce jour)
- Workflow de validation RH d'une compétence déclarée
- Upload binaire dans cet incrément (référencer un `document_id` déjà créé seulement)
- Recoder `resolve_org` / directory public / picker / CRUD segments / affectations
- `docker compose down -v`
- Changer le SIRH

---



## Après le jour 20

Chapitre **Annuaire (§3) fermé**. Jour 21 : [00-jour-21-crypto-00.md](00-jour-21-crypto-00.md) — **CRYPTO-00** (revue de clôture du modèle de chiffrement, 0 code, 0 table).

---



## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour**. Le jour 2 (admin + Swagger) est un extra déjà clos.


| Jours  | Plan                                           | Ticket MVP                            |
| ------ | ---------------------------------------------- | ------------------------------------- |
| 0      | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health`   |
| 1–2    | AUTH-A ; admin + Swagger                       | Connexion locale ; lab admin          |
| 3–11   | D+B … AUTH-R                                   | §1 entrer + droits HTTP               |
| 12     | ADMIN-A                                        | §9 comptes                            |
| 13     | PROF-A                                         | §2 ma fiche / photo                   |
| 14     | PROF-B                                         | Préférences                           |
| 15     | PROF-C                                         | §2 visibilité                         |
| 16     | PRES-A                                         | §2 statut en ligne                    |
| 17     | ANNUAIRE-A                                     | §3 recherche collègue                 |
| 18     | ANNUAIRE-B                                     | §3 organigramme (types + arbre)       |
| 19     | ANNUAIRE-C                                     | §3 mutations / affectations           |
| **20** | **ANNUAIRE-D** (ce plan)                       | §3 compétences / certifications       |
| 21     | CRYPTO-00                                      | §6 décision E2E                       |
| 22     | MEDIA-R + MEDIA-A                              | §4 upload (plafonds ; pas de reprise) |
| 23     | NOTIF-R + NOTIF-A                              | §5 alertes + MOB-PUSH (VoIP / worker) |
| 24     | CRYPTO-R + CRYPTO-A                            | Clés HTTP                             |
| 25     | MESSAGERIE-R, A, B                             | §7 1-to-1                             |
| 26     | MESSAGERIE-C, D                                | §7 groupes + temps réel               |
| 27     | MESSAGERIE-E (partiel), F, G                   | §7 enrichissements                    |
| 28     | MEDIA-B, C, D, E                               | §4 album / vocal / coffre             |
| 29     | APPELS-R, A, B, C                              | §8 appel 1-1 + `CALL_CANCELLED`       |
| 30     | APPELS-D, E, G                                 | §8 écran / CR                         |


**Total : 31 plans (jours 0 à 30).**  
Déjà clos : **20** (0–19). Restant : **11** (20–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.