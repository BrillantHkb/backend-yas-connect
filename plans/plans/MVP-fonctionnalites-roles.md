# YAS Connect — Les fonctions de la première version, à quoi elles servent

Ce document décrit **chaque fonction** de la première version de l’app, et **le rôle qu’elle joue** pour l’utilisateur.  
Ce n’est pas une liste de droits informatiques : c’est « à quoi ça sert dans la vraie vie ».

**But de cette version :** pouvoir écrire à un collègue, lui envoyer un fichier, et **être joint au téléphone même si l’app est fermée**.

---

## 1. Entrer dans l’application

| Fonction | À quoi ça sert |
|----------|----------------|
| Connexion identifiant + mot de passe | Ouvrir l’app avec le compte YAS Connect (comme une messagerie d’entreprise). |
| Connexion compte Windows / Active Directory | Les gens déjà dans l’annuaire informatique de YAS n’ont pas un second « univers » : ils prouvent qui ils sont avec le même compte bureau. |
| Scanner le QR Google Authenticator | **Première fois seulement.** Lier **Google Authenticator** au compte (`otpauth://`). Tant que ce QR n’est pas scanné **et** validé, on n’entre pas dans l’app. |
| Valider avec le code Authenticator (6 chiffres) | Prouver que c’est bien **votre** Google Authenticator. Sans ce code, identifiant + mot de passe ne suffisent pas. À **chaque** nouvelle connexion ensuite (plus de QR Authenticator). |
| Inscription avec compte Windows | Un nouvel arrivant qui a déjà un compte entreprise crée lui-même son accès à Connect, sans attendre un formulaire papier. |
| Inscription sans compte Windows | Permettre à quelqu’un hors Active Directory de demander un accès ; un responsable valide avant qu’il puisse entrer. |
| Mot de passe oublié (via Authenticator) | Récupérer l’accès **sans e-mail** : le code est déjà dans l’app Authenticator, plus sûr en terrain / hors réseau mail. |
| Changer son mot de passe | L’utilisateur maîtrise son secret, sans passer par l’informatique pour un changement simple. |
| Déconnexion (un appareil ou tous) | Couper l’accès si on quitte un ordi partagé, ou si un téléphone est perdu. |
| Historique de mes connexions | Vérifier soi-même : « ce n’était pas moi à Lomé hier soir ». |
| Compte verrouillé après trop d’essais | Freiner les tentatives de piratage ; un responsable peut rouvrir le compte. |
| Conditions d’utilisation + premier paramétrage | S’assurer que la personne a accepté les règles, et que l’app parle sa langue / son fuseau dès le premier jour. |

---

## 2. Mon profil et mes appareils

| Fonction | À quoi ça sert |
|----------|----------------|
| Ma fiche (nom, photo…) | Me reconnaître dans l’annuaire et dans le chat, comme une carte de visite interne. |
| Fiche d’un collègue | Savoir à qui j’écris avant d’appeler : nom, photo, service (selon ce qu’il a choisi de montrer). |
| Réglages de visibilité | Choisir si les autres voient ma photo, si je suis en ligne, si on a le droit de m’appeler. |
| Statut (disponible, absent, en réunion, hors ligne) | Éviter d’appeler quelqu’un déjà en réunion, ou de croire qu’il ignore volontairement. |
| Liste de mes téléphones et ordis | Savoir où mon compte est ouvert ; détecter un appareil inconnu. |
| Nommer un appareil | S’y retrouver (« iPhone perso » vs « PC bureau »). |
| Déconnecter un appareil | Couper tout de suite un téléphone perdu, sans changer de mot de passe. |
| Alerte « nouvel appareil » | Prévenir : quelqu’un vient d’entrer sur votre compte depuis une machine que vous n’aviez pas encore. |
| Relier un ordi / autre écran par QR | Ouvrir Connect sur un PC sans retaper le mot de passe : l’ordi affiche un QR, le téléphone déjà ouvert le scanne. |
| Confirmer le lien avec Google Authenticator | Après le scan, un code à 6 chiffres est **exigé**. Le scan tout seul ne connecte pas l’ordi (ce n’est pas le QR Authenticator de la 1re connexion). |

Deux QR différents : (1) **Google Authenticator** à la première connexion ; (2) **lier un 2ᵉ appareil**, scanné par l’app Connect, puis code Authenticator.

---

## 3. Annuaire — trouver un collègue

