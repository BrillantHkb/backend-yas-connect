# CRYPTO-00 — Modèle de chiffrement (décision figée)

**Produit :** YAS Connect uniquement.  
**Statut :** **FIGÉ** — ne pas rouvrir sans décision explicite.  
**Contrat HTTP des clés :** [CRYPTO-A](CRYPTO-A-cles.md) · [CRYPTO-R](CRYPTO-R-roles-permissions.md) · [routes](CRYPTO-routes.md).

Cette page fixe **qui peut lire quoi**. Elle ne décrit pas les primitives ni les endpoints de clés.

---

## Règle unique

| Contexte | Référence | Qui tient les clés | Le serveur lit le texte ? | Modération / audit |
|----------|-----------|--------------------|---------------------------|--------------------|
| 1-to-1 `conversations.type=PRIVATE` | WhatsApp / Signal (double ratchet) | Uniquement les deux clients | **Jamais** | Impossible sur le corps ; métadonnées seules (ids, horodatage, `media_id`) |
| Groupes `type=GROUP` et canaux (futur) | Telegram *cloud* | Plateforme (clé de fil côté serveur) | **Oui** (après déchiffrement service) | Possible (signalements, rétention, SOC) |
| `type=AI` | Cloud | Plateforme | Oui | Logs service IA |

**Pas d’E2E groupe au MVP.** Un groupe n’est pas un Signal sender-key.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Colonne corps | `messages.encrypted_content` (`bytea`) — **jamais** de `content` clair en PG |
| Flag `conversations.encrypted` | `PRIVATE` : **toujours `true`** à la création. `GROUP` / `AI` : **`false`** (chiffrement transport + at-rest plateforme, pas E2E) |
| Édition / sondages / localisation | Même régime que le fil : 1-to-1 = blob opaque ; groupe = service peut déchiffrer |
| PJ / avatars 1-to-1 | Client chiffre **avant** PUT MinIO ; `media_files.encrypted=true` ; serveur = ciphertext |
| PJ / avatars groupe | Upload clair côté plateforme (scan, preview) ; `encrypted=false` sauf politique at-rest S3 |
| Push / in-app (NOTIF) | 1-to-1 : titre/corps **génériques** (« Nouveau message ») — **interdit** de mettre le plaintext dans `payload` |
| Recherche serveur | 1-to-1 : tags / métadonnées seulement. Groupe : recherche texte possible côté service |
| CRYPTO-A | Bundles par **appareil** + `conversation_keys` (GROUP/AI) — [CRYPTO-A](CRYPTO-A-cles.md) |

---

## Ce que le serveur ne fait jamais (PRIVATE)

- Stocker, logger ou renvoyer le plaintext d’un message 1-to-1
- Déchiffrer `encrypted_content` / PJ E2E pour preview, STT, GED ou IA
- Inclure le corps dans une notification, un webhook ou un audit

---

## Alignement catalogues

- Messagerie : pas de `content` ; `message_edits.previous_encrypted_content` ; GPS dans le blob (pas PostGIS message).
- Médias : `scan_status` s’applique au **ciphertext** en 1-to-1 (ClamAV ne « voit » pas le clair) — acceptable MVP ; groupes = scan du clair.
- Appels : signalisation LiveKit **hors** ce modèle (média temps réel ≠ chat). Enregistrement = [APPELS-E](../calls_plans/APPELS-E-enregistrements.md) (MVP, clés plateforme).

**Hors incrément :** E2E groupes, sealed sender, backup seed phrase, SGX, search E2E (Sesame).
