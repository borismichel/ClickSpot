"""Tests for the MCP PII masking and HubSpot URL injection layer."""

from __future__ import annotations

import pytest

from app.mcp.pii import (
    ID_TO_OBJECT_TYPE,
    apply_privacy,
    hubspot_url,
    mask_email,
    mask_phone,
    mask_text,
)


# ---------------------------------------------------------------------------
# mask_text
# ---------------------------------------------------------------------------

class TestMaskText:
    def test_single_word(self):
        assert mask_text("Boris") == "B***"

    def test_two_words(self):
        assert mask_text("Alice Anderson") == "A*** A***"

    def test_multiple_words(self):
        assert mask_text("Jean Claude Van Damme") == "J*** C*** V*** D***"

    def test_single_character(self):
        # Fixed-width *** appended even for single-char words so length
        # cannot be inferred from output width.
        assert mask_text("X") == "X***"

    def test_empty_string(self):
        assert mask_text("") == ""

    def test_whitespace_only(self):
        assert mask_text("   ") == "   "

    def test_unicode_first_char_preserved(self):
        assert mask_text("Étienne") == "É***"

    def test_none(self):
        assert mask_text(None) is None

    def test_non_string_coerced(self):
        assert mask_text(12345) == "1***"


# ---------------------------------------------------------------------------
# mask_email
# ---------------------------------------------------------------------------

class TestMaskEmail:
    def test_basic(self):
        # TLD "com" preserved; every other segment becomes first char + ***
        assert mask_email("alice.anderson@example.com") == "a***.a***@e***.com"

    def test_multi_segment_domain(self):
        assert mask_email("b@foo.bar.co.uk") == "b***@f***.b***.c***.uk"

    def test_bare_domain_no_tld(self):
        assert mask_email("b@localhost") == "b***@l***"

    def test_no_at_sign_falls_back_to_text(self):
        assert mask_email("no-at-here") == "n***"

    def test_empty(self):
        assert mask_email("") == ""

    def test_none(self):
        assert mask_email(None) is None


# ---------------------------------------------------------------------------
# mask_phone
# ---------------------------------------------------------------------------

class TestMaskPhone:
    def test_international_formatted(self):
        # Each run of digits collapses to a single '***' — digit count hidden
        assert mask_phone("+33 6 12 34 56 78") == "+*** *** *** *** *** ***"

    def test_digits_only(self):
        # One contiguous digit run -> one '***'
        assert mask_phone("0301234567") == "***"

    def test_with_dashes(self):
        assert mask_phone("+1-555-123-4567") == "+***-***-***-***"

    def test_no_digits_returned_unchanged(self):
        assert mask_phone("N/A") == "N/A"

    def test_empty(self):
        assert mask_phone("") == ""

    def test_none(self):
        assert mask_phone(None) is None


# ---------------------------------------------------------------------------
# hubspot_url
# ---------------------------------------------------------------------------

class TestHubspotUrl:
    def test_contact(self):
        assert hubspot_url("12345", "contact_id", "999") == (
            "https://app.hubspot.com/contacts/12345/record/0-1/999"
        )

    def test_deal(self):
        assert hubspot_url("12345", "deal_id", "42") == (
            "https://app.hubspot.com/contacts/12345/record/0-3/42"
        )

    def test_company(self):
        assert hubspot_url("12345", "company_id", "77") == (
            "https://app.hubspot.com/contacts/12345/record/0-2/77"
        )

    def test_lead(self):
        assert hubspot_url("12345", "lead_id", "555") == (
            "https://app.hubspot.com/contacts/12345/record/0-34/555"
        )

    def test_eu_host_from_parameter(self):
        # User's actual portal (5087510 / EU region) — matches the canonical
        # link the user provided as the correct format.
        assert hubspot_url("5087510", "deal_id", "222059286771", "app-eu1.hubspot.com") == (
            "https://app-eu1.hubspot.com/contacts/5087510/record/0-3/222059286771"
        )

    def test_missing_hub_id_returns_none(self):
        assert hubspot_url(None, "deal_id", "42") is None
        assert hubspot_url("", "deal_id", "42") is None

    def test_missing_id_value_returns_none(self):
        assert hubspot_url("12345", "deal_id", None) is None
        assert hubspot_url("12345", "deal_id", "") is None

    def test_unknown_id_col_returns_none(self):
        assert hubspot_url("12345", "hubspot_owner_id", "1") is None