| Fonction | À quoi ça sert |
|----------|----------------|
| Recherche par nom | Démarrer un message ou un appel sans connaître le numéro ni l’e-mail : on cherche « Dupont ». |
| Listes région / service à l’inscription | Ranger la personne dans l’organisation YAS dès le départ (pas un compte « flottant »). |

**Pas encore :** modifier l’organigramme, muter les gens, coller diplômes et compétences.

---

## 4. Photos et fichiers

| Fonction | À quoi ça sert |
|----------|----------------|
| Joindre une photo ou un fichier au message | Envoyer un schéma, une photo terrain, un PDF, sans passer par WhatsApp perso. |
| Photo de profil | Reconnaître les gens dans la liste, pas seulement un nom. |
| Ouvrir / télécharger un fichier de la conversation | Relire plus tard ce qui a été partagé dans le fil. |
| Supprimer un fichier que j’ai envoyé | Retirer une pièce jointe envoyée par erreur (dans la limite de ce que l’app autorise). |
| Contrôle antivirus | Éviter qu’un document piégé circule dans l’entreprise. Un fichier dangereux ne s’ouvre pas. |
| Album photo | Revoir ses photos (aperçu, miniature) sans tout retélécharger en original. |
| Conversion vidéo | Envoyer une vidéo terrain : l’app la prépare pour qu’elle se lise sur téléphone, même avec un réseau moyen. |
| Dictée / message vocal | Parler au lieu d’écrire (mains occupées) ; le texte peut s’afficher à côté pour relire sans réécouter. |
| Coffre-fort documentaire | Ranger les PDF / Word d’équipe (procédures, PV) avec versions, pas seulement en pièce jointe de chat. |

## 5. Notifications — l’app me prévient

| Fonction | À quoi ça sert |
|----------|----------------|
| Liste d’alertes dans l’app | Retrouver ce que j’ai manqué (message, appel, nouvel appareil) sans fouiller dans chaque conversation. |
| Pastille « non lus » | Savoir d’un coup d’œil s’il faut ouvrir l’app. |
| Marquer comme lu | Faire le ménage : ce n’est plus urgent. |
| Couper le son, heures de silence, sonnerie d’appel | Travailler la nuit / sur le terrain sans être réveillé pour un message, tout en pouvant encore être **sonné** pour un appel si on le souhaite. |
| Alerte téléphone même app fermée | C’est le cœur du produit : un message ou un appel arrive comme sur WhatsApp, pas seulement si l’écran est ouvert. |

Sur un **message privé**, l’écran de verrouillage dit seulement « Nouveau message » : le texte n’est pas affiché (secret).

---

## 6. Secret des messages — le rôle de la « serrure »

Ce n’est pas un bouton que l’utilisateur règle. Ça explique **pourquoi** deux discussions ne se comportent pas pareil.

| Situation | Rôle |
|-----------|------|
| Discussion **à deux** | Comme une lettre cachetée. Seuls les deux téléphones lisent le texte. L’entreprise transporte le paquet, elle ne l’ouvre pas. |
| **Groupe** d’équipe | Comme un casier partagé. Les membres lisent. L’entreprise **peut** ouvrir le casier si besoin (litige, signalement, sécurité). |

Sans cette distinction : soit tout le monde (y compris le serveur) lit tout, soit on ne peut plus contrôler un groupe. Les deux cas existent, chacun a son rôle.

---

## 7. Messagerie

| Fonction | À quoi ça sert |
|----------|----------------|
| Liste des conversations | Voir d’un coup avec qui on a parlé, le plus récent en haut. |
| Chat à deux | Échanger en privé, comme un SMS interne chiffré. |
| Groupe | Parler à une équipe (NOC, agence, projet) sans créer dix discussions séparées. |
| Envoyer du texte | Le besoin de base : poser une question, donner une consigne. |
| Joindre un fichier | Appuyer le texte (photo d’un équipement, PDF). |
| Modifier / supprimer un message | Corriger une faute ou retirer une info envoyée trop vite. |
| Mettre en sourdine | Garder le fil sans être notifié à chaque ligne (groupe bruyant). |
| Archiver | Ranger une conversation finie, sans la détruire. |
| Épingler | Garder le fil important (astreinte, chef) en haut de liste. |
| Doubles coches (envoyé / lu) | Savoir si le collègue a vu le message — utile en urgence. |
| Message en direct | Voir arriver la réponse sans rafraîchir l’écran. |
| Réaction emoji | Répondre d’un tap (« OK », « vu ») sans écrire un message. |
| Transférer | Renvoyer un message dans un autre fil, sans le retaper. |
| Sondage | Trancher à plusieurs (qui vient, quel créneau) sans dix messages « +1 ». |
| Favoris | Retrouver plus tard un message important (consigne, numéro, photo terrain). |
| Bloquer quelqu’un | Ne plus recevoir ses privés ni ses appels. |
| « En train d’écrire… » | Savoir que l’autre compose, avant que le message arrive. |

