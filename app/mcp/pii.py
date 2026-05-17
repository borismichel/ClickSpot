"""PII masking + HubSpot URL injection for MCP query results.

Masks customer PII (names, emails, phones, company info, deal/lead names) so the
MCP client (e.g. Claude Desktop) sees de-identified data, and appends HubSpot
record URLs for each entity ID column so the user can click through to the real
record in HubSpot.

Owners and other internal-staff fields are intentionally *not* masked.

Masking is column-name based (not AST-based). The MCP prompt preamble tells the
LLM not to alias PII columns and not to use dictGet against PII dictionaries
(dict_contacts / dict_companies / dict_deals). A substring check on dictGet output
column names provides defense in depth against that specific leak.

IMPORTANT: The PII column registry below is keyed by bare column name. If a
non-PII table later adds a column that collides with one of these names (e.g.
`name`, `company`, `domain`), masking will over-apply. Re-verify against
app/config.py::TABLES on schema changes.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Iterable, Sequence

log = logging.getLogger("app.mcp.pii")

# ---------------------------------------------------------------------------
# PII column registry — lowercase column names
# ---------------------------------------------------------------------------

# Email-style (local@domain) masking
EMAIL_COLUMNS: set[str] = {"email"}

# Phone-style (digit → '*') masking
PHONE_COLUMNS: set[str] = {"phone"}

# Text masking: first char + asterisks per space-split word
_TEXT_PII_COLUMNS: set[str] = {
    # People names
    "full_name",
    "firstname",
    "lastname",
    # Customer-identifying role
    "jobtitle",
    # Deal / lead names
    "dealname",
    "hs_lead_name",
    "lead_name",
    # Company identifiers
    "name",
    "company",
    "domain",
    "website",
    # Customer-identifying location (fine-grained only; `country` deliberately excluded — too coarse)
    "address",
    "city",
    "zip",
}

PII_COLUMN_NAMES: set[str] = _TEXT_PII_COLUMNS | EMAIL_COLUMNS | PHONE_COLUMNS

# ---------------------------------------------------------------------------
# HubSpot record-URL mapping — mirrors frontend/src/components/viz/ResultTable.tsx
# ---------------------------------------------------------------------------

ID_TO_OBJECT_TYPE: dict[str, str] = {
    "contact_id": "0-1",
    "company_id": "0-2",
    "deal_id":    "0-3",
    "lead_id":    "0-34",
}

# dictGet source dicts that return PII (used by defense-in-depth dictGet detector)
_PII_SOURCE_DICTS = ("dict_contacts", "dict_companies", "dict_deals")
_PII_DICT_ATTRS = ("full_name", "firstname", "lastname", "email", "phone",
                   "name", "domain", "website", "address", "city", "zip",
                   "dealname", "jobtitle")


# ---------------------------------------------------------------------------
# Mask primitives
# ---------------------------------------------------------------------------
# Every masked token is a fixed-width '***' so the reader can't count characters
# to narrow down the original value. Mirrors the storage-side masking in
# app/engine/anon_masking.py exactly — the MCP client sees the same shape
# whether the mask happened at storage time (silver_anon) or at runtime
# (dictGet-aliasing backstop).

_MASK_STAR = "***"


def _mask_word(word: str) -> str:
    """'Michel' -> 'M***'. Empty input round-trips."""
    if not word:
        return word
    return word[0] + _MASK_STAR


def mask_text(value):
    """'Alice Anderson' -> 'B*** M***'. Per-word (space-split). Preserves None and empty."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if not value or value.isspace():
        return value
    return " ".join(_mask_word(w) for w in value.split(" "))


def mask_email(value):
    """'alice.anderson@example.com' -> 'a***.a***@e***.com'. TLD preserved verbatim."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if not value or value.isspace():
        return value
    if "@" not in value:
        return mask_text(value)
    local, _, domain = value.partition("@")
    masked_local = ".".join(_mask_word(seg) for seg in local.split("."))
    segs = domain.split(".")
    if len(segs) <= 1:
        masked_domain = _mask_word(domain)
    else:
        # Preserve the last segment (TLD) verbatim; mask everything before it.
        masked_domain = ".".join(_mask_word(s) for s in segs[:-1]) + "." + segs[-1]
    return f"{masked_local}@{masked_domain}"


_DIGIT_RUN_RE = re.compile(r"\d+")


def mask_phone(value):
    """Collapse each run of digits to '***'. '+33 6 12 34' -> '+*** *** *** ***'.

    Uses a digit-run collapse (not per-digit replacement) so the reader can't
    recover the digit count by counting asterisks.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if not value or value.isspace():
        return value
    return _DIGIT_RUN_RE.sub(_MASK_STAR, value)


