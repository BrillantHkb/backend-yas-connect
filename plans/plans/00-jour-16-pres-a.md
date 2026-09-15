# Jour 16 — PRES-A (présence temps réel)

**Statut :** clos (2026-09-14).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–15 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 15](00-jour-15-prof-c.md)).  
**Livré :** liveness cache `presence:{id}` ; `effective_status` ; PATCH `/me/presence` ; POST heartbeat ; WS `/ws/v1/presence` ; `status_message` ; enum `AWAY` / `IN_MEETING`. Login **≠** pastille.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §2 — *statut en ligne*) :


| Fonction MVP                         | Ticket   | Statut                                     |
| ------------------------------------ | -------- | ------------------------------------------ |
| Fiche / prefs / masques              | PROF-A/B/C | **fait** (jours 13–15)                   |
| **Pastille online / away / last_seen live** | **PRES-A** | **fait** (ce jour)                    |
| People-picker `GET /users`           | ANNUAIRE-A | [jour 17](00-jour-17-annuaire-a.md)      |


**À quoi ça sert (MVP) :** jean ouvre l’app → pastille verte **seulement** tant que le socket (ou le ping REST) vit. Login seul = gris. Marie en `NOBODY` : jean ne voit ni pastille ni `status_message` (GET **et** WS). `last_seen` n’est plus uniquement `last_login`.

**Plan métier (code à coller) :** [PRES-A-presence.md](iam_plans/PRES-A-presence.md) (PRES-01 … 16).  
Chemins lab = ce fichier (`views/presence.py`, `services/presence_service.py`, `apps/realtime/` — **pas** `views_presence.py` à la racine IAM).

**Déjà en base / code (avant ce jour) :**

- `users.status` : `varchar(16)`, défaut `OFFLINE` ; TextChoices `ONLINE` / `OFFLINE` seulement
- `GET /me` : `status` = colonne PG ; `last_seen` = `last_login` ; **pas** de `last_login` / `badge` / `connection`
- `GET /users/{id}` : `status` déjà masqué PROF-25 ; **pas** de `badge` / `status_message` / `last_login`
- AUTH-60 heartbeat session : debounce 60 s, **ne pose pas** `users.status`
- `complete_login` : **ne pose pas** ONLINE
- Cache Django : Redis si `REDIS_URL`, sinon LocMem (pytest)
- ASGI = HTTP Django seulement (pas Channels)
- USER a déjà `iam.presence.update` / `heartbeat` et `iam.profile.read`

**Pas encore (avant ce jour) :** `PATCH /me/presence`, `POST /me/presence/heartbeat`, WS `/ws/v1/presence`, `status_message`, enum `AWAY` / `IN_MEETING`, `apps.realtime`.

**Livré (code) :** liveness cache `presence:{id}` TTL 90 s ; `effective_status` + `badge` ; GET `/me` (`connection`, `availability`, `last_login` soi) ; GET collègue `badge` / `status_message` si PROF-25 ; PATCH `/me/presence` ; POST heartbeat ; WS `/ws/v1/presence` ; hooks `on_call_*` ; seed `presence.*` ; Channels InMemory si pas de Redis. Login **≠** pastille. `public_user` **inchangé**.

**Objectif du jour (fait) :**

1. Liveness Redis (cache) : connect WS / ping REST = clé `presence:{id}` TTL 90 s. Login **reste** OFFLINE tant qu’il n’y a pas de ping.
2. `effective_status` (ticket) + `badge` ; GET `/me` enrichi (`connection`, `availability`, `last_login` soi) ; GET collègue : `badge` + `status_message` **seulement** si `status` visible.
3. `PATCH /me/presence` : message 0–140 ; seul `status=ONLINE` settable (clear sticky). AWAY/OFFLINE/IN_MEETING/BUSY/DND/IN_FIELD → 400.
4. WS `/ws/v1/presence` : JWT, portes AUTH-F, PING/PONG, WATCH max 100, `USER_STATUS_CHANGED` filtré PROF-25.
5. Hook interne `on_call_started` / `on_call_ended` (pas d’app `calls`). Seed `presence.*`. Migration **additive** `status_message` seulement.

**Hors jour 16 :** ANNUAIRE-A people-picker, `CALL_STARTED` réel, typing WS, push FCM, liste d’amis, `status_until` / reaper, BUSY/DND/IN_FIELD, MOB-PUSH, recoder PROF-C privacy / AUTH-H idle.

---



## Pourquoi ce jour (après PROF-C)

Les masques existent, mais `users.status` ne bouge **jamais** : tout le monde est OFFLINE en PG après login. Sans Redis + WS, le critère « pastille en ligne » est faux. PROF-25 doit aussi filtrer l’event WS, pas seulement GET.

```text
JWT + HasPermission + portes AUTH-F (après CGU + wizard)
    PATCH  /me/presence                 iam.presence.update
    POST   /me/presence/heartbeat       iam.presence.heartbeat
    WS     /ws/v1/presence              iam.profile.read
    GET    /me  + /users/{id}           deltas présence (perms déjà là)

Déjà là (ne pas casser)
    GET /me prefs + privacy + editable + gates
    GET /users/{id} masque 23–25
    AUTH-60 heartbeat session (pas de pastille)
    complete_login sans write status
```

---



## Paliers (figés pour ce jour)


| Sujet | Choix jour 16 | Plus tard |
| ----- | ------------- | --------- |
| Login vs pastille | `complete_login` / AUTH-H / AUTH-60 **ne** posent **pas** ONLINE | — |
| Store liveness | **Cache Django** (`presence:{id}`). Redis si `REDIS_URL`, LocMem en pytest. Pas de client Redis à part | channel layer Redis en prod |
| Channel layer | `InMemoryChannelLayer` si `REDIS_URL` vide ; `RedisChannelLayer` sinon | — |
| Enum PG | Ajouter `AWAY` / `IN_MEETING` au **TextChoices**. Colonne **reste** `varchar(16)` (tient `IN_MEETING`) | — |
| `status_message` | **Migration additive** `varchar(140)` défaut `''`. Pas de `status_until` | — |
| Sticky | Seul `IN_MEETING` en PG. Autres : effective calculée. Dropout Redis → les **autres** voient OFFLINE ; **soi** : `availability` encore `IN_MEETING` | appel réel jour 26 |
| Away | Clé encore là et `at` plus vieux que `presence.away_after_seconds` (défaut **300**) | — |
| Offline | Clé absente (TTL ou last socket). **Pas** de write PG massif | — |
| GET `/me` `status` | **Effective soi** (ticket). Ajouter `connection`, `availability`, `badge`, `status_message`, `last_login` | — |
| GET collègue | `status` + `badge` + `status_message` (message **seulement** si status non null). **Pas** `connection` / `availability` / `last_login` | — |
| `last_seen` | `max(presence.at, sessions.last_activity max)` sinon `last_login`. Privacy 23 inchangée | — |
| PATCH `status` | Seul `ONLINE` (clear sticky). `AWAY`/`OFFLINE` → 400 `STATUS_NOT_SETTABLE`. `IN_MEETING` → 400 `STATUS_RESERVED`. `BUSY`/`DND`/`IN_FIELD` → 400 `STATUS_UNKNOWN` | — |
| `status_until` | 400 `FIELD_UNKNOWN` | — |
| Autre extra PATCH | 400 `UNKNOWN_FIELD` | — |
| Message | 0–140, trim ; `""` = clear ; 141 → 400 `VALIDATION_ERROR` | — |
| WS JWT | Query `token=` **ou** header `Authorization: Bearer` (même decode que HTTP). 4401 si KO | — |
| Portes WS | CGU + wizard **dans le consumer** (pas DRF). 4403 `TOS_REQUIRED` / `ONBOARDING_REQUIRED` | — |
| Watch | Max **100** uuids. Groupes Channels `presence.watch.{target_id}` | — |
| Compte sockets | Cache `presence:conns:{id}` : disconnect **dernier** socket → DEL liveness | — |
| Privacy WS | Même matrice PROF-A/C. Event `status=null`, `badge=null`, **pas** de `status_message` | — |
| Login JSON | `public_user` **inchangé** (pas de badge / connection / last_login) | — |
| AUTH-H | Inchangé. Ping PRES **peut** `touch_last_activity` (debounce 60 s déjà) | — |
| Hook appels | `on_call_started` / `on_call_ended` publics. **0** route calls | jour 26 |
| Audit | `PRESENCE_SET` sur PATCH message / clear sticky | — |


