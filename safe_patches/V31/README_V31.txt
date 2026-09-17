V31 - INCREMENTAL DOM LIVE UPDATE

Purpose
-------
Stop the 5-second automatic background refresh from rebuilding the active page.
The automatic poll continues, but it updates state and stable visible values only.

Expected behavior
-----------------
- No orange/new-data refresh banner.
- No page flash/rebuild every 5 seconds.
- Reading/scroll position stays where the user left it.
- Machine hostname search text/focus/caret remains intact while typing.
- Dashboard KPIs and common Machine 360 / Network live values update in place.
- Manual Refresh still performs the application's normal full refresh.
- Page changes and machine selection still use existing render logic.

Scope exclusions
----------------
No server.py, database, client, heartbeat/offline, notification, API contract,
inventory data, import or collection logic changes.

Install
-------
powershell -ExecutionPolicy Bypass -File .\APPLY_V31_INCREMENTAL_DOM_LIVE_UPDATE.ps1 -CheckOnly
powershell -ExecutionPolicy Bypass -File .\APPLY_V31_INCREMENTAL_DOM_LIVE_UPDATE.ps1 -Apply

Rollback
--------
powershell -ExecutionPolicy Bypass -File .\APPLY_V31_INCREMENTAL_DOM_LIVE_UPDATE.ps1 -Rollback