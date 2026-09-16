# Jour 24 — CRYPTO-R + CRYPTO-A (bundles de clés Signal par appareil)

**Statut :** à faire.  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–23 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 23](00-jour-23-notif-r-a.md)). CRYPTO-00 (jour 21) figé : ce jour l'implémente pour le 1-to-1 (bundles Signal), pas pour les groupes (ça, c'est `ensure_conversation_key`, hook seulement).

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §6 — *secret des messages*) :

| Fonction MVP                              | Ticket             | Statut          |
| ------------------------------------------ | ------------------ | --------------- |
| Centre de notifs + push                    | NOTIF-R + NOTIF-A  | **fait** (jour 23) |
| **Bundles de clés Signal (par appareil)**  | **CRYPTO-R + CRYPTO-A** | **ce jour** |
| Messagerie 1-to-1                          | MESSAGERIE-R,A,B    | jour 25         |

**À quoi ça sert (MVP) :** CRYPTO-00 (jour 21) a décidé que le serveur ne lit jamais un message 1-to-1 — mais pour que deux téléphones puissent s'échanger des clés Signal (X3DH) **sans jamais se voir directement**, il faut un endroit où chacun publie ses clés publiques et va chercher celles de l'autre. C'est tout le rôle de ce jour : **aucun texte de message n'est concerné**, seulement des clés publiques et un compteur. Sans ce jour, `MESSAGERIE-B` (jour 25) ne peut tout simplement pas envoyer un premier message 1-to-1 chiffré.

**Plan métier (code à coller) :** [CRYPTO-R-roles-permissions.md](crypto_plans/CRYPTO-R-roles-permissions.md) (CRY-R01…R04) + [CRYPTO-A-cles.md](crypto_plans/CRYPTO-A-cles.md) (CRY-01…14, **hors** CRY-10 — voir §0). Modèles : [code/crypto_models.py](code/crypto_models.py).  
Chemins lab = ce fichier (nouvelle app `apps/crypto/`).

**Déjà en base / code :**

- `CRYPTO_MASTER_KEY` : déjà dans `.env`/`.env.example`, **vide** pour l'instant (commentaire : « lus à MEDIA-A / CRYPTO-A / APPELS-C / AUTH-D — vides = no-op lab »). **Contrairement** à MinIO/scan, ce jour a besoin d'une **vraie** valeur (32 octets) — CRY-13 le dit explicitement.
- `cryptography>=43.0,<47.0` : déjà dans `requirements/base.txt` (utilisé par AUTH-C TOTP) — AES-256-GCM en fait partie, **aucune** nouvelle dépendance.
- `Device` (IAM) : porte déjà `push_token`/`voip_push_token`. `session.device_id` (AUTH-E) est déjà la source de vérité « appareil courant » utilisée par `/me/devices/current`.
- `apps/iam/services/device_service.py::kill_device` : ne supprime **jamais** la ligne `Device` (« Jamais DELETE devices », AUTH-33/34) — donc le CASCADE FK `identity_keys`/`signed_prekeys`/`one_time_prekeys` → `device` **ne se déclenchera jamais tout seul**. Delta nécessaire (§0).

