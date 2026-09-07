# CRYPTO-A — Contrat API des clés (CRY-01 … 14)

**Produit :** YAS Connect uniquement.  
**Préalable :** **CRYPTO-R** + **AUTH-E** (session → `device_id`) + [CRYPTO-00](CRYPTO-00-modele-chiffrement.md).  
**Attributs :** [CRYPTO-catalogue-tables.md](../../catalogues/CRYPTO-catalogue-tables.md).  
**Models :** [code/crypto_models.py](../code/crypto_models.py).

**Périmètre :** publier / consommer les bundles Signal **par appareil** (1-to-1) ; générer / servir la clé cloud **GROUP/AI**.  
Sans cet incrément, `MESSAGERIE-B` ne peut pas envoyer un `PRIVATE` opaque.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **CRY-01** | **Gardé** | Publier identité publique + `registration_id` de **cet** appareil | `identity_keys` |
| **CRY-02** | **Gardé** | Publier signed prekey (rotation = nouvel `key_id`) | `signed_prekeys` |
| **CRY-03** | **Gardé** | Recharger one-time prekeys (batch) | `one_time_prekeys` |
| **CRY-04** | **Gardé** | Compteur OTPK restantes (appareil courant) | lecture |
| **CRY-05** | **Gardé** | Bundles d’un user : 1 par appareil ayant une identité | consomme 1 OTPK / appareil |
| **CRY-06** | **Gardé** | Refus bundle si aucune identité pair | **409** `PEER_KEYS_MISSING` |
| **CRY-07** | **Gardé** | Envoi 1-to-1 : sender sans identité appareil → **409** `CRYPTO_KEYS_MISSING` | hook MESSAGERIE-B |
| **CRY-08** | **Gardé** | `encrypted_content` = blob **opaque** (enveloppes multi-appareils côté client) | — |
| **CRY-09** | **Gardé** | Création `GROUP`/`AI` → `ensure_conversation_key` | `conversation_keys` |
| **CRY-10** | **Gardé** | GET clé cloud si membre actif | déwrap TLS |
| **CRY-11** | **Gardé** | Pas de ligne `conversation_keys` pour `PRIVATE` | — |
| **CRY-12** | **Gardé** | Wrap at-rest : `CRYPTO_MASTER_KEY` (env, 32 octets) | settings |
| **CRY-13** | **Gardé** | Lab : générer la master key dans `.env` ; jamais `DJANGO_SECRET_KEY` | — |
| **CRY-14** | **Gardé** | OTPK épuisées : bundle sans OTPK (`one_time_prekey: null`) ; client utilise SPK seule | pas d’erreur |

**Hors incrément :** rotation clé de fil (re-wrap membres), backup seed, Sesame, sender-key E2E groupe.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Portée Signal | **Par `devices.id`** (session courante), pas une identité unique user |
| Format clés | `bytea` / JSON **base64** en HTTP |
| Consommation OTPK | `consumed_at=now()` dans la même transaction que le GET bundle |
| Fan-out | Le client chiffre vers **chaque** appareil du pair ; le serveur ne parse pas le blob |
| Clé groupe | 32 octets aléatoires, wrap AES-256-GCM, `algorithm=AES-256-GCM` |
| Modération groupe | Service déwrappe `wrapped_key` pour lire `encrypted_content` GROUP |
| Hook création | `MESSAGERIE-C` MSG-41 (et fil `AI`) appelle `CryptoService.ensure_conversation_key(conversation_id)` |

---

## Contrat HTTP

Préfixe `/api/v1`. Portes AUTH-F. Appareil = `request.auth.session.device_id`.

### CRY-01 — `PUT /api/v1/crypto/me/identity`

`crypto.keys.manage`.

```json
{ "registration_id": 12345, "identity_public_key": "<base64>" }
```

**200** upsert 1-1 appareil. **400** si clé vide.

### CRY-02 — `PUT /api/v1/crypto/me/signed-prekey`

`{ "key_id": 1, "public_key": "<base64>", "signature": "<base64>" }` → **200**.

### CRY-03 — `PUT /api/v1/crypto/me/one-time-prekeys`

`{ "keys": [ { "key_id": 1, "public_key": "<base64>" }, … ] }` (max 100).  
Ignore les `key_id` déjà présents. **200** `{ "accepted": 80, "skipped": 20 }`.

### CRY-04 — `GET /api/v1/crypto/me/one-time-prekeys/count`

**200** `{ "available": 42 }` (`consumed_at IS NULL`).

### CRY-05 — `GET /api/v1/crypto/users/{id}/bundles`

`crypto.bundle.read`. **404** user inconnu. **409** `PEER_KEYS_MISSING` si 0 identité.

**200**

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

`one_time_prekey` peut être `null` (CRY-14).

### CRY-10 — `GET /api/v1/crypto/conversations/{id}/key`

`crypto.conversation_key.read`. Membre actif du fil `GROUP`/`AI` sinon **404**.  
`PRIVATE` → **409** `E2E_NO_SERVER_KEY`.

**200** `{ "conversation_id", "version", "algorithm", "key": "<base64>" }` — clé **claire** (TLS). Jamais `wrapped_key`.

---

## Hooks (pas d’HTTP public)

| Source | Action |
|--------|--------|
| MESSAGERIE-C création GROUP/AI | `ensure_conversation_key` si aucune version |
| MESSAGERIE-B send PRIVATE | Sender : identité appareil courante sinon **409** `CRYPTO_KEYS_MISSING`. Pair : au moins 1 bundle sinon **409** `PEER_KEYS_MISSING` (check sans consommer, ou bundles déjà fetch côté client) |
| Révocation appareil AUTH-E | CASCADE `identity_keys` / prekeys du `device_id` |
| Lien QR AUTH-J | Après tokens : le **nouvel** appareil `PUT /crypto/me/identity` (même règle session `device_id`) |

---

## Tests (minimum)

| Cas | Attendu |
|-----|---------|
| PUT identity autre `device_id` que la session | ignoré / 400 — toujours session device |
| GET bundles consomme 1 OTPK | 2e GET : autre `key_id` ou null |
| GET clé GROUP non-membre | 404 |
| GET clé PRIVATE | 409 `E2E_NO_SERVER_KEY` |
| wrapped_key dans une réponse | interdit |
| CRYPTO_MASTER_KEY manquante | boot / ensure_conversation_key **500** `CRYPTO_MASTER_UNSET` (lab : poser `.env`) |

---

## Critères de fin CRYPTO-A

- [ ] Seed `seed_crypto` + 4 tables
- [ ] 6 routes vertes
- [ ] Hook GROUP + garde MESSAGERIE-B 1-to-1
- [ ] CRYPTO-00 : aucune privée Signal en PG
