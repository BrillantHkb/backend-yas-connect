# IAM — Catalogue des routes planifiées

**Produit :** YAS Connect uniquement (pas le SIRH).  
**Source :** plans AUTH-A…J, AUTH-R, ADMIN-A, PROF-A/B/C, PRES-A. Annuaire lecture (`/directory/*`, `GET /users`) : [ANNUAIRE-A](../annuaire_plans/ANNUAIRE-A-recherche-referentiels.md). Write RH : [annuaire_plans](../annuaire_plans/ANNUAIRE-routes.md).  
**Préfixe HTTP :** `/api/v1` sauf WebSocket `/ws/v1`.  
**AuthZ :** JWT + `HasPermission` partout sauf `AllowAny`. Portes CGU / wizard **après** la perm, sauf logout / sessions / refresh / vues admin / routes publiques.


**Permission** = code `required_permission` (`HasPermission`, un seul code par vue).  
**Rôles** = qui a ce code après `seed_iam` (USER et/ou ADMIN). ADMIN a aussi toutes les perms USER.  
Public = `AllowAny` : pas de JWT, pas de permission.

**86 routes.** Un **ADMIN** a aussi toutes les routes Collaborateur (seed = **58** perms system : 27 self + 31 admin).

**Hors tableau :** jobs (sync LDAP AUTH-16, reapers), `GET /health`, OpenAPI.

---

## Pourquoi cet ordre (pas le A→Z tel quel)

Le [socle A→Z §4](../00-application-A-Z.md) est un **ordre de documentation des incréments**. Pour **coder**, on inverse quelques morceaux :

| Écart | Raison |
|-------|--------|
| **AUTH-R seed + `HasPermission` dès la vague 1** (HTTP rôles plus tard) | Sinon chaque vue JWT est à rétrofitter. Le CRUD `/admin/roles` n’est pas bloquant pour login. |
| **AUTH-H avant AUTH-B / D / G public** | Logout, idle, rotation refresh = hygiène dès qu’on a un JWT. LDAP et inscription s’appuient dessus. |
| **Jour 3 lab : AUTH-D avant AUTH-B** | Pas de seed `ldap_dn`. `ldap_service` + `register/ad` créent le user ; `login/ldap` ensuite. [00-jour-3-auth-b.md](../00-jour-3-auth-b.md). |
| **Directory public + seed régions avant AUTH-D** | `region_id` / `segment_id` obligatoires à l’inscription. Livré **dans** le jour 3 (pas attendre ANNUAIRE-A people-picker). |
| **PROF puis privacy avant `GET /users`** | La fiche collègue et le people-picker masquent photo / online. |
| **PRES-A en dernier** | Channels + Redis présence, après les portes AUTH-F et PROF-C. |

---

## Vagues (résumé)


| Vague | Routes | Livrable | Dépend de |
|-------|--------|----------|-----------|
| **0** | — | Phase 0 : health, OpenAPI, Docker | — |
| **1** | 2 | Login local + refresh + **seed RBAC** + `HasPermission` | 0 |
| **2** | 1 | MFA : plus de JWT tant que TOTP KO | 1 |
| **3** | 6 | Sessions / logout / heartbeat idle | 2 |
| **4** | 5 | Appareils (soi) | 3 |
| **4b** | 3 | Lier un 2ᵉ appareil par QR + TOTP (AUTH-J) | 2, 4 |
| **5** | 6 | `GET /me` + CGU + wizard | 2 |
| **6** | 4 | Mot de passe app (change + forgot TOTP) | 3, 5 (portes sur `/me/password`) |
| **7** | 1 | Login LDAP (+ job AUTH-16, pas une route) | **AUTH-D déjà là** (jour 3) ; catalogue : 2 |
| **8** | 5 | Logins, e-mail, codes secours | 5, 2 |
| **9** | 8 | Profil, avatar, prefs, privacy, fiche collègue | 5 |
| **10** | 8 | Régions admin + `GET /directory/*` | 1 (admin JWT) ; **slice publique dès jour 3** |
| **11** | 5 | Inscription AD / hors AD | **avant vague 7 en lab** ; catalogue : 10 |
| **12** | 14 | Lifecycle RH, unlock, MFA reset, rôle, audit | 3, 6, 11 |
| **13** | 12 | CRUD rôles / permissions / matrice | 12 (users existent) |
| **14** | 2 | Appareils compromis (admin) | 4 |
| **15** | 1 | People-picker `GET /users` | 9 |
| **16** | 3 | Présence REST + WebSocket | 5, 9 |

