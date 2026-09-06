---
id: log-process
layer: system
description: Append-only chronological log of /minder:mem:process runs. Newest-first.
owned_by:
  - minder:mem:process
read_by:
  - minder:mem:lint
  - minder:mem:maintain
# One-time migration flags (add as needed):
# migration_completed:
#   {migration_name}: YYYY-MM-DD
---

# Operations Log

> Append-only chronological log of `/minder:mem:process` runs.
> Each entry — one batch invocation.

---

<!-- Entries append BELOW this line, newest first -->
