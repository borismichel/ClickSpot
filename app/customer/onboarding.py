"""Interactive CLI wizard that walks an operator through per-portal config.

Run:
    python -m app.customer.onboarding

What it does:
1. Verifies HUBSPOT_TOKEN + HUBSPOT_HUB_ID are present in .env.
2. Verifies ClickHouse is reachable.
3. If silver is loaded, auto-discovers pipelines / stages / currency from it
   and shows the operator the discovered values.
4. Asks the operator to:
   - confirm or rename the company,
   - write a one-line business blurb,
   - pick the main pipeline (numbered list),
   - pick the canonical revenue column (numbered list of amount-like columns).
5. Persists everything to ~/.clickspot/customer.json (0600).
6. Suggests follow-up: re-run silver_job + gold_job + anon_job so any newly
   added custom silver columns get materialized.

No external deps — pure stdin/stdout numbered choices. Works in any terminal,
is keyboard-only, and is idempotent (re-running just lets you re-edit each value).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.customer import config as cc

log = logging.getLogger("app.customer.onboarding")


def _input(prompt: str, default: str | None = None) -> str:
    """Free-text input with optional default."""
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    return raw or (default or "")


def _choose(prompt: str, options: list[str], default_idx: int = 0) -> str | None:
    """Numbered-list pick. Returns None if the operator types nothing and there's no default option."""
    if not options:
        print(f"  ({prompt} — no options to choose from)")
        return None
    print(f"\n{prompt}")
    for i, opt in enumerate(options, start=1):
        marker = " ←" if (i - 1) == default_idx else ""
        print(f"  [{i}] {opt}{marker}")
    while True:
        raw = input(f"Pick 1-{len(options)} (Enter = {default_idx + 1}): ").strip()
        if not raw:
            return options[default_idx]
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print(f"  Invalid — type a number 1-{len(options)} (or just Enter to accept default).")


def _confirm(prompt: str, default: bool = True) -> bool:
    default_str = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{prompt} [{default_str}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False


def _discover_amount_columns(client) -> list[str]:
    """Returns dim_deals columns that look revenue-shaped (amount, arr, tcv, mrr, revenue, ACV)."""
    try:
        rows = client.query(
            "SELECT name FROM system.columns WHERE database = 'silver' AND table = 'dim_deals' ORDER BY name"
        ).result_rows
        candidates = []
        for (name,) in rows:
            low = name.lower()
            if any(token in low for token in ("amount", "arr", "tcv", "mrr", "revenue", "acv", "value", "price")):
                candidates.append(name)
        # Make sure 'amount' (the HubSpot default) comes first
        candidates.sort(key=lambda n: (n != "amount", n))
        return candidates
    except Exception as e:
        log.warning("Could not discover amount columns: %s", e)
        return ["amount"]


def run() -> int:
    """Main wizard. Returns 0 on success, non-zero on abort."""
    load_dotenv()

    print("=" * 70)
    print("ClickSpot — first-time portal setup")
    print("=" * 70)

    # ---- Step 1: env vars
    token = os.environ.get("HUBSPOT_TOKEN", "").strip()
    hub_id = os.environ.get("HUBSPOT_HUB_ID", "").strip()
    if not token or not hub_id:
        print("\n❗ HUBSPOT_TOKEN and HUBSPOT_HUB_ID must be set in .env before running this wizard.")
        print("   Edit .env and re-run.")
        return 1
    print(f"\n✓ HubSpot token loaded (hub_id: {hub_id})")

    # ---- Step 2: ClickHouse reachable + silver populated?
    try:
        from app.db import get_client
        client = get_client()
        pipeline_rows = client.query(
            "SELECT label FROM silver.dim_pipelines WHERE label != '' ORDER BY label"
        ).result_rows
        pipelines = [r[0] for r in pipeline_rows]
    except Exception as e:
        print(f"\n❗ ClickHouse not reachable or silver not loaded: {e}")
        print("   Start ClickHouse (`docker compose up -d`) and run `dagster job execute -j bronze_job -m definitions`")
        print("   followed by silver_job, then re-run this wizard.")
        return 1

    if not pipelines:
        print("\n❗ silver.dim_pipelines is empty. Run bronze + silver jobs first, then re-run this wizard.")
        return 1
    print(f"✓ Silver loaded — {len(pipelines)} pipelines discovered.")

    # ---- Step 3: auto-discover into customer.json (merge defaults only)
    current = cc.load()
    discovered = cc.auto_discover(client)
    merged = cc.merge_defaults_only(current, discovered)

    # ---- Step 4: company name + blurb
    print("\n--- Company ---")
    company = _input("Company / portal name", default=merged.get("company_name") or "")
    blurb = _input(
        "One-line business blurb (shown to the LLM as context)",
        default=merged.get("company_blurb") or "",
    )

    # ---- Step 5: main pipeline
    print("\n--- Main pipeline ---")
    print("Which is your main sales pipeline? (The LLM defaults to filtering here unless asked otherwise.)")
    current_main = merged.get("main_pipeline")
    default_idx = pipelines.index(current_main) if current_main in pipelines else 0
    main_pipeline = _choose("Pipelines:", pipelines, default_idx=default_idx)

    # ---- Step 6: canonical amount column
    print("\n--- Canonical revenue column ---")
    print("Which column on dim_deals is your canonical revenue field? (Default `amount` works for most portals;")
    print("override if you use a custom ARR/TCV field as the 'real' revenue number.)")
    amount_candidates = _discover_amount_columns(client)
    current_amount = merged.get("canonical_amount_col", "amount")
    default_idx = amount_candidates.index(current_amount) if current_amount in amount_candidates else 0
    canonical_amount = _choose("Revenue-shaped columns:", amount_candidates, default_idx=default_idx)

    # ---- Step 7: pipeline notes (one each)
    if pipelines and _confirm("\nAdd one-line note per pipeline (helps the LLM disambiguate)?", default=False):
        notes_map = {p["label"]: p.get("note", "") for p in (merged.get("all_pipelines") or []) if isinstance(p, dict)}
        all_pipelines_out = []
        for p in pipelines:
            note = _input(f"  Note for '{p}'", default=notes_map.get(p, ""))
            all_pipelines_out.append({"label": p, "note": note})
        merged["all_pipelines"] = all_pipelines_out

    # ---- Step 8: assemble + save
    merged["company_name"] = company or merged["company_name"]
    merged["company_blurb"] = blurb
    merged["main_pipeline"] = main_pipeline
    merged["canonical_amount_col"] = canonical_amount

    cc.save(merged)
    print(f"\n✓ Saved {cc.CONFIG_FILE}")
    print("\nSuggested next steps:")
    print("  - Re-run silver_job + gold_job + anon_job to fully materialize any new portal-specific columns")
    print("    (relevant if you added tuples to silver_config_custom.py):")
    print("      dagster job execute -j silver_job -m definitions")
    print("      dagster job execute -j gold_job -m definitions")
    print("      dagster job execute -j anon_job -m definitions")
    print("  - Restart the backend so the new customer config picks up:")
    print("      uvicorn app.main:app --port 8192 --reload")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(130)
