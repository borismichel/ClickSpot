"""Tests for the MCP defense-in-depth value-based PII scrub.

Covers collect_ids_from_rows, scrub_by_values, and _infer_and_mask. The
client-facing fetch_* functions are covered with stubbed clients.
"""

from __future__ import annotations

import pytest

from app.mcp import pii as pii_mod
from app.mcp.pii import (
    _infer_and_mask,
    collect_ids_from_rows,
    fetch_owner_names,
    fetch_scoped_pii_values,
    scrub_by_values,
)


# ---------------------------------------------------------------------------
# _infer_and_mask
# ---------------------------------------------------------------------------

class TestInferAndMask:
    def test_email_routed_to_email_mask(self):
        assert _infer_and_mask("alice@example.com") == "a***@e***.com"

    def test_phone_routed_to_phone_mask(self):
        assert _infer_and_mask("+33 6 12 34 56 78") == "+*** *** *** *** *** ***"

    def test_plain_text_routed_to_text_mask(self):
        assert _infer_and_mask("Bob Builder") == "B*** B***"


# ---------------------------------------------------------------------------
# collect_ids_from_rows
# ---------------------------------------------------------------------------

class TestCollectIdsFromRows:
    def test_collects_contact_ids(self):
        cols = ["contact_id", "full_name"]
        rows = [["c1", "Boris"], ["c2", "Ada"]]
        assert collect_ids_from_rows(cols, rows) == {"contact_id": {"c1", "c2"}}

    def test_collects_multiple_id_types(self):
        cols = ["contact_id", "deal_id", "amount"]
        rows = [["c1", "d1", 100], ["c2", "d2", 200]]
        assert collect_ids_from_rows(cols, rows) == {
            "contact_id": {"c1", "c2"},
            "deal_id": {"d1", "d2"},
        }

    def test_case_insensitive_column_name(self):
        cols = ["Contact_ID", "COMPANY_ID"]
        rows = [["c1", "co1"]]
        got = collect_ids_from_rows(cols, rows)
        assert got == {"contact_id": {"c1"}, "company_id": {"co1"}}

    def test_skips_aliased_ids(self):
        # Aliased IDs are intentionally ignored — privacy policy forbids aliasing
        cols = ["cid", "full_name"]
        rows = [["c1", "Boris"]]
        assert collect_ids_from_rows(cols, rows) == {}

    def test_skips_empty_and_null_ids(self):
        cols = ["contact_id"]
        rows = [["c1"], [None], [""], [0], ["c2"]]
        assert collect_ids_from_rows(cols, rows) == {"contact_id": {"c1", "c2"}}

    def test_empty_rows(self):
        assert collect_ids_from_rows(["contact_id"], []) == {}

    def test_no_id_columns(self):
        assert collect_ids_from_rows(["foo", "bar"], [[1, 2]]) == {}

    def test_lead_id_mapped(self):
        got = collect_ids_from_rows(["lead_id"], [["l1"]])
        assert got == {"lead_id": {"l1"}}


# ---------------------------------------------------------------------------
# scrub_by_values
# ---------------------------------------------------------------------------

class TestScrubByValues:
    def test_masks_matching_cell_as_text(self):
        cols = ["lead", "stage"]
        rows = [["Bob Builder", "SQL"]]
        known = {"bob builder"}
        out = scrub_by_values(cols, rows, known)
        assert out == [["B*** B***", "SQL"]]

    def test_case_insensitive_matching(self):
        out = scrub_by_values(
            ["x"], [["ALICE ANDERSON"]], {"alice anderson"},
        )
        assert out == [["A*** A***"]]

    def test_strips_whitespace_before_matching(self):
        out = scrub_by_values(
            ["x"], [["  Bob Builder  "]], {"bob builder"},
        )
        # Matched, masked text preserves original spacing
        assert out[0][0].strip().startswith("B***")

    def test_no_match_passes_through(self):
        cols = ["stage", "owner"]
        rows = [["SQL", "Alice Anderson"]]
        known = {"bob builder"}
        assert scrub_by_values(cols, rows, known) == rows

    def test_email_cell_routed_to_email_masker(self):
        out = scrub_by_values(
            ["x"], [["alice@example.com"]], {"alice@example.com"},
        )
        assert "@" in out[0][0]
        assert "*" in out[0][0]

    def test_phone_cell_routed_to_phone_masker(self):
        out = scrub_by_values(
            ["x"], [["+33 612 34 56 78"]], {"+33 612 34 56 78"},
        )
        assert out[0][0] == "+*** *** *** *** ***"

    def test_empty_known_set_noop(self):
        cols = ["name"]
        rows = [["anything"]]
        assert scrub_by_values(cols, rows, set()) == [["anything"]]

    def test_none_cells_not_matched(self):
        out = scrub_by_values(
            ["x", "y"], [[None, "Bob Builder"]], {"bob builder"},
        )
        assert out[0][0] is None
        assert out[0][1].startswith("B***")

    def test_non_string_cells_ignored(self):
        out = scrub_by_values(
            ["amount", "name"], [[1000, "Bob Builder"]],
            {"bob builder", "1000"},
        )
        assert out[0][0] == 1000  # int passes through
        assert out[0][1].startswith("B***")

    def test_does_not_mutate_inputs(self):
        rows_in = [["Bob Builder"]]
        scrub_by_values(["x"], rows_in, {"bob builder"})
        assert rows_in == [["Bob Builder"]]

    def test_multiple_rows(self):
        cols = ["lead"]
        rows = [["Bob Builder"], ["Carol Carter"], ["Product Spec"]]
        known = {"bob builder", "carol carter"}
        out = scrub_by_values(cols, rows, known)
        assert out[0][0].startswith("B***")
        assert out[1][0].startswith("C***")
        assert out[2][0] == "Product Spec"


