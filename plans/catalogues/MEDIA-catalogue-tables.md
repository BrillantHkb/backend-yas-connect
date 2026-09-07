# Catalogue Médias — tables et attributs

App Django prévue : `apps.media`.  
Référencé par IAM (`users.avatar_id`), Annuaire (`user_certifications.document_id`), Messagerie (`messages.media_id`), conversations (`avatar_media_id`).

**Légende « Renseigné par »** : User / Médias (service upload) / Système / Scanner — **0 ligne AUTH-01**. Premier INSERT métier : avatar **PROF-A**.

Index : [INDEX-catalogue.md](INDEX-catalogue.md).

**Modèle** : table centrale `media_files` (blob S3/MinIO) + tables spécialisées **1:1** selon `media_type` + audit et quotas.

---

## Index des tables

| Table | Rôle |
|--------|------|
| `media_files` | Fichier stocké (métadonnées communes, chemin objet) |
| `media_metadata` | EXIF / technique transversal (dimensions, GPS, codec…) |
| `images` | Dérivés image (thumbnail, optimisé, qualité) |
| `videos` | Vidéo (transcodage, streaming) |
| `audio_messages` | Message vocal (waveform, transcription en attente) |
| `voice_transcriptions` | Texte STT lié à un vocal |
| `documents` | GED (titre, confidentialité, OCR) |
| `document_versions` | Historique de versions document |
| `media_access_logs` | Journal d’accès (conformité / SOC) |
| `storage_usage` | Quota agrégé par user et type de stockage |

---

## Relations (ERD)

| De | Vers | Cardinalité | FK |
|----|------|-------------|-----|
| `media_files` | `users` | n → 1 | `owner_id` (propriétaire technique / quota upload) |
| `media_metadata` | `media_files` | 1 → 1 | `media_id` UK |
| `images` | `media_files` | 1 → 1 | `media_id` UK |
| `videos` | `media_files` | 1 → 1 | `media_id` UK |
| `audio_messages` | `media_files` | 1 → 1 | `media_id` UK |
| `voice_transcriptions` | `audio_messages` | n → 1 | `audio_id` |
| `documents` | `media_files` | 1 → 1 | `media_id` UK |
| `documents` | `users` | n → 1 | `owner_id` (responsable métier GED) |
| `document_versions` | `documents` | n → 1 | `document_id` |
| `document_versions` | `media_files` | n → 1 | `media_id` (fichier de cette version) |
| `document_versions` | `users` | n → 1 | `changed_by_id` |
| `media_access_logs` | `media_files` | n → 1 | `media_id` |
| `media_access_logs` | `users` | n → 1 | `user_id` |
| `media_access_logs` | `devices` | n → 1 | `device_id` |
| `storage_usage` | `users` | n → 1 | `user_id` |

Une ligne `media_files` a **au plus une** extension parmi `images`, `videos`, `audio_messages`, `documents` (selon `media_type`). `media_metadata` peut coexister avec une extension type.

---

## 1. `media_files`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | Identifiant fichier | | FK avatar, PJ, chat | Système |
| `owner_id` | `uuid` | FK `users` SET NULL, NULL | Propriétaire upload / quota | | Galerie user | User / Système |
| `storage_path` | `text` | NOT NULL | Clé objet bucket | `avatars/uuid.jpg` | S3 / MinIO | Médias |
| `original_name` | `varchar(255)` | défaut `''` | Nom fichier client | `photo.jpg` | Téléchargement | User |
| `mime_type` | `varchar(100)` | défaut `''` | Type MIME | `image/jpeg` | Rendu | Médias |
| `media_type` | `varchar(16)` | NOT NULL | `IMAGE` / `VIDEO` / `AUDIO` / `DOCUMENT` / `OTHER` | `IMAGE` | Routage sous-table | Médias |
| `size_bytes` | `bigint` | défaut `0` | Taille octets | `1048576` | Quota | Médias |
| `checksum` | `varchar(128)` | UK, NULL | Empreinte (SHA-256…) | | Dédup | Médias ; NULL si inconnu |
| `bucket_name` | `varchar(100)` | défaut `''` | Bucket cible | `yas-media` | Multi-bucket | Médias |
| `encrypted` | `boolean` | défaut `false` | Chiffré au repos | | Sécurité | Médias |
| `compressed` | `boolean` | défaut `false` | Fichier compressé | | Pipeline | Médias |
| `virus_scanned` | `boolean` | défaut `false` | Scan antivirus passé | | Gate lecture | Scanner |
| `scan_status` | `varchar(20)` | défaut `PENDING` | `PENDING` / `CLEAN` / `INFECTED` / `SKIPPED` | `CLEAN` | Bloquer infecté | Scanner |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |
| `updated_at` | `timestamptz` | NOT NULL | | | | Système |

---

## 2. `media_metadata`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `media_id` | `uuid` | FK `media_files` CASCADE, UK, NOT NULL | Fichier parent | | 1:1 | Système |
| `width` | `integer` | NULL | Largeur px | `1920` | Image / vidéo | Médias |
| `height` | `integer` | NULL | Hauteur px | `1080` | | Médias |
| `duration_seconds` | `integer` | NULL | Durée (audio/vidéo) | `42` | Player | Médias |
| `codec` | `varchar(50)` | défaut `''` | Codec détecté | `h264` | | Médias |
| `latitude` | `decimal(10,7)` | NULL | GPS EXIF | | Carte | Médias |
| `longitude` | `decimal(10,7)` | NULL | GPS EXIF | | | Médias |
| `captured_at` | `timestamptz` | NULL | Date prise de vue | | Tri galerie | Médias |
| `device_model` | `varchar(100)` | défaut `''` | Appareil source | `iPhone 15` | | Médias |
| `metadata` | `jsonb` | défaut `{}` | EXIF / tags libres | | Extensibilité | Médias |

---

## 3. `images`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `media_id` | `uuid` | FK `media_files` CASCADE, UK, NOT NULL | Original | | `media_type=IMAGE` | Système |
| `thumbnail_path` | `text` | défaut `''` | Miniature | | Liste / chat | Médias |
| `optimized_path` | `text` | défaut `''` | Variante WebP/JPEG | | Bande passante | Médias |
| `original_resolution` | `varchar(50)` | défaut `''` | ex. `4032x3024` | | Affichage | Médias |
| `format` | `varchar(20)` | défaut `''` | `JPEG`, `PNG`, `WEBP` | | | Médias |
| `quality` | `smallint` | défaut `0` | Qualité compression 0–100 | `85` | | Médias |
| `annotated` | `boolean` | défaut `false` | Annotations dessinées | | Messagerie | User |
| `blurred` | `boolean` | défaut `false` | Floutage privacy | | Modération | Système |

---

## 4. `videos`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `media_id` | `uuid` | FK `media_files` CASCADE, UK, NOT NULL | Original | | `media_type=VIDEO` | Système |
| `duration_seconds` | `integer` | défaut `0` | Durée lecture | `120` | Player | Médias |
| `resolution` | `varchar(30)` | défaut `''` | ex. `1080p` | | | Médias |
| `codec` | `varchar(50)` | défaut `''` | `h264`, `vp9` | | | Médias |
| `thumbnail_path` | `text` | défaut `''` | Poster frame | | Preview | Médias |
| `streaming_ready` | `boolean` | défaut `false` | HLS/DASH prêt | | Lecture progressive | Médias |
| `transcoding_status` | `varchar(30)` | défaut `PENDING` | `PENDING` / `PROCESSING` / `READY` / `FAILED` | | Pipeline async | Médias |

---

## 5. `audio_messages`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `media_id` | `uuid` | FK `media_files` CASCADE, UK, NOT NULL | Fichier audio | | Vocal chat | Système |
| `duration_seconds` | `integer` | défaut `0` | Durée | `15` | UI waveform | Médias |
| `waveform` | `jsonb` | défaut `[]` | Points amplitude | | Affichage | Médias |
| `codec` | `varchar(30)` | défaut `''` | `opus`, `aac` | | | Médias |
| `transcription_status` | `varchar(30)` | défaut `PENDING` | `PENDING` / `PROCESSING` / `DONE` / `FAILED` | | STT async | Système |

---