---

## Vague 0 — Socle (pas IAM)

`GET /health`, `/api/docs`. Redis optionnel (LocMem). **Aucune** route ci-dessous.

---

## Vague 1 — Tunnel login (AUTH-A + seed AUTH-R)

**Hors HTTP :** migrations IAM / Annuaire / `media_files` ; seed rôles `USER`/`ADMIN` + 58 perms ; classe `HasPermission` (fail-closed) prête pour la vague 2. Login peut encore renvoyer un JWT **tant que** la vague 2 n’est pas branchée.


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 1 | `POST` | `/api/v1/auth/login` | Public | `AllowAny` | — | AUTH-A | Connexion email ou username + MDP app + device obligatoire | Pas de JWT dès la vague 2. 401 unique. Rate-limit IP + identifiant. Device upsert. |
| 2 | `POST` | `/api/v1/auth/refresh` | Public | `AllowAny` | — | AUTH-A / H | Nouvel access + rotation du refresh opaque | Sans OTP. Réuse déjà rotaté → `FORCE_LOGOUT` **vague 3**. Pas de porte CGU. |

---

## Vague 2 — MFA (AUTH-C)

Coupe le contrat : login → `mfa_token` seulement.


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 3 | `POST` | `/api/v1/auth/mfa/verify` | Public | `AllowAny` | — | AUTH-C | 2e facteur TOTP ou code secours → JWT | Enroll 1er login : `otpauth_uri`, backups une fois. Refresh ne redemande pas d’OTP. |

---

## Vague 3 — Sessions (AUTH-H)

Complète le refresh (réuse → kick partout). `revoke_sessions` réutilisé ensuite par G / ADMIN / MFA reset.


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 4 | `POST` | `/api/v1/auth/logout` | Collaborateur | `iam.session.logout` | USER, ADMIN | AUTH-H-53 | Déconnexion session courante | Pas de porte CGU. JTI Redis + refresh. |
| 5 | `POST` | `/api/v1/auth/logout-all` | Collaborateur | `iam.session.logout` | USER, ADMIN | AUTH-H-55 | Tout couper, y compris l’appareil courant | Même service que reset MDP. |
| 6 | `GET` | `/api/v1/me/sessions` | Collaborateur | `iam.session.read` | USER, ADMIN | AUTH-H-56 | Lister ses sessions | Autorisé pendant wizard. `is_current`. |
| 7 | `POST` | `/api/v1/me/sessions/{id}/logout` | Collaborateur | `iam.session.logout` | USER, ADMIN | AUTH-H-54 | Tuer une session distante (la sienne) | Ligne `devices` inchangée. |
| 8 | `POST` | `/api/v1/me/devices/{id}/logout` | Collaborateur | `iam.session.logout` | USER, ADMIN | AUTH-H-54 | Tuer toutes les sessions d’un de ses appareils | ≠ revoke appareil (vague 4). |
| 9 | `POST` | `/api/v1/me/sessions/current/heartbeat` | Collaborateur | `iam.session.heartbeat` | USER, ADMIN | AUTH-H-60 | Rafraîchir `last_activity` (idle 7 j) | Debounce 60 s. Ne pose pas `users.status`. |

---

