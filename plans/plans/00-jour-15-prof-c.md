# Jour 15 — PROF-C (confidentialité / écriture masques)

**Statut :** à faire.  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–14 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 14](00-jour-14-prof-b.md)).  
Lecture collègue **déjà** masquée (PROF-A). Prefs **déjà** distinctes (PROF-B). Perms `iam.privacy.read` / `iam.privacy.update` **déjà** seedées (jour 11). Ligne `privacy_settings` 1-1 **déjà** à `create_user`.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §2 — *visibilité*) :


| Fonction MVP                       | Ticket   | Statut                                     |
| ---------------------------------- | -------- | ------------------------------------------ |
| Ma fiche / photo / prefs           | PROF-A/B | **fait** (jours 13–14)                     |
| **Écrire ses masques confidentialité** | **PROF-C** | **ce jour**                            |
| Statut en ligne / last_seen live   | PRES-A   | [jour 16](00-jour-16-pres-a.md)            |


**À quoi ça sert (MVP) :** marie pose photo / last seen / online en `NOBODY` ; jean ouvre sa fiche : `avatar_url` / `last_seen` / `status` à `null`. Les booléens `allow_*` et `*_enabled` sont stockés pour le chat / les appels plus tard.

**Plan métier (code à coller) :** [PROF-C-confidentialite.md](iam_plans/PROF-C-confidentialite.md) (PROF-23 … 30).  
Chemins lab = ce fichier (`views/privacy.py`, `services/privacy_service.py` — **pas** `views_privacy.py` à la racine IAM).

**Déjà en base / code :**

- `PrivacySetting` : 3 visibilités `EVERYONE` / `CONTACTS` / `NOBODY` + 5 booléens
- `GET /me` : bloc `privacy` **lu** (AUTH-F / PROF-A) ; soi **non** masqué
- `GET /users/{id}` : masque 23–25 déjà (photo / last_seen / status) ; **pas** de fiche privacy du cible
- CONTACTS = même `segment_id` non NULL (sinon = NOBODY)
- Prefs `read_receipts` / `typing_indicator` ≠ colonnes `*_enabled`
- USER a déjà `iam.privacy.read` / `update`

**Pas encore :** `GET/PATCH /api/v1/me/privacy`.

**Objectif du jour :**

1. `GET /api/v1/me/privacy` : 8 champs + `updated_at`.
2. `PATCH /api/v1/me/privacy` partiel ≥ 1 clé ; effet **immédiat** 23–25 sur `GET /users/{id}`.
3. Visibilité hors enum → 400 `INVALID_VISIBILITY`. Clé inconnue / clé prefs (`read_receipts`) → 400 `UNKNOWN_FIELD`.
4. 26–27 n’écrivent **pas** les souhaits PROF-B. 28–30 persistés seulement (pas d’enforcement appel / mention / groupe).
5. **Garder** le bloc `privacy` sur `GET /me` (déjà jour 13 — ne **pas** le retirer).

**Hors jour 15 :** PRES-A (Redis / WS `USER_STATUS_CHANGED`), moteur chat / appels / invitations, graphe d’amis, PATCH privacy d’un **autre**, admin override, recoder PROF-A masque / PROF-B prefs.

---



## Pourquoi ce jour (après PROF-B)

Les masques sont **lus** depuis le jour 13, mais marie ne peut pas les **changer** en HTTP (seulement SQL / Django admin). Le MVP §2 demande l’écran confidentialité **derrière JWT + perm**. Les codes sont seedés depuis le jour 11.

```text
JWT + HasPermission + portes AUTH-F (après CGU + wizard)
    GET    /me/privacy                 iam.privacy.read
    PATCH  /me/privacy                 iam.privacy.update

Déjà là (ne pas casser)
    GET /me (+ bloc privacy lu, soi non masqué)
    GET /users/{id} masque 23–25
    GET/PATCH /me/preferences (souhait ≠ *_enabled)
```

---



## Paliers (figés pour ce jour)


| Sujet | Choix jour 15 | Plus tard |
| ----- | ------------- | --------- |
| Bloc `privacy` sur `GET /me` | **Garder** (déjà AUTH-F / PROF-A). Ticket « pas dans `/me` » = l’**écran** écrit via `/me/privacy`, pas un strip | — |
| Masque collègue | **Inchangé** (`profile_service.serialize_colleague`). Pas d’extraction obligatoire vers `privacy_service` | — |
| Enum | `EVERYONE` \| `CONTACTS` \| `NOBODY` **exact** (casse). `everyone` → 400 `INVALID_VISIBILITY` | — |
| CONTACTS | Même règle PROF-A (segment non NULL et égal) | graphe amis |
| Clé prefs `read_receipts` | 400 `UNKNOWN_FIELD` (utiliser `/me/preferences`) | — |
| Booléens | JSON `true`/`false` seulement (`"0"` → 400 `VALIDATION_ERROR`) | — |
| Portes AUTH-F | GET/PATCH `/me/privacy` **après** CGU + wizard | — |
| Audit | `PRIVACY_PATCH` (lab : oui, comme `PREFS_PATCH`) | — |
| 26–30 | Stockage seulement | messaging / appels / groupes |
| Login JSON | `public_user` **inchangé** | — |
| Fuite | `GET /users/{id}` **sans** fiche privacy du cible (déjà) | — |


Perms déjà seedées : `iam.privacy.read` / `iam.privacy.update` (self USER).

---



## 1. Tables

**0 migration.** `privacy_settings` existe, 1-1 à `create_user`.  
**Interdit :** `docker compose down -v`.

`audit_logs.action` : `PRIVACY_PATCH`.

---



## 2. Settings + seed

Pas de nouvelle clé `.env`. Pas de `seed_config` nouveau.  
Tests : poser les visibilités en PATCH HTTP (pas besoin de fixture SQL sauf segment / avatar).

---



## 3. Services


| Fichier | Sert à |
| ------- | ------ |
| `apps/iam/services/privacy_service.py` | **nouveau.** serialize, PATCH, get_or_create orphelin |
| `apps/iam/services/profile_service.py` | **inchangé** (masque collègue déjà là) |
| `apps/iam/views/privacy.py` | GET + PATCH `/me/privacy` |
| `public_user` | **inchangé** |


8 champs PATCH :

```text
last_seen_visibility, profile_photo_visibility, online_status_visibility
read_receipts_enabled, typing_indicator_enabled
allow_calls, allow_mentions, allow_group_invites
```

GET ne crée pas (get_or_create orphelin seulement).  
`updated_at` = `privacy_settings.updated_at` (auto_now).

---



## 4. HTTP

Arborescence `views/` / `urls/me.py`. `path("privacy")` **avant** tout catch-all (comme `preferences`).


| Fichier | Rôle |
| ------- | ---- |
| `apps/iam/views/privacy.py` | **nouveau.** GET + PATCH |
| `apps/iam/serializers/privacy.py` | **nouveau.** body PATCH + OpenAPI |
| `apps/iam/urls/me.py` | `privacy` |
| `apps/iam/tests/test_prof_c.py` | **nouveau.** |


| Méthode | Chemin | Perm |
| ------- | ------ | ---- |
| GET | `/api/v1/me/privacy` | `iam.privacy.read` |
| PATCH | `/api/v1/me/privacy` | `iam.privacy.update` |


`MePrivacyView.required_permissions = {"GET": "iam.privacy.read", "PATCH": "iam.privacy.update"}`.

**GET `/me/privacy` 200**

```json
{
  "success": true,
  "data": {
    "last_seen_visibility": "EVERYONE",
    "profile_photo_visibility": "EVERYONE",
    "online_status_visibility": "EVERYONE",
    "read_receipts_enabled": true,
    "typing_indicator_enabled": true,
    "allow_calls": true,
    "allow_mentions": true,
    "allow_group_invites": true,
    "updated_at": "2026-08-27T10:15:00Z"
  }
}
```

**PATCH `/me/privacy`** partiel ≥ 1 clé. **200** = même JSON que GET.  
400 `INVALID_VISIBILITY` / `UNKNOWN_FIELD` / `VALIDATION_ERROR`.

Effet immédiat 23–25 : jean `GET /users/{marie}` après le PATCH de marie.

---



## 5. Impact tests existants


| Fichier | Adapter |
| ------- | ------- |
| `test_prof_a.py` | Masque collègue **encore vrai** (NOBODY / CONTACTS). Ne pas exiger l’absence de `/me/privacy` dans le schéma. |
| `test_prof_b.py` | Prefs `read_receipts` n’écrit toujours pas `*_enabled`. |
| `test_auth_f.py` | GET `/me` bloc `privacy` **reste**. |


GET/PATCH `/me/privacy` : portes fermées (`close_gates`) comme `/me/preferences`.

---



## 6. Tests nouveaux (`test_prof_c.py`)