class TestHubspotAppHost:
    """hubspot_app_host() resolves in this order: customer.json hubspot_region →
    HUBSPOT_REGION env → token parse → NA1 default. These tests isolate the
    token-parse leg by mocking out the first two so the developer's local
    customer.json doesn't poison results."""

    @pytest.fixture(autouse=True)
    def _isolate_region_sources(self, monkeypatch):
        from app.customer import config as customer_config

        monkeypatch.setattr(customer_config, "load", lambda: {})
        monkeypatch.delenv("HUBSPOT_REGION", raising=False)
        monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    def test_na1_token_uses_default_host(self):
        from app.mcp.pii import hubspot_app_host
        assert hubspot_app_host("pat-na1-abc-def") == "app.hubspot.com"

    def test_eu1_token_uses_regional_host(self):
        from app.mcp.pii import hubspot_app_host
        assert hubspot_app_host("pat-eu1-931e928a-b875-4910-9030-f05c4bc7fea3") == (
            "app-eu1.hubspot.com"
        )

    def test_missing_token_falls_back_to_default(self):
        from app.mcp.pii import hubspot_app_host
        assert hubspot_app_host("") == "app.hubspot.com"
        assert hubspot_app_host(None) == "app.hubspot.com"

    def test_non_pat_token_falls_back_to_default(self):
        from app.mcp.pii import hubspot_app_host
        assert hubspot_app_host("bearer-xyz") == "app.hubspot.com"

    def test_customer_json_region_wins_over_token(self, monkeypatch):
        from app.customer import config as customer_config
        from app.mcp.pii import hubspot_app_host

        monkeypatch.setattr(customer_config, "load", lambda: {"hubspot_region": "na2"})
        # Token says eu1, customer.json says na2 — customer.json wins
        assert hubspot_app_host("pat-eu1-abc") == "app-na2.hubspot.com"

    def test_env_var_wins_over_token(self, monkeypatch):
        from app.mcp.pii import hubspot_app_host

        monkeypatch.setenv("HUBSPOT_REGION", "na2")
        assert hubspot_app_host("pat-eu1-abc") == "app-na2.hubspot.com"


# ---------------------------------------------------------------------------
# apply_privacy — column selection
# ---------------------------------------------------------------------------