# ---------------------------------------------------------------------------
# fetch_scoped_pii_values / fetch_owner_names — stubbed client
# ---------------------------------------------------------------------------

class _StubResult:
    def __init__(self, rows):
        self.result_rows = rows


class _StubClient:
    def __init__(self, responses):
        # responses: list[list] — each sub-list is the next query's result rows
        self.responses = list(responses)
        self.calls = []

    def query(self, sql, parameters=None):
        self.calls.append((sql, parameters))
        rows = self.responses.pop(0) if self.responses else []
        return _StubResult(rows)


class TestFetchScopedPiiValues:
    def test_queries_each_id_type(self):
        client = _StubClient([
            [["alice anderson"], ["ada lovelace"]],   # contact pii
            [["widget co"], ["acme inc"]],          # company pii
        ])
        got = fetch_scoped_pii_values(client, {
            "contact_id": {"c1", "c2"},
            "company_id": {"co1"},
        })
        assert "alice anderson" in got
        assert "ada lovelace" in got
        assert "widget co" in got
        assert "acme inc" in got
        assert len(client.calls) == 2

    def test_empty_ids_skipped(self):
        client = _StubClient([])
        got = fetch_scoped_pii_values(client, {"contact_id": set()})
        assert got == set()
        assert client.calls == []

    def test_unknown_id_type_skipped(self):
        client = _StubClient([])
        got = fetch_scoped_pii_values(client, {"foo_id": {"x"}})
        assert got == set()
        assert client.calls == []

    def test_swallows_client_exceptions(self):
        class Broken:
            def query(self, sql, parameters=None):
                raise RuntimeError("connection refused")

        got = fetch_scoped_pii_values(Broken(), {"contact_id": {"c1"}})
        assert got == set()  # best-effort, no raise

    def test_uses_parameterized_query(self):
        client = _StubClient([[]])
        fetch_scoped_pii_values(client, {"contact_id": {"c1", "c2"}})
        sql, params = client.calls[0]
        assert "%(ids)s" in sql
        assert set(params["ids"]) == {"c1", "c2"}


class TestFetchOwnerNames:
    def setup_method(self):
        pii_mod._owner_names_cache = None

    def teardown_method(self):
        pii_mod._owner_names_cache = None

    def test_returns_lowercased_owner_names(self):
        client = _StubClient([
            [["alice"], ["anderson"], ["alice anderson"]],
        ])
        got = fetch_owner_names(client)
        assert got == {"alice", "anderson", "alice anderson"}

    def test_cached_after_first_call(self):
        client = _StubClient([[["ada"]]])
        fetch_owner_names(client)
        fetch_owner_names(client)
        assert len(client.calls) == 1  # second call uses cache

    def test_empty_on_client_failure(self):
        class Broken:
            def query(self, sql, parameters=None):
                raise RuntimeError("boom")

        got = fetch_owner_names(Broken())
        assert got == set()


# ---------------------------------------------------------------------------
# End-to-end scrub integration — owners subtracted
# ---------------------------------------------------------------------------

class TestScrubRespectsOwnerExemption:
    def setup_method(self):
        pii_mod._owner_names_cache = None

    def teardown_method(self):
        pii_mod._owner_names_cache = None

    def test_owner_name_survives_scrub_even_if_also_contact(self):
        # Alice Anderson appears as both owner AND contact; policy = keep visible
        scoped_pii = {"alice anderson", "bob builder"}
        owner_names = {"alice anderson"}
        effective = scoped_pii - owner_names

        cols = ["owner_name", "lead"]
        rows = [["Alice Anderson", "Bob Builder"]]
        out = scrub_by_values(cols, rows, effective)

        assert out[0][0] == "Alice Anderson"       # owner untouched
        assert out[0][1].startswith("B***")      # lead masked
