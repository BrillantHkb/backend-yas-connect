# MESSAGERIE-C — Groupes (MSG-41 … 58)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MESSAGERIE-A](MESSAGERIE-A-inbox-conversations.md), [MESSAGERIE-B](MESSAGERIE-B-messages.md), **MEDIA-A** (avatar), [CRYPTO-A](../crypto_plans/CRYPTO-A-cles.md) (`ensure_conversation_key`).  
**Models :** [code/messaging_models.py](../code/messaging_models.py).

**Périmètre :** création groupe, métadonnées, membres, rôles, visibilité, mode annonce, règles, message d’accueil.

---

## Cartographie


| ID         | Statut    | Comportement                                        | Écritures                                            |
| ---------- | --------- | --------------------------------------------------- | ---------------------------------------------------- |
| **MSG-41** | **Gardé** | Créer groupe                                        | `type=GROUP`, `owner_id`, membres initiaux           |
| **MSG-42** | **Gardé** | Modifier titre / description                        | `title`, `description`                               |
| **MSG-43** | **Gardé** | Photo groupe                                        | `avatar_media_id`                                    |
| **MSG-44** | **Gardé** | Ajouter membre                                      | respect `allow_group_invites`                        |
| **MSG-45** | **Gardé** | Retirer membre                                      | par admin ou self si policy                          |
| **MSG-46** | **Gardé** | Quitter groupe                                      | membre quitte                                        |
| **MSG-47** | **Gardé** | Plusieurs ADMIN                                     | `role=ADMIN`                                         |
| **MSG-48** | **Gardé** | OWNER unique ; transfert propriété                  | PATCH role                                           |
| **MSG-49** | **Gardé** | READ_ONLY = annonce seulement pour membres          | pas d’envoi MEMBER                                   |
| **MSG-50** | **Gardé** | Mode annonce : `locked` ou tous MEMBER en READ_ONLY | `conversation_settings`                              |
| **MSG-51** | **Gardé** | Groupe privé `visibility=PRIVATE`                   | invitation uniquement ou ajout administrateur        |
| **MSG-52** | **Gardé** | Groupe public interne `visibility=PUBLIC`           | découvrable annuaire                                 |
| **MSG-53** | **Gardé** | `max_members` plafond                               | refus ajout                                          |
| **MSG-54** | **Gardé** | Message d’accueil                                   | `custom_settings.welcome_message` + SYSTEM optionnel |
| **MSG-55** | **Gardé** | Règles groupe                                       | `custom_settings.rules` texte                        |
| **MSG-56** | **Gardé** | Pseudo dans groupe                                  | `members.username`                                   |
| **MSG-57** | **Gardé** | Historique conservé après leave                     | lecture selon policy (défaut : oui si réinvité)      |
| **MSG-58** | **Gardé** | Groupe temporaire                                   | `custom_settings.expires_at` ; job clôture           |


**Hors incrément :** lien invitation public tokenisé.

---



## Décisions figées


| Sujet         | Choix                                                                                           |
| ------------- | ----------------------------------------------------------------------------------------------- |
| Création      | `POST /conversations` `{ "type": "GROUP", "title", "member_ids": [], "visibility": "PRIVATE" }` |
| OWNER         | Créateur = OWNER ; impossible de quitter sans transfert                                         |
| Retrait OWNER | Interdit sans transfert préalable                                                               |
| PUBLIC        | Liste `GET /conversations/discoverable` (optionnel phase 3b)                                    |
| Clé cloud     | À la création GROUP/AI : `CryptoService.ensure_conversation_key(conversation_id)` (CRYPTO-A)   |


---



## Contrat HTTP



### MSG-41 — `POST /api/v1/conversations` (groupe)

`messaging.conversation.create`. Min 1 membre en plus du créateur.

### MSG-42/43 — `PATCH /api/v1/conversations/{id}`

`messaging.conversation.update`. Body : `title`, `description`, `avatar_media_id`.

### MSG-44–46 — Membres


| Route                          | Perm                          | Body                              |
| ------------------------------ | ----------------------------- | --------------------------------- |
| `GET .../members`              | `messaging.member.read`       | —                                 |
| `POST .../members`             | `messaging.member.manage`     | `{ "user_id", "role": "MEMBER" }` |
| `PATCH .../members/{user_id}`  | `messaging.member.manage`     | `{ "role", "username" }`          |
| `DELETE .../members/{user_id}` | `messaging.member.manage`     | —                                 |
| `POST .../leave`               | `messaging.conversation.read` | —                                 |




### Réglages groupe — `PATCH /api/v1/conversations/{id}/group-settings`

`messaging.conversation.update` (OWNER/ADMIN).

```json
{
  "visibility": "PUBLIC",
  "locked": false,
  "max_members": 256,
  "welcome_message": "Bienvenue",
  "rules": "Pas de spam"
}
```

Stocke dans `conversation_settings` ligne **owner** ou table dédiée groupe (dénormalisation `custom_settings` par conversation — première ligne OWNER fait foi pour `visibility`/`locked`/`max_members`).