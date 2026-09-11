# Jour 14 — PROF-B (préférences, editable, job_title)

**Statut :** clos (2026-09-11).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–13 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 13](00-jour-13-prof-a.md)).  
**Livré :** `user.editable` ; `job_title` gated ; GET/PATCH `/me/preferences` ; GET onboarding = JSON prefs. 0 migration.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §2 — *Ma fiche / photo*) :


| Fonction MVP                             | Ticket      | Statut                                      |
| ---------------------------------------- | ----------- | ------------------------------------------- |
| Ma fiche, photo, fiche collègue          | PROF-A      | **fait** ([jour 13](00-jour-13-prof-a.md))  |
| **Préférences UI + whitelist job_title** | **PROF-B**  | **fait** (ce jour)                          |
| Confidentialité (écriture masques)       | PROF-C      | [jour 15](00-jour-15-prof-c.md)             |


**À quoi ça sert (MVP) :** jean change langue / fuseau / son depuis Réglages, pas depuis la carte identité. Le client sait quels champs PATCH `/me` accepter (`editable`). Le RH peut un jour autoriser l’auto-édition du poste (`profile.job_title_self_edit`) sans release.

**Plan métier (code à coller) :** [PROF-B-edition-preferences.md](iam_plans/PROF-B-edition-preferences.md) (PROF-15 … 22).  
Chemins lab = ce fichier (`views/prefs.py`, `services/prefs_service.py` — **pas** `views_prefs.py` à la racine IAM).

**Déjà en base / code :**

- `GET /me` : fiche PROF-A (`display_name`, `org`, prefs **lues**, privacy **lues**, **pas** de `role`) + `gates`
- `PATCH /me` : `first_name` / `last_name` / `username` / `phone` ; `job_title` / `language` / matricule → 400 `FIELD_FORBIDDEN`
- `GET /me/onboarding` : 3 champs (`language`, `timezone`, `notification_sound`) ; PATCH wizard écrit les 3 + aligne `users.*`
- `UserPreference` 1-1 (langue, tz, son, `auto_download_media`, `read_receipts`, `typing_indicator`)
- `HasPermission` ; USER a déjà `iam.prefs.read` / `update`

**Livré (code) :** `editable` (`phone` true, `matricule` false, `job_title` flag) ; PATCH `/me` `job_title` si `profile.job_title_self_edit` ; GET/PATCH `/me/preferences` ; GET `/me/onboarding` = 6 champs + `last_updated`. Login `public_user` **inchangé**.

**Objectif du jour (fait) :**

1. `GET /me` : ajouter `user.editable` (6 booléens, dont **`phone`** et **`matricule`**). **Garder** `preferences` + `privacy` (déjà jour 13 — ne **pas** les retirer).
2. `PATCH /me` : `job_title` autorisé **seulement** si `profile.job_title_self_edit=true` ; sinon 400 `FIELD_FORBIDDEN` + `field=job_title`.
3. `GET/PATCH /api/v1/me/preferences` : 6 champs catalogue ; langue `fr`\|`en` ; tz IANA ; aligner `users.language` / `users.timezone`.
4. Wizard : `GET /me/onboarding` = **même** JSON que GET prefs (préremplissage). `PATCH /me/onboarding` **n’écrit toujours que** 3 champs, via le **même** service.
5. Seed `system_settings` `profile.job_title_self_edit=false`.

**Hors jour 14 :** PROF-C (`GET/PATCH /me/privacy`), écran admin HTTP pour le flag (Django `/admin/` SystemSetting suffit), thème dark, PATCH prefs d’un **autre**, i18n fichiers front, PRES-A, ANNUAIRE write, recoder PROF-A avatar / AUTH-R.

---



## Pourquoi ce jour (après PROF-A)

La carte `/me` est assez pour l’écran profil. Il manque l’écran **réglages** (prefs ≠ privacy) et le contrat `editable` pour que le front masque `job_title`. Les codes `iam.prefs.*` sont seedés depuis le jour 11.