Perms déjà seedées : `iam.presence.update` / `iam.presence.heartbeat` (self USER). WS lecture = `iam.profile.read`.

---



## 1. Tables

**1 migration additive** : `users.status_message` (`varchar(140)`, défaut `''`).  
**Pas** d’alter `status` (largeur 16 suffisante). **Interdit :** `docker compose down -v`.

`audit_logs.action` : `PRESENCE_SET`.  
Pas de job `presence_until_reaper`.

---



## 2. Settings + seed + paquets

`requirements/base.txt` :

```text
channels>=4.2,<5.0
daphne>=4.1,<5.0
channels-redis>=4.2,<5.0
```

`INSTALLED_APPS` : `daphne` **avant** `django.contrib.staticfiles` ; `channels` ; `apps.realtime`.  
`ASGI_APPLICATION = "config.asgi.application"`.

`CHANNEL_LAYERS` : InMemory si `REDIS_URL` vide, sinon Redis (`hosts` depuis l’URL). Même règle que `CACHES` : **pas** d’import Redis au boot si URL vide.

`python manage.py seed_config` : upsert

| category | setting_key | value | type |
|----------|-------------|-------|------|
| `presence` | `heartbeat_seconds` | `30` | int |
| `presence` | `redis_ttl_seconds` | `90` | int |
| `presence` | `away_after_seconds` | `300` | int |

Pas de nouvelle clé `.env`. Tests : défauts si ligne absente (comme `job_title_self_edit`).

---



## 3. Algo (à coller dans `presence_service`)

```
live = cache presence:{id} existe
age = now - redis.at
if not live:
    effective = OFFLINE
elif users.status == IN_MEETING:
    effective = IN_MEETING
elif age > away_after_seconds:
    effective = AWAY
else:
    effective = ONLINE
```

GET `/me` :

| Champ | Sens |
|-------|------|
| `connection` | ONLINE / AWAY / OFFLINE (**liveness**, ignore sticky) |
| `availability` | `users.status` PG (sticky, souvent OFFLINE ou IN_MEETING) |
| `status` | si live : effective ; si pas live : **OFFLINE** (même si availability IN_MEETING) |
| `badge` | table PRES-16 sur `status` |
| `last_login` | `users.last_login` (PRES-10, **soi**) |
| `last_seen` | PRES-09 |

GET collègue : `status` = effective **si** PROF-25 visible, sinon `null`. `badge` idem. `status_message` seulement si `status` non null.

Badge : ONLINE `green` · AWAY `orange` · IN_MEETING `purple` · OFFLINE `grey` · masqué `null`.

---



## 4. HTTP / WS

Arborescence `views/` / `urls/me.py`. `path("presence/heartbeat")` **avant** `path("presence")`.


| Fichier | Rôle |
| ------- | ---- |
| `apps/iam/services/presence_service.py` | **nouveau.** cache, effective, last_seen, PATCH, hooks appel |
| `apps/iam/views/presence.py` | PATCH + POST heartbeat |
| `apps/iam/serializers/presence.py` | body PATCH + envelopes OpenAPI |
| `apps/realtime/` | **nouvelle app** 0 modèle : `consumers.py`, `routing.py` |
| `config/asgi.py` | `ProtocolTypeRouter` HTTP + WS `URLRouter` |
| `apps/iam/services/profile_service.py` | **delta** serialize_me / serialize_colleague (pas recoder le masque 23–25) |
| `apps/iam/tests/test_pres_a.py` | **nouveau.** |


| Méthode | Chemin | Perm |
| ------- | ------ | ---- |
| PATCH | `/api/v1/me/presence` | `iam.presence.update` |
| POST | `/api/v1/me/presence/heartbeat` | `iam.presence.heartbeat` |
| WS | `/ws/v1/presence` | `iam.profile.read` |

**PATCH `/me/presence` 200** — même forme présence que le bloc user GET `/me` (status, connection, availability, badge, status_message, last_seen, last_login).  
Body partiel ≥ 1 clé parmi `status`, `status_message`.

