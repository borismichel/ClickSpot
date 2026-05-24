"""Unit tests for period-over-period KPI delta computation (CLI-42).

Guards the zero-baseline fix: a change from a zero baseline must report a
sensible label ("New"), never the meaningless "+100% vs 0" the route produced
before.
"""

import pytest

from app.api.chat_routes import compute_kpi_delta


@pytest.mark.parametrize(
    "cur, prev, expected_pct, expected_label",
    [
        # Normal non-zero baseline → signed percentage, no label.
        (150, 100, 50.0, None),
        (50, 100, -50.0, None),
        (100, 100, 0.0, None),
        (1, 3, -66.7, None),  # rounding to 1 dp
        # Zero baseline with a current value → "New", never a percentage.
        (42, 0, None, "New"),
        (0.5, 0, None, "New"),
        (-3, 0, None, "New"),  # going negative from nothing is still "New"
        # Nothing to compare against / no change from zero → no delta at all.
        (0, 0, None, None),
        (None, 100, None, None),
        (100, None, None, None),
        (None, None, None, None),
        # Non-numeric inputs are ignored rather than raising.
        ("not-a-number", 100, None, None),
        (100, "not-a-number", None, None),
        # String-encoded numbers (ClickHouse can return strings) still work.
        ("150", "100", 50.0, None),
        ("9", "0", None, "New"),
    ],
)
def test_compute_kpi_delta(cur, prev, expected_pct, expected_label):
    pct, label = compute_kpi_delta(cur, prev)
    assert pct == expected_pct
    assert label == expected_label


def test_delta_percent_and_label_are_mutually_exclusive():
    """At most one of (percent, label) is ever set — the renderer relies on it."""
    cases = [(150, 100), (42, 0), (0, 0), (None, 5)]
    for cur, prev in cases:
        pct, label = compute_kpi_delta(cur, prev)
        assert not (pct is not None and label is not None)