```text
JWT + HasPermission + portes AUTH-F (sauf GET /me et GET /me/onboarding déjà allowlist)
    GET    /me                         iam.profile.read     (+ editable)
    PATCH  /me                         iam.profile.update   (+ job_title si flag)
    GET    /me/preferences             iam.prefs.read
    PATCH  /me/preferences             iam.prefs.update
    GET    /me/onboarding              iam.onboarding.manage   (JSON = prefs)

Déjà là (ne pas casser)
    PATCH /me identité PROF-A
    PATCH /me/onboarding (3 champs AUTH-38)
    GET /users/{id} sans prefs
```

---



## Paliers (figés pour ce jour)


| Sujet | Choix jour 14 | Plus tard |
| ----- | ------------- | --------- |
| Bloc `preferences` sur `GET /me` | **Garder** (déjà AUTH-F / PROF-A). Ticket « pas de bloc ici » = l’**écriture** réglages passe par `/me/preferences`, pas un strip | — |
| `editable` | Dans **`data.user.editable`** (GET `/me` seulement). Clés : `first_name`, `last_name`, `username`, **`phone`**, **`matricule`**, `job_title`. Pas sur `GET /users/{id}` ni login `public_user` | — |
| `job_title` | Flag `system_settings` `profile` / `job_title_self_edit` bool, défaut **false** si ligne **absente**. **Pas** de cache lab (tests flipent la clé) | écran admin config |
| 400 `job_title` | `FIELD_FORBIDDEN` + extra **`field=job_title`** (comme `permission` AUTH-R) | — |
| Prefs vs privacy | `read_receipts` / `typing_indicator` **n’écrivent pas** `privacy_settings` | PROF-C + chat |
| Langues | `fr` \| `en` seulement → 400 `INVALID_LANGUAGE` (wizard PATCH **aussi** si délégué au service) | — |
| Timezone | `zoneinfo` IANA → 400 `INVALID_TIMEZONE` | — |
| GET onboarding | **Même** payload que GET prefs (6 champs + `last_updated`). Tests F : les 3 clés actuelles **restent** | — |
| PATCH onboarding | Toujours **3** champs seulement (AUTH-38). Réutilise `prefs_service` | — |
| Portes AUTH-F | GET/PATCH `/me/preferences` **après** CGU + wizard. GET onboarding allowlist **inchangée** | — |
| Audit | `PREFS_PATCH` (lab : oui, comme `PROFILE_PATCH`) | — |
| Champ inconnu prefs | 400 `UNKNOWN_FIELD` (contrôler `request.data` brut) | — |
| Login JSON | `public_user` **inchangé** (pas d’`editable`) | — |


Perms déjà seedées : `iam.prefs.read` / `iam.prefs.update` (self USER).

---



## 1. Tables

**0 migration.** `user_preferences` et `system_settings` existent.  
**Interdit :** `docker compose down -v`.

Seed (idempotent, `seed_config`) :

| category | setting_key | value | type |
|----------|-------------|-------|------|
| `profile` | `job_title_self_edit` | `false` | bool |

`audit_logs.action` : `PREFS_PATCH` (et `PROFILE_PATCH` déjà si `job_title`).

---



## 2. Settings + seed

Pas de nouvelle clé `.env`.  
`python manage.py seed_config` : upsert `profile.job_title_self_edit`.  
Tests flag `true` : `SystemSetting.objects.update_or_create(...)` en fixture (pas besoin du seed dans pytest).

---



## 3. Services


| Fichier | Sert à |
| ------- | ------ |
| `apps/iam/services/prefs_service.py` | **nouveau.** serialize, PATCH prefs, `job_title_self_edit()`, écriture partagée wizard |
| `apps/iam/services/profile_service.py` | `editable` ; `job_title` dans la whitelist si flag |
| `apps/iam/services/compliance_service.py` | `onboarding_payload` / `patch_onboarding` **délèguent** au prefs_service |
| `apps/iam/views/me.py` | GET déjà `serialize_me` (gagner `editable`) |
| `public_user` | **inchangé** |


`editable` :

```text
first_name, last_name, username, phone = true
matricule = false          # RH seulement (PROF-06) — clé présente pour que le client masque le champ
job_title = job_title_self_edit()
```

