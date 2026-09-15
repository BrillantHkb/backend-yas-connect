# Jour 21 — CRYPTO-00 (décision de modèle de chiffrement)

**Statut :** clos (2026-09-15).  
**Produit :** YAS Connect. **Dépôt :** `backend-yas-connect`.  
**Préalable :** jours 0–20 **clos** ([jour 1](00-jour-1-auth-a.md) … [jour 20](00-jour-20-annuaire-d.md)).  
Chapitre **Annuaire (§3) fermé** depuis le jour 20. Aucune app `messagerie` / `crypto` / `media_encryption` / `notif` n'existe encore dans `apps/` — ce jour ne crée ni table, ni app, ni endpoint.

**MVP** ([MVP-fonctionnalites-roles.md](MVP-fonctionnalites-roles.md) §6 — *secret des messages, rôle de la « serrure »*) :

| Fonction MVP                              | Ticket    | Statut      |
| ------------------------------------------ | --------- | ----------- |
| Compétences / certifications (Annuaire)    | ANNUAIRE-D | **fait** (jour 20) |
| **Qui tient les clés : 1-to-1 vs groupe**  | **CRYPTO-00** | **ce jour** |
| Bundles de clés HTTP                       | CRYPTO-A  | jour 24     |

**À quoi ça sert (MVP) :** avant d'écrire le moindre modèle `messages` (jour 25) ou `media_files` chiffré (jour 22), il faut trancher **une bonne fois** qui a le droit de lire quoi. Sans cette règle figée en premier, chaque module suivant (upload chiffré, notifications, sondages, appels) improviserait sa propre réponse à « le serveur peut-il voir le contenu ? » — et on se retrouverait avec des incohérences (ex. un sondage E2E en 1-to-1, ou une notif push qui fuite le texte). CRYPTO-00 est la référence unique que MEDIA-A, NOTIF-A, CRYPTO-A et MESSAGERIE-* devront respecter sans la rouvrir.

**Plan métier (déjà rédigé, à figer) :** [CRYPTO-00-modele-chiffrement.md](crypto_plans/CRYPTO-00-modele-chiffrement.md). Document déjà marqué **Statut : FIGÉ** dans son en-tête — ce jour est sa **revue de clôture officielle** dans le calendrier des plans (pas une réécriture).

**Déjà en base / code :** rien côté messagerie/crypto/media-chiffrement — ces apps n'existent pas encore. Ce jour ne dépend d'aucun modèle créé aux jours précédents.

**Pas encore :** tout ce que CRYPTO-00 encadre reste à construire : `apps/media` — flag `encrypted` sur `MediaFile` (jour 22, MEDIA-A) ; `apps/notif` — règle « titre/corps génériques en 1-to-1 » (jour 23, NOTIF-A) ; `apps/crypto` — bundles de clés par appareil + `conversation_keys` (jour 24, CRYPTO-A) ; `apps/messagerie` — `messages.encrypted_content`, `conversations.encrypted`, sondages `GROUP` seulement (jours 25+).

**Objectif du jour :**

1. Relire [CRYPTO-00-modele-chiffrement.md](crypto_plans/CRYPTO-00-modele-chiffrement.md) en entier et vérifier qu'il répond sans ambiguïté aux 4 questions qui reviendront dans MEDIA-A / NOTIF-A / CRYPTO-A / MESSAGERIE-* (voir §2 ci-dessous).
2. Vérifier l'alignement avec les catalogues déjà écrits (Messagerie, Médias, Appels — section « Alignement catalogues » du document) : aucune contradiction avec ce qui a déjà été figé aux jours précédents (ANNUAIRE, PROF-C confidentialité, PRES-A présence).
3. Ne **rien coder**. 0 migration, 0 fichier Python, 0 test. Cocher la checklist du jour uniquement sur la base d'une relecture, pas d'une implémentation.
4. Ne rien casser : évidemment sans impact code, mais **ne pas** anticiper CRYPTO-A (jour 24) ni créer de squelette d'app `crypto`/`messagerie` en avance.

**Hors jour 21 :** tout code (CRYPTO-A jour 24, MESSAGERIE-* jours 25+, MEDIA-A jour 22, NOTIF-A jour 23) ; E2E groupes ; sondage E2E 1-to-1 ; sealed sender ; backup seed phrase ; SGX ; search E2E — tous explicitement **hors incrément** dans le document lui-même.

---

## Pourquoi ce jour (avant MEDIA-A / NOTIF-A / CRYPTO-A / MESSAGERIE)

Chronologiquement, jour 22 (MEDIA-A) va poser un flag `encrypted` sur `media_files`, jour 23 (NOTIF-A) va décider ce qu'un payload push a le droit de contenir, jour 24 (CRYPTO-A) va exposer les endpoints de bundles de clés, et jours 25+ (MESSAGERIE) vont créer `messages`/`conversations`. **Chacun de ces jours a besoin que CRYPTO-00 soit déjà tranché** pour ne pas re-débattre la question à chaque fois. C'est pourquoi ce jour est calé juste après la fermeture du chapitre Annuaire et avant tout code transverse.

```text
Aucune route HTTP ce jour (0 code).

CRYPTO-00 encadre par avance :
    MEDIA-A   (jour 22) → MediaFile.encrypted, scan sur ciphertext en 1-to-1
    NOTIF-A   (jour 23) → payload générique 1-to-1, caller_name autorisé
    CRYPTO-A  (jour 24) → bundles clés par appareil + conversation_keys (GROUP/AI)
    MESSAGERIE-* (25+)  → conversations.encrypted, messages.encrypted_content, POLL_PRIVATE_FORBIDDEN
```

---