| ID | Cas | Attendu |
| -- | --- | ------- |
| 23 | PATCH `last_seen_visibility=NOBODY` | collègue `last_seen=null` ; `GET /me` encore renseigné |
| 23 | `CONTACTS`, même `segment_id` | collègue voit last_seen |
| 23 | `CONTACTS`, autre segment | `last_seen=null` |
| 24 | `profile_photo_visibility=NOBODY` | collègue `avatar_url=null` (avatar posé avant) |
| 25 | `online_status_visibility=NOBODY` | collègue `status=null` |
| 23 | typo `everyone` | **400** `INVALID_VISIBILITY` |
| 26 | `read_receipts_enabled=false` | privacy OK ; **prefs** `read_receipts` inchangé |
| 27 | `typing_indicator_enabled=false` | idem typing |
| 28–30 | `allow_calls` / `mentions` / `group_invites=false` | persisté |
| — | PATCH `read_receipts` (clé prefs) | **400** `UNKNOWN_FIELD` |
| — | GET `/me/privacy` avant wizard | **403** TOS puis `ONBOARDING_REQUIRED` |
| — | GET privacy d’un autre | **pas** de route ; `GET /users/{id}` sans fiche privacy |
| — | retirer `iam.privacy.update` | **403** `FORBIDDEN` |
| — | sans JWT | **401** |
| — | `/health`, `/api/docs/` | schéma contient `/me/privacy` |


Helper MFA : `login_until_jwt`. Portes : `close_gates` sauf GET `/me`.  
JPEG avatar : même helper que `test_prof_a.py` (`SimpleUploadedFile`).

Régression : PROF-A (masque lecture) + PROF-B (souhait ≠ `*_enabled`).

---



## 7. Vérif manuelle

```powershell
python manage.py check
pytest apps/iam/tests/test_prof_c.py apps/iam/tests/test_prof_a.py apps/iam/tests/test_prof_b.py --reuse-db
```

`marie` : PATCH `/me/privacy` `profile_photo_visibility=NOBODY`.  
`jean` : GET `/users/{marie}` → `avatar_url` null ; GET `/me` de marie (son JWT) → photo encore visible.  
Compte neuf : GET `/me/privacy` bloqué.  
`/admin/` cookie : **pas** ces routes.

---



## Checklist jour 15

- [ ] GET/PATCH `/me/privacy` (8 champs + `updated_at`)
- [ ] 23–25 effet immédiat collègue ; soi non masqué sur GET `/me`
- [ ] `INVALID_VISIBILITY` / `UNKNOWN_FIELD` (dont clé prefs `read_receipts`)
- [ ] 26–27 ≠ souhaits PROF-B ; 28–30 persistés
- [ ] Bloc `privacy` **conservé** sur GET `/me` ; login inchangé
- [ ] `test_prof_c.py` + régression A/B
- [ ] SIRH non modifié
- [ ] 0 `docker compose down -v`

---



## Interdits

- Recoder PROF-A masque / avatar / org
- Recoder PROF-B prefs / `editable`
- Coder PRES-A / chat / appels / invitations
- PATCH privacy d’un autre user / `GET /users` liste
- Retirer `privacy` de GET `/me`
- `docker compose down -v`
- Changer le SIRH

---



## Après le jour 15

Jour 16 : [00-jour-16-pres-a.md](00-jour-16-pres-a.md) — **PRES-A** (présence Redis + `last_seen` live ; `online_status_visibility` filtre aussi le WS).

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
| **15** | **PROF-C** (ce plan)                           | §2 visibilité                       |
| 16     | PRES-A                                         | §2 statut en ligne                  |
| 17     | ANNUAIRE-A                                     | §3 recherche collègue               |
| 18     | CRYPTO-00                                      | §6 décision E2E                     |
| 19     | MEDIA-R + MEDIA-A                              | §4 upload                           |
| 20     | NOTIF-R + NOTIF-A                              | §5 alertes                          |
| 21     | CRYPTO-R + CRYPTO-A                            | Clés HTTP                           |
| 22     | MESSAGERIE-R, A, B                             | §7 1-to-1                           |
| 23     | MESSAGERIE-C, D                                | §7 groupes + temps réel             |
| 24     | MESSAGERIE-E (partiel), F, G                   | §7 enrichissements                  |
| 25     | MEDIA-B, C, D, E                               | §4 album / vocal / coffre           |
| 26     | APPELS-R, A, B, C                              | §8 appel 1-1                        |
| 27     | APPELS-D, E, G                                 | §8 écran / CR                       |


**Total : 28 plans (jours 0 à 27).**  
Déjà clos : **15** (0–14). Restant : **13** (15–27).

Hors ce compteur (A→Z §4.2) : ANNUAIRE-B/C/D, MEDIA-F, APPELS-F, mentions / modération, social, IA.
