# Demo data

Synthetic CRM data for demos, screenshots, and local testing. **No real people, companies, or PII** — every name, email, domain, and deal is fabricated. Safe to share publicly.

## `clickspot-demo-data.csv`

998 contacts (~8,700 physical lines — activity bodies span multiple lines) in HubSpot's flat import/export column layout: one row per contact, with the associated company, deal, ticket, and activity columns denormalized alongside. Covers the object surface the pipeline extracts:

- **Contacts** — name, email, job title, lifecycle stage, contact owner, original source (998 rows)
- **Companies** — name, domain, industry, employee count, country (77 distinct)
- **Deals** — name, stage, pipeline, amount, owner, create/close dates (244 distinct, one "Sales Pipeline" with 6 stages)
- **Activities** — calls, emails, meetings, notes, tasks with bodies/subjects/timestamps (one of each per contact)
- **Tickets** — name, pipeline, status (present in the CSV but **not loaded**: the pipeline has no ticket object)

### Loading it — offline seed loader (recommended)

`scripts/seed.py` loads this CSV **directly into ClickHouse** with no HubSpot portal and no token. It maps the flat columns into bronze (`properties` Map + `_raw` JSON, just like the live extractor), mints coherent synthetic owner/pipeline/stage/object IDs so `dictGet` label resolution works, then materializes silver → gold → anon:

```bash
source .venv/bin/activate
docker compose up -d            # ClickHouse on :8124 (one-time)
make seed                       # or: python scripts/seed.py
```

The loader is idempotent (synthetic IDs are deterministic; bronze tables are `ReplacingMergeTree`), so re-running replaces rather than duplicates. Use `make seed-bronze` (or `--bronze-only`) to load just the bronze layer.

### Loading it — via a real HubSpot portal (alternative)

Because the CSV is HubSpot import-shaped, you can also import it into a sandbox and run the normal API extraction:

1. Import the CSV into a HubSpot sandbox via *Settings → Import*.
2. Point `HUBSPOT_TOKEN` / `HUBSPOT_HUB_ID` at that portal.
3. Materialize the bronze assets in Dagster as usual.
