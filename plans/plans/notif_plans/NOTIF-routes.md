# Notifications — Catalogue des routes planifiées

**Produit :** YAS Connect uniquement.  
**Source :** [NOTIF-R](NOTIF-R-roles-permissions.md) · [NOTIF-A](NOTIF-A-in-app-push.md).  
**Préfixe HTTP :** `/api/v1`.  
**Dépendances :** IAM (JWT, `devices.push_token`, prefs IAM), CRYPTO-00 (payload 1-to-1).

**Permission** = `required_permission` (`HasPermission`).  
**Rôles** = USER / ADMIN après `seed_notifications` + AUTH-R.

**6 routes HTTP.** Pas de WebSocket dédié (événement optionnel sur le socket user existant).

**Hors tableau :** `NotificationService.emit()` (hooks Messagerie / Appels / AUTH-E), worker FCM, `GET /health`, OpenAPI.

---

## Pourquoi cet ordre

| Vague | Plan | Pourquoi |
|-------|------|----------|
| **0** | NOTIF-R | Seed `notifications.*` avant toute vue |
| **A** | NOTIF-A | Inbox + prefs ; emit interne ensuite |

Portes **AUTH-F** (CGU + wizard) sur toutes les routes JWT.

---

## Vague 0 — RBAC (NOTIF-R)

Hors HTTP : `python manage.py seed_notifications` (3 permissions).

---

## Vague A — Inbox & préférences (NOTIF-A)

| # | Méthode | Chemin | Acteur | Permission | Rôles | Plan | Sert à | Spécificités |
|---|---------|--------|--------|------------|------|------|--------|--------------|
| 1 | `GET` | `/api/v1/notifications` | Collaborateur | `notifications.inbox.read` | USER, ADMIN | A-01 | Inbox | Keyset `created_at`. Query `unread_only`. |
| 2 | `GET` | `/api/v1/notifications/unread-count` | Collaborateur | `notifications.inbox.read` | USER, ADMIN | A-02 | Badge | `{ "count" }`. |
| 3 | `POST` | `/api/v1/notifications/{id}/read` | Collaborateur | `notifications.inbox.update` | USER, ADMIN | A-03 | Marquer lu | 404 si pas à soi. 204. |
| 4 | `POST` | `/api/v1/notifications/read-all` | Collaborateur | `notifications.inbox.update` | USER, ADMIN | A-04 | Tout lu | 204. |
| 5 | `GET` | `/api/v1/notification-preferences` | Collaborateur | `notifications.preferences.manage` | USER, ADMIN | A-05 | Lire prefs | 1-1. |
| 6 | `PATCH` | `/api/v1/notification-preferences` | Collaborateur | `notifications.preferences.manage` | USER, ADMIN | A-05 | MAJ prefs | Whitelist champs. |

`urls` : `unread-count` et `read-all` **avant** `{id}` pour éviter le conflit.

Token push : [IAM-routes](../iam_plans/IAM-routes.md) AUTH-E (PATCH device) — pas une route NOTIF.
