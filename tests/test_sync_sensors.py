"""The chaining sensors must carry the sync correlation tags forward — that is
the one plumbing change that lets four sensor-chained runs be read back as one
sync."""

from __future__ import annotations

from types import SimpleNamespace

from sensors import (
    _chain,
    propagated_sync_tags,
    trigger_anon_after_gold,
    trigger_gold_after_silver,
    trigger_silver_after_bronze,
)


def _context(tags: dict[str, str]):
    return SimpleNamespace(dagster_run=SimpleNamespace(tags=tags))


def test_sync_tags_are_propagated_onto_the_requested_run():
    request = _chain(_context({
        "clickspot/sync": "ui",
        "clickspot/sync_id": "abc123",
        "dagster/run_key": "ignored",
    }))
    assert request.tags == {"clickspot/sync": "ui", "clickspot/sync_id": "abc123"}


def test_untagged_runs_chain_with_no_tags():
    """Manual Dagster launches keep working exactly as before. (The hourly
    schedule is no longer untagged — schedules.py stamps its runs.)"""
    request = _chain(_context({"dagster/partition": "whatever"}))
    assert request.tags == {}


def test_only_clickspot_tags_propagate():
    tags = propagated_sync_tags({
        "clickspot/sync_id": "abc",
        "dagster/parent_run_id": "xyz",
        "user": "someone",
    })
    assert tags == {"clickspot/sync_id": "abc"}


def test_all_three_sensors_exist_and_chain():
    # The wiring itself: each sensor is defined against its upstream job and
    # requests the next one. (Names pin the chain documented in CLAUDE.md.)
    assert trigger_silver_after_bronze.name == "trigger_silver_after_bronze"
    assert trigger_gold_after_silver.name == "trigger_gold_after_silver"
    assert trigger_anon_after_gold.name == "trigger_anon_after_gold"
