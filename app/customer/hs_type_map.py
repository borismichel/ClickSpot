"""Map HubSpot property (type, fieldType) → ClickHouse column type.

Used by the Property picker so the operator doesn't have to know ClickHouse
types. Falls back to `String` for anything unrecognized — always safe.
"""

from __future__ import annotations


def hubspot_to_clickhouse(hubspot_type: str, field_type: str = "") -> str:
    """Translate a HubSpot property's (type, fieldType) into a ClickHouse type."""
    ht = (hubspot_type or "").lower()
    ft = (field_type or "").lower()

    if ht == "number":
        return "Nullable(Float64)"
    if ht in ("date", "datetime"):
        return "DateTime"
    if ht == "bool":
        # HubSpot returns "true"/"false" string values
        return "LowCardinality(String)"
    if ht == "enumeration":
        return "LowCardinality(String)"
    if ht == "string":
        if ft in ("phonenumber", "phone"):
            return "String"
        if ft == "select":
            return "LowCardinality(String)"
        return "String"
    return "String"