**POST heartbeat 200** `{ "at": "<iso>" }`. Refresh cache. `touch_last_activity` (debounce AUTH-H).

**WS** (JSON) :

| Direction | Type | Body |
|-----------|------|------|
| C→S | `PING` | `{}` |
| S→C | `PONG` | `{ "at" }` |
| C→S | `WATCH` | `{ "user_ids": ["…"] }` max 100 |
| C→S | `UNWATCH` | `{ "user_ids": ["…"] }` |
| S→C | `USER_STATUS_CHANGED` | `{ "user_id", "status", "badge", "status_message" }` |

Connect → SET liveness + si availability OFFLINE → PG `ONLINE` (disponible, pas sticky réunion).  
Last disconnect → DEL liveness + event OFFLINE (si visible).

---



## 5. Impact tests existants


| Fichier | Adapter |
| ------- | ------- |
| `test_prof_a.py` | Collègue **toujours sans** `last_login` / `connection` / `availability`. `status` NOBODY encore `null`. `last_seen` encore masqué. GET `/me` **garde** prefs/privacy/editable |
| `test_prof_b.py` | Inchangé (prefs) |
| `test_prof_c.py` | Inchangé (privacy HTTP) |
| `test_auth_f.py` | GET `/me` bloc privacy **reste** |
| `test_auth_h.py` | AUTH-60 **ne** pose **pas** `users.status` |


Portes : GET/PATCH présence **fermées** (`close_gates`) comme `/me/preferences`.  
WS tests : `channels.testing.WebsocketCommunicator` + `InMemoryChannelLayer` (pas besoin de Redis Docker).

---



## 6. Tests nouveaux (`test_pres_a.py`)


| ID | Cas | Attendu |
| -- | --- | ------- |
| 01 | login sans WS / sans heartbeat | PG OFFLINE ; GET `/me` `connection=OFFLINE` ; collègue OFFLINE/`grey` (si visible) |
| 01 | POST heartbeat | cache ; GET `/me` `status=ONLINE` `badge=green` |
| 02 | last WS close | cache del ; effective OFFLINE |
| 03 | 2e heartbeat < 60 s | 0 ou 1 write `sessions.last_activity` |
| 03 | AUTH-60 | `users.status` **inchangé** par le heartbeat session |
| 04 | clé présente, `at` vieux de 6 min | effective AWAY / `orange` |
| 05 | PATCH `BUSY` / `DND` / `IN_FIELD` | 400 `STATUS_UNKNOWN` |
| 05 | PATCH `AWAY` / `OFFLINE` | 400 `STATUS_NOT_SETTABLE` |
| 07 | `on_call_started` | PG `IN_MEETING` ; live → `purple` ; pas live → collègue OFFLINE, soi `availability=IN_MEETING` |
| 07 | PATCH `IN_MEETING` | 400 `STATUS_RESERVED` |
| 07 | `on_call_ended` + live | effective ONLINE |
| 09 | `last_seen` | ≥ `last_activity` session après ping |
| 10 | GET `/me` a `last_login` ; GET collègue **sans** |
| 11 | message 141 car. | 400 `VALIDATION_ERROR` |
| 12 | PATCH `status_until` | 400 `FIELD_UNKNOWN` |
| 14 | watcher WS reçoit event | `badge` + `status` |
| 15 | cible `online_status_visibility=NOBODY` | GET + event : `status=null`, `badge=null`, pas de message |
| 15 | CONTACTS autre segment | idem null |
| 16 | mapping couleurs | table PRES-16 |
| — | GET présence avant wizard | 403 TOS puis `ONBOARDING_REQUIRED` |
| — | WS sans JWT | 4401 |
| — | sans `iam.presence.update` | 403 `FORBIDDEN` |
| — | sans JWT HTTP | 401 |
| — | `/api/schema/` | contient `/me/presence` |


Helper MFA : `login_until_jwt`. Portes : `close_gates`.

Régression : PROF-A/C masque + AUTH-H heartbeat session.

---



## 7. Vérif manuelle

```powershell
python manage.py check
python manage.py migrate
python manage.py seed_config
pytest apps/iam/tests/test_pres_a.py apps/iam/tests/test_prof_a.py apps/iam/tests/test_prof_c.py apps/iam/tests/test_auth_h.py --reuse-db
```

