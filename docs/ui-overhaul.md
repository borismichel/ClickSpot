# ClickSpot UI Overhaul

ClickSpot's interface started as a working but prototypical Ant Design app: capable underneath, visually unfinished on top. This overhaul (tracked in CLI-37) made it a coherent, branded product without rebuilding the foundations. The stack is unchanged (React 19, Ant Design v6, Recharts, React Flow); what's new is a real design system underneath it.

I evaluated the work jobs-to-be-done first: what is each surface *for*, and where does it fail the user? Two patterns drove the plan. The app had **no design-system layer**, so nothing felt intentional. And it was **strong at authoring but weak at retrieval**: you could build things but couldn't easily find them again. Everything below fixes one of those.

> Screenshots are at desktop **1440×900** unless noted. "Before" images are the pre-overhaul UI; "after" images are the shipped result on `main`.

---

## 1. A real design system (the root fix)

**Before:** no theme layer at all. `index.css` was four lines, there was no Ant `ConfigProvider`, and the framework's default blue `#1677ff` was hardcoded across 25+ files. ClickSpot's own coral brand appeared nowhere in the app.

**After:** a single token layer (`frontend/src/theme/`) wraps the app in a `ConfigProvider`. ClickSpot coral `#e76636` is the primary accent over AA-contrast-checked neutrals, with one shared chart palette. Coral stays an *accent* (primary actions, active states, focus); the neutrals still carry the surfaces.

| Before | After |
| --- | --- |
| ![Chat (before)](assets/screenshots/chat-home.png) | ![Chat (after)](assets/screenshots/overhaul/chat-home.png) |

In the "after": the coral brand mark, the **active-state nav** (you can finally tell which section you're in), coral primary buttons and input focus, plus the redesigned conversation sidebar from §3.

_Tickets: CLI-38 (tokens + ConfigProvider, AA-clean coral)._

---

## 2. Search and retrieval: a global command palette

**Before:** search existed only where you *configured* things. The places you *return to* were all unsearchable lists: conversation history, the saved Library, the table browser, the add-filter column picker.

**After:** a global command palette (**⌘K / Ctrl-K**) spans conversations, saved objects, data spaces, tables, and settings, plus in-list search on the Library and table/column browser.

![Command palette](assets/screenshots/overhaul/cmdk-search.png)

_Tickets: CLI-39 (global + in-list search), CLI-48 (palette keyboard-nav fix)._

---

## 3. Conversation history that scales

**Before:** a flat, unsearchable list of near-identical truncated titles, with a one-click delete that had no confirmation (easy accidental data loss).

**After:** conversations are **grouped by date** (Today / Yesterday / Last 7 days), there's a **search box**, titles are meaningful, and delete is a safe, hover-revealed action. See the sidebar in the §1 "after" image.

_Tickets: CLI-41 (group, search, safe delete); follow-up CLI-55 (date suffix + matched-text snippet)._

---

## 4. One filter system, shareable

**Before:** three different filter implementations with divergent UX, and filtered views couldn't be shared (no URL state).

**After:** one type-aware filter bar (date ranges, numeric operators, searchable multi-selects) everywhere, and **filter state lives in the URL**. Copy the link and you reproduce the exact filtered view.

| Before | After |
| --- | --- |
| ![Dashboard (before)](assets/screenshots/dashboard-deals.png) | ![Dashboard (after)](assets/screenshots/overhaul/dashboard.png) |

_Tickets: CLI-40 (unify filters + URL state), CLI-58 (shareable dashboard links)._

---

## 5. Chat you can trust

**Before:** the result view prominently showed raw latency chips (`LLM 13.2s · Total 13.2s`) and a blank wait while generating; a `+100% vs 0` divide-by-zero appeared in KPI deltas.

**After:** generation shows progress, the latency detail moves behind a popover, the zero-baseline delta renders sensibly, and the nav gained active state plus the brand mark.

_Tickets: CLI-42 (chat progress + latency demote + KPI delta fix + active-state nav)._

---

## 6. Data Spaces without writing SQL

**Before:** the Data Space designer is a genuinely powerful semantic-layer builder, but it forced raw ClickHouse SQL at three points: a freeform `WHERE`, computed expressions, and a user-typed ID that leaked into the physical `gold.ds_{id}` view name. That broke the product's "ask in plain language, no SQL" promise the moment you left chat.

**After:** the same filter-builder from §4 is the default for grain and space filters (raw SQL stays as an opt-in advanced escape hatch), the Space ID auto-generates, and there are computed-column presets. There's also a "chat with this space" bridge.

![Data Space designer](assets/screenshots/overhaul/space-designer.png)

_Tickets: CLI-43 / CLI-61 (no-SQL designer: filter builder + presets + chat bridge), CLI-64 (mobile label ellipsis)._

---

## 7. Phase-4 round-off

**Dashboard / Explorer polish:** tokenised cards, a legend for the property-tag taxonomy (`locked-core / core / extra / …`), and schema-table search plus a density control (CLI-57).

| Data Explorer (before) | Data Explorer (after) |
| --- | --- |
| ![Explorer (before)](assets/screenshots/explorer-schema.png) | ![Explorer (after)](assets/screenshots/overhaul/data-explorer.png) |

**First-run onboarding checklist:** the Settings → Onboarding tab now shows a live setup-status checklist, so a new operator can see exactly what's connected (CLI-59).

![Onboarding checklist](assets/screenshots/overhaul/settings.png)

**Read-only mobile:** dashboards and chat render without horizontal overflow on small screens (CLI-60).

![Chat on mobile (390px)](assets/screenshots/overhaul/chat-mobile.png)

**Shareable dashboards:** share links built on the URL-persisted filters (CLI-58). A dashboard white-screen bug turned up during QA; a route error boundary fixed it (CLI-63).

---

## What's intentionally not here

- **Role/auth (user vs admin).** ClickSpot has no permission model today. Adding one is a product and security decision well beyond UI polish, so it's deferred on purpose.
- **Non-blocking polish** tracked separately: chart colour-blindness audit (CLI-45), tokenised medallion tier colours (CLI-46), dashboard CSV/PNG export (CLI-67).

---

*Delivered under [CLI-37 "Propose UI Overhaul"]. Generated screenshots reflect the shipped `main` build against seeded demo data.*
