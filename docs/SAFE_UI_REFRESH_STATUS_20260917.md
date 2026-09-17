# Safe UI / Refresh Recovery Status — 2026-09-17

Repository: `sagarkerhalkar/Systeam_Monitor_Tool`

Safety branch: `safe-ui-refresh-v25-v27-20260917`

Base branch kept untouched: `workingcode`

## Source-of-truth warning

The GitHub `workingcode` branch is older than the current live/Drive frontend. For that reason, the recovery work is being kept as rollback-capable patch/install documentation rather than replacing `public/app.js` in GitHub.

## Live recovery sequence

- V25 — selected-client live refresh/cache correction.
- V26 — search overlay + mobile/touch layering correction.
- V27 — mobile-first layout correction. User reported roughly 70% acceptable on mobile.
- V28 — reduced frequency of UI-only maintenance/self-heal timers. Main 5-second monitoring poll remains unchanged.
- V29 — attempted silent background refresh. Did not fully solve visible refresh/re-render interruption.
- V30 — attempted typing-protected silent refresh. Did not fully solve the issue because older refresh/render layers can still rebuild the active page/search DOM.
- V31 — incremental DOM live-update architecture correction. Automatic 5-second polling fetches `/api/overview`, updates state, and patches stable visible values without calling `renderAll()` or replacing page/search DOM. Manual refresh, page changes, and user machine selection keep the existing full-render behavior.

## Critical bug being addressed by V31

The current frontend contains a global 5-second refresh plus legacy UI maintenance loops, including a client-host search maintenance loop around every 1.8 seconds. When the active page is rebuilt, the hostname search control can be recreated, which destroys user typing/focus/caret and disturbs reading/scroll position.

V31 changes the automatic poll path so the active page is no longer rebuilt during polling. Search inputs should remain physically in the DOM while the user types.

## What V31 does not change

- `server.py`
- database/schema/data
- API contracts
- Windows/Linux clients
- heartbeat/offline logic
- notifications
- hardware/assets inventory data or import rules
- machine identity
- the 5-second polling frequency itself

## Merge policy

This PR must remain draft and must not be merged into `workingcode` until V31 is verified on the live machine and the current live source is reconciled with GitHub.
