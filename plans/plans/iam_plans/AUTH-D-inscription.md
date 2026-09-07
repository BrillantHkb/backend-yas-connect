# AUTH-D — Inscription (AD + hors AD)

**Produit :** YAS Connect uniquement (pas le SIRH).  
**Préalable :** Phase 0 + **AUTH-A** + **AUTH-B** (`ldap_service`) + **AUTH-C** (MFA à l’issue de l’inscription AD).  
**Attributs :** [IAM](../../catalogues/IAM-catalogue-tables.md) · [Annuaire](../../catalogues/ANNUAIRE-catalogue-tables.md) · [CONFIG](../../catalogues/CONFIG-catalogue-tables.md).

**Périmètre :** self-service **création de compte** — avec preuve Active Directory, ou hors AD avec **approbation RH**.  
Ce n’est **pas** le login LDAP (AUTH-13) : le login ne crée toujours pas de user ; **seul** `register/ad` crée un user lié AD.

---

## Cartographie


| ID | Fonctionnalité | Comportement | Écritures |
|----|----------------|--------------|-----------|
| **AUTH-D01** | Pré-check AD | `POST /register/check-ad` : email\|username + MDP AD → search + UAC + expires + bind | aucune (rate-limit cache) |
| **AUTH-D02** | Inscription AD | Création user : UPN / sAMAccountName / `ldap_dn` auto ; MDP **app** distinct ; rôle `USER` ; `is_active=true` ; puis **MFA** | `users`, prefs, privacy, `email_verifications` optionnel, audit |
| **AUTH-D03** | Inscription hors AD | Username auto `jdupont` ; `ldap_dn=NULL` ; `is_active=false` ; **pas** de JWT | idem + garde-fou si AD loggable |
| **AUTH-D04** | Vérif email | Token → `email_verifications.verified_at` ; **`is_active` inchangé** | `email_verifications` |
| **AUTH-D05** | Approbation RH | approve / reject / liste `pending` | `users.is_active` ; `audit_logs` |
| **AUTH-D06** | Connexion après | AD → login + MFA ; hors AD pending → **403 `ACCOUNT_PENDING`** | — |


**Hors incrément :** mapping groupe AD → rôle, copie attributs AD vers profil (hors UPN / sAMAccountName / DN), OIDC/SAML, soft-delete RH (reject = reste inactif + motif). Dropdown `region_id` / `segment_id` = [ANNUAIRE-A](../annuaire_plans/ANNUAIRE-A-recherche-referentiels.md) `GET /directory/*`.

---

## Décisions figées


| Sujet | Choix |
|-------|--------|
| MDP inscription AD | **Deux secrets** : MDP AD (preuve, jamais stocké) + MDP **applicatif** (saisi, politique YAS, Argon2id) — peuvent différer |
| Après D02 | **MFA obligatoire** (`begin_mfa` AUTH-C) — pas d’`access_token` tant que `/mfa/verify` KO |
| Hors AD | Validation **RH uniquement** (D03b) ; email D04 = preuve d’adresse **sans** activer |
| Login pending | **403 `ACCOUNT_PENDING`** (distinct de `ACCOUNT_DISABLED`) |
| `region_id` / `segment_id` | **Obligatoires** sur D02 et D03 (contrainte API ; nullable en base pour seed/legacy) |
| Username D03 | `first_name[0] + last_name` normalisé → `jdupont` ; collision → `jdupont2` |
| Rôle | Toujours seed **`USER`** |
| `status` | Toujours **`OFFLINE`** à la création |
| Side tables | `provision_user_rows` : prefs + privacy + **notification_preferences** (D02, D03, seed, ADM-02) |
| SMTP D04 | Lab = Mailhog (`EMAIL_HOST`). Vide = pas d’envoi, token quand même. Non bloquant |


### Politique MDP applicatif (D02 + D03)

Contractuelle (settings / `system_settings` catégorie `security`) :