PATCH prefs : au moins une clé parmi les 6.  
Si `language` / `timezone` présents → aussi `users.language` / `users.timezone`.  
`last_updated` = `user_preferences.last_updated` (auto_now).  
get_or_create orphelin seulement (ne devrait pas arriver).

`job_title` PATCH `/me` si flag : trim, max 128, `''` autorisé.

---



## 4. HTTP

Arborescence `views/` / `urls/me.py`. `path("preferences")` **avant** tout catch-all (comme `avatar`).


| Fichier | Rôle |
| ------- | ---- |
| `apps/iam/views/prefs.py` | **nouveau.** GET + PATCH `/me/preferences` |
| `apps/iam/serializers/prefs.py` | **nouveau.** body PATCH + OpenAPI |
| `apps/iam/urls/me.py` | `preferences` |
| `apps/iam/views/me.py` | GET `editable` (via service) |
| `apps/iam/views/compliance.py` | GET onboarding = serialize prefs |
| `apps/config/management/commands/seed_config.py` | clé profil |


| Méthode | Chemin | Perm |
| ------- | ------ | ---- |
| GET | `/api/v1/me` | `iam.profile.read` |
| PATCH | `/api/v1/me` | `iam.profile.update` |
| GET | `/api/v1/me/preferences` | `iam.prefs.read` |
| PATCH | `/api/v1/me/preferences` | `iam.prefs.update` |
| GET | `/api/v1/me/onboarding` | `iam.onboarding.manage` |


`MePreferencesView.required_permissions = {"GET": "iam.prefs.read", "PATCH": "iam.prefs.update"}`.

**GET `/me` 200** — inchangé PROF-A **plus** :

```json
"editable": {
  "first_name": true,
  "last_name": true,
  "username": true,
  "phone": true,
  "matricule": false,
  "job_title": false
}
```

dans `data.user`. `preferences` / `privacy` / `gates` **restent**.

**PATCH `/me`** — body PROF-A **plus** `job_title` si flag.  
`language` / toggles prefs / `matricule` / `email` → 400 `FIELD_FORBIDDEN` (comme jour 13).

**GET `/me/preferences` 200**

```json
{
  "success": true,
  "data": {
    "language": "fr",
    "timezone": "Africa/Lome",
    "notification_sound": true,
    "auto_download_media": false,
    "read_receipts": true,
    "typing_indicator": true,
    "last_updated": "2026-08-27T10:15:00Z"
  }
}
```

**PATCH `/me/preferences`** partiel ≥ 1 clé. **200** = même JSON que GET.  
400 `INVALID_LANGUAGE` / `INVALID_TIMEZONE` / `UNKNOWN_FIELD` / `VALIDATION_ERROR`.

**GET `/me/onboarding`** : même `data` que GET prefs (prérempli, jamais vide).  
**PATCH `/me/onboarding`** : body 3 champs **inchangé** ; 200 peut renvoyer le JSON prefs complet (les 3 clés F restent).

Collègue `GET /users/{id}` : **pas** de prefs, **pas** d’`editable`.

---



## 5. Impact tests existants


| Fichier | Adapter |
| ------- | ------- |
| `test_prof_a.py` | `PATCH job_title` **400** encore vrai (flag défaut false). GET `/me` **gagne** `editable` (ne pas exiger l’absence). |
| `test_auth_f.py` | GET onboarding : `language` / `timezone` / `notification_sound` encore là ; clés extras **OK** |
| `test_auth_r.py` | jean `GET /me` 200 inchangé |
| `test_auth_a.py` | login `public_user` **sans** `editable` |


GET/PATCH `/me/preferences` : portes fermées (`close_gates`) comme `/me/password`.

---



## 6. Tests nouveaux (`test_prof_b.py`)


