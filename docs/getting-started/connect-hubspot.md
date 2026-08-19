# Connect HubSpot

This page applies only when you're loading your **own** HubSpot data. Running on the
bundled demo seed (`make seed`, or the preloaded `:demo` image)? Skip it; there's no
portal to connect.

ClickSpot ships with no portal-specific assumptions. Three things tune it to your portal.

## 1. Create a private app token

ClickSpot reads from HubSpot via a **private app token** (recommended) or a legacy
"HubSpot API key" app. All scopes are read-only, and the pipeline never writes back to
HubSpot.

1. In HubSpot, go to **Settings → Integrations → Private Apps → Create private app**.
2. Grant the read scopes for the objects you want (the full per-endpoint list is in
   [HubSpot token scopes](../configuration/hubspot-scopes.md)).
3. Copy the access token into `HUBSPOT_TOKEN` in `.env`, and grab the portal ID from the
   app page URL for `HUBSPOT_HUB_ID`.

```bash
# .env
HUBSPOT_TOKEN=pat-na1-...
HUBSPOT_HUB_ID=12345678
```

`HUBSPOT_HUB_ID` also builds the canonical record URLs that the frontend and MCP link back
to, so a row in a result can deep-link to the matching contact or deal in HubSpot.

!!! tip "Skipping marketing scopes is fine"
    If you skip the marketing scopes (`marketing.campaigns.read`, `forms`), the
    corresponding bronze assets just fail to materialize, and the CRM pipeline still runs.

## 2. Let it discover your portal

`~/.clickspot/customer.json` holds your portal's pipeline names, stages, currency, and
company name. It's **auto-discovered from the silver tables on the first successful run**,
then editable. Override it through the onboarding wizard or by hand:

```bash
python -m app.customer.onboarding
```

## 3. (Optional) Map non-standard properties

Non-standard HubSpot properties — an ARR-specific deal amount, a custom dropdown — become
silver columns through the **Settings → Properties** tab in the frontend. Its sibling
**Settings → Extraction** turns off whole objects you don't want extracted at all.

A property change takes three steps, in this order:

1. **Save** in the Properties tab. Chat, the MCP schema, and the Data Explorer pick up the
   new column list immediately — no restart.
2. **Reload Pipeline** — the button in the banner that appears after a save. It reloads
   Dagster's code location over GraphQL (see
   [`DAGSTER_GRAPHQL_URL`](../configuration/index.md)), which is what makes the pipeline
   aware of the column at all.
3. **Materialize `silver_job`** in Dagster so the column is rebuilt with data. (Tick
   *Run bronze job after reload* in that banner instead if the property is new to bronze
   too.)

Between steps 1 and 3 the assistant knows about a column ClickHouse does not have yet, so
queries against it fail until the rebuild finishes. That window is why the rebuild belongs
immediately after the save.

!!! warning "`silver_config_custom.py` is deprecated"
    The gitignored sibling module still appends columns and still works, with a deprecation
    warning at import. It cannot reach a container deployment at all — released images are
    built from a clean checkout, so the file is never in them. Move existing tuples to the
    Properties tab.

!!! note "It works without any of this"
    If `customer.json` holds no portal specifics, chat still works; it just produces generic
    SQL without portal-specific filters.

## Then load your portal

**Setting the token does not load anything by itself.** Nothing is scheduled on startup —
a fresh stack sits with an empty warehouse until you ask for an extraction:

1. Open Dagster at <http://localhost:8194>.
2. Materialize **`bronze_job`**. Sensors chain the rest: bronze → silver → gold → anon.

The recurring `hourly_schedule` ships **stopped** by design, so nothing refreshes behind
your back. Turn it on under **Automation → Schedules** in the same UI if you want hourly
runs. Walkthrough: [First run](first-run.md).
