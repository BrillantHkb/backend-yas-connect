# CRYPTO-R — Rôles & permissions (CRY-R01 … R04)

**Produit :** YAS Connect uniquement.  
**Préalable :** Phase 0 + **AUTH-R** + **AUTH-F** + [CRYPTO-00](CRYPTO-00-modele-chiffrement.md).  
**Attributs :** [CRYPTO-catalogue-tables.md](../../catalogues/CRYPTO-catalogue-tables.md).  
**Models :** [code/crypto_models.py](../code/crypto_models.py).

**Périmètre :** seed `crypto.*`, clés **de son appareil**, lecture bundles d’autrui, clé de fil si membre.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **CRY-R01** | **Gardé** | Convention `crypto.{resource}.{action}` | — |
| **CRY-R02** | **Gardé** | Seed **3** permissions `is_system=true` (`audience=self`) | `permissions`, `role_permissions` |
| **CRY-R03** | **Gardé** | USER et ADMIN reçoivent les 3 | `role_permissions` |
| **CRY-R04** | **Gardé** | Upload clés : `device_id` = session courante. Bundle autrui : user existant. Clé groupe : membre actif | — |

**Hors incrément :** perm admin « lire toutes les clés cloud », export SOC des `wrapped_key`.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Module | `crypto` |
| Portes AUTH-F | Toutes les routes JWT après CGU + wizard |
| Privées Signal | **Jamais** en PG ni en JSON réponse |
| Clé groupe | GET renvoie la clé déwrappée **au membre** ; `wrapped_key` **jamais** en API |

---

## CRY-R02 — Catalogue seed

| Code | audience | Rôles | Sert à |
|------|----------|-------|--------|
| `crypto.keys.manage` | self | USER, ADMIN | Publier / compter ses prekeys |
| `crypto.bundle.read` | self | USER, ADMIN | Bundles d’un pair (démarrer 1-to-1) |
| `crypto.conversation_key.read` | self | USER, ADMIN | Clé cloud d’un fil GROUP/AI |

Commande : `python manage.py seed_crypto` (idempotent).
