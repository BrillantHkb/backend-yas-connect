# MESSAGERIE-F — Blocage, signalement & modération (MSG-89 … 98)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MESSAGERIE-A](MESSAGERIE-A-inbox-conversations.md), **MESSAGERIE-R** (`messaging.report.review`).  
**Models :** [code/messaging_models.py](../code/messaging_models.py).

**Périmètre MVP :** blocage user (et effet sur privé + appels).  
**Après le MVP :** signalement message, file modération admin.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MSG-89** | **Gardé** | Bloquer utilisateur | `blocked_users` UK (blocker, blocked) |
| **MSG-90** | **Gardé** | Débloquer | DELETE |
| **MSG-91** | **Gardé** | Liste des bloqués | lecture |
| **MSG-92** | **Gardé** | Empêche nouveau privé | check à création conversation |
| **MSG-93** | **Gardé** | Signaler message | `reported_messages` status PENDING |
| **MSG-94** | **Gardé** | Motif obligatoire | `reason` text |
| **MSG-95** | **Gardé** | File admin signalements | filtres status |
| **MSG-96** | **Gardé** | Traiter signalement REVIEWED / DISMISSED | `reviewed_by`, `reviewed_at` |
| **MSG-97** | **Gardé** | Action modération (hors scope) : masquer message, suspendre user | lien ADMIN-A |
| **MSG-98** | **Gardé** | Anti-spam signalements | max 10 / user / jour |

**Hors incrément :** modération automatique IA contenu.

---

## Contrat HTTP

### Blocage — `messaging.block.manage`

| Route | Méthode | Body |
|-------|---------|------|
| `/api/v1/me/blocked-users` | GET | — |
| `/api/v1/me/blocked-users` | POST | `{ "user_id", "reason": "" }` |
| `/api/v1/me/blocked-users/{user_id}` | DELETE | — |

**409** si déjà bloqué. Impossible de se bloquer soi.

### Signalement — `messaging.report.create`

`POST /api/v1/messages/{id}/reports`

```json
{ "reason": "Harcèlement" }
```

### Admin — `messaging.report.review`

| Route | Méthode |
|-------|---------|
| `GET /api/v1/admin/reported-messages` | Liste `?status=PENDING` |
| `PATCH /api/v1/admin/reported-messages/{id}` | `{ "status": "REVIEWED", "note": "" }` |
