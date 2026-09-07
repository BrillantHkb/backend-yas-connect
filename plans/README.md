# YAS Connect — dossier de conception

Ce dossier contient les **plans et spécifications** de la future application **YAS Connect**.  
Ce n’est **pas** le code de `backend-gestion-personnel-yas` (SIRH). Les deux produits restent séparés.

Backend figé : **Python + Django + Django REST Framework**.

**Fermer le MVP** = socle transverse (notif, crypto, ordre Media/Chat, scan, mail) pour que IAM → Annuaire-A → Messagerie → Médias → Appels tiennent en conditions réelles. **Pas** un 6ᵉ module (Social / Canaux / IA).

**Créer le repo Django :** [plans/00-creer-le-projet.md](plans/00-creer-le-projet.md) (versions, venv, PostgreSQL, jour 0).  
Socle détaillé + ordre de livraison : [plans/00-application-A-Z.md](plans/00-application-A-Z.md).

| Fichier | Contenu |
|---------|---------|
| [plans/00-creer-le-projet.md](plans/00-creer-le-projet.md) | Créer le projet : Python/Django/DRF, dépendances, Docker, `DATABASE_URL`, checklist `/health` |
| [plans/00-application-A-Z.md](plans/00-application-A-Z.md) | Socle A→Z, settings à coller, phases MVP, scan/SMTP, critères de fermeture |
| [plans/MVP-fonctionnalites-roles.md](plans/MVP-fonctionnalites-roles.md) | Chaque fonction MVP expliquée : à quoi elle sert (langage métier) |
| [plans/crypto_plans/CRYPTO-00-modele-chiffrement.md](plans/crypto_plans/CRYPTO-00-modele-chiffrement.md) | Décision : E2E 1-to-1 (Signal) / cloud groupes |
| [plans/crypto_plans/CRYPTO-A-cles.md](plans/crypto_plans/CRYPTO-A-cles.md) | Contrat HTTP des clés + [routes](plans/crypto_plans/CRYPTO-routes.md) (6) |
| [catalogues/](catalogues/) | Attributs (IAM, Config, Annuaire, Médias, Messagerie, Appels, Notif, **Crypto**) |
| [catalogues/INDEX-catalogue.md](catalogues/INDEX-catalogue.md) | Index PostgreSQL btree / GIN |
| [plans/iam_plans/](plans/iam_plans/) | AUTH-A…J, AUTH-R, PROF, PRES, ADMIN + [IAM-routes](plans/iam_plans/IAM-routes.md) (86) |
| [plans/annuaire_plans/](plans/annuaire_plans/) | A picker → D skills + [ANNUAIRE-routes](plans/annuaire_plans/ANNUAIRE-routes.md) (38) |
| [plans/media_plans/](plans/media_plans/) | R, A upload → F quotas + [MEDIA-routes](plans/media_plans/MEDIA-routes.md) (34) |
| [plans/notif_plans/](plans/notif_plans/) | R, A in-app+push + [NOTIF-routes](plans/notif_plans/NOTIF-routes.md) (6) |
| [plans/messaging_plans/](plans/messaging_plans/) | R, A→G + [MESSAGERIE-routes](plans/messaging_plans/MESSAGERIE-routes.md) (52) |
| [plans/calls_plans/](plans/calls_plans/) | R, A→G + [APPELS-routes](plans/calls_plans/APPELS-routes.md) (36) |
| [plans/code/](plans/code/) | Modèles Django à coller (`*_models.py`) |
| [plans/diagrams/02-annuaire-users.mmd](plans/diagrams/02-annuaire-users.mmd) | ER Mermaid annuaire ↔ `users` |

Les générateurs `generate_yas_connect_tome*.py` produisent les tomes Word de vision / architecture (Documents personnels).