| Règle | Valeur défaut |
|-------|----------------|
| Longueur min | 10 |
| Majuscule | ≥ 1 |
| Minuscule | ≥ 1 |
| Chiffre | ≥ 1 |
| Caractère spécial | ≥ 1 (`!@#$%^&*()_+-={}[]:;,.?`) |
| Max | 128 |
| Interdit | égal à email / username (case-insensitive) |

Échec → **400** `WEAK_PASSWORD` (pas 401).

---

## Chemins


| Chemin | Prérequis | Création | Ensuite |
|-------|-----------|----------|---------|
| Avec AD | Compte AD loggable | Oui | Challenge MFA, puis JWT |
| Sans AD | Email pro + formulaire | Oui, `is_active=false` | RH approve → login + MFA |

---

## AUTH-D01 — `POST /api/v1/auth/register/check-ad` (public)

**Body :** exactement un identifiant + MDP AD :

```json
{ "email": "jean.dupont@yas.tg", "password": "<mdp-AD>" }
```

ou `"username": "jdupont"` à la place de `email`.

**Ordre :**
1. Rate-limit (même politique AUTH-06, clés `register_ad:{ident}` + IP).
2. `search_user_dn` + état logon (`userAccountControl`, `accountExpires`) — règles AUTH-B.
3. Absent / non loggable → **200** `{ "success": true, "data": { "ad_available": false } }` + message neutre.
4. `bind_user_dn` avec le MDP.
5. Bind KO → **200** `{ "ad_available": false }` (neutre ; pas 401).
6. OK → **200** `{ "ad_available": true }`.
7. AD down → **503** `DIRECTORY_UNAVAILABLE`.

**Ne jamais** renvoyer DN, UAC, ni attributs AD. MDP AD jamais en log / history.

---

## AUTH-D02 — `POST /api/v1/auth/register/ad` (public)

Le serveur **refait** search + bind (ne pas faire confiance au seul D01).

### Body

```json
{
  "email": "jean.dupont@yas.tg",
  "password_ad": "<mdp-AD>",
  "password": "SecretApp123!",
  "first_name": "Jean",
  "last_name": "Dupont",
  "phone": "+22890123456",
  "job_title": "Ingénieur NOC",
  "language": "fr",
  "region_id": "<uuid>",
  "segment_id": "<uuid>",
  "matricule": "TG2026015",
  "avatar_id": null,
  "device": { }
}
```

- `email` **ou** `username` : identifiant AD pour search/bind (le serveur écrase email/username stockés par UPN / sAMAccountName).
- `password_ad` : preuve AD uniquement.
- `password` : MDP **applicatif** (politique ci-dessus).
- `device` : obligatoire (même schéma AUTH-A) pour enchaîner MFA / future session.
- `region_id`, `segment_id`, `first_name`, `last_name`, `phone`, `job_title` : **obligatoires**.
- `matricule`, `avatar_id` : optionnels.

### Remplissage `users`


| Champ | Règle |
|-------|--------|
| `email` | `userPrincipalName` AD (lower/trim) |
| `username` | `sAMAccountName` AD |
| `ldap_dn` | DN AD **immédiat** |
| `role_id` | Rôle `code=USER` |
| `password_hash` | Argon2id(`password`) |
| `is_active` | `true` |
| `is_locked` | `false` |
| `status` | `OFFLINE` |
| `first_name` / `last_name` / `phone` / `job_title` / `language` / `region_id` / `segment_id` | body |
| `matricule` / `avatar_id` | body ou NULL |
| prefs / privacy / **notif prefs** | 1-1 à la création (`provision_user_rows` : `user_preferences`, `privacy_settings`, `notification_preferences`) |
| `user_segments` | Dès [ANNUAIRE-C](../annuaire_plans/ANNUAIRE-C-affectations.md) : `open_assignment` (ouverte, `assigned_by=NULL`). Avant C : colonne IAM seulement |

Attributs AD lus au search (étendre `ldap_service`) : `distinguishedName`, `userPrincipalName`, `sAMAccountName`, `userAccountControl`, `accountExpires`. **Pas** de copie displayName / title AD (profil = body).

