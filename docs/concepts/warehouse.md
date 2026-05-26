# The medallion warehouse

ClickSpot stores everything in ClickHouse using a three-layer medallion architecture, plus
an anonymized mirror. Each layer has a clear job, and Dagster rebuilds them in order on
every run.

## The layers

| Layer | Tables | Engine | Strategy |
|-------|--------|--------|----------|
| **Bronze** | 16 objects + 25 associations | `ReplacingMergeTree` (`_raw` ZSTD(3)) | Full list-endpoint loads, deduped on `_record_id` |
| **Silver** | 10 dimensions + 3 facts + 13 bridges + 9 dicts | `ReplacingMergeTree` — partitioned + bloom-filter skip indexes on hot lookups | Full rebuild via `EXCHANGE TABLES` (atomic swap) |
| **Gold** | 7 aggregates | `ReplacingMergeTree` — partitioned where there's a natural date axis | Full rebuild |
| **Anon** | Masked silver + gold mirrors in `silver_anon` / `gold_anon` | `ReplacingMergeTree` | Rebuilt after gold via sensor |

- **Bronze** is the raw landing zone: the HubSpot list endpoints, loaded whole and
  deduplicated. Nothing is interpreted here.
- **Silver** is the typed, modeled layer: dimensions (deals, contacts, companies, owners…),
  facts, and the bridge tables that connect them. This is what most queries hit. It's
  rebuilt atomically with `EXCHANGE TABLES`, so readers never see a half-built table.
- **Gold** is pre-aggregated: rep performance, deal health, source attribution, pipeline
  snapshots: the numbers you'd otherwise recompute on every dashboard load.
- **Anon** is a masked copy of silver and gold in separate `silver_anon` / `gold_anon`
  databases. It's what the [MCP server](../guides/mcp.md) and demos read, so the warehouse
  can be shared without exposing real names, emails, or amounts. See
  [The privacy model](privacy.md).

## How it's orchestrated

Dagster runs the chain hourly with atomic rebuilds, and a sensor triggers each layer once
the one before it lands: bronze → silver → gold → anon. Because silver and gold do full
rebuilds with atomic swaps, a failed run never leaves the warehouse in a partial state.

## By the numbers

| | Count |
|---|---|
| Bronze tables | 41 (16 objects + 25 associations) |
| Silver assets | 27 (10 dims + 3 facts + 13 bridges + DQ) |
| Gold tables | 7 |
| Anon mirrors | `silver_anon` + `gold_anon` (masked copies) |
| Dictionaries | 9 (in-memory lookups from silver dims) |
| Silver columns | ~207 (across all dimensions) |
| Graph relationships | 13 bridge edges |
| Computed metrics | 22 |

## Going deeper

The [Data pipeline](../data-pipeline.md) engineering doc covers the bronze/silver/gold/anon
layers, the Dagster jobs, and the sensor chain in full detail.