## 6. `voice_transcriptions`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `audio_id` | `uuid` | FK `audio_messages` CASCADE, NOT NULL | Vocal source | | | Système |
| `language` | `varchar(10)` | défaut `''` | ISO 639-1 | `fr` | | STT |
| `text` | `text` | NOT NULL | Transcription | | Recherche / accessibilité | STT |
| `confidence` | `decimal(5,2)` | NULL | Score 0–100 | `94.50` | Qualité | STT |
| `model_used` | `varchar(100)` | défaut `''` | Modèle IA | `whisper-large` | Audit | STT |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

Plusieurs transcriptions par vocal possibles (re-traitement, autre langue).

---

## 7. `documents`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `media_id` | `uuid` | FK `media_files` CASCADE, UK, NOT NULL | Fichier binaire courant | | `media_type=DOCUMENT` | Système |
| `title` | `varchar(255)` | défaut `''` | Titre affiché | `Contrat 2026` | GED | User |
| `category` | `varchar(100)` | défaut `''` | Classement | `RH` | Filtres | User |
| `confidential` | `boolean` | défaut `false` | Restriction accès | | ACL | User |
| `version` | `integer` | défaut `1` | Numéro version courante | `3` | GED | Système |
| `owner_id` | `uuid` | FK `users` SET NULL, NULL | Responsable métier | | ≠ `media_files.owner_id` possible | User |
| `extracted_text` | `text` | défaut `''` | OCR / extraction | | Recherche plein texte | Médias |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

---

## 8. `document_versions`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `document_id` | `uuid` | FK `documents` CASCADE, NOT NULL | Document logique | | | Système |
| `version_number` | `integer` | NOT NULL | Indice version | `2` | Historique | Système |
| `media_id` | `uuid` | FK `media_files` CASCADE, NOT NULL | Blob de cette version | | Immuable | Système |
| `changed_by_id` | `uuid` | FK `users` SET NULL, NULL | Auteur modification | | Audit | User |
| `comment` | `text` | défaut `''` | Note de version | `Correction typo` | | User |
| `created_at` | `timestamptz` | NOT NULL | | | | Système |

UK `(document_id, version_number)`.

---

## 9. `media_access_logs`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `bigint` | PK auto | Identifiant log (volume) | | | Système |
| `media_id` | `uuid` | FK `media_files` CASCADE, NOT NULL | Fichier accédé | | | Système |
| `user_id` | `uuid` | FK `users` SET NULL, NULL | Qui | | SOC | Système |
| `action` | `varchar(20)` | NOT NULL | `VIEW` / `DOWNLOAD` / `DELETE` / `SHARE` | `DOWNLOAD` | | Système |
| `ip_address` | `inet` | NULL | IP client | | SOC | Système |
| `device_id` | `uuid` | FK `devices` SET NULL, NULL | Appareil | | | Système |
| `created_at` | `timestamptz` | NOT NULL | | | Rétention logs | Système |

Pas d’UPDATE : append-only.

---

## 10. `storage_usage`

| Attribut | Type PG | Contraintes | Rôle | Exemple | Cas d’usage | Renseigné par |
|----------|---------|-------------|------|---------|-------------|---------------|
| `id` | `uuid` | PK | | | | Système |
| `user_id` | `uuid` | FK `users` CASCADE, NOT NULL | User quota | | | Système |
| `storage_type` | `varchar(20)` | NOT NULL | `PERSONAL` / `SHARED` / `DOCUMENT` | `PERSONAL` | Plafonds distincts | Système |
| `used_bytes` | `bigint` | défaut `0` | Consommé | | Barre quota | Système |
| `quota_bytes` | `bigint` | NULL | Plafond (NULL = illimité admin) | `5368709120` | | Admin / Système |
| `updated_at` | `timestamptz` | NOT NULL | Dernière agrégation | | | Système |

UK `(user_id, storage_type)`.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| PK | `uuid` partout sauf `media_access_logs.id` (`bigint` séquentiel) |
| Sous-types | 1:1 via `media_id` UK ; une seule extension type par fichier |
| `checksum` | UK ; valeur **NULL** si empreinte inconnue (évite collision sur `''`) |
| `documents.owner_id` | Responsable GED ; `media_files.owner_id` = uploader technique |
| Versions document | Chaque version = nouveau `media_files` + ligne `document_versions` |
| AUTH-01 | Toutes les tables créées ; **0 ligne** jusqu’à PROF-A / upload métier |