# ---------------------------------------------------------------------------
# HubSpot URL builder
# ---------------------------------------------------------------------------

_DEFAULT_APP_HOST = "app.hubspot.com"


def hubspot_app_host(token: str | None = None) -> str:
    """Derive the HubSpot app host from the token region (pat-eu1-... -> app-eu1.hubspot.com).

    NA1 tokens map to the canonical `app.hubspot.com` (no subdomain). Other
    regions (`eu1`, `na2`, ...) map to `app-<region>.hubspot.com`. Falls back
    to the NA1 host if the token is missing or unrecognized.
    """
    tok = token if token is not None else os.environ.get("HUBSPOT_TOKEN", "")
    if not tok.startswith("pat-"):
        return _DEFAULT_APP_HOST
    parts = tok.split("-", 2)
    if len(parts) < 3:
        return _DEFAULT_APP_HOST
    region = parts[1].lower()
    if region == "na1":
        return _DEFAULT_APP_HOST
    if not region.isalnum():
        return _DEFAULT_APP_HOST
    return f"app-{region}.hubspot.com"


def hubspot_url(hub_id, id_col: str, id_value, app_host: str = _DEFAULT_APP_HOST) -> str | None:
    """Build a HubSpot record URL. Returns None if hub_id or id_value is empty."""
    if not hub_id or id_value in (None, "", 0):
        return None
    obj_type_id = ID_TO_OBJECT_TYPE.get(id_col.lower())
    if not obj_type_id:
        return None
    return f"https://{app_host}/contacts/{hub_id}/record/{obj_type_id}/{id_value}"


# ---------------------------------------------------------------------------
# Column classification
# ---------------------------------------------------------------------------

def _is_dictget_pii(col_name: str) -> bool:
    """Heuristic: dictGet(silver.dict_contacts, 'full_name', ...) leaks PII even without alias."""
    lower = col_name.lower()
    if "dictget(" not in lower:
        return False
    if not any(d in lower for d in _PII_SOURCE_DICTS):
        return False
    return any(attr in lower for attr in _PII_DICT_ATTRS)


def _classify(col_name: str) -> str | None:
    """Return 'email' / 'phone' / 'text' / 'dictget_pii' / None."""
    lower = col_name.lower()
    if lower in EMAIL_COLUMNS:
        return "email"
    if lower in PHONE_COLUMNS:
        return "phone"
    if lower in _TEXT_PII_COLUMNS:
        return "text"
    if _is_dictget_pii(col_name):
        return "text"
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_MASKERS = {
    "email": mask_email,
    "phone": mask_phone,
    "text":  mask_text,
}


def _infer_and_mask(value: str) -> str:
    """Pick a masker for a value whose column name didn't classify it."""
    if "@" in value:
        return mask_email(value)
    if any(c.isdigit() for c in value):
        return mask_phone(value)
    return mask_text(value)


def apply_privacy(
    columns: Sequence[str],
    rows: Iterable[Sequence],
    hub_id: str | None,
    app_host: str = _DEFAULT_APP_HOST,
) -> tuple[list[str], list[list]]:
    """Mask PII cells in-row-wise and append <id_col>_url columns.

    Inputs are not mutated. Returns fresh (columns, rows) lists.
    """
    columns = list(columns)
    rows = [list(r) for r in rows]

    # Per-index classification
    col_kinds: list[str | None] = [_classify(c) for c in columns]

    # Which ID columns can we generate URLs for?
    id_col_indices: list[tuple[int, str]] = []
    seen_id_names: set[str] = set()
    for i, c in enumerate(columns):
        lower = c.lower()
        if lower in ID_TO_OBJECT_TYPE and lower not in seen_id_names:
            id_col_indices.append((i, lower))
            seen_id_names.add(lower)

    # Mask existing cells
    new_rows: list[list] = []
    for row in rows:
        if len(row) != len(columns):
            log.warning("apply_privacy row/column length mismatch: %d cols vs %d cells", len(columns), len(row))
            row = list(row)[: len(columns)] + [None] * max(0, len(columns) - len(row))
        new_row = list(row)
        for i, kind in enumerate(col_kinds):
            if kind is None:
                continue
            new_row[i] = _MASKERS[kind](new_row[i])
        new_rows.append(new_row)

    # URL injection — skip entirely if hub_id unset or no data
    if not hub_id or not new_rows or not id_col_indices:
        return columns, new_rows

    url_col_names = [f"{name}_url" for _, name in id_col_indices]
    for r_i, new_row in enumerate(new_rows):
        src_row = rows[r_i] if r_i < len(rows) else new_row  # prefer original id values
        for i, name in id_col_indices:
            id_val = src_row[i] if i < len(src_row) else None
            new_row.append(hubspot_url(hub_id, name, id_val, app_host))

    return columns + url_col_names, new_rows