class TestApplyPrivacyColumnSelection:
    def test_pii_text_column_masked(self):
        cols, rows = apply_privacy(
            ["contact_id", "full_name"],
            [["c1", "Alice Anderson"]],
            hub_id="9999",
        )
        # url col appended at end
        assert cols[:2] == ["contact_id", "full_name"]
        assert rows[0][0] == "c1"
        assert rows[0][1] == "A*** A***"

    def test_email_column_uses_mask_email(self):
        cols, rows = apply_privacy(
            ["email"],
            [["alice.anderson@example.com"]],
            hub_id=None,
        )
        assert rows[0][0] == "a***.a***@e***.com"

    def test_phone_column_uses_mask_phone(self):
        cols, rows = apply_privacy(
            ["phone"],
            [["+49 30 12345678"]],
            hub_id=None,
        )
        assert rows[0][0] == "+*** *** ***"

    def test_non_pii_column_untouched(self):
        cols, rows = apply_privacy(
            ["deal_id", "amount", "createdate"],
            [["d1", 99.5, "2024-01-01"]],
            hub_id=None,
        )
        assert rows[0] == ["d1", 99.5, "2024-01-01"]

    def test_owner_columns_not_masked(self):
        # owner_name, first_name, last_name, hubspot_owner_id are all exempt
        cols, rows = apply_privacy(
            ["owner_name", "first_name", "last_name", "hubspot_owner_id"],
            [["Jan Birkholz", "Jan", "Birkholz", "123"]],
            hub_id=None,
        )
        assert rows[0] == ["Jan Birkholz", "Jan", "Birkholz", "123"]

    def test_dictget_dim_owners_not_masked(self):
        col_name = "dictGet('silver.dict_owners', 'first_name', tuple(hubspot_owner_id))"
        cols, rows = apply_privacy(
            [col_name],
            [["Boris"]],
            hub_id=None,
        )
        assert rows[0] == ["Boris"]  # NOT masked

    def test_dictget_dim_contacts_full_name_masked(self):
        col_name = "dictGet('silver.dict_contacts', 'full_name', tuple(contact_id))"
        cols, rows = apply_privacy(
            [col_name],
            [["Alice Anderson"]],
            hub_id=None,
        )
        assert rows[0] == ["A*** A***"]

    def test_aliased_pii_not_masked_documented_limitation(self):
        # `SELECT full_name AS customer` produces an output column named "customer",
        # which is not in PII_COLUMN_NAMES. The schema://privacy_policy resource tells
        # the LLM not to do this; we document the bypass here.
        cols, rows = apply_privacy(
            ["customer"],
            [["Alice Anderson"]],
            hub_id=None,
        )
        assert rows[0] == ["Alice Anderson"]  # NOT masked by design

    def test_case_insensitive_column_match(self):
        cols, rows = apply_privacy(
            ["FULL_NAME", "Email", "Phone"],
            [["Alice Anderson", "b@x.com", "+49 30"]],
            hub_id=None,
        )
        assert rows[0][0] == "A*** A***"
        assert rows[0][1] == "b***@x***.com"  # TLD preserved; all other segments fixed-width ***
        assert rows[0][2] == "+*** ***"


# ---------------------------------------------------------------------------
# apply_privacy — URL injection
# ---------------------------------------------------------------------------

class TestApplyPrivacyUrlInjection:
    def test_deal_id_url_appended(self):
        cols, rows = apply_privacy(
            ["deal_id", "dealname"],
            [["D42", "Big Deal"]],
            hub_id="9999",
        )
        assert cols == ["deal_id", "dealname", "deal_id_url"]
        assert rows[0][2] == "https://app.hubspot.com/contacts/9999/record/0-3/D42"

    def test_contact_id_url_appended(self):
        cols, rows = apply_privacy(
            ["contact_id", "full_name"],
            [["C1", "Alice Anderson"]],
            hub_id="9999",
        )
        assert cols[-1] == "contact_id_url"
        assert rows[0][-1] == "https://app.hubspot.com/contacts/9999/record/0-1/C1"

    def test_company_id_url_appended(self):
        cols, rows = apply_privacy(
            ["company_id", "name"],
            [["CO77", "Acme Corp"]],
            hub_id="9999",
        )
        assert cols[-1] == "company_id_url"
        assert rows[0][-1] == "https://app.hubspot.com/contacts/9999/record/0-2/CO77"

    def test_lead_id_uses_record_segment(self):
        cols, rows = apply_privacy(
            ["lead_id", "hs_lead_name"],
            [["L5", "Lead X"]],
            hub_id="9999",
        )
        assert rows[0][-1] == "https://app.hubspot.com/contacts/9999/record/0-34/L5"

    def test_multiple_id_columns_multiple_url_columns(self):
        cols, rows = apply_privacy(
            ["deal_id", "contact_id", "dealname"],
            [["D1", "C1", "Big Deal"]],
            hub_id="9999",
        )
        assert cols[-2:] == ["deal_id_url", "contact_id_url"]
        assert rows[0][-2] == "https://app.hubspot.com/contacts/9999/record/0-3/D1"
        assert rows[0][-1] == "https://app.hubspot.com/contacts/9999/record/0-1/C1"

    def test_eu_host_propagates_through_apply_privacy(self):
        cols, rows = apply_privacy(
            ["deal_id", "dealname"],
            [["222059286771", "Big EU Deal"]],
            hub_id="5087510",
            app_host="app-eu1.hubspot.com",
        )
        assert rows[0][-1] == (
            "https://app-eu1.hubspot.com/contacts/5087510/record/0-3/222059286771"
        )

    def test_null_id_produces_null_url_cell(self):
        cols, rows = apply_privacy(
            ["deal_id", "dealname"],
            [[None, "Nameless"]],
            hub_id="9999",
        )
        assert rows[0][-1] is None

    def test_missing_hub_id_skips_url_columns(self):
        cols, rows = apply_privacy(
            ["deal_id", "dealname"],
            [["D1", "Big Deal"]],
            hub_id=None,
        )
        assert cols == ["deal_id", "dealname"]
        assert rows[0] == ["D1", "B*** D***"]

    def test_empty_rows_skips_url_columns(self):
        cols, rows = apply_privacy(
            ["deal_id", "dealname"],
            [],
            hub_id="9999",
        )
        assert cols == ["deal_id", "dealname"]
        assert rows == []

    def test_url_column_count_matches_row_count(self):
        cols, rows = apply_privacy(
            ["deal_id", "dealname"],
            [["D1", "Alpha"], ["D2", "Beta"], ["D3", "Gamma"]],
            hub_id="9999",
        )
        assert all(len(r) == 3 for r in rows)
        assert rows[0][-1].endswith("/record/0-3/D1")
        assert rows[1][-1].endswith("/record/0-3/D2")
        assert rows[2][-1].endswith("/record/0-3/D3")