## Vague 4 — Appareils soi (AUTH-E)


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 10 | `GET` | `/api/v1/me/devices` | Collaborateur | `iam.device.read` | USER, ADMIN | AUTH-E-35 | Lister ses appareils | `is_current` via session. Push token jamais renvoyé. |
| 11 | `PATCH` | `/api/v1/me/devices/current` | Collaborateur | `iam.device.update` | USER, ADMIN | AUTH-E-27/28 | Heartbeat appareil + `push_token` + jailbreak | Sans re-login. `trusted` ≠ skip MFA. |
| 12 | `PATCH` | `/api/v1/me/devices/{id}` | Collaborateur | `iam.device.update` | USER, ADMIN | AUTH-E-30/31/36 | Renommer / `trusted` (owner) | Retirer trusted ne tue pas les sessions. |
| 13 | `POST` | `/api/v1/me/devices/{id}/revoke` | Collaborateur | `iam.device.revoke` | USER, ADMIN | AUTH-E-34 | Révoquer un appareil (kill sessions + push) | Ligne conservée, `trusted=false`. |
| 14 | `POST` | `/api/v1/me/devices/{id}/compromise` | Collaborateur | `iam.device.compromise` | USER, ADMIN | AUTH-E-33 | Signaler vol / compromis (soi) | Kill + login 403. Miroir admin = vague 14. |

---

## Vague 4b — Lier un appareil par QR (AUTH-J)

Numéros **84–86** (après le 83 des vagues 5–16) pour ne pas décaler le catalogue existant. À coder **juste après** AUTH-E + AUTH-C.

Le QR `otpauth://` (enroll Authenticator) reste vague 2. Ici = QR **2ᵉ écran**, puis TOTP.


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 84 | `POST` | `/api/v1/auth/device-link/start` | Public | `AllowAny` | — | AUTH-J-67 | Nouvel écran : créer le challenge + payload QR | `DeviceSpec` waiter. Secret **pas** dans le QR. TTL 90 s. |
| 85 | `GET` | `/api/v1/auth/device-link/{id}` | Public | `AllowAny` | — | AUTH-J-68 | Poll jusqu’aux tokens | Header `X-Device-Link-Secret`. APPROVED = one-shot puis 410. |
| 86 | `POST` | `/api/v1/me/devices/link` | Collaborateur | `iam.device.update` | USER, ADMIN | AUTH-J-69 | Téléphone : confirmer le scan avec Google Authenticator | Body `{ challenge_id, otp }`. Pas de backup. Pas de JWT dans la réponse téléphone. |

---

## Vague 5 — Portes + moi (AUTH-F)

Première surface « app ». Toutes les vues métier suivantes s’appuient sur CGU / wizard **sauf** logout / sessions / admin.


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 15 | `GET` | `/api/v1/me` | Collaborateur | `iam.profile.read` | USER, ADMIN | AUTH-F / PROF-A | Sa fiche : identité, org, présence, portes | Toujours tout visible pour soi. `last_login` ici seulement. |
| 16 | `GET` | `/api/v1/me/tos` | Collaborateur | `iam.tos.manage` | USER, ADMIN | AUTH-F | Lire la version CGU courante | Autorisé même si CGU pas encore acceptées. |
| 17 | `POST` | `/api/v1/me/tos/accept` | Collaborateur | `iam.tos.manage` | USER, ADMIN | AUTH-F-40 | Accepter les CGU | Sans ça : 403 `TOS_REQUIRED` sur le métier. |
| 18 | `GET` | `/api/v1/me/onboarding` | Collaborateur | `iam.onboarding.manage` | USER, ADMIN | AUTH-F / PROF-22 | État du wizard + préremplissage prefs | Jamais un formulaire vide. MFA déjà fait. |
| 19 | `PATCH` | `/api/v1/me/onboarding` | Collaborateur | `iam.onboarding.manage` | USER, ADMIN | AUTH-F-38 | Sauver langue / fuseau / son | Même écriture que `PATCH /me/preferences` (vague 9). |
| 20 | `POST` | `/api/v1/me/onboarding/complete` | Collaborateur | `iam.onboarding.manage` | USER, ADMIN | AUTH-F-42 | Clôturer le wizard | Pose `onboarding_completed_at`. |

---