# ---------------------------------------------------------------------------
# Defense-in-depth: per-query scoped PII lookup
# ---------------------------------------------------------------------------
# Column-name masking (apply_privacy above) misses aliased PII
# (`hs_lead_name AS lead`) and concat'd columns (`concat(firstname,' ',lastname)`).
#
# For every run_sql call we pull the PII values of the IDs actually present in
# the result (scoped, not global), subtract owner names (owners are exempt),
# and scrub any cell whose full lowercased value matches. This catches name
# bypasses regardless of the output column name.
#
# Not caught: partial-substring leaks ("Mr. Alice Anderson from Acme Corp") —
# exact-cell match only, to keep false-positive rate near zero.

# Per-ID-type → (silver dim table, PII column tuple) for the scoped fetch.
_SCOPED_PII_SOURCES: dict[str, tuple[str, tuple[str, ...]]] = {
    "contact_id": ("silver.dim_contacts", (
        "full_name", "firstname", "lastname", "email", "phone",
        "jobtitle", "address", "city", "zip",
    )),
    "company_id": ("silver.dim_companies", (
        "name", "domain", "website", "address", "city", "zip", "phone",
    )),
    "deal_id": ("silver.dim_deals", ("dealname",)),
    "lead_id": ("silver.dim_leads", ("hs_lead_name",)),
}


def collect_ids_from_rows(
    columns: Sequence[str],
    rows: Iterable[Sequence],
) -> dict[str, set]:
    """Return {lowercase_id_col: {id_values}} for IDs present in the rows.

    Only collects IDs whose column name matches ID_TO_OBJECT_TYPE exactly;
    aliased IDs (`contact_id AS cid`) are skipped — the privacy policy tells
    the LLM not to alias them, and we'd rather miss the scrub than scrub the
    wrong thing.
    """
    out: dict[str, set] = {}
    for i, col in enumerate(columns):
        low = col.lower()
        if low in ID_TO_OBJECT_TYPE:
            bucket = out.setdefault(low, set())
            for row in rows:
                if i < len(row):
                    v = row[i]
                    if v not in (None, "", 0):
                        bucket.add(v)
    return {k: v for k, v in out.items() if v}


def fetch_scoped_pii_values(client, ids_by_col: dict[str, set]) -> set[str]:
    """Fetch PII string values referenced by the given IDs.

    One UNION DISTINCT per ID type; one roundtrip per type. Results are
    lowercased and stripped. Failures are swallowed — this pass is
    best-effort defense-in-depth, it must not break the main tool call.
    """
    known: set[str] = set()
    for id_col, ids in ids_by_col.items():
        spec = _SCOPED_PII_SOURCES.get(id_col)
        if not spec or not ids:
            continue
        table, pii_cols = spec
        parts = [
            f"SELECT DISTINCT lower(trim({pc})) AS v FROM {table} "
            f"WHERE {id_col} IN %(ids)s AND {pc} IS NOT NULL AND {pc} != ''"
            for pc in pii_cols
        ]
        sql = " UNION DISTINCT ".join(parts)
        try:
            res = client.query(sql, parameters={"ids": list(ids)})
            for row in res.result_rows:
                v = row[0]
                if v:
                    known.add(v)
        except Exception as exc:
            log.warning("scoped PII fetch failed for %s: %s", id_col, exc)
    return known


_owner_names_cache: set[str] | None = None


def fetch_owner_names(client) -> set[str]:
    """Return lowercased first / last / 'first last' strings for every owner.

    Cached on the module — owners change rarely and a false-positive scrub of
    an owner name breaks the policy (owners are exempt). Module-level cache
    means the set is rebuilt once per MCP server process.
    """
    global _owner_names_cache
    if _owner_names_cache is not None:
        return _owner_names_cache
    sql = (
        "SELECT DISTINCT v FROM ("
        "  SELECT lower(trim(first_name)) AS v FROM silver.dim_owners "
        "  WHERE first_name IS NOT NULL AND first_name != ''"
        "  UNION DISTINCT"
        "  SELECT lower(trim(last_name)) AS v FROM silver.dim_owners "
        "  WHERE last_name IS NOT NULL AND last_name != ''"
        "  UNION DISTINCT"
        "  SELECT lower(trim(concat(first_name, ' ', last_name))) AS v "
        "  FROM silver.dim_owners "
        "  WHERE first_name IS NOT NULL AND first_name != '' "
        "    AND last_name IS NOT NULL AND last_name != ''"
        ") WHERE v != ''"
    )
    try:
        res = client.query(sql)
        _owner_names_cache = {row[0] for row in res.result_rows if row[0]}
    except Exception as exc:
        log.warning("owner names fetch failed: %s", exc)
        _owner_names_cache = set()
    return _owner_names_cache


