---
id: log-maintenance
layer: system
description: Append-only audit trail of /minder:mem:maintain + /minder:mem:bootstrap runs. Per-run aggregation.
owned_by:
  - minder:mem:maintain
  - minder:mem:bootstrap
read_by:
  - minder:mem:lint
# One-time migration flags (add as needed):
# migration_completed:
#   {migration_name}: YYYY-MM-DD
---

# Maintenance Log

> Append-only log of maintenance + bootstrap operations.
> Each entry — one skill run (`/minder:mem:bootstrap`, `/minder:mem:maintain`).
> Format: timestamp (ISO 8601 UTC) | mode | by: {skill} | batch: {id or —}
>
> **Read-only consumer:** `/minder:mem:lint` reads this file for activity detection (Scan B.1 thread staleness).

---

<!-- Entries append BELOW this line, newest first -->