### Dans un groupe — le rôle de chacun **dans ce fil**

Ce n’est pas le grade dans l’entreprise. C’est « qui tient ce groupe ».

| Rôle dans le groupe | À quoi ça sert |
|---------------------|----------------|
| **Propriétaire** | Il y a un responsable du groupe : c’est lui qui l’a créé. On ne laisse pas un groupe orphelin. |
| **Admin du groupe** | Déléguer : quelqu’un d’autre peut ajouter des membres ou changer le nom, sans être le créateur. |
| **Membre** | Participer normalement (lire et écrire). |
| **Lecture seule** | Diffuser une consigne (mode annonce) sans que tout le monde réponde par-dessus. |

---

## 8. Appels

| Fonction | À quoi ça sert |
|----------|----------------|
| Appel audio ou vidéo à un collègue | Remplacer le GSM perso / le « tu es où ? » pour un sujet interne. |
| Petite réunion | À plusieurs sans outil visio externe pour un point court. |
| Décrocher / refuser / raccrocher | Contrôler l’appel comme un téléphone classique. |
| Couper micro ou caméra | Parler en open-space ou couper l’image. |
| Liste des participants | Savoir qui est dans l’appel. |
| Inviter ou faire sortir (organisateur) | Garder la réunion cadrée. |
| Sonnerie app fermée | Être joint vraiment, pas seulement si on a l’écran ouvert. |
| Statut « en réunion » | Les autres voient que vous êtes déjà au téléphone — moins de double appel. |
| Historique de mes appels | Retrouver qui a appelé, un appel manqué. |
| Partage d’écran | Montrer son bureau ou une appli pendant l’appel (consigne, ticket, carte) — un partage à la fois par personne. |
| Enregistrement | Garder l’appel pour ceux qui n’étaient pas là, ou pour une preuve interne. L’organisateur le lance ; les participants sont prévenus. |
| Compte-rendu automatique | Après une réunion : texte de ce qui s’est dit + un résumé, pour ne pas tout réécrire. |

## 9. Côté entreprise (administration des comptes)

Ces fonctions ne sont pas le chat. Elles servent à **faire vivre les identités**, pour que le reste de l’app ait des gens réels derrière.

| Fonction | À quoi ça sert |
|----------|----------------|
| Liste des comptes | Voir qui a accès à Connect. |
| Créer un compte | Onboarder quelqu’un qui n’a pas Windows. |
| Activer / désactiver un compte | Couper l’accès d’un départ, sans toucher au compte Windows s’il est géré ailleurs. |
| Imposer un mot de passe | Débloquer un collègue qui ne peut plus entrer. |
| Déconnecter quelqu’un de partout | Urgence : téléphone volé, départ brutal. |
| Journal d’activité | Comprendre après coup qui a ouvert un compte, pas lire les messages privés. |
| Régions (Maritime, Plateaux…) | Filtrer et ranger les gens par zone du Togo. |
| Qui est administrateur | Limiter le nombre de personnes qui peuvent tout ça. |
| Accepter une inscription en attente | La porte d’entrée pour les gens hors Active Directory. |

---

## 10. Volontairement absent (pour plus tard)

Pas oublié : **reporté** pour d’abord faire sonner le téléphone et faire passer un fichier.

- Fil d’actualité / réseau social interne  
- Canaux d’astreinte, salle de crise  
- Assistant intelligent  
- Organigramme éditable, compétences, diplômes  
- Signaler un message / file de modération  
- Mentions @, localisation sur carte, épingler un message dans le fil  

---

## En une phrase

Chaque fonction a **un job** : **entrer en confiance**, **trouver la bonne personne**, **écrire ou appeler**, **être prévenu les mains dans le cambouis**, **sans que l’entreprise lise vos privés**.
