# NOTIF-R — Rôles & permissions (NOTIF-R01 … R04)

**Produit :** YAS Connect uniquement.  
**Préalable :** Phase 0 + **AUTH-R** (`HasPermission`, seed USER/ADMIN) + **AUTH-F** (portes CGU/wizard).  
**Attributs :** [NOTIF-catalogue-tables.md](../../catalogues/NOTIF-catalogue-tables.md).  
**Models :** [code/notif_models.py](../code/notif_models.py).

**Périmètre :** seed `notifications.*`, enforcement inbox **uniquement soi**.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **NOTIF-R01** | **Gardé** | Convention `notifications.{resource}.{action}` (minuscule), alignée AUTH-R01 | — |
| **NOTIF-R02** | **Gardé** | Seed **3** permissions `is_system=true` (toutes `audience=self`) | `permissions`, `role_permissions` |
| **NOTIF-R03** | **Gardé** | USER et ADMIN reçoivent les 3 (pas de perm admin dédiée au MVP) | `role_permissions` |
| **NOTIF-R04** | **Gardé** | Lecture / mark-read : `notifications.user_id = me` sinon **404** | — |

**Hors incrément :** broadcast admin, templates, stats push cross-users.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Module | `notifications` |
| Portes AUTH-F | Toutes les routes JWT **après** CGU + wizard |
| Isolation | Pas de lecture de l’inbox d’un autre user, même ADMIN |
| Création | **Aucun** POST public — `NotificationService.emit()` interne (Messagerie, Appels, AUTH-E) |
| Push token | AUTH-E `devices.push_token` ; perm IAM appareils, pas `notifications.*` |

---

## NOTIF-R02 — Catalogue seed

| Code | audience | Rôles | Sert à |
|------|----------|-------|--------|
| `notifications.inbox.read` | self | USER, ADMIN | Liste, unread-count |
| `notifications.inbox.update` | self | USER, ADMIN | Mark-read / read-all |
| `notifications.preferences.manage` | self | USER, ADMIN | GET/PATCH prefs |

Commande : `python manage.py seed_notifications` (idempotent).