### Réponses

| Code | Cas |
|------|-----|
| **200** | Compte créé + payload AUTH-C `mfa_required` + `mfa_token` (pas d’`access_token`) |
| **400** | Validation / `WEAK_PASSWORD` / `REGION_INVALID` / `SEGMENT_INVALID` |
| **401** | Bind / AD non loggable / rate-limit → `INVALID_CREDENTIALS` |
| **409** | UPN ou sAMAccountName déjà en base |
| **503** | AD down |

Après `/mfa/verify` : `complete_login(..., login_method=PASSWORD)` — le hash app vient d’être posé ; le LDAP a servi à **prouver** l’identité.

**Audit :** `USER_REGISTER_AD` (`entity_type=users`, `severity=INFO`, `success=true`).

---

## AUTH-D03 — `POST /api/v1/auth/register` (public)

### Body

```json
{
  "email": "marie.koevi@partenaire.tg",
  "password": "SecretApp123!",
  "first_name": "Marie",
  "last_name": "Koevi",
  "phone": "+22890…",
  "job_title": "Consultante",
  "language": "fr",
  "region_id": "<uuid>",
  "segment_id": "<uuid>",
  "matricule": null,
  "avatar_id": null
}
```

Pas de `device` (pas de login immédiat).

### Username auto

```text
base = normalize(first_name[0] + last_name)   # lower, strip accents, alnum only
# Jean Dupont → jdupont
# si existe → jdupont2, jdupont3, …
```

### Remplissage `users`


| Champ | Règle |
|-------|--------|
| `email` | body (lower) |
| `username` | généré |
| `ldap_dn` | `NULL` |
| `role_id` | `USER` |
| `password_hash` | Argon2id |
| `is_active` | **`false`** |
| `status` | `OFFLINE` |
| reste | comme D02 (champs obligatoires identiques) |

### Garde-fou AD

Avant insert : `search_user_dn(email=…)` (sans bind). Si entrée **loggable** → **409** `AD_ACCOUNT_EXISTS`  
message : « Utilisez l’inscription Active Directory. »  
Si AD **503** : ne pas bloquer D03 (inscription locale continue) — log warning.

### Email D04 (option A)

À la création : INSERT `email_verifications` (token hashé, TTL **48 h**).  
Envoi : si `EMAIL_HOST` posé (**Mailhog** en lab, `127.0.0.1:1025`) → SMTP ; sinon skip, `email_verification_sent=false`. **Non bloquant** (A→Z §4.3) : hors AD = pending RH ; AD = MFA.  
**Ne pas** poser `is_active=true` à la vérif.

### Réponse

```json
{
  "success": true,
  "message": "Compte créé. Validation requise avant connexion.",
  "data": {
    "user_id": "<uuid>",
    "username": "mkoevi",
    "email_verification_sent": true
  }
}
```

**201** — aucun JWT / MFA.

---

## AUTH-D04 — Email (sans activer)

| Endpoint | Effet |
|----------|--------|
| `POST /api/v1/auth/register/verify-email` `{ "token" }` | Hash OK + non expiré + non used → `verified_at=now()` ; **`is_active` inchangé** |
| 2e appel | **200** déjà vérifié |
| Expiré / invalide | **400** `INVALID_TOKEN` |
| `POST /api/v1/auth/register/resend-verification` `{ "email" }` | Rate-limit ; nouveau token si user `is_active=false` et `ldap_dn` null |

RH peut filtrer « email vérifié » avant approve (jointure `email_verifications.verified_at`).

---

## AUTH-D05 — Approbation RH

Permission : `iam.user.approve` / `iam.user.reject` via `HasPermission` ([AUTH-R](AUTH-R-roles-permissions.md) R05/R10). Liste = `iam.user.read` ([ADMIN-A](ADMIN-A-lifecycle-audit.md) ADM-01). **Pas** de fallback `role.code == "ADMIN"`.

