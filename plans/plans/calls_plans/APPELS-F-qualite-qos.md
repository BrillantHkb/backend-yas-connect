# APPELS-F — Qualité d’appel / QoS (CALL-77 … 88)

**Produit :** YAS Connect uniquement.  
**Préalable :** **APPELS-A/B**.  
**Attributs :** `call_quality_metrics`.  
**Models :** [code/calls_models.py](../code/calls_models.py).

**Périmètre :** collecte d’échantillons QoS, lecture courbes, rétention, préparation partitionnement.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **CALL-77** | **Gardé** | Client poste batch d’échantillons (5–10 s) | INSERT only |
| **CALL-78** | **Gardé** | Champs : latency, jitter, packet_loss, bitrate, fps, cpu, network_type | colonnes |
| **CALL-79** | **Gardé** | `packet_loss` decimal(6,3) 0–100 | CHECK |
| **CALL-80** | **Gardé** | PK `bigint` BIGSERIAL | — |
| **CALL-81** | **Gardé** | Lecture QoS d’un appel (participant) | lecture |
| **CALL-82** | **Gardé** | Agrégats simples (avg latency, max loss) | query |
| **CALL-83** | **Gardé** | Admin `calls.metrics.read_all` | cross-user |
| **CALL-84** | **Gardé** | Rétention **90 jours** (job scheduled) | DELETE |
| **CALL-85** | **Gardé** | Partition mensuelle **après** montée en charge | ticket ops |
| **CALL-86** | **Gardé** | Export métriques Prometheus optionnel (ops) | — |
| **CALL-87** | **Gardé** | Rate-limit write (anti flood) | — |
| **CALL-88** | **Gardé** | Pas d’UPDATE sur lignes existantes | INSERT only |

**Hors incrément :** MOS score serveur, alerting auto seuil perte, partition dès j0.

---

## Décisions figées

| Sujet | Choix |
|-------|--------|
| MVP stockage | Table PG **non partitionnée** + index + rétention 90 j |
| Partition | Quand > ~100k lignes/jour ou DELETE lent |
| Source | SDK client (LiveKit stats) prioritaire |
| Admin NOC | Dashboards Grafana + endpoint admin |
| Volume | Batch max 50 samples / requête |

---

## Contrat HTTP

### CALL-77 — `POST /api/v1/calls/{id}/metrics`

`calls.metrics.write`.

```json
{
  "samples": [
    {
      "latency_ms": 45,
      "jitter_ms": 3,
      "packet_loss": "0.052",
      "bitrate": 800000,
      "fps": 28,
      "cpu_usage": 22,
      "network_type": "WIFI",
      "captured_at": "2026-08-31T12:00:00Z"
    }
  ]
}
```

**202** `{ "inserted": N }`. **422** si `packet_loss` hors 0–100.

### CALL-81 — `GET /api/v1/calls/{id}/metrics`

`calls.metrics.read`. Query `from`, `to`, `user_id`, `limit`.

### CALL-82 — `GET /api/v1/calls/{id}/metrics/summary`

Avg / p95 latency, avg packet_loss, avg bitrate.

### Admin — `GET /api/v1/admin/calls/metrics`

`calls.metrics.read_all`.

---

## Job rétention

`scheduled_jobs` : `calls.purge_quality_metrics` quotidien — `DELETE WHERE created_at < now() - interval '90 days'`.

---

## Tests (F)

| Cas | Attendu |
|-----|---------|
| Batch valide | 202 inserted |
| packet_loss 150 | 422 |
| Lecture non-participant | 403 |
| Job purge | lignes > 90 j absentes |