## Vague 6 — Mot de passe (AUTH-G)


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 21 | `POST` | `/api/v1/me/password` | Collaborateur | `iam.password.change` | USER, ADMIN | AUTH-G-43 | Changer le MDP app (ancien + nouveau) | Bloqué si CGU/wizard KO. Option `logout_others`. Pas le MDP AD. |
| 22 | `POST` | `/api/v1/auth/password/forgot` | Public | `AllowAny` | — | AUTH-G-46 | Démarrer un reset MDP app | Toujours 200. Preuve = TOTP, pas mail/SMS. |
| 23 | `POST` | `/api/v1/auth/password/reset/verify` | Public | `AllowAny` | — | AUTH-G-47/48 | Prouver TOTP / backup → ticket | Ne consomme pas le ticket. Sans MFA → même 400. |
| 24 | `POST` | `/api/v1/auth/password/reset` | Public | `AllowAny` | — | AUTH-G-49 | Poser le nouveau MDP avec le ticket | Politique + historique. `logout_all` défaut true. Ne déverrouille pas. |

---

## Vague 7 — LDAP (AUTH-B)

**Lab jour 3 :** cette route se code **après** la vague 11 (inscription). User déjà créé par `register/ad`.  
**Hors HTTP :** job AUTH-16 (sync DN / `userAccountControl` / `accountExpires`).


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 25 | `POST` | `/api/v1/auth/login/ldap` | Public | `AllowAny` | — | AUTH-B | Connexion mot de passe Active Directory | User déjà créé par `register/ad`. Pas de JIT. Pas de seed `ldap_dn`. |

---

## Vague 8 — Sécurité compte (AUTH-I + AUTH-C-23)


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 26 | `GET` | `/api/v1/me/security/logins` | Collaborateur | `iam.login.read` | USER, ADMIN | AUTH-I-61 | Historique de ses connexions | IP, geo, device, succès/échec. |
| 27 | `POST` | `/api/v1/me/email` | Collaborateur | `iam.email.change` | USER, ADMIN | AUTH-I-65 | Demander un changement d’e-mail | LDAP : e-mail de login inchangé. |
| 28 | `POST` | `/api/v1/me/email/resend` | Collaborateur | `iam.email.change` | USER, ADMIN | AUTH-I-66 | Renvoyer le mail de changement | Rate-limit identifiant + IP. |
| 29 | `POST` | `/api/v1/auth/email/verify` | Public | `AllowAny` | — | AUTH-I-65 | Confirmer le changement (lien token) | Distinct du verify **inscription** (vague 11). |
| 30 | `POST` | `/api/v1/auth/mfa/backup-codes/regenerate` | Collaborateur | `iam.mfa.regenerate` | USER, ADMIN | AUTH-C-23 | Régénérer les codes de secours | Session déjà MFA. Affichés une fois. |

---

## Vague 9 — Identité affichée (PROF-A / B / C)

`GET /users/{id}` ici (masque privacy). La **liste** de recherche = vague 15.


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 31 | `PATCH` | `/api/v1/me` | Collaborateur | `iam.profile.update` | USER, ADMIN | PROF-A / B | Éditer prénom, nom, username, téléphone | Whitelist. Jamais matricule, rôle, segment, e-mail. |
| 32 | `POST` | `/api/v1/me/avatar` | Collaborateur | `media.avatar.manage` | USER, ADMIN | PROF-03 | Uploader la photo de profil | JPEG/PNG/WebP, 2 Mo, scan. |
| 33 | `DELETE` | `/api/v1/me/avatar` | Collaborateur | `media.avatar.manage` | USER, ADMIN | PROF-04 | Retirer l’avatar | Fichier `media_files` conservé. |
| 34 | `GET` | `/api/v1/me/preferences` | Collaborateur | `iam.prefs.read` | USER, ADMIN | PROF-B | Lire langue, fuseau, son, DL, souhait accusés | Distinct de `privacy_settings`. |
| 35 | `PATCH` | `/api/v1/me/preferences` | Collaborateur | `iam.prefs.update` | USER, ADMIN | PROF-B | Modifier ses préférences UI | `read_receipts` ici = souhait, pas le booléen privacy. |
| 36 | `GET` | `/api/v1/me/privacy` | Collaborateur | `iam.privacy.read` | USER, ADMIN | PROF-C | Lire visibilités + `allow_*` | Pas exposé dans `GET /me`. |
| 37 | `PATCH` | `/api/v1/me/privacy` | Collaborateur | `iam.privacy.update` | USER, ADMIN | PROF-C | Masquer photo / last_seen / online | 23–25 effet immédiat sur GET collègue. |
| 38 | `GET` | `/api/v1/users/{id}` | Collaborateur | `iam.profile.read_other` | USER, ADMIN | PROF-02 | Fiche d’un collègue | 404 si inactif. Self → 400. Après CGU/wizard. |

