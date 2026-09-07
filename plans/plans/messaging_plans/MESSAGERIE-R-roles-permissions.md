# MESSAGERIE-R — Rôles & permissions (MSG-R01 … R05)

**Produit :** YAS Connect uniquement.  
**Préalable :** Phase 0 + **AUTH-R** (`HasPermission`, seed USER/ADMIN) + **AUTH-F** (portes CGU/wizard) + **PROF-C** (privacy messagerie).  
**Attributs :** [MESSAGERIE-catalogue-tables.md](../../catalogues/MESSAGERIE-catalogue-tables.md).  
**Models :** [code/messaging_models.py](../code/messaging_models.py).

**Périmètre :** seed des permissions `messaging.*`, branchement sur toutes les vues HTTP + WS authentifié du module.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MSG-R01** | **Gardé** | Convention `messaging.{resource}.{action}` (minuscule), alignée AUTH-R01 | — |
| **MSG-R02** | **Gardé** | Seed **18** permissions `is_system=true` (17 self + 1 admin) | `permissions`, `role_permissions` |
| **MSG-R03** | **Gardé** | USER reçoit toutes les perms `audience=self` ; ADMIN = self + `messaging.report.review` | `role_permissions` |
| **MSG-R04** | **Gardé** | Chaque vue REST/WS métier : `required_permission` obligatoire | — |
| **MSG-R05** | **Gardé** | Vérifications métier **en plus** du RBAC : membre actif, blocage, privacy mentions/invites/accusés/typing | — |

**Hors incrément :** permissions modérateur dédié, rôles NOC chat, ACL par segment.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Module | `messaging` |
| Portes AUTH-F | Toutes les routes **après** CGU + wizard |
| Membre | Lecture/envoi si `conversation_members.active=true` et pas bloqué |
| Privé | Création 1-to-1 : refus si `blocked_users` |
| Groupe | `READ_ONLY` = lecture ; envoi selon `locked` et rôle |
| Admin | `messaging.report.review` = audience **admin** |

---

## MSG-R02 — Catalogue seed

| Code | audience | Rôles | Sert à |
|------|----------|-------|--------|
| `messaging.conversation.read` | self | USER, ADMIN | Inbox, détail, épinglés |
| `messaging.conversation.create` | self | USER, ADMIN | Créer privé / groupe |
| `messaging.conversation.update` | self | USER, ADMIN | Métadonnées groupe, avatar |
| `messaging.conversation.archive` | self | USER, ADMIN | Archiver / désarchiver |
| `messaging.message.read` | self | USER, ADMIN | Historique, recherche |
| `messaging.message.send` | self | USER, ADMIN | Envoyer messages |
| `messaging.message.update` | self | USER, ADMIN | Éditer ses messages |
| `messaging.message.delete` | self | USER, ADMIN | Supprimer pour soi / tous |
| `messaging.message.react` | self | USER, ADMIN | Réactions emoji |
| `messaging.message.forward` | self | USER, ADMIN | Transférer |
| `messaging.receipt.update` | self | USER, ADMIN | Livré / lu |
| `messaging.member.read` | self | USER, ADMIN | Liste participants |
| `messaging.member.manage` | self | USER, ADMIN | Ajouter / retirer / rôles |
| `messaging.poll.vote` | self | USER, ADMIN | Voter / clôturer sondage |
| `messaging.block.manage` | self | USER, ADMIN | Blocage user |
| `messaging.report.create` | self | USER, ADMIN | Signaler message |
| `messaging.bookmark.manage` | self | USER, ADMIN | Signets |
| `messaging.report.review` | admin | ADMIN | Modération signalements |

Commande : `python manage.py seed_messaging` (idempotent).

---

## Enforcement privacy (MSG-R05)

| Règle IAM | Effet messagerie |
|-----------|------------------|
| `allow_mentions=false` | Rejet ou drop mention |
| `allow_group_invites=false` | Refus ajout membre |
| `read_receipts_enabled=false` | Pas d’accusés lus émis |
| `typing_indicator_enabled=false` | Pas d’événement typing |