**Pas encore :** l'app `apps.crypto` **n'existe pas du tout** (2ᵉ fois après `apps.notifications`, jour 23, qu'un jour crée une app de zéro). `apps.messaging` n'existe toujours pas (jour 25+) : CRY-10 (clé de fil GROUP/AI) ne peut pas vérifier une appartenance qui n'a pas de table.

**Objectif du jour :**

1. Créer l'app `apps/crypto/` (`IdentityKey`, `SignedPreKey`, `OneTimePreKey`, `ConversationKey`), migration `0001_initial`.
2. **CRYPTO-R** : 3 permissions `crypto.*` dans `rbac_catalog.py`.
3. `apps/crypto/services/wrapping.py` : `wrap`/`unwrap` AES-256-GCM avec `CRYPTO_MASTER_KEY` ; **500** `CRYPTO_MASTER_UNSET` si absente/mal formée.
4. `apps/crypto/services/key_service.py` : upsert identity/signed-prekey, recharge OTPK (batch), compteur, bundles (consomme 1 OTPK/appareil), `ensure_conversation_key` (hook interne, testé directement).
5. 5 routes HTTP (CRY-01…05). **Pas** de route CRY-10 ce jour (§0).
6. Delta AUTH-E : `kill_device` supprime explicitement les clés du `device_id` révoqué/compromis (CASCADE réel impossible, la ligne `Device` n'est jamais supprimée).
7. Générer une vraie `CRYPTO_MASTER_KEY` (32 octets, base64) dans `.env` (**pas** `.env.example`, qui reste vide comme les autres secrets lab).
8. Ne rien casser : AUTH-E (revoke/compromise), NOTIF-A, tout le reste.

**Hors jour 24 :** `GET /crypto/conversations/{id}/key` (CRY-10 — nécessite une notion de membre/type de fil que Messagerie n'a pas encore, jour 26 MESSAGERIE-C) ; garde `CRYPTO_KEYS_MISSING` réellement branchée sur un envoi de message (MESSAGERIE-B, jour 25 — la fonction est écrite et testée directement, pas encore appelée par une route) ; rotation de clé de fil ; vraie vérification cryptographique des signatures (le serveur stocke des blobs opaques, ne valide jamais Signal côté serveur) ; backup seed, Sesame, sender-key E2E groupe.

---

## 0. Corrections apportées au plan métier (avant de coder)

| Écart trouvé | Correction |
|---|---|
| CRYPTO-A liste **6** routes (« 6 routes vertes ») | CRY-10 (`GET /crypto/conversations/{id}/key`) est **impossible** aujourd'hui : elle exige de savoir si l'appelant est « membre actif » d'un fil `GROUP`/`AI`, or aucune table de conversation/membre n'existe. **5 routes** ce jour ; `ensure_conversation_key` reste écrit et testé comme hook interne (CRY-09), prêt pour MESSAGERIE-C (jour 26). |
| CRYPTO-R dit « Commande `python manage.py seed_crypto` » | Même correction que AUTH-R/MEDIA-R/NOTIF-R : 3 codes ajoutés à `rbac_catalog.py`, pas de nouvelle commande. |
| « Révocation appareil AUTH-E → CASCADE `identity_keys`/prekeys » | Le CASCADE FK ne se déclenche **que** si la ligne `Device` est supprimée — or `kill_device` ne supprime **jamais** `Device` (règle AUTH-33/34 déjà en place). Delta : `kill_device` **supprime explicitement** les 3 tables de clés pour ce `device_id`, sans toucher à `Device` lui-même. |
| Bundle : le JSON exemple montre toujours `signed_prekey` rempli (jamais `null`) | Un appareil sans `SignedPreKey` n'apparaît **pas** dans les bundles (pas encore prêt pour X3DH) — seul `one_time_prekey` peut être `null` (CRY-14). |

---

## Pourquoi ce jour (après NOTIF-A, avant MESSAGERIE)

MESSAGERIE-B (jour 25) va vouloir, dès son premier test d'envoi 1-to-1, vérifier que l'expéditeur a une identité (`CRYPTO_KEYS_MISSING`) et récupérer les bundles du destinataire (`PEER_KEYS_MISSING`). Construire ce socle maintenant — avec CRYPTO-00 déjà figé (jour 21) — évite de le improviser en pleine Messagerie, exactement comme NOTIF-A (jour 23) a été construit avant Messagerie/Appels pour la même raison.

```text
JWT + HasPermission + portes AUTH-F. Appareil = request.auth.session.device_id (jamais le body).
    PUT  /crypto/me/identity                  crypto.keys.manage
    PUT  /crypto/me/signed-prekey              crypto.keys.manage
    PUT  /crypto/me/one-time-prekeys           crypto.keys.manage
    GET  /crypto/me/one-time-prekeys/count     crypto.keys.manage
    GET  /crypto/users/{id}/bundles            crypto.bundle.read

Hooks internes (pas d'HTTP, testés directement)
    ensure_conversation_key(conversation_id)          → MESSAGERIE-C (jour 26)
    require_sender_identity(device)                   → MESSAGERIE-B (jour 25)

Delta AUTH-E
    kill_device(device, reason) → + suppression identity_keys/signed_prekeys/one_time_prekeys

Hors jour 24 (table absente)
    GET /crypto/conversations/{id}/key   → CRY-10, besoin de « membre du fil » (Messagerie, jour 26)
```

---

## Paliers (figés pour ce jour)

| Sujet | Choix jour 24 | Plus tard |
| ----- | ------------- | --------- |
| Nouvelle app | `apps/crypto` créée ce jour, migration `0001_initial` (2ᵉ app créée de zéro après `apps.notifications`) | — |
| Appareil = session | **Toujours** `request.auth.session.device_id`. Un `device_id` dans le corps de la requête est **ignoré** (pas un champ du serializer) | — |
| Format clés HTTP | `bytea` en base → **base64** en JSON (entrée et sortie). Décodage invalide → **400** `VALIDATION_ERROR` | — |
| Identité (CRY-01) | `IdentityKey` 1-1 par appareil (`OneToOneField`). **200** upsert (jamais 201) | — |
| Signed prekey (CRY-02) | Upsert par `(device, key_id)` — republier le même `key_id` **remplace** (idempotent), un nouveau `key_id` = rotation | — |
| OTPK (CRY-03) | Batch max **100** → au-delà **400** `VALIDATION_ERROR`. `key_id` déjà présent pour cet appareil → **skip** silencieux (compté dans `skipped`) | — |
| Bundles (CRY-05) | 1 entrée par appareil du destinataire **ayant** une `IdentityKey` **et** au moins une `SignedPreKey`. 0 appareil valide → **409** `PEER_KEYS_MISSING` | — |
| Consommation OTPK | La **plus ancienne** non consommée (FIFO), `consumed_at=now()` dans la même transaction (Django `ATOMIC_REQUESTS=True`, comme ANNUAIRE-C) | — |
| `ensure_conversation_key` | Génère 32 octets aléatoires, wrap AES-256-GCM, `is_current=true`, `version=1`. **Aucune** ligne pour `PRIVATE` (jamais appelé pour ce type) | Rotation = nouvelle version, ré-wrap (hors incrément) |
| `CRYPTO_MASTER_KEY` | 32 octets, **base64** dans `.env`. Absente/mal formée → **500** `CRYPTO_MASTER_UNSET` dès qu'une opération de wrap est tentée (pas au boot Django, pour ne pas bloquer les jours qui ne touchent pas la crypto) | — |
| Révocation appareil | `kill_device` supprime les 3 tables de clés pour ce `device_id` (delta, §0) — un appareil révoqué ne peut plus recevoir de message chiffré à son intention | — |
| CRY-10 | **Hors jour 24** (§0). `ensure_conversation_key` existe et est testé, mais aucune route ne l'expose encore | Route ajoutée avec MESSAGERIE-C (jour 26) |
| Portes AUTH-F | Toutes les routes `/crypto/*` sous JWT + CGU/wizard (comme tout `/me/*`) | — |
| Audit | `module=CRYPTO` ; pas de ligne `AuditLog` par clé publiée (bruyant, ce sont des clés publiques) — seule la révocation (`kill_device`) reste auditée côté IAM (déjà fait) | — |

---

## 1. Tables (nouvelle app)

**1 migration** : `apps/crypto/migrations/0001_initial.py` — `identity_keys`, `signed_prekeys`, `one_time_prekeys`, `conversation_keys` (0 ligne).  
**Interdit :** `docker compose down -v`.

---

## 2. Fichiers

| Fichier | Rôle |
| ------- | ---- |
| `apps/crypto/__init__.py`, `apps.py`, `migrations/` | **nouveau.** Scaffolding app |
| `apps/crypto/models.py` | **nouveau.** `IdentityKey`, `SignedPreKey`, `OneTimePreKey`, `ConversationKey` (coller [code/crypto_models.py](code/crypto_models.py)) |
| `apps/crypto/services/wrapping.py` | **nouveau.** `wrap`, `unwrap` (AES-256-GCM, `CRYPTO_MASTER_KEY`) |
| `apps/crypto/services/key_service.py` | **nouveau.** upsert identity/SPK, OTPK batch/count, bundles, `ensure_conversation_key`, `require_sender_identity` |
| `apps/crypto/serializers/keys.py` | **nouveau.** shape DRF (base64 en entrée/sortie) |
| `apps/crypto/views/keys.py` | **nouveau.** 5 vues |
| `apps/crypto/urls.py` | **nouveau.** monté sous `/api/v1/crypto/` |
| `apps/iam/services/device_service.py` | **delta.** `_current_device`/`_current_device_id` promues en fonctions publiques (réutilisées par `apps/crypto`) ; `kill_device` supprime les clés du device |
| `apps/iam/views/devices.py` | **delta.** utilise les fonctions promues (pas de duplication) |
| `apps/iam/services/rbac_catalog.py` | **delta.** + 3 permissions `crypto.*` |
| `config/settings.py` | **delta.** `CRYPTO_MASTER_KEY` |
| `.env` | **delta.** vraie valeur 32 octets base64 (`.env.example` reste vide) |
| `apps/iam/tests/test_crypto_a.py` | **nouveau.** |

---

## 3. Contrat HTTP

Préfixe `/api/v1/crypto`. JWT + portes AUTH-F. Appareil = session courante (jamais un `device_id` du corps).

| Méthode | Chemin | Perm |
|---------|--------|------|
| PUT | `/crypto/me/identity` | `crypto.keys.manage` |
| PUT | `/crypto/me/signed-prekey` | `crypto.keys.manage` |
| PUT | `/crypto/me/one-time-prekeys` | `crypto.keys.manage` |
| GET | `/crypto/me/one-time-prekeys/count` | `crypto.keys.manage` |
| GET | `/crypto/users/{id}/bundles` | `crypto.bundle.read` |

**401** sans JWT (toutes les routes). **403** `FORBIDDEN` sans la perm / `TOS_REQUIRED` / `ONBOARDING_REQUIRED` (portes AUTH-F, toutes les routes).

### 3.1 `PUT /crypto/me/identity` (CRY-01)

**Quand le client l'appelle :** une seule fois par appareil, juste après l'avoir généré localement (premier login, ou lien QR AUTH-J pour un nouvel appareil) — avant de pouvoir recevoir des bundles ou en publier. Rejouable sans risque (upsert).

**Requête**

```json
PUT /api/v1/crypto/me/identity
{ "registration_id": 12345, "identity_public_key": "<base64 32o>" }
```

**Flux serveur**

1. `HasPermission` vérifie `crypto.keys.manage` + portes AUTH-F (avant la vue).
2. La vue résout l'appareil courant via `request.auth.session.device_id` (jamais un champ du body — le serializer n'a pas de `device_id`, donc un client qui en enverrait un le verrait **silencieusement ignoré**).
3. `IdentitySerializer` valide `registration_id` (entier) et décode `identity_public_key` (base64 → bytes). Base64 invalide ou vide → **400** `VALIDATION_ERROR` (`extra.field` nomme le champ), **avant** tout accès DB.
4. `key_service.upsert_identity(device, registration_id, identity_public_key)` :
   `IdentityKey.objects.update_or_create(device=device, defaults={"user": device.user, "registration_id": ..., "identity_public_key": ...})`.
5. **200** `{ "device_id", "registration_id", "identity_public_key": "<base64>" }` (jamais 201 — c'est toujours un upsert 1-1, même la toute première fois).

**Erreurs :** 400 `VALIDATION_ERROR` (base64/entier invalide).

### 3.2 `PUT /crypto/me/signed-prekey` (CRY-02)

**Quand :** au provisioning initial de l'appareil (juste après l'identité), puis périodiquement pour la rotation (le client génère un nouveau `key_id` incrémental et le republie).

**Requête**

```json
PUT /api/v1/crypto/me/signed-prekey
{ "key_id": 1, "public_key": "<base64>", "signature": "<base64>" }
```

**Flux serveur**

1. Perm + portes AUTH-F + appareil = session (identique à 3.1).
2. `SignedPrekeySerializer` valide `key_id` (entier ≥ 0) + décode `public_key`/`signature` en base64.
3. `key_service.upsert_signed_prekey(device, key_id, public_key, signature)` :
   `SignedPreKey.objects.update_or_create(device=device, key_id=key_id, defaults={"public_key": ..., "signature": ...})`.
   → republier le **même** `key_id` remplace la ligne (idempotent, pas de doublon) ; un **nouveau** `key_id` = vraie rotation (nouvelle ligne, l'ancienne reste en base pour l'historique mais n'est **jamais** servie — seule la plus récente par `created_at` est renvoyée dans un bundle, §3.5).
4. **200** `{ "key_id", "public_key": "<base64>", "signature": "<base64>" }`.

**Erreurs :** 400 `VALIDATION_ERROR`.

### 3.3 `PUT /crypto/me/one-time-prekeys` (CRY-03)

**Quand :** au provisioning initial (charge un lot, ex. 100), puis rechargé périodiquement par le client quand `GET count` (3.4) redescend sous un seuil qu'il choisit lui-même.

**Requête**

```json
PUT /api/v1/crypto/me/one-time-prekeys
{ "keys": [ { "key_id": 1, "public_key": "<base64>" }, { "key_id": 2, "public_key": "<base64>" }, … ] }
```

**Flux serveur**

1. Perm + portes AUTH-F + appareil = session.
2. `OneTimePrekeysBatchSerializer` valide `keys` : liste non vide, **≤ 100** entrées, chaque entrée `key_id`(entier) + `public_key`(base64). Plus de 100 → **400** `VALIDATION_ERROR` **avant** toute écriture (pas de dépôt partiel).
3. `key_service.load_otpks(device, keys)` — pour chaque entrée, dans une seule transaction :
   - `key_id` déjà présent pour cet appareil (`OneTimePreKey.objects.filter(device=device, key_id=key_id).exists()`) → **skip** (compté dans `skipped`), aucune écriture.
   - sinon → `OneTimePreKey.objects.create(device=device, key_id=key_id, public_key=...)`, compté dans `accepted`.
4. **200** `{ "accepted": <n>, "skipped": <n> }`.

**Erreurs :** 400 `VALIDATION_ERROR` (liste vide, > 100, entrée malformée).

### 3.4 `GET /crypto/me/one-time-prekeys/count` (CRY-04)

**Quand :** le client l'appelle périodiquement (ex. après chaque envoi de message 1-to-1, ou au démarrage de l'app) pour décider s'il doit déclencher une recharge (3.3).

**Flux serveur**

1. Perm + portes AUTH-F + appareil = session.
2. `key_service.otpk_count(device)` → `OneTimePreKey.objects.filter(device=device, consumed_at__isnull=True).count()`.
3. **200** `{ "available": <n> }`.

**Erreurs :** aucune spécifique (juste 401/403 génériques).

### 3.5 `GET /crypto/users/{id}/bundles` (CRY-05, CRY-06, CRY-14)

**Quand :** le client veut démarrer (ou reprendre) une conversation 1-to-1 avec `{id}` — X3DH côté client a besoin d'un bundle par appareil du pair pour chiffrer vers **chacun**. C'est aussi la route que `MESSAGERIE-B` (jour 25) appellera en interne avant d'accepter un premier envoi.

**Flux serveur**

1. Perm `crypto.bundle.read` + portes AUTH-F.
2. `key_service.get_target_user_or_404(id)` → **404** `NOT_FOUND` si l'utilisateur n'existe pas (pas de fuite : même 404 qu'un ID mal formé).
3. `key_service.get_bundles(target_user)` :
   a. Récupère les `Device` de `target_user` qui ont **à la fois** une `IdentityKey` **et** au moins une `SignedPreKey` (`select_related`/`prefetch` pour éviter le N+1) — un appareil sans l'un des deux n'apparaît **pas** (§0, correction).
   b. Aucun appareil valide → **409** `PEER_KEYS_MISSING` (avant toute consommation d'OTPK — on ne "dépense" rien si on va échouer).
   c. Pour **chaque** appareil valide, dans la **même transaction** que la lecture :
      - `signed_prekey` = la `SignedPreKey` la plus récente (`-created_at`) de cet appareil.
      - `one_time_prekey` = la **plus ancienne** `OneTimePreKey` non consommée (`consumed_at IS NULL`, FIFO) ; si trouvée → `consumed_at = now()` **immédiatement** (posé même si le client abandonne ensuite — c'est le contrat CRY-14, pas de réservation "molle") ; si aucune → `one_time_prekey: null` (**pas** une erreur, CRY-14).
4. **200**

```json
{
  "bundles": [
    {
      "device_id": "<uuid>",
      "registration_id": 12345,
      "identity_public_key": "<base64>",
      "signed_prekey": { "key_id": 1, "public_key": "<base64>", "signature": "<base64>" },
      "one_time_prekey": { "key_id": 9, "public_key": "<base64>" }
    }
  ]
}
```

**Erreurs :** 404 `NOT_FOUND` (user inconnu), 409 `PEER_KEYS_MISSING` (0 appareil valide).

---

## 4. Tests nouveaux (`test_crypto_a.py`)

| ID | Cas | Attendu |
| -- | --- | ------- |
| 01 | PUT identity | 200 ; re-PUT (même appareil) → upsert, toujours 1 ligne |
| 02 | PUT signed-prekey, republier même `key_id` | 200, remplace, toujours 1 ligne pour ce `key_id` |
| 03 | PUT one-time-prekeys 5 clés puis les 5 mêmes | 1ʳᵉ fois `accepted=5,skipped=0` ; 2ᵉ fois `accepted=0,skipped=5` |
| 03 | PUT one-time-prekeys > 100 | 400 `VALIDATION_ERROR` |
| 04 | GET count après recharge | `available` correct |
| 05 | GET bundles, cible avec 1 appareil + identity + SPK + 2 OTPK | 200, 1 bundle, `one_time_prekey` non null |
| 05 | 2ᵉ GET bundles même cible | OTPK différente consommée (ou `null` si épuisées, CRY-14) |
| 06 | GET bundles cible sans identité | 409 `PEER_KEYS_MISSING` |
| 05 | GET bundles cible inconnue | 404 |
| — | `ensure_conversation_key` deux fois même `conversation_id` | même version, pas de doublon |
| — | `ensure_conversation_key` avec `CRYPTO_MASTER_KEY` vidée (monkeypatch settings) | 500 `CRYPTO_MASTER_UNSET` |
| — | `require_sender_identity` sans identité posée | lève `CRYPTO_KEYS_MISSING` (appel direct, pas de route) |
| — | `kill_device` (revoke) | `identity_keys`/`signed_prekeys`/`one_time_prekeys` de cet appareil supprimées |
| — | sans JWT | 401 |
| — | sans la permission | 403 `FORBIDDEN` |
| — | self sans CGU | 403 `TOS_REQUIRED` |
| — | `/api/schema/` | contient `/api/v1/crypto/users/{id}/bundles` |

---

## 5. Vérif manuelle

```powershell
python manage.py makemigrations crypto
python manage.py migrate
python manage.py check
pytest apps/iam/tests/test_crypto_a.py apps/iam/tests/test_auth_e.py --reuse-db
```

Générer la master key (une fois) :

```powershell
python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Coller le résultat dans `.env` → `CRYPTO_MASTER_KEY=...`.

---

## Checklist jour 24

- [ ] App `apps.crypto` créée, migration `0001_initial`
- [ ] 3 permissions `crypto.*` seedées
- [ ] `CRYPTO_MASTER_KEY` réelle en `.env` ; `wrap`/`unwrap` AES-256-GCM ; `CRYPTO_MASTER_UNSET` géré
- [ ] 5 routes CRY-01…05 vertes, appareil = session (jamais le body)
- [ ] Bundles : consomme 1 OTPK/appareil (FIFO), `null` si épuisées, 409 si 0 appareil valide
- [ ] `ensure_conversation_key` (hook, testé directement)
- [ ] `require_sender_identity` (hook, testé directement)
- [ ] `kill_device` supprime les clés du device révoqué/compromis
- [ ] `test_crypto_a.py` + régression AUTH-E
- [ ] 0 régression NOTIF-A
- [ ] SIRH non modifié

---

## Interdits

- `GET /crypto/conversations/{id}/key` (CRY-10) — jour 26 (MESSAGERIE-C)
- Brancher `CRYPTO_KEYS_MISSING`/`PEER_KEYS_MISSING` sur un vrai envoi de message (Messagerie n'existe pas)
- Vérification cryptographique réelle des signatures Signal (blobs opaques stockés tels quels)
- Rotation de clé de fil, backup seed, Sesame, sender-key E2E groupe
- `docker compose down -v`
- Changer le SIRH

---

## Après le jour 24

Jour 25 : **MESSAGERIE-R, A, B** — premier jour de la Messagerie (rôles, inbox/conversations, messages 1-to-1), premier consommateur réel de `require_sender_identity`/bundles CRYPTO-A et de `emit()` NOTIF-A. Lab pas encore écrit.

---

## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour**. Le jour 2 (admin + Swagger) est un extra déjà clos.

| Jours  | Plan                                           | Ticket MVP                            |
| ------ | ----------------------------------------------- | -------------------------------------- |
| 0      | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health`    |
| 1–2    | AUTH-A ; admin + Swagger                        | Connexion locale ; lab admin           |
| 3–11   | D+B … AUTH-R                                    | §1 entrer + droits HTTP                |
| 12     | ADMIN-A                                         | §9 comptes                             |
| 13     | PROF-A                                          | §2 ma fiche / photo                    |
| 14     | PROF-B                                          | Préférences                            |
| 15     | PROF-C                                          | §2 visibilité                          |
| 16     | PRES-A                                          | §2 statut en ligne                     |
| 17     | ANNUAIRE-A                                      | §3 recherche collègue                  |
| 18     | ANNUAIRE-B                                      | §3 organigramme (types + arbre)        |
| 19     | ANNUAIRE-C                                      | §3 mutations / affectations            |
| 20     | ANNUAIRE-D                                      | §3 compétences / certifications        |
| 21     | CRYPTO-00                                       | §6 décision E2E                        |
| 22     | MEDIA-R + MEDIA-A                               | §4 upload (plafonds ; pas de reprise)  |
| 23     | NOTIF-R + NOTIF-A                               | §5 alertes + MOB-PUSH (VoIP / worker)  |
| **24** | **CRYPTO-R + CRYPTO-A** (ce plan)               | Clés HTTP                              |
| 25     | MESSAGERIE-R, A, B                              | §7 1-to-1                              |
| 26     | MESSAGERIE-C, D                                 | §7 groupes + temps réel                |
| 27     | MESSAGERIE-E (partiel), F, G                    | §7 enrichissements                     |
| 28     | MEDIA-B, C, D, E                                | §4 album / vocal / coffre              |
| 29     | APPELS-R, A, B, C                               | §8 appel 1-1 + `CALL_CANCELLED`        |
| 30     | APPELS-D, E, G                                  | §8 écran / CR                          |

**Total : 31 plans (jours 0 à 30).**  
Déjà clos : **24** (0–23). Restant : **7** (24–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.