---

## Vague 10 — Référentiels d’inscription (ADMIN-A-08 + ANNUAIRE-A lecture)

Seed 5 régions TG + types `DIRECTION`/`DEPARTEMENT`/`SERVICE` + segment `YAS`. Débloque AUTH-D.


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 39 | `GET` | `/api/v1/admin/regions` | Admin | `iam.region.read` | ADMIN | ADMIN-A-08 | Liste admin des régions | Distinct du GET public. |
| 40 | `GET` | `/api/v1/admin/regions/{id}` | Admin | `iam.region.read` | ADMIN | ADMIN-A-08 | Détail d’une région | Table IAM `region`. |
| 41 | `POST` | `/api/v1/admin/regions` | Admin | `iam.region.manage` | ADMIN | ADMIN-A-08 | Créer une région | `code` SCREAMING_SNAKE unique. |
| 42 | `PATCH` | `/api/v1/admin/regions/{id}` | Admin | `iam.region.manage` | ADMIN | ADMIN-A-08 | Modifier code / libellé | Audit `REGION_*`. |
| 43 | `DELETE` | `/api/v1/admin/regions/{id}` | Admin | `iam.region.manage` | ADMIN | ADMIN-A-08 | Supprimer une région | 409 `REGION_IN_USE` si encore pointée. |
| 44 | `GET` | `/api/v1/directory/regions` | Public | `AllowAny` | — | ANNUAIRE-A | Dropdowns d’inscription | `id`, `code`, `name` seulement. |
| 45 | `GET` | `/api/v1/directory/segment-types` | Public | `AllowAny` | — | ANNUAIRE-A | Types d’unité | Actifs seulement. Pas de JWT. |
| 46 | `GET` | `/api/v1/directory/segments` | Public | `AllowAny` | — | ANNUAIRE-A | Segments org (`parent_id`) | Pas de responsable ni e-mails. |

---

## Vague 11 — Inscription (AUTH-D)

**Lab jour 3 :** livrer **avant** `POST /login/ldap` (vague 7). Slice `GET /directory/regions` + `GET /directory/segments` + seed `YAS` dans le même jour.  
Approve / reject RH = vague 12 (même ressource `/admin/users`) ; jour 3 = rôle ADMIN / `is_staff` jusqu’à AUTH-R.


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 47 | `POST` | `/api/v1/auth/register/check-ad` | Public | `AllowAny` | — | AUTH-D01 | Pré-check compte AD loggable | Aucune écriture. Rate-limit. |
| 48 | `POST` | `/api/v1/auth/register/ad` | Public | `AllowAny` | — | AUTH-D02 | Créer un compte lié AD + MDP app | `USER`, actif, puis MFA. `region_id` + `segment_id` obligatoires. |
| 49 | `POST` | `/api/v1/auth/register` | Public | `AllowAny` | — | AUTH-D03 | Self-register hors AD (attente RH) | `pending_approval`, pas de JWT. |
| 50 | `POST` | `/api/v1/auth/register/verify-email` | Public | `AllowAny` | — | AUTH-D04 / I | Confirmer l’e-mail d’inscription | N’active pas le compte. SMTP Mailhog / skip si `EMAIL_HOST` vide. |
| 51 | `POST` | `/api/v1/auth/register/resend-verification` | Public | `AllowAny` | — | AUTH-D / I-66 | Renvoyer le mail de vérif | Seulement hors AD inactif. |

---

