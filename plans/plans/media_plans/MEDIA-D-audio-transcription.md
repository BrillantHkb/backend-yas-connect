# MEDIA-D — Audio & transcription (MED-43 … 54)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MEDIA-A](MEDIA-A-upload-stockage.md), intégration STT + [CRYPTO-00](../crypto_plans/CRYPTO-00-modele-chiffrement.md).  
**Models :** `AudioMessage`, `VoiceTranscription`.

**Périmètre MVP :** messages vocaux, waveform, transcription (dictée). Lecture accélérée = client.  
**CRYPTO-00 :** STT **serveur** sur vocal **groupe** (clair plateforme). Vocal **1-to-1** : pas de déchiffrement serveur — dictée côté client ou pas de texte.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MED-43** | **Gardé** | Message vocal | `audio_messages` + upload AUDIO |
| **MED-44** | **Gardé** | Enregistrement micro → upload | client + MEDIA-A |
| **MED-45** | **Gardé** | Pause / annulation enregistrement | **client** uniquement |
| **MED-46** | **Gardé** | Durée affichée | `duration_seconds` |
| **MED-47** | **Gardé** | Waveform UI | `waveform` jsonb |
| **MED-48** | **Gardé** | Codec opus/aac | `codec` |
| **MED-49** | **Gardé** | Transcription async | `transcription_status` |
| **MED-50** | **Gardé** | Texte STT | `voice_transcriptions.text` |
| **MED-51** | **Gardé** | Langue détectée | `language` |
| **MED-52** | **Gardé** | Score confiance / modèle | `confidence`, `model_used` |
| **MED-53** | **Gardé** | Re-transcription (autre langue) | plusieurs rows |
| **MED-54** | **Gardé** | Lecture ×1.5 / ×2 | **client** player |

---

## Contrat HTTP

### Upload vocal

Même flow MEDIA-A avec `media_type=AUDIO` ; à `complete`, crée `audio_messages` lié.

### `POST /api/v1/media/{id}/audio/transcribe`

`media.audio.manage`. Body optionnel `{ "language": "fr" }`. **202** + job.

### `GET /api/v1/media/{id}/audio/transcriptions`

Liste historique STT pour ce vocal.
