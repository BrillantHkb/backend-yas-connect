# Crypto — Catalogue des routes planifiées

**Produit :** YAS Connect uniquement.  
**Source :** [CRYPTO-R](CRYPTO-R-roles-permissions.md) · [CRYPTO-A](CRYPTO-A-cles.md) · [CRYPTO-00](CRYPTO-00-modele-chiffrement.md).  
**Préfixe HTTP :** `/api/v1`.  
**Dépendances :** IAM (JWT, `session.device_id`), Messagerie (membre fil) pour la clé cloud.

**6 routes HTTP.** Pas de WebSocket.

**Hors tableau :** `ensure_conversation_key` (hook MESSAGERIE-C), garde `CRYPTO_KEYS_MISSING` (MESSAGERIE-B).

---

## Vague 0 — RBAC (CRYPTO-R)

`python manage.py seed_crypto` (3 permissions).

---

## Vague A — Clés (CRYPTO-A)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 1 | `PUT` | `/api/v1/crypto/me/identity` | Collaborateur | `crypto.keys.manage` | USER, ADMIN | A-01 | Identité publique appareil | Session `device_id`. |
| 2 | `PUT` | `/api/v1/crypto/me/signed-prekey` | Collaborateur | `crypto.keys.manage` | USER, ADMIN | A-02 | Signed prekey | Rotation = nouveau `key_id`. |
| 3 | `PUT` | `/api/v1/crypto/me/one-time-prekeys` | Collaborateur | `crypto.keys.manage` | USER, ADMIN | A-03 | Recharge OTPK | Batch max 100. |
| 4 | `GET` | `/api/v1/crypto/me/one-time-prekeys/count` | Collaborateur | `crypto.keys.manage` | USER, ADMIN | A-04 | Compteur | `urls` : `count` avant conflits. |
| 5 | `GET` | `/api/v1/crypto/users/{id}/bundles` | Collaborateur | `crypto.bundle.read` | USER, ADMIN | A-05 | Bundles pair | Consomme 1 OTPK / appareil. 409 si vide. |
| 6 | `GET` | `/api/v1/crypto/conversations/{id}/key` | Collaborateur | `crypto.conversation_key.read` | USER, ADMIN | A-10 | Clé cloud groupe | Membre GROUP/AI. Jamais PRIVATE. |