## Vague 12 — Lifecycle RH (ADMIN-A + D05 + I-64 + C-24 + R09)


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 52 | `GET` | `/api/v1/admin/users` | Admin | `iam.user.read` | ADMIN | ADMIN-A / D05 | Liste RH, filtres, file pending | Pas de porte CGU. `ldap_bound`, pas le DN. |
| 53 | `GET` | `/api/v1/admin/users/{id}` | Admin | `iam.user.read` | ADMIN | ADMIN-A | Fiche admin | Jamais hash / TOTP / refresh. |
| 54 | `POST` | `/api/v1/admin/users` | Admin | `iam.user.create` | ADMIN | ADMIN-A-02 | Créer un compte RH hors AD | Toujours `USER`. `role_code` interdit. |
| 55 | `POST` | `/api/v1/admin/users/{id}/approve` | Admin | `iam.user.approve` | ADMIN | AUTH-D05 | Approuver un self-register | 400 si `ldap_dn`. |
| 56 | `POST` | `/api/v1/admin/users/{id}/reject` | Admin | `iam.user.reject` | ADMIN | AUTH-D05 | Rejeter l’inscription hors AD | Reste inactif. Motif dans audit. |
| 57 | `POST` | `/api/v1/admin/users/{id}/disable` | Admin | `iam.user.disable` | ADMIN | ADMIN-A-03 | Couper un hors-AD + sessions | LDAP → `LDAP_MANAGED`. Dernier ADMIN / soi → 409/400. |
| 58 | `POST` | `/api/v1/admin/users/{id}/enable` | Admin | `iam.user.enable` | ADMIN | ADMIN-A-04 | Réactiver un hors-AD | Ne déverrouille pas. Pending → approve. |
| 59 | `POST` | `/api/v1/admin/users/{id}/password` | Admin | `iam.user.reset_password` | ADMIN | ADMIN-A-05 | Reset MDP app helpdesk | Body `new_password`, jamais renvoyé. Logout-all. |
| 60 | `POST` | `/api/v1/admin/users/{id}/sessions/revoke-all` | Admin | `iam.session.revoke_other` | ADMIN | ADMIN-A-06 | Kick sans disable | Interdit sur soi. |
| 61 | `POST` | `/api/v1/admin/users/{id}/unlock` | Admin | `iam.user.unlock` | ADMIN | AUTH-I-64 | Déverrouiller après lock auto | Distinct de enable. |
| 62 | `GET` | `/api/v1/admin/users/{id}/logins` | Admin | `iam.user.security.read` | ADMIN | AUTH-I-61 | Historique d’un autre user | Pas le GET `/me/security/logins`. |
| 63 | `POST` | `/api/v1/admin/users/{id}/mfa/reset` | Admin | `iam.mfa.reset` | ADMIN | AUTH-C-24 | Effacer le TOTP → ré-enroll | Révoque les sessions de la cible. |
| 64 | `PATCH` | `/api/v1/admin/users/{id}/role` | Admin | `iam.user.role.assign` | ADMIN | AUTH-R09 | Changer le rôle unique | `LAST_ADMIN` si 0 ADMIN restant. |
| 65 | `GET` | `/api/v1/admin/audit-logs` | Admin | `iam.audit.read` | ADMIN | ADMIN-A-07 | Lire le journal | Pas de DELETE. Jamais de hash dans jsonb. |

---

## Vague 13 — RBAC HTTP (AUTH-R06–R08)