| ID | Cas | Attendu |
| -- | --- | ------- |
| 15 | GET `/me` `editable` | `phone=true`, `matricule=false`, `job_title=false` par défaut |
| 15 | PATCH `phone` | 200 (PROF-10, régression) |
| 15 | PATCH `job_title` flag false | **400** `FIELD_FORBIDDEN` + `field=job_title` |
| 15 | flag true + `job_title` | **200** ; GET `/me` reflète ; `editable.job_title=true` |
| 15 | PATCH `language` sur `/me` | **400** `FIELD_FORBIDDEN` |
| 16 | PATCH prefs `language=en` | **200** ; `users.language=en` |
| 16 | `language=de` | **400** `INVALID_LANGUAGE` |
| 17 | tz IANA OK | **200** ; `users.timezone` aligné |
| 17 | `timezone=Not/AZone` | **400** `INVALID_TIMEZONE` |
| 18 | `notification_sound=false` | **200** |
| 19 | `auto_download_media=true` | **200** |
| 20 | `read_receipts=false` | prefs OK ; **privacy.read_receipts_enabled** inchangé |
| 21 | `typing_indicator=false` | idem privacy `typing_indicator_enabled` |
| 22 | GET onboarding user neuf | défauts seed (`fr`, `Africa/Lome`, son true, DL false, …) |
| 22 | prefs `language=en` avant wizard | GET onboarding `en` |
| 22 | GET `/me/preferences` avant wizard | **403** `ONBOARDING_REQUIRED` (TOS d’abord si portes ouvertes) |
| — | GET prefs collègue | **pas** de route liste ; `GET /users/{id}` sans `preferences` |
| — | retirer `iam.prefs.update` | **403** `FORBIDDEN` |
| — | sans JWT | **401** |
| — | `/health`, `/api/docs/` | schéma contient `/me/preferences` |


Helper MFA : `login_until_jwt`. Portes : `close_gates` sauf GET `/me` et GET `/me/onboarding`.  
User neuf (portes ouvertes) : GET prefs → 403 TOS ou ONBOARDING selon l’ordre AUTH-F (TOS d’abord).

Régression : A (login) + F (3 clés wizard) + PROF-A (`job_title` 400 défaut).

---



## 7. Vérif manuelle

```powershell
python manage.py seed_config
python manage.py check
pytest apps/iam/tests/test_prof_b.py apps/iam/tests/test_prof_a.py apps/iam/tests/test_auth_f.py --reuse-db
```

`jean.dupont@yas.tg` : GET `/me` → `editable.job_title=false`. PATCH prefs `language=en` → `users.language=en`.  
PATCH `/me` `job_title` → 400. SQL / Django admin : poser `profile.job_title_self_edit=true` → PATCH 200.  
Compte neuf : GET `/me/onboarding` prérempli ; GET `/me/preferences` bloqué.  
`/admin/` cookie : **pas** ces routes.

---



## Checklist jour 14

- [x] `user.editable` sur GET `/me` ; prefs/privacy **conservés** ; login inchangé
- [x] `job_title` gated (`system_settings`, défaut false, extra `field`)
- [x] GET/PATCH `/me/preferences` + `INVALID_LANGUAGE` / `INVALID_TIMEZONE` / `UNKNOWN_FIELD`
- [x] Align `users.language` / `timezone` ; souhait 20/21 ≠ privacy
- [x] GET onboarding = serialize prefs ; PATCH onboarding 3 champs via le même service
- [x] `seed_config` `profile.job_title_self_edit`
- [x] `test_prof_b.py` + régression A/F/PROF-A
- [x] SIRH non modifié
- [x] 0 `docker compose down -v`

---



## Interdits

- Recoder PROF-A avatar / org / `GET /users/{id}` privacy
- Coder PROF-C (`/me/privacy`) / PRES-A / ANNUAIRE write
- Endpoint admin HTTP pour le flag (hors Django `/admin/`)
- Retirer `preferences` / `privacy` de GET `/me`
- Colonne `display_name` / thème / i18n fichiers
- `docker compose down -v`
- Changer le SIRH

---



## Après le jour 14

Jour 15 : [00-jour-15-prof-c.md](00-jour-15-prof-c.md) — **PROF-C** (`GET/PATCH /me/privacy`, écriture des masques déjà lus en PROF-A).

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
| **14** | **PROF-B** (ce plan)                           | Préférences                         |
| 15     | PROF-C                                         | §2 visibilité                       |
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
