# APPELS-G — Compte-rendu & historique réunion (CALL-89 … 98)

**Produit :** YAS Connect uniquement.  
**Préalable :** **APPELS-A/E** + STT ([MEDIA-D](../media_plans/MEDIA-D-audio-transcription.md)) / worker résumé.  
**Attributs :** `meeting_history`.  
**Models :** [code/calls_models.py](../code/calls_models.py).

**Périmètre MVP :** dossier post-appel (titre, notes, transcript STT, résumé automatique), 1:1 avec `calls`. Réunions : CR auto à la fin. Appel 1-to-1 : sur demande.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **CALL-89** | **Gardé** | Créer `meeting_history` à ENDED (si MEETING/CONFERENCE/CRISIS ou flag) | INSERT 1:1 |
| **CALL-90** | **Gardé** | Titre / summary éditables par HOST | UPDATE |
| **CALL-91** | **Gardé** | Lancer STT sur recording → `transcript` | async |
| **CALL-92** | **Gardé** | Générer `ai_summary` | async |
| **CALL-93** | **Gardé** | Lire CR (participants) | lecture |
| **CALL-94** | **Gardé** | Liste historique réunions perso | lecture |
| **CALL-95** | **Gardé** | WS `TRANSCRIPTION_READY` / `AI_SUMMARY_READY` | — |
| **CALL-96** | **Gardé** | Recherche trgm sur `transcript` (si activée) | GIN |
| **CALL-97** | **Gardé** | AUDIO/VIDEO 1-to-1 : CR optionnel (opt-in) | flag create |
| **CALL-98** | **Gardé** | Pas de second CR (UK `call_id`) | contrainte |

**Hors incrément :** partage CR hors participants, export PDF, action items structurés.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| Cardinalité | **1:1** `meeting_history.call_id` UNIQUE |
| Déclencheur auto | `MEETING`, `CONFERENCE`, `CRISIS_ROOM` à ENDED |
| 1-to-1 | Sur demande `?create_history=true` à end ou POST dédié |
| STT | Sur `recordings` si présent ; sinon LiveKit transcription si dispo |
| Accès | Participants + admin ; pas public |
| Messagerie | Pas de dump transcript dans le fil (lien `call_id` seulement) |

---

## Contrat HTTP

### CALL-93 — `GET /api/v1/calls/{id}/meeting`

`calls.meeting.read`. **404** si pas de CR.

### CALL-90 — `PATCH /api/v1/calls/{id}/meeting`

`calls.meeting.update` (HOST). `{ "title", "summary" }`.

### CALL-91 — `POST /api/v1/calls/{id}/meeting/transcribe`

`calls.meeting.update`. **202** job STT.

### CALL-92 — `POST /api/v1/calls/{id}/meeting/summarize`

`calls.meeting.update`. **202** job IA (nécessite transcript).

### CALL-94 — `GET /api/v1/meetings/history`

`calls.meeting.read`. Keyset `created_at`. Filtres `q` (titre / trgm transcript).

### CALL-89 — `POST /api/v1/calls/{id}/meeting`

Crée CR manuellement si absent (1-to-1 opt-in). **409** si existe.

---

## Tests (G)

| Cas | Attendu |
|-----|---------|
| ENDED MEETING | meeting_history créé |
| Double create | 409 |
| Summarize sans transcript | 409 `NO_TRANSCRIPT` |
| Non-participant | 403 |