| Endpoint | Effet |
|----------|--------|
| `GET /api/v1/admin/users?pending=true` | `pending_approval=true` (file hors AD). Perm `iam.user.read` |
| `POST /api/v1/admin/users/{id}/approve` | `is_active=true` ; `pending_approval=false` ; audit `USER_APPROVE` |
| `POST /api/v1/admin/users/{id}/reject` `{ "reason": "…" }` | reste `is_active=false` ; audit `USER_REJECT` + `metadata.reason` |

Approve sur user déjà actif → **200** idempotent.  
Approve sur user avec `ldap_dn` → **400** (parcours AD, pas pending).

---

## AUTH-D06 — Connexion après inscription

| Situation | Comportement |
|-----------|--------------|
| Inscrit AD, actif | `POST /login` (MDP app) et/ou `POST /login/ldap` ; MFA AUTH-C |
| Hors AD, non approuvé | Après MDP OK → **403 `ACCOUNT_PENDING`** — « Compte en attente de validation. » |
| Hors AD, approuvé | Login AUTH-A + MFA |
| Tentative `/register` alors qu’AD loggable | 409 → UI D02 |

### Delta AUTH-A (obligatoire)

Dans `login()` / `login_ldap()`, **après** MDP/bind OK, **avant** `ACCOUNT_DISABLED` générique :

```python
if not user.is_active:
    if user.ldap_dn is None:
        # candidat self-register hors AD non approuvé
        _history(..., reason="ACCOUNT_PENDING")
        raise AuthAPIError(403, "ACCOUNT_PENDING", "Compte en attente de validation.")
    _history(..., reason="ACCOUNT_DISABLED")
    raise AuthAPIError(403, "ACCOUNT_DISABLED", "Compte désactivé.")
```

(Si un RH désactive un hors-AD déjà approuvé, `is_active=false` + `ldap_dn` null → `ACCOUNT_PENDING` serait ambigu. **Règle raffinée :** stocker `registration_source` optionnel, **ou** : `ACCOUNT_PENDING` seulement si `is_active=false` et **aucune** ligne `audit_logs` `USER_APPROVE` pour ce user.  

**Choix retenu (simple) :** colonne optionnelle `users.pending_approval` boolean, défaut `false` ; D03 pose `true` ; D05 approve pose `false` + `is_active=true` ; reject laisse `pending_approval=true`. Login : si `pending_approval` → `ACCOUNT_PENDING` ; elif not `is_active` → `ACCOUNT_DISABLED`.)

#### Colonne catalogue (delta AUTH-D)

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `pending_approval` | `boolean` | NOT NULL, DEF `false` | Self-register hors AD en attente RH | `true` | 403 `ACCOUNT_PENDING` | D03 = true ; D05 approve = false ; D02 / seed = false |

---

## Fichiers à ajouter / toucher

```
apps/iam/
  services/register_service.py
  services/password_policy.py
  serializers_register.py
  views_register.py
  views_admin_users.py
  urls.py                    # + register* + admin/users*
apps/iam/services/ldap_service.py   # attrs UPN / sAMAccountName au search
apps/iam/services/auth_service.py   # ACCOUNT_PENDING
apps/iam/models.py                  # pending_approval
```

Routes :

```python
path("register/check-ad", CheckAdView.as_view()),
path("register/ad", RegisterAdView.as_view()),
path("register", RegisterLocalView.as_view()),
path("register/verify-email", VerifyEmailView.as_view()),
path("register/resend-verification", ResendVerificationView.as_view()),
# admin (autre urls include)
path("admin/users", AdminUserListView.as_view()),
path("admin/users/<uuid:pk>/approve", AdminUserApproveView.as_view()),
path("admin/users/<uuid:pk>/reject", AdminUserRejectView.as_view()),
```

Préfixe API : `/api/v1/auth/` pour register* ; `/api/v1/` pour admin (ou `/api/v1/iam/admin/…`).

---

## Pseudocode clé

### Username D03

