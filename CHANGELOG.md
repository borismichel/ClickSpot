# Changelog

All notable changes to ClickSpot are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- **UI overhaul:** ClickSpot's interface moved from a prototypical Ant Design
  app to a coherent, branded product on a real design-system foundation. Full
  before/after writeup with screenshots: **[docs/ui-overhaul.md](docs/ui-overhaul.md)**.
  - Design tokens + `ConfigProvider`; ClickSpot coral applied app-wide, replacing
    the framework default blue (CLI-38).
  - Global ⌘K command palette + in-list search across conversations, Library,
    data spaces, tables, and settings (CLI-39).
  - Conversation sidebar: date grouping, search, and safe delete (CLI-41).
  - One unified, type-aware filter system with shareable URL-persisted state (CLI-40).
  - Chat: generation progress, demoted latency detail, fixed zero-baseline KPI
    deltas, and active-state navigation (CLI-42).
  - Data Spaces: no-SQL filter builder with computed-column presets and a
    chat-on-a-space bridge; raw SQL kept as an advanced escape hatch (CLI-43 / CLI-61).
  - Phase-4 round-off: dashboard/explorer polish + property-tag legend (CLI-57),
    shareable dashboards (CLI-58), first-run onboarding checklist (CLI-59), and a
    read-only mobile layout (CLI-60).

### Fixed
- Dashboard white-screen on non-array filter values; added a route error boundary (CLI-63).

## [0.1.1] — 2026-05-24
### Added
- Multi-arch (amd64 + arm64) container image manifests (CLI-56).
