# MEDIA-F — Quotas & audit (MED-69 … 76)

**Produit :** YAS Connect uniquement.  
**Préalable :** [MEDIA-A](MEDIA-A-upload-stockage.md).  
**Models :** `StorageUsage`, `MediaAccessLog`.

**Périmètre :** quotas par user, journal d’accès, admin SOC.

---

## Cartographie

| ID | Statut | Comportement | Écritures |
|----|--------|--------------|-----------|
| **MED-69** | **Gardé** | Quota PERSONAL / SHARED / DOCUMENT | `storage_usage` UK (user, type) |
| **MED-70** | **Gardé** | Affichage barre quota user | `used_bytes`, `quota_bytes` |
| **MED-71** | **Gardé** | Incrément / décrément à upload/delete | service quota |
| **MED-72** | **Gardé** | Admin fixe plafond | `media.storage.manage` |
| **MED-73** | **Gardé** | Log VIEW / DOWNLOAD / DELETE / SHARE | `media_access_logs` append-only |
| **MED-74** | **Gardé** | IP + device sur chaque accès | `ip_address`, `device_id` |
| **MED-75** | **Gardé** | Admin consulte logs d’un fichier | pagination |
| **MED-76** | **Gardé** | Rétention logs 365 j (config) | job purge |

---

## Contrat HTTP

### `GET /api/v1/me/storage-usage`

`media.storage.read`. Retourne tableau par `storage_type`.

### `GET /api/v1/admin/users/{id}/storage-usage`

`media.storage.manage`.

### `PATCH /api/v1/admin/users/{id}/storage-usage`

```json
{
  "storage_type": "PERSONAL",
  "quota_bytes": 5368709120
}
```

### `GET /api/v1/admin/media/{id}/access-logs`

`media.access_log.read`. Query `limit`, `offset`, `action`.
