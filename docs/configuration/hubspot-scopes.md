# HubSpot token scopes

ClickSpot reads from HubSpot via a **private app token** (recommended) or a legacy "HubSpot
API key" app. Create the token in **Settings → Integrations → Private Apps → Create private
app** and grant the read scopes below.

All scopes are read-only — the pipeline never writes back to HubSpot.

## Required read scopes, per endpoint group

| Endpoint group | Used by | Required scope |
|---|---|---|
| Contacts (`/crm/v3/objects/contacts`) | `hs_contacts` bronze + property metadata | `crm.objects.contacts.read`, `crm.schemas.contacts.read` |
| Companies (`/crm/v3/objects/companies`) | `hs_companies` bronze + property metadata | `crm.objects.companies.read`, `crm.schemas.companies.read` |
| Deals (`/crm/v3/objects/deals`) + pipelines (`/crm/v3/pipelines/deals`) | `hs_deals`, `hs_pipelines` bronze | `crm.objects.deals.read`, `crm.schemas.deals.read` |
| Leads (`/crm/v3/objects/leads`) + pipelines (`/crm/v3/pipelines/leads`) | `hs_leads`, `hs_lead_pipelines` bronze | `crm.objects.leads.read` |
| Owners (`/crm/v3/owners`) | `hs_owners` bronze | `crm.objects.owners.read` |
| Engagements — calls, meetings, notes, tasks (`/crm/v3/objects/{type}`) | `hs_calls`, `hs_meetings`, `hs_notes`, `hs_tasks` bronze | `crm.objects.contacts.read` (covers non-email engagements) |
| Engagements — emails (`/crm/v3/objects/emails`) | `hs_engagement_emails` bronze | `sales-email-read` |
| Associations (`/crm/v4/objects/.../associations/...`) | 21 bridge tables | Covered by the parent-object scopes above |
| Marketing campaigns (`/marketing/v3/campaigns`) | `hs_campaigns` bronze | `marketing.campaigns.read` |
| Forms + form submissions (`/marketing/v3/forms`, `/form-integrations/v1/submissions`) | `hs_forms`, `hs_form_submissions` bronze | `forms` |
| Lists / segments (`/crm/v3/lists/search`, `/crm/v3/lists/{id}/memberships`) | `hs_lists`, `hs_assoc_list_{contact,company,deal,lead}` bronze | `crm.lists.read` |

## After creating the app

1. Copy the access token into `HUBSPOT_TOKEN` in `.env`.
2. Grab the portal ID from the app page URL for `HUBSPOT_HUB_ID`.

!!! tip "Marketing scopes are optional"
    If you skip the marketing scopes (`marketing.campaigns.read`, `forms`), the
    corresponding bronze assets fail to materialize — but the CRM pipeline still runs.

See [Connect HubSpot](../getting-started/connect-hubspot.md) for the rest of the portal
setup.