```python
import re
import unicodedata

def suggest_username(first_name: str, last_name: str) -> str:
    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]", "", s.lower())

    base = (norm(first_name)[:1] + norm(last_name))[:64] or "user"
    candidate = base
    n = 2
    while User.objects.filter(username=candidate).exists():
        suffix = str(n)
        candidate = f"{base[: 64 - len(suffix)]}{suffix}"
        n += 1
    return candidate
```

### Register AD (extrait)

```python
def register_ad(*, ident_email, ident_username, password_ad, password_app, profile, device, ip, ua):
    enforce_password_policy(password_app)
    dn, upn, sam = search_user_identity(email=ident_email, username=ident_username)
    # raises LdapBindFailed / DirectoryUnavailable / not loggable
    bind_user_dn(dn, password_ad)
    if User.objects.filter(models.Q(email=upn.lower()) | models.Q(username=sam)).exists():
        raise AuthAPIError(409, "CONFLICT", "Compte déjà existant.")
    role = Role.objects.get(code="USER")
    user = User(
        email=upn.lower().strip(),
        username=sam,
        ldap_dn=dn,
        role=role,
        pending_approval=False,
        is_active=True,
        status=User.Status.OFFLINE,
        **profile,
    )
    user.set_password(password_app)
    user.save()
    UserPreference.objects.create(user=user, language=profile.get("language", "fr"))
    PrivacySettings.objects.create(user=user)
    audit(...)
    return begin_mfa(user=user, ip=ip, user_agent=ua, device_spec=device,
                     ident_key=user.email, login_method=LoginMethod.PASSWORD)
```

---

## Tests (acceptation)


| ID | Cas | Attendu |
|----|-----|---------|
| D01 | bind OK | 200 `ad_available=true` |
| D01 | mauvais MDP AD | 200 `ad_available=false` |
| D01 | AD down | 503 |
| D02 | OK | 200 `mfa_required` ; `ldap_dn` posé ; rôle USER ; `password_hash` ≠ MDP AD |
| D02 | UPN déjà pris | 409 |
| D02 | MDP app faible | 400 `WEAK_PASSWORD` |
| D02 | sans region/segment | 400 |
| D03 | OK | 201 ; `is_active=false` ; `pending_approval=true` ; username `jdupont` |
| D03 | collision username | `jdupont2` |
| D03 | email AD loggable | 409 `AD_ACCOUNT_EXISTS` |
| D03 | login avant approve | 403 `ACCOUNT_PENDING` |
| D04 | verify email | `verified_at` set ; `is_active` toujours false |
| D05 | approve | `is_active=true` ; `pending_approval=false` ; login possible (+ MFA) |
| D05 | reject | reste inactif ; audit reason |
| D06 | login AD user | MDP app et LDAP OK |

---

## Critères d’acceptation

- [ ] Check-ad + register/ad + register local documentés OpenAPI
- [ ] Inscription AD : `ldap_dn` + UPN + sAMAccountName + MDP app + MFA
- [ ] Inscription hors AD : pending RH + email optionnel sans activer
- [ ] `ACCOUNT_PENDING` sur login
- [ ] AUTH-B inchangé pour **login** (pas de JIT login) ; register/ad = seul JIT
- [ ] Tests verts ci-dessus
- [ ] SIRH non concerné

---

## Écarts documents liés

- **AUTH-B** : « LDAP n’invente pas l’utilisateur » → vrai pour **login** ; **register/ad** crée le user.
- **AUTH-B** : `ldap_dn` aussi à l’inscription AD, pas seulement au 1er `login/ldap`.
- **AUTH-A / AUTH-C** : brancher `ACCOUNT_PENDING` + enchaînement MFA post-D02.
- **AUTH-R** : D05 = `HasPermission` uniquement (plus « ou ADMIN »).
- **Catalogue IAM** : colonne `pending_approval` ; notes « renseigné par » inscription.
- **ANNUAIRE-A** : dropdowns `/directory/*`. **ANNUAIRE-C** : historique `user_segments` à la création.
