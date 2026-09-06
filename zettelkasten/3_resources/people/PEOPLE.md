# People Registry

**Last Updated:** REPLACE_WITH_DATE

All people mentioned in the system. New entries appear automatically when
`/minder:mem:process` resolves a name during transcript processing.

**Schema:**
- `Tier` — 1 (has profile OR mentions ≥ 8), 2 (3–7 mentions), 3 (1–2), `stale` (0 mentions + no profile)
- `Mentions` — 1-per-file count across `_records/` and PARA. Recomputed by `/minder:mem:bootstrap` and `/minder:mem:maintain`
- `Last` — latest `created` date where person appears in frontmatter
- Tier `stale` → row MUST be moved to `## Stale People` (split-table) and populate `Reason` per Archive Contract Form B (`_system/docs/SYSTEM_CONFIG.md`).

---

## Owner

The person this base belongs to. Kept in its own section, separate from the general table, because tier mechanics — mention counting, promote, demote — do not apply to them: they are present in nearly everything, so a count carries no signal.

- **Identifier** — derived from `_system/SOUL.md → ## Identity → Name:` by the same `firstname-lastname` rule as every other row. It is the id used in `speaker:` on observation records.
- **Always a valid identity.** Identity checks treat the owner identifier as registered by definition — it is never reported as an identifier missing from the registry.
- **Registered, never auto-populated.** The owner is NOT added to the `people:` array of records and notes automatically. They are present by default almost everywhere; auto-population would inflate every count and carry no signal. Their *absence* from a record is what is significant.
- **Profile** — `3_resources/people/{id}.md`, same shape as any other profile (`5_meta/templates/person-template.md`), assembled by `/minder:mem:bootstrap` from SOUL, the active constitution and the registry.

| ID | Name | Role | Profile |
|---|---|---|---|
| _(seeded by `/minder:mem:bootstrap`)_ | | | |

---

## People

Sorted by mentions desc within tier.

| ID | Name | Role | Org | Profile | Tier | Mentions | Last |
|---|---|---|---|---|---|---|---|
| _(empty)_ | | | | | | | |

---

## Stale People

People with `Tier: stale`. Per Archive Contract Form B, every row here carries a `Reason` cell — free-form one-sentence rationale. Forward-only: rows that became stale before contract adoption are not backfilled.

| ID | Name | Role | Org | Profile | Tier | Mentions | Last | Reason |
|---|---|---|---|---|---|---|---|---|
| _(empty)_ | | | | | | | | |
