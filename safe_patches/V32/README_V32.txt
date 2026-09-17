V32 BACKGROUND DATA / NO UI RERENDER - IMMEDIATE REFRESH-ONLY FIX

Purpose
-------
Fix only the remaining automatic-refresh disturbance.

Diagnosed baseline SHA256:
9bfa4ee98c73c0e2526e777b9b25f21968ec9964df13754b5e0b9138d07704bf

What V32 changes
----------------
The existing automatic timer currently calls refresh(false).
That function historically owns selector hydration, banner logic and full render paths.

V32 replaces ONLY that automatic timer with a direct /api/overview background poll.
The poll:
- keeps the same DASHBOARD_POLL_SECONDS interval
- updates state.overview and state.machines
- keeps status online/offline current
- uses the already-installed V31 safe leaf updater for visible numeric values
- does not call refresh(false)
- does not call hydrateSelectors()
- does not call renderAll()
- does not recreate Machine 360 / Network / Software / USB pages
- hides the refresh banner / last-refresh indicator

Manual Refresh still uses the existing full refresh behavior.
Changing tabs or selecting another machine still uses existing working behavior.

No server.py, DB, APIs, clients, heartbeat, inventory data, notification data or collection logic is changed.

Run
---
1) Check:
powershell -ExecutionPolicy Bypass -File ".\APPLY_V32_BACKGROUND_ONLY_REFRESH.ps1" -CheckOnly

2) If PASS:
powershell -ExecutionPolicy Bypass -File ".\APPLY_V32_BACKGROUND_ONLY_REFRESH.ps1" -Apply

3) Ctrl+F5 once.

Rollback:
powershell -ExecutionPolicy Bypass -File ".\APPLY_V32_BACKGROUND_ONLY_REFRESH.ps1" -Rollback