Le **seed** est déjà vague 1. Ici l’UI admin de la matrice.


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 66 | `GET` | `/api/v1/admin/roles` | Admin | `iam.role.read` | ADMIN | AUTH-R06 | Lister les rôles | `users_count`. |
| 67 | `GET` | `/api/v1/admin/roles/{id}` | Admin | `iam.role.read` | ADMIN | AUTH-R06 | Détail + `permission_codes` | Pas de `/me/roles`. |
| 68 | `POST` | `/api/v1/admin/roles` | Admin | `iam.role.manage` | ADMIN | AUTH-R06 | Créer un rôle custom | `is_system` interdit. Perms vides → R08. |
| 69 | `PATCH` | `/api/v1/admin/roles/{id}` | Admin | `iam.role.manage` | ADMIN | AUTH-R06 | Renommer / décrire | USER/ADMIN : code / level gelés. |
| 70 | `DELETE` | `/api/v1/admin/roles/{id}` | Admin | `iam.role.manage` | ADMIN | AUTH-R06 | Supprimer un rôle custom | 409 si system ou encore assigné. |
| 71 | `GET` | `/api/v1/admin/roles/{id}/permissions` | Admin | `iam.role.read` | ADMIN | AUTH-R08 | Perms du rôle | Même liste que GET rôle. |
| 72 | `POST` | `/api/v1/admin/roles/{id}/permissions` | Admin | `iam.role.grant` | ADMIN | AUTH-R08 | Ajouter (union) | Tout-ou-rien. `ADMIN_PERMS_FROZEN`. |
| 73 | `DELETE` | `/api/v1/admin/roles/{id}/permissions` | Admin | `iam.role.grant` | ADMIN | AUTH-R08 | Retirer | Idempotent. |
| 74 | `PUT` | `/api/v1/admin/roles/{id}/permissions` | Admin | `iam.role.grant` | ADMIN | AUTH-R08 | Remplacer tout le set | Seul PUT de la matrice. |
| 75 | `GET` | `/api/v1/admin/permissions` | Admin | `iam.permission.read` | ADMIN | AUTH-R07 | Catalogue | `?module=iam`. |
| 76 | `POST` | `/api/v1/admin/permissions` | Admin | `iam.permission.manage` | ADMIN | AUTH-R07 | Créer une perm custom | `is_system=false`. |
| 77 | `DELETE` | `/api/v1/admin/permissions/{id}` | Admin | `iam.permission.manage` | ADMIN | AUTH-R07 | Supprimer une perm custom | System → `PERMISSION_SYSTEM`. |

---

## Vague 14 — Appareils admin (AUTH-E)


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 78 | `POST` | `/api/v1/admin/devices/{id}/compromise` | Admin | `iam.device.manage` | ADMIN | AUTH-E | Marquer n’importe quel appareil compromis | Y compris l’appareil courant de la cible. |
| 79 | `POST` | `/api/v1/admin/devices/{id}/clear-compromise` | Admin | `iam.device.manage` | ADMIN | AUTH-E | Lever le flag | Ne réactive pas `trusted`. |

---

## Vague 15 — People-picker (ANNUAIRE-A)


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 80 | `GET` | `/api/v1/users` | Collaborateur | `iam.profile.read_other` | USER, ADMIN | ANNUAIRE-A | Chercher des collègues | `q` 2–64 car. Pas d’e-mail. Actifs, soi exclu, privacy. Après CGU/wizard. |

---

## Vague 16 — Présence (PRES-A)

Channels. Login ≠ online. Sticky `IN_MEETING` = hook appels (plus tard).


| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 81 | `PATCH` | `/api/v1/me/presence` | Collaborateur | `iam.presence.update` | USER, ADMIN | PRES-A | Légende sous la pastille ; clear sticky via `ONLINE` | Statuts settables interdits → 400. Pas de `status_until`. |
| 82 | `POST` | `/api/v1/me/presence/heartbeat` | Collaborateur | `iam.presence.heartbeat` | USER, ADMIN | PRES-03 | Ping Redis si pas de WS | Distinct du heartbeat **session** (vague 3). |
| 83 | `WS` | `/ws/v1/presence` | Collaborateur | `iam.profile.read` | USER, ADMIN | PRES-A | Online/away/offline + watch + events | JWT + portes AUTH-F. Watch max 100. Privacy PROF-25. |

---

## Index par acteur


| Acteur | Combien | Vagues | Qui |
|--------|---------|--------|-----|
| **Public** | 18 | 1, 2, 4b, 6, 7, 8, 10, 11 | Anonyme : login, MFA, inscription, forgot, `/directory/*`, device-link start/poll |
| **Collaborateur** | 35 | 3–6, 8–9, 15–16, 4b | Rôle `USER` |
| **Admin** | 33 | 10, 12–14 | Rôle `ADMIN` (+ toutes les routes Collaborateur) |
