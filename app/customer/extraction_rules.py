"""Dependency-cascade rules for HubSpot object toggles.

When one toggle is disabled, certain other toggles become impossible
(`lead_pipelines` is meaningless without `leads`, `form_submissions` without
`forms`, etc.). The frontend uses these to preview and grey-out affected rows;
the backend re-applies them on save so a bad PUT can't bypass the rules.

`OBJECT_GROUPS` is consumed by the frontend ObjectToggleGrid to render the
hybrid grouped-by-default / per-type-on-expand UX.
"""

from __future__ import annotations

import copy


# Hybrid grouping used by the frontend toggle grid.
OBJECT_GROUPS: dict[str, dict] = {
    "CRM": {
        "children": ["contacts", "companies", "deals", "leads"],
        "expandable": False,
    },
    "Activities": {
        "children": ["calls", "meetings", "emails", "notes", "tasks"],
        "expandable": True,  # rendered as a single "Activities" group, expandable
        "container_key": "activities",
    },
    "Marketing": {
        "children": ["campaigns", "forms", "form_submissions"],
        "expandable": False,
    },
    "Other": {
        "children": ["owners", "deal_pipelines", "lead_pipelines"],
        "expandable": False,
    },
}


# Hard dependencies: if `key` is disabled, every `forced_off` toggle must also
# be disabled. The frontend uses this for live preview; the backend applies it
# on save.
DEPENDENCIES: dict[str, list[str]] = {
    "leads":    ["lead_pipelines"],
    "forms":    ["form_submissions"],
    "deals":    [],
    "contacts": [],
    "companies": [],
}


def apply_cascade(toggles: dict) -> dict:
    """Return a new toggle dict with dependent toggles forced-off where needed.

    The input is a mutable nested dict matching `DEFAULT_OBJECTS` in extraction.py.
    """
    out = copy.deepcopy(toggles)

    # First pass: handle the activities sub-dict (no cascade needed inside,
    # but normalize structure if missing).
    if "activities" not in out or not isinstance(out["activities"], dict):
        out["activities"] = {
            "calls": True, "meetings": True, "emails": True, "notes": True, "tasks": True,
        }

    # Second pass: hard cascades.
    changed = True
    while changed:
        changed = False
        for trigger, forced in DEPENDENCIES.items():
            if out.get(trigger, True) is False:
                for off in forced:
                    if out.get(off, True) is not False:
                        out[off] = False
                        changed = True

    return out


def describe_cascade(toggles: dict) -> dict[str, list[str]]:
    """Return a map: toggle key → list of other toggles it would force off if
    the user disabled it. Used by the frontend to render the tooltip preview.
    """
    out: dict[str, list[str]] = {}
    for trigger, forced in DEPENDENCIES.items():
        if forced:
            out[trigger] = list(forced)
    return out