Login jean **sans** ouvrir le WS → GET `/me` `connection=OFFLINE`.  
`POST /me/presence/heartbeat` → `green`.  
Marie PATCH privacy `online_status_visibility=NOBODY` → jean GET `/users/{marie}` `status`/`badge` null.  
`/admin/` cookie : **pas** ces routes.

Runserver **ASGI** (`daphne`) pour le WS manuel ; `runserver` WSGI ne sert pas `/ws/`.

---



## Checklist jour 16

- [x] Migration `status_message` ; enum AWAY / IN_MEETING ; 0 `down -v`
- [x] Cache liveness ; login ≠ ONLINE
- [x] GET `/me` + collègue (badge, last_seen PRES-09, last_login soi)
- [x] PATCH présence + heartbeat REST
- [x] WS JWT + portes + WATCH + event filtré PROF-25
- [x] Hook `on_call_*` (tests service)
- [x] `seed_config` `presence.*` ; Channels InMemory si pas de Redis
- [x] `test_pres_a.py` + régression A/C/H
- [x] SIRH non modifié

---



## Interdits

- Recoder PROF-A masque / PROF-C PATCH privacy
- Poser ONLINE dans `complete_login` ou AUTH-60
- Coder ANNUAIRE-A / appels LiveKit / typing / push
- `status_until`, job reaper, BUSY/DND/IN_FIELD
- Exposer `last_login` / `connection` / `availability` sur GET collègue
- `docker compose down -v`
- Changer le SIRH

---



## Après le jour 16

Jour 17 : [00-jour-17-annuaire-a.md](00-jour-17-annuaire-a.md) — **ANNUAIRE-A** (people-picker `GET /users`).

---



## Calendrier des plans de jours (MVP sonnant)

Cadence actuelle : **1 ligne** [A→Z §4.1](00-application-A-Z.md) = **1 plan de jour**. Le jour 2 (admin + Swagger) est un extra déjà clos.


| Jours  | Plan                                           | Ticket MVP                          |
| ------ | ---------------------------------------------- | ----------------------------------- |
| 0      | [00-creer-le-projet.md](00-creer-le-projet.md) | Socle Django / Postgres / `/health` |
| 1–2    | AUTH-A ; admin + Swagger                       | Connexion locale ; lab admin        |
| 3–11   | D+B … AUTH-R                                   | §1 entrer + droits HTTP             |
| 12     | ADMIN-A                                        | §9 comptes                          |
| 13     | PROF-A                                         | §2 ma fiche / photo                 |
| 14     | PROF-B                                         | Préférences                         |
| 15     | PROF-C                                         | §2 visibilité                       |
| **16** | **PRES-A** (ce plan)                           | §2 statut en ligne                  |
| 17     | ANNUAIRE-A                                     | §3 recherche collègue               |
| 18     | ANNUAIRE-B                                     | §3 organigramme (types + arbre)     |
| 19     | ANNUAIRE-C                                     | §3 mutations / affectations         |
| 20     | ANNUAIRE-D                                     | §3 compétences / certifications     |
| 21     | CRYPTO-00                                      | §6 décision E2E                     |
| 22     | MEDIA-R + MEDIA-A                              | §4 upload (plafonds ; pas de reprise) |
| 23     | NOTIF-R + NOTIF-A                              | §5 alertes + MOB-PUSH (VoIP / worker) |
| 24     | CRYPTO-R + CRYPTO-A                            | Clés HTTP                           |
| 25     | MESSAGERIE-R, A, B                             | §7 1-to-1                           |
| 26     | MESSAGERIE-C, D                                | §7 groupes + temps réel             |
| 27     | MESSAGERIE-E (partiel), F, G                   | §7 enrichissements                  |
| 28     | MEDIA-B, C, D, E                               | §4 album / vocal / coffre           |
| 29     | APPELS-R, A, B, C                              | §8 appel 1-1 + `CALL_CANCELLED`     |
| 30     | APPELS-D, E, G                                 | §8 écran / CR                       |


**Total : 31 plans (jours 0 à 30).**  
Déjà clos : **17** (0–16). Restant : **14** (17–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.
