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

`silver_config_custom.py` is for non-standard HubSpot properties on your portal: an
ARR-specific deal amount, a custom dropdown. It's gitignored. Copy the example and add a
tuple per property you want in silver:

```bash
cp silver_config_custom.py.example silver_config_custom.py
```

The onboarding wizard can also auto-suggest these by scanning
`/crm/v3/properties/{deals,contacts}`.

!!! note "It works without any of this"
    If neither `customer.json` nor `silver_config_custom.py` exists, chat still works; it
    just produces generic SQL without portal-specific filters.

## Then run the pipeline

With the token in place, materialize the assets and the warehouse fills with your data. See [First run](first-run.md).
