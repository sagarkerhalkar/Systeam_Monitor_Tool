V29 SILENT BACKGROUND REFRESH SAFE FIX
======================================

Goal
----
Keep the existing live 5-second data polling, but make automatic refresh invisible to the user.

What V29 changes
----------------
- Hides the old "new data arrived / refresh" banner during automatic polling.
- Keeps the active page visually stable while background data is painted.
- Suppresses CSS animation/transition effects only during the automatic refresh paint.
- Clears the old pending-update banner state.
- Updates the Settings refresh explanation to say that live data refreshes silently.
- Keeps the manual Refresh button available as a fallback.

What V29 does NOT change
------------------------
- The 5-second polling frequency.
- server.py.
- Database or inventory records.
- API contracts.
- Windows/Linux client logic.
- Heartbeat/offline logic.
- Notifications.
- Machine identity.
- V25 selected-machine freshness logic.
- V26 search-selection logic.
- V27 mobile layout.
- V28 timer optimization.

Install
-------
1) Check only:
   powershell -ExecutionPolicy Bypass -File .\APPLY_SILENT_BACKGROUND_REFRESH_V29.ps1 -CheckOnly

2) If CHECK ONLY PASSED:
   powershell -ExecutionPolicy Bypass -File .\APPLY_SILENT_BACKGROUND_REFRESH_V29.ps1 -Apply

3) Ctrl+F5 once after installation.

Rollback
--------
powershell -ExecutionPolicy Bypass -File .\APPLY_SILENT_BACKGROUND_REFRESH_V29.ps1 -Rollback

Expected behavior
-----------------
- Data continues to update in the background.
- No automatic refresh banner appears.
- No automatic refresh animation should be visible.
- The page should not visibly flash just because the 5-second poll completed.
- Manual Refresh still works when explicitly clicked.
