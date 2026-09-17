# Safe UI / Refresh Recovery Status — V25 to V27

Date: 2026-09-17
Repository: `sagarkerhalkar/Systeam_Monitor_Tool`
Safety branch: `safe-ui-refresh-v25-v27-20260917`
Base branch: `workingcode`

## Important source-of-truth note

The repository `workingcode` branch is older than the current Google Drive / live server frontend. For that reason the V25-V27 work was delivered as **safe append-only / in-place patch installers** rather than by replacing `public/app.js` from GitHub.

Do not copy `public/app.js` from this branch over the live server unless the current live source has first been reconciled and tested.

## User-confirmed problem sequence

The live application had several frontend issues:

- Machine 360 and other machine-detail tabs could show stale data until the browser was manually refreshed.
- Network, Software and USB machine search suggestions could be clipped/hidden behind page containers.
- Mobile layout was desktop-first and consumed too much screen space, especially the navigation and top action area.
- General UI smoothness remains below target because the current frontend contains multiple historical compatibility layers, recurring UI maintenance timers, repeated render wrappers and heavy visual effects.

## V25 — Selected client live refresh

Purpose: remove the need for repeated browser refreshes when changing/refreshing the selected machine.

Scope:

- selected-machine detail cache invalidation based on the latest machine `updated_at`
- fresh `/api/machine` loading only when required
- Machine 360 / Network / Software / USB selected-machine refresh flow
- Assets Inventory excluded from the machine-detail lazy loader

Not changed:

- `server.py`
- database/schema/data
- Windows/Linux clients
- heartbeat/offline rules
- notification logic
- inventory save/edit/import rules

Live application result reported by user: V25 installed successfully.

## V26 — Search overlay + mobile/touch compatibility

Purpose: fix machine search suggestions being hidden/clipped and improve basic mobile control behavior.

Scope:

- portals visible search suggestions to a top-level overlay
- keeps existing V16/V17 machine selection behavior
- improves touch control sizing and mobile viewport positioning
- reduces expensive effects on small/touch devices

Not changed: backend, APIs, DB or monitoring logic.

## V27 — Mobile-first layout correction

Purpose: replace the oversized mobile navigation/header presentation with a compact mobile-first layout while retaining all pages.

Scope:

- compact horizontally scrollable mobile navigation
- smaller title/action area
- single-column mobile content where appropriate
- horizontally scrollable data tables instead of page breakage
- lower visual-effect cost on mobile

User feedback after V27: approximately **70% acceptable**. Further mobile polishing and smoothness work is still required.

## Next step — V28 smoothness / performance cleanup

V28 must stay frontend-only first. The first safe targets are UI-only recurring maintenance loops that are already backed by event/render hooks:

1. approved login layout maintenance loop
2. Machine 360 selection/text maintenance loop
3. V16 client hostname search maintenance loop
4. V17 USB / Software Inventory UI maintenance loop

The plan is to reduce unnecessary repeated DOM work without changing monitoring, refresh, API, DB or collection logic. Every modification must have:

- `-CheckOnly`
- backup before change
- exact anchor/count validation
- `node --check`
- automatic rollback on syntax failure
- explicit rollback command

## Safety rule

Do not directly overwrite the live frontend from an older GitHub branch. The live server / Drive source must be treated as newer until source reconciliation is complete.
