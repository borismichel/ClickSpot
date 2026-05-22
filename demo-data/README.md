# Demo data

Synthetic CRM data for demos, screenshots, and local testing. **No real people, companies, or PII** — every name, email, domain, and deal is fabricated. Safe to share publicly.

## `clickspot-demo-data.csv`

~8,700 rows in HubSpot's flat import/export column layout: one row per contact, with the associated company, deal, ticket, and activity columns denormalized alongside. Covers the full object surface the pipeline extracts:

- **Contacts** — name, email, job title, lifecycle stage, contact owner, original source
- **Companies** — name, domain, industry, employee count, country
- **Deals** — name, stage, pipeline, amount, owner, create/close dates
- **Tickets** — name, pipeline, status
- **Activities** — calls, emails, meetings, notes, tasks (with bodies/subjects/timestamps)

### Loading it

This is **HubSpot import-shaped**, not ClickHouse bronze-shaped — it's meant to be imported into a HubSpot demo/sandbox portal, after which the normal bronze → silver → gold pipeline extracts it via the API. There's no direct CSV → ClickHouse loader; the medallion layers expect raw HubSpot API records (`properties` Map + `_raw` JSON), not flat CSV columns.

To use it:
1. Import the CSV into a HubSpot sandbox via *Settings → Import*.
2. Point `HUBSPOT_TOKEN` / `HUBSPOT_HUB_ID` at that portal.
3. Materialize the bronze assets in Dagster as usual.