# ---------------------------------------------------------------------------
# apply_privacy — edge cases
# ---------------------------------------------------------------------------

class TestApplyPrivacyEdgeCases:
    def test_empty_inputs(self):
        cols, rows = apply_privacy([], [], hub_id="9999")
        assert cols == []
        assert rows == []

    def test_preserves_row_order(self):
        cols, rows = apply_privacy(
            ["full_name"],
            [["Alice"], ["Bob"], ["Charlie"]],
            hub_id=None,
        )
        assert rows == [["A***"], ["B***"], ["C***"]]

    def test_does_not_mutate_inputs(self):
        orig_cols = ["full_name", "contact_id"]
        orig_rows = [["Alice Anderson", "C1"]]
        apply_privacy(orig_cols, orig_rows, hub_id="9999")
        assert orig_cols == ["full_name", "contact_id"]  # unchanged
        assert orig_rows == [["Alice Anderson", "C1"]]      # unchanged

    def test_row_length_mismatch_truncated(self):
        # 2 columns declared but row has only 1 cell
        cols, rows = apply_privacy(
            ["full_name", "contact_id"],
            [["Boris"]],
            hub_id=None,
        )
        assert len(rows[0]) == 2
        assert rows[0][0] == "B***"
        assert rows[0][1] is None

    def test_id_value_appears_only_in_url_when_masked_elsewhere(self):
        # contact_id is NOT PII; it's present both in its own column and in the URL
        cols, rows = apply_privacy(
            ["contact_id", "full_name"],
            [["C1", "Alice Anderson"]],
            hub_id="9999",
        )
        assert rows[0][0] == "C1"  # ID visible
        assert rows[0][1] == "A*** A***"
        assert rows[0][2].endswith("/record/0-1/C1")


# ---------------------------------------------------------------------------
# ID_TO_OBJECT_TYPE parity with frontend
# ---------------------------------------------------------------------------

def test_id_mapping_mirrors_frontend():
    # Frontend ResultTable.tsx ID_COL_TO_TYPE — keep these in sync.
    # Values are HubSpot object type IDs used as /record/<typeId>/<id>.
    assert ID_TO_OBJECT_TYPE == {
        "contact_id": "0-1",
        "company_id": "0-2",
        "deal_id":    "0-3",
        "lead_id":    "0-34",
    }
