# APPELS-R — Rôles & permissions (CALL-R01 … R05)

**Produit :** YAS Connect uniquement.  
**Préalable :** Phase 0 + **AUTH-R** (`HasPermission`, seed USER/ADMIN) + **AUTH-F** (CGU/wizard) + **PROF-C** (`allow_calls`) + **PRES-A** (hook `IN_MEETING`).  
**Attributs :** [APPELS-catalogue-tables.md](../../catalogues/APPELS-catalogue-tables.md).  
**Models :** [code/calls_models.py](../code/calls_models.py).

**Périmètre :** seed des permissions `calls.*`, branchement sur toutes les vues HTTP + webhooks LiveKit authentifiés + WS appels.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **CALL-R01** | **Gardé** | Convention `calls.{resource}.{action}` (minuscule), alignée AUTH-R01 | — |
| **CALL-R02** | **Gardé** | Seed **16** permissions `is_system=true` (14 self + 2 admin) | `permissions`, `role_permissions` |
| **CALL-R03** | **Gardé** | USER = toutes les perms `audience=self` ; ADMIN = self + admin | `role_permissions` |
| **CALL-R04** | **Gardé** | Chaque vue REST métier : `required_permission` obligatoire | — |
| **CALL-R05** | **Gardé** | Règles métier **en plus** du RBAC : participant, `allow_calls`, blocage, plafond simultané | — |

**Hors incrément :** rôle opérateur NOC dédié, ACL par segment / crise (ticket Canaux).

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Module | `calls` |
| Portes AUTH-F | Toutes les routes JWT **après** CGU + wizard |
| Privacy | `privacy_settings.allow_calls=false` → refus appel entrant (**403** `CALLS_DISABLED`) |
| Blocage | `blocked_users` (Messagerie) → refus 1-to-1 dans les deux sens |
| Participant | Lecture / join / mute si ligne `call_participants` active (`left_at` NULL) ou invitee RINGING |
| Admin | `calls.metrics.read_all`, `calls.recording.manage_all` = audience **admin** |
| LiveKit | Token court ; Django ne stocke **pas** SDP (`webrtc_sessions` hors MVP) |

---

## CALL-R02 — Catalogue seed

| Code | audience | Rôles | Sert à |
|------|----------|-------|--------|
| `calls.call.create` | self | USER, ADMIN | Créer appel / réunion |
| `calls.call.read` | self | USER, ADMIN | Détail, historique perso |
| `calls.call.control` | self | USER, ADMIN | Accepter, rejeter, terminer, mute self |
| `calls.participant.read` | self | USER, ADMIN | Liste participants |
| `calls.participant.manage` | self | USER, ADMIN | Inviter, éjecter, rôles (HOST/MOD) |
| `calls.session.manage` | self | USER, ADMIN | Join / leave session device |
| `calls.token.create` | self | USER, ADMIN | Token LiveKit join |
| `calls.track.read` | self | USER, ADMIN | Pistes / screen shares |
| `calls.recording.read` | self | USER, ADMIN | Lister / lire ses enregistrements |
| `calls.recording.create` | self | USER, ADMIN | Démarrer / arrêter enregistrement (HOST) |
| `calls.metrics.write` | self | USER, ADMIN | Poster échantillons QoS |
| `calls.metrics.read` | self | USER, ADMIN | QoS de ses appels |
| `calls.meeting.read` | self | USER, ADMIN | Compte-rendu / transcript |
| `calls.meeting.update` | self | USER, ADMIN | Titre / notes CR |
| `calls.metrics.read_all` | admin | ADMIN | QoS cross-users / NOC |
| `calls.recording.manage_all` | admin | ADMIN | Accès enregistrements tous appels |

Commande : `python manage.py seed_calls` (idempotent).

---

## Enforcement métier (CALL-R05)

| Règle | Effet |
|-------|--------|
| `allow_calls=false` (callee) | Pas de `RINGING` ; **403** `CALLS_DISABLED` |
| `blocked_users` | **403** `USER_BLOCKED` sur create 1-to-1 |
| Non-participant | **403** / **404** sur détail, token, mute |
| Host / Moderator | Seuls `participant.manage`, `recording.create`, kick |
| Appel `ENDED` / `FAILED` / `CANCELLED` | Pas de token ; **409** `CALL_CLOSED` |
| Présence | Sur `ACTIVE` : sticky `users.status=IN_MEETING` (PRES-A) ; restore à `ENDED` |
| Plafond | Max X appels `RINGING`/`ACTIVE` initiés par user (config `calls.max_concurrent`) |

---

## Lien permissions croisées

| Module | Usage |
|--------|--------|
| Messagerie | Création message `type=CALL` + `call_id` (pas de perm messaging dédiée : écriture système) |
| Médias | `recordings.media_id` → `media.file.read` pour télécharger le fichier |
| Présence | `IN_MEETING` réservé Appels (PRES-A) |
