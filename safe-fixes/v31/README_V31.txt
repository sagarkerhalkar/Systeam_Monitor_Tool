V31 - CORE NO AUTO RERENDER

Purpose
- Fix the remaining visible auto-refresh disturbance after V30 rollback.

What changes
- Keeps the existing 5-second /api/overview polling.
- Automatic polling updates state and a few leaf values only.
- Automatic polling no longer calls hydrateSelectors/renderAll/applyRoleControls.
- V25 may refresh the selected machine payload in the background, but an overview-driven payload refresh no longer rebuilds Machine 360/Network/Software/USB.
- Manual Refresh, tab changes and machine selection still render normally.
- Search text, focus, scroll and reading position are not replaced by automatic polling.

Not changed
- server.py, DB/data, APIs, clients, heartbeat/offline logic, notifications, inventory logic, port 2278.

Run
1) powershell -ExecutionPolicy Bypass -File .\APPLY_V31_CORE_NO_AUTO_RERENDER.ps1 -CheckOnly
2) If CHECK ONLY PASSED: powershell -ExecutionPolicy Bypass -File .\APPLY_V31_CORE_NO_AUTO_RERENDER.ps1 -Apply

Rollback
powershell -ExecutionPolicy Bypass -File .\APPLY_V31_CORE_NO_AUTO_RERENDER.ps1 -Rollback
