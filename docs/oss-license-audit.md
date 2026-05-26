# OSS License Audit — ClickSpot

**Issue:** CLI-21 · **Date:** 2026-05-24 · **Auditor:** CTO

## Question

> Check the licenses of all bundled dependencies/tools. Validate against our license
> and copyright notice. Are we in the green? Any action needed?

## Verdict: ✅ In the green

ClickSpot ships under the **MIT License, © 2026 Boris Michel**. Every bundled
dependency and tool is license-compatible with MIT redistribution. There are
**no GPL / AGPL / LGPL (strong copyleft) components** anywhere in the shipped
Python runtime tree, the shipped frontend bundle, or the bundled container tools.
Nothing forces ClickSpot to change its license or open additional source.

One **non-blocking hygiene action** is recommended and has been completed in this
change: a `THIRD_PARTY_NOTICES.md` file (see below).

## What was scanned

| Surface | Method | Result |
|---|---|---|
| Python runtime deps (105) | `.venv` `*.dist-info` METADATA (`License-Expression`, classifiers, fallback map) | All permissive + 2× weak MPL-2.0 |
| Frontend deps **bundled into the build** (235) | `npm ls --prod --all` ∩ `node_modules/*/package.json` | All permissive; 2 dual-licensed elect permissive |
| Frontend build-only tooling | excluded from shipped artifact | Not redistributed |
| Container tools / base images | `Dockerfile`, `Dockerfile.demo`, `docker-compose.yml` | ClickHouse Apache-2.0; OS layers = mere aggregation |

Full per-package inventory: [`THIRD_PARTY_NOTICES.md`](https://github.com/borismichel/ClickSpot/blob/main/THIRD_PARTY_NOTICES.md).
Regenerate with `python3 scripts/gen-third-party-notices.py`.

## Findings detail

### License distribution
- **Python (105):** MIT 55, Apache-2.0 ~24, BSD-family ~19, PSF-2.0 3, ISC 1, MPL-2.0 2 (`certifi`, `tqdm`).
- **Frontend, shipped (235):** MIT 193, ISC 28, BSD-3 3, Apache-2.0 2, plus a handful of dual/compound (all with a permissive option).

### Dual-licensed components (we elect the permissive option)
- **`jszip`** (via `exceljs`): `MIT OR GPL-3.0-or-later` → used under **MIT**. The `OR` lets us decline GPL; no copyleft obligation.
- **`dompurify`** (via `jspdf`): `MPL-2.0 OR Apache-2.0` → used under **Apache-2.0**.

### Weak (file-level) copyleft — no obligation on our code
- **`certifi`, `tqdm`** (Python) and the build-only **`lightningcss`** (JS) are MPL-2.0.
  MPL-2.0 is file-level copyleft: obligations attach only if we modify those
  packages' own source files, which we do not. Using them unmodified imposes nothing
  on ClickSpot.

### Build-only tooling (not redistributed)
- `lightningcss` (MPL-2.0) and `caniuse-lite` (CC-BY-4.0) are dev/build dependencies
  used by Vite; they are **not** present in the shipped bundle, so their terms do not
  reach end users. `caniuse-lite`'s CC-BY attribution applies only if its dataset is
  redistributed, which we don't do.

### Container / base images
- **ClickHouse** (`clickhouse/clickhouse-server`) is **Apache-2.0** and runs as a
  separate service (not linked into our code).
- `python:3.10-slim-bookworm` and `node:20-alpine` carry GPL/LGPL **OS-layer** packages
  (glibc, coreutils, busybox, …). These are *mere aggregation* in a container image —
  not combined with or linked into ClickSpot — so they do not affect our MIT licensing.
  Their license texts ship inside the images (`/usr/share/doc/*/copyright`). This is
  standard for every container distribution.

### Minor data-quality note
- **`buffers@0.1.1`** (deep transitive, substack) publishes no `license` field in its
  `package.json`. Upstream is de-facto MIT. Negligible risk; noted for completeness.

## Attribution / copyright-notice validation

MIT, BSD, Apache-2.0 and ISC all require that the original copyright + permission
notices be **preserved on redistribution**. When we ship source, each dependency's
own LICENSE travels with it; when we ship a *minified Vite bundle* or *Docker image*,
those per-file notices are no longer obvious. Best practice for a public release is a
single aggregated notices file.

- ✅ Our own notice is correct and consistent: `LICENSE` (MIT, © 2026 Boris Michel),
  README badge + License section both say MIT © 2026 Boris Michel.
- ⛏️ **Action taken:** added [`THIRD_PARTY_NOTICES.md`](https://github.com/borismichel/ClickSpot/blob/main/THIRD_PARTY_NOTICES.md)
  aggregating all third-party components, their versions, and licenses, plus the
  explicit dual-license elections and the container-image note. Generator committed at
  `scripts/gen-third-party-notices.py` so it can be refreshed when deps change.

## Recommendations

1. **Merge `THIRD_PARTY_NOTICES.md`** with the release (done in this change; needs review/merge). Optionally reference it from the README License section.
2. **Optional CI guard:** add a license-check step (e.g. `pip-licenses` + `license-checker`) that fails on GPL/AGPL/LGPL to prevent a future copyleft dependency from slipping in. Pairs with the existing SECURITY_AUDIT.md scanning items.
3. No license changes, no dependency removals, and no copyright-notice corrections are required.