## Paliers (figés — rappel, ne pas rouvrir)

| Sujet | Choix | Rouvrable ? |
| ----- | ----- | ----------- |
| 1-to-1 (`PRIVATE`) | E2E double ratchet. Serveur ne lit **jamais** le texte. `conversations.encrypted = true` toujours | Non |
| Groupe (`GROUP`) / canal | Chiffrement plateforme (clé de fil serveur). Serveur **peut** déchiffrer (modération, SOC). `encrypted = false` | Non |
| `AI` | Cloud, plateforme lit, logs service IA | Non |
| Sondages | **GROUP seulement**. `PRIVATE` → **400** `POLL_PRIVATE_FORBIDDEN` | Non |
| PJ / avatars 1-to-1 | Chiffrées côté client avant upload ; `media_files.encrypted=true` | Non |
| PJ / avatars groupe | Upload clair (scan, preview) ; `encrypted=false` sauf politique at-rest | Non |
| Notifications 1-to-1 | Titre/corps génériques. Jamais le plaintext dans `payload`. `caller_name` autorisé sur appel | Non |
| Recherche serveur | 1-to-1 : métadonnées seulement. Groupe : texte possible | Non |

Détail complet, tableau des colonnes et justifications : [CRYPTO-00-modele-chiffrement.md](crypto_plans/CRYPTO-00-modele-chiffrement.md).

---

## 1. Tables

**0 migration.** Aucune table créée ni modifiée ce jour — `messages`, `conversations`, `media_files.encrypted`, `conversation_keys` seront posées par leurs jours respectifs (22, 24, 25+).  
**Interdit :** `docker compose down -v`.

---

## 2. Questions auxquelles le document doit déjà répondre (grille de relecture)

| # | Question | Réponse attendue dans CRYPTO-00 |
| - | -------- | -------------------------------- |
| 1 | Le serveur peut-il lire un message 1-to-1 ? | Non, jamais — ni preview, ni STT, ni IA, ni audit |
| 2 | Le serveur peut-il lire un message de groupe ? | Oui, après déchiffrement service (modération/SOC possibles) |
| 3 | Un sondage peut-il exister en 1-to-1 ? | Non — **400** `POLL_PRIVATE_FORBIDDEN` |
| 4 | Une notification push 1-to-1 peut-elle contenir le texte du message ? | Non — titre/corps génériques uniquement |
| 5 | Qui chiffre les PJ en 1-to-1 ? | Le client, avant l'upload — le serveur ne voit que le ciphertext |
| 6 | `CRYPTO-A` gère-t-il des clés par conversation de groupe ? | Oui — `conversation_keys` (GROUP/AI), en plus des bundles par appareil |

Si une de ces 6 réponses n'est pas explicite dans le document → **ne pas fermer ce jour**, corriger le document d'abord (c'est encore permis puisqu'il n'y a pas encore de code qui en dépend).

---

## 3. Vérif manuelle

```powershell
python manage.py check
```

Pas de test à lancer ce jour (aucun code ajouté). La seule vérification est documentaire : relire [CRYPTO-00-modele-chiffrement.md](crypto_plans/CRYPTO-00-modele-chiffrement.md) et confirmer que les 6 questions du §2 ci-dessus ont une réponse sans ambiguïté.

---

## Checklist jour 21

- [x] Document CRYPTO-00 relu en entier, statut `FIGÉ` confirmé
- [x] Les 6 questions du §2 ont toutes une réponse explicite dans le document
- [x] Alignement vérifié avec Messagerie / Médias / Appels (section « Alignement catalogues »)
- [x] Aucune contradiction avec PROF-C (confidentialité) ni PRES-A (présence)
- [x] 0 code, 0 migration, 0 test ajouté
- [x] SIRH non modifié

---

## Interdits

- Coder quoi que ce soit de CRYPTO-A / MEDIA-A / NOTIF-A / MESSAGERIE-* ce jour
- Créer une app `crypto`, `messagerie` ou `notif` en avance
- Rouvrir une décision figée sans raison explicite (E2E groupe, sondage E2E, etc. restent hors incrément)
- `docker compose down -v`
- Changer le SIRH

---

## Après le jour 21

Jour 22 : [00-jour-22-media-r-a.md](00-jour-22-media-r-a.md) — **MEDIA-R + MEDIA-A** (upload de fichiers, plafonds, pas de reprise), premier module à appliquer le flag `encrypted` de CRYPTO-00 sur `media_files`.

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
| **21** | **CRYPTO-00** (ce plan)                         | §6 décision E2E                        |
| 22     | MEDIA-R + MEDIA-A                               | §4 upload (plafonds ; pas de reprise)  |
| 23     | NOTIF-R + NOTIF-A                               | §5 alertes + MOB-PUSH (VoIP / worker)  |
| 24     | CRYPTO-R + CRYPTO-A                             | Clés HTTP                              |
| 25     | MESSAGERIE-R, A, B                              | §7 1-to-1                              |
| 26     | MESSAGERIE-C, D                                 | §7 groupes + temps réel                |
| 27     | MESSAGERIE-E (partiel), F, G                    | §7 enrichissements                     |
| 28     | MEDIA-B, C, D, E                                | §4 album / vocal / coffre              |
| 29     | APPELS-R, A, B, C                               | §8 appel 1-1 + `CALL_CANCELLED`        |
| 30     | APPELS-D, E, G                                  | §8 écran / CR                          |

**Total : 31 plans (jours 0 à 30).**  
Déjà clos : **21** (0–20). Restant : **10** (21–30).

Hors ce compteur (A→Z §4.2) : MEDIA-F, APPELS-F, mentions / modération, social, IA.