def scrub_by_values(
    columns: Sequence[str],
    rows: Iterable[Sequence],
    known_pii_values: set[str],
) -> list[list]:
    """Mask any string cell whose lower/stripped value matches known_pii_values.

    Runs AFTER column-name masking (apply_privacy). Already-masked cells are
    safe — their destroyed form won't match any raw PII string. URL cells
    contain scheme+host, also safe.

    `columns` is accepted for symmetry / future column-aware heuristics.
    """
    known_pii_values = known_pii_values or set()
    new_rows: list[list] = []
    for row in rows:
        new_row = list(row)
        if known_pii_values:
            for i, v in enumerate(new_row):
                if not isinstance(v, str) or not v.strip():
                    continue
                low = v.strip().lower()
                if low in known_pii_values:
                    new_row[i] = _infer_and_mask(v)
        new_rows.append(new_row)
    return new_rows


# ---------------------------------------------------------------------------
# Privacy policy text — served as schema://privacy_policy MCP resource
# ---------------------------------------------------------------------------

PRIVACY_POLICY_TEXT = """PRIVACY POLICY — PII MASKING (MCP-only)

The MCP surface reads from the ANONYMIZED layer (silver_anon.* / gold_anon.*).
Customer PII is pre-masked at storage time: the underlying rows physically do
not contain raw names, emails, phones, or other customer-identifying strings,
regardless of what query you write. Owners, pipeline labels, stage labels,
dictionary enums, IDs, dates, numeric metrics, and country are copied verbatim.

Mask shape — every masked token is a fixed-width '***' so length cannot be
inferred by counting characters:
  text   'Alice Anderson'         -> 'A*** A***'
  email  'alice.anderson@example.com' -> 'a***.a***@e***.com'   (TLD preserved)
  phone  '+33 6 12 34 56 78'      -> '+*** *** *** *** *** ***'
                                      (each digit run collapsed to '***')

ACTIVITY/ENGAGEMENT TABLES ARE BLOCKED:
  fact_activities and bridge_activity_contact / _company / _deal are NOT copied
  into silver_anon — they are physically absent from the MCP-visible layer.
  Their free-text subjects, call dispositions, email bodies, note content and
  task descriptions may contain unstructured PII that storage-side masking
  cannot scrub. run_sql will reject any query that references these tables.
  If you need activity data, use the in-app chat.

WHAT IS MASKED (storage-side, in silver_anon / gold_anon):
  - People:  full_name, firstname, lastname, jobtitle
  - Deals / leads: dealname, company_name, hs_lead_name, lead_name
  - Companies: name, domain, website, address, city, zip
  - Contact:   email (segments masked, TLD preserved),
               phone (digit runs collapsed)
  - Form submissions: firstname, lastname, email, company, jobtitle, phone,
                      page_url

WHAT IS NOT MASKED (internal / non-identifying):
  - Owner / rep / staff: owner_name, first_name, last_name (on dim_owners),
                         hubspot_owner_id, all dictGet(...dict_owners...) output
  - Pipeline labels, stage labels, dictionary enums
  - All IDs, dates, numeric metrics, lifecycle enums
  - country (too coarse to identify individuals)

RULES YOU SHOULD FOLLOW WHEN WRITING SQL:
  1. Always SELECT the matching ID column alongside any masked label so the
     user can open the record in HubSpot:
       dealname     -> also select deal_id
       full_name    -> also select contact_id
       name (co.)   -> also select company_id
       hs_lead_name -> also select lead_id
     The server appends <id_col>_url columns automatically when HUBSPOT_HUB_ID
     is configured. You do not need to build the URL yourself.

  2. Aliasing or transforming PII columns is harmless — the underlying rows
     are already masked. 'full_name AS customer', 'substring(full_name, 1, 5)',
     'concat(firstname, ' ', lastname)' all yield masked values.

  3. GROUP BY / WHERE / ORDER BY on PII columns works but matches against the
     masked strings, not the originals. Prefer grouping by ID.

  4. Don't try to bypass masking via dictGet(...dict_contacts...) — the anon
     dictionaries are built from silver_anon.dim_contacts, so they return the
     same masked values. dict_owners / dict_pipelines / dict_pipeline_stages
     remain unmasked and are the intended label source for those entities.
"""
