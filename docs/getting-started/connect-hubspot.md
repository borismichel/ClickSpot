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

A property change takes two steps:

1. **Save** in the Properties tab. The change is recorded, and a banner appears on the
   Settings page: *"Settings saved — your changes are not live yet."*
2. **Apply changes** — the button in that banner. One click makes the edit live end to
   end: it reloads the pipeline's configuration, rebuilds your tables from data already
   synced (silver → gold → anon; nothing is fetched from HubSpot, so no token is needed
   and it's much faster than a full sync), and then refreshes the schema the assistant
   sees. Progress and any failure show up in the banner and on the
   **Settings → Data sync** tab.

Until the apply lands, chat, the MCP schema, and the Data Explorer deliberately keep
describing the *old* column list — so the assistant never suggests a column the warehouse
doesn't hold yet. Once the rebuild finishes, they all pick up the new columns without a
restart.

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
a fresh stack sits with an empty warehouse until you ask for a sync:

1. Open the frontend at <http://localhost:8193> and go to **Settings → Data sync**.
2. Click **Sync now**. It runs the full pipeline — raw HubSpot loads, then the typed,
   aggregated, and anonymized tables — with staged progress right on the tab. (The button
   is disabled until `HUBSPOT_TOKEN` is set.)

Automatic refreshes ship **off** by design, so nothing runs behind your back. Flip
**"Keep my data up to date automatically"** on the same tab to refresh hourly; it shows
the next scheduled run time. Walkthrough: [First run](first-run.md).

!!! note "The technical route still works"
    The Data sync tab drives Dagster under the hood. If you prefer the orchestrator
    directly, open Dagster at <http://localhost:8194> and materialize **`bronze_job`** —
    sensors chain silver → gold → anon — and manage the hourly schedule under
    **Automation → Schedules**. Both routes show up identically on the Data sync tab.
