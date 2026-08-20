"""Shared fixtures for the route tests."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.customer import config as cc
from app.semantic import layer as semantic_layer


@pytest.fixture
def isolated_config(tmp_path):
    """Redirect customer.json (and the semantic cache) to a temp dir so tests
    never touch the developer's real ~/.clickspot state."""
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(json.dumps({"company_name": "Test"}))
    with (
        patch.object(cc, "CONFIG_FILE", cfgfile),
        patch.object(cc, "CONFIG_DIR", tmp_path),
        # A save unlinks the semantic layer cache. Redirect it too, or the tests
        # delete the developer's real ~/.clickspot/schema_cache.json.
        patch.object(semantic_layer, "CACHE_FILE", tmp_path / "schema_cache.json"),
    ):
        yield cfgfile
    # Tests may refresh process-wide state that outlives them: the table
    # catalog and the memoized schema prompt built on top of it. Redo both once
    # the patches are off, so the next test sees the real config rather than a
    # warehouse schema invented here.
    from app.config import rebuild_tables
    from app.llm.providers import refresh_schema_prompt
    rebuild_tables()
    refresh_schema_prompt()
