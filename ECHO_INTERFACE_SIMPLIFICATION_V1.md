# ECHO Interface Simplification v1

## 1. Why the main UI was simplified

The sidebar had grown to 17 flat items (Atlas, Personality, Evaluation Lab, Actions, Tools, Cognitive Core, Release Manager, Permissions, Constitution, Amendments, Self-Improvement, Knowledge Vault, plus the 6 everyday pages) — it read as a developer control panel rather than a personal AI companion's home screen. Every one of those systems is real and still fully functional; the problem was purely presentation.

## 2. What moved to Advanced

Grouped under a single collapsible "Advanced" section in the sidebar (see `Sidebar.tsx`'s `ADVANCED_NAV_GROUPS`):

- **Knowledge & Memory** — Knowledge Vault, Atlas, Cognitive Core
- **Assistant Behaviour** — Personality, Permissions
- **Developer & Testing** — Evaluation Lab, Actions, Tools, Release Manager, Self-Improvement
- **Governance** — Constitution, Amendments

No route was deleted, no page was removed, no backend endpoint changed. `NAV_ITEMS` (the flat list used for "is this a valid view" checks) still contains every one of these.

## 3. What remains in Main

Exactly 6 everyday items: Mission Control, Chats, Projects, Tasks, Schedule, Library — plus Settings and the Advanced toggle, both always visible at the bottom of the sidebar.

## 4. How to enable Advanced / Developer Mode

Advanced is **always reachable** — it's not hidden behind a setting, just collapsed by default. Click "Advanced" in the sidebar (or the equivalent entry in the mobile drawer) to expand it; the open/closed state is remembered in `localStorage` across visits.

Settings > Interface has:
- **Show Advanced systems expanded by default** — starts Advanced pre-expanded instead of collapsed.
- **Show developer controls** — reveals the "acting as (simulated role)" Guardian Council switcher in the top bar (off by default; it's for testing role-gated features, not everyday use).
- **Show usage in top bar** / **Show model selector** — toggle those top-bar elements.
- **Compact sidebar** — tighter spacing.

## 5. How internal systems still work

Nothing about how these systems function changed — their routers, services, and database tables are untouched. Only their entry point in the navigation moved. A user who never opens Advanced never has to think about Cognitive Core or the Permission Center; a user who wants to inspect them still can, in two clicks.

## 6. Manual UI checklist

1. Open ECHO — confirm the sidebar shows exactly: Mission Control, Chats, Projects, Tasks, Schedule, Library, Settings, Advanced.
2. Click Advanced — confirm it expands to show the 4 grouped headings and all 11 internal pages.
3. Click each internal page once — confirm it still loads and functions exactly as before.
4. Collapse Advanced — confirm the sidebar returns to its calm, 8-item default.
5. Resize to mobile width — confirm the mobile drawer shows the same Main/Settings/Advanced structure.
6. Open Settings — confirm the "acting as (simulated role)" switcher is hidden in the top bar until "Show developer controls" is turned on.
