"""Snapshot tests for the ClickHouse-native PII mask-expression builders.

The builders emit SQL strings that are spliced into `assets/silver_anon.py`
and `assets/gold_anon.py`. If a snapshot changes, review the change against
the storage-side expectations: every mask token must be a fixed-width '***'
so original length cannot be inferred.
"""

from __future__ import annotations

import pytest

from app.engine.anon_masking import mask_column


# ---------------------------------------------------------------------------
# Text mask — per-word first char + '***'
# ---------------------------------------------------------------------------

class TestTextMask:
    def test_wraps_in_empty_guard(self):
        sql = mask_column("full_name", "text")
        assert sql.startswith("if(empty(full_name), full_name, ")
        assert sql.endswith(")")

    def test_uses_fixed_width_star_token(self):
        sql = mask_column("full_name", "text")
        # Single-quoted *** token appears — fixed-width, not per-char
        assert "'***'" in sql
        # No per-character repeat expressions
        assert "repeat(" not in sql

    def test_renders_split_map_concat_pipeline(self):
        sql = mask_column("full_name", "text")
        assert "splitByChar(' '," in sql
        assert "arrayMap" in sql
        assert "arrayStringConcat" in sql
        assert "substring(w, 1, 1)" in sql


# ---------------------------------------------------------------------------
# Email mask — per-segment first char + '***', TLD preserved
# ---------------------------------------------------------------------------

class TestEmailMask:
    def test_no_at_falls_back_to_text(self):
        sql = mask_column("email", "email")
        # The builder wraps the whole expression in a position('@')=0 guard
        # that falls through to the text mask when no '@' is present.
        assert "position(email, '@') = 0" in sql

    def test_splits_local_and_domain(self):
        sql = mask_column("email", "email")
        assert "splitByChar('@', email)[1]" in sql
        assert "splitByChar('@', email)[2]" in sql

    def test_preserves_tld_via_arrayelement(self):
        sql = mask_column("email", "email")
        assert "arrayElement(splitByChar('.', splitByChar('@', email)[2]), -1)" in sql

    def test_uses_fixed_width_star_token(self):
        sql = mask_column("email", "email")
        assert "'***'" in sql


# ---------------------------------------------------------------------------
# Phone mask — collapse each digit run to '***'
# ---------------------------------------------------------------------------

class TestPhoneMask:
    def test_regex_collapses_digit_runs(self):
        sql = mask_column("phone", "phone")
        assert "replaceRegexpAll(phone, '[0-9]+', '***')" in sql

    def test_wrapped_in_empty_guard(self):
        sql = mask_column("phone", "phone")
        assert sql.startswith("if(empty(phone), phone, ")


# ---------------------------------------------------------------------------
# mask_column — unknown kind
# ---------------------------------------------------------------------------

class TestUnknownKind:
    def test_raises_valueerror(self):
        with pytest.raises(ValueError):
            mask_column("full_name", "ssn")

    def test_error_lists_supported_kinds(self):
        with pytest.raises(ValueError) as exc:
            mask_column("x", "bogus")
        msg = str(exc.value)
        assert "email" in msg
        assert "phone" in msg
        assert "text" in msg


# ---------------------------------------------------------------------------
# Column-name interpolation — the builder must bind to the caller's col name
# ---------------------------------------------------------------------------

class TestColumnBinding:
    def test_text_mentions_col_name(self):
        sql = mask_column("jobtitle", "text")
        assert "jobtitle" in sql
        assert "full_name" not in sql

    def test_email_mentions_col_name(self):
        sql = mask_column("work_email", "email")
        assert "work_email" in sql

    def test_phone_mentions_col_name(self):
        sql = mask_column("mobile_phone", "phone")
        assert "mobile_phone" in sql
