V30 TYPING-PROTECTED SILENT BACKGROUND REFRESH

Problem confirmed from the supplied screen recording:
1. Orange "New data arrived. Update view" banner still interrupts reading.
2. Machine/client search input is rebuilt by background render/maintenance, so typing/focus is lost.

V30 behavior:
- Existing background polling remains active.
- Refresh banner is permanently suppressed.
- If the user is typing in a text/search field, automatic refresh updates overview data in memory but does not redraw the active page.
- Typed value, focus and caret are restored if another compatibility layer replaces the input node.
- When typing/focus ends, normal page rendering resumes on later automatic refreshes.
- Manual Refresh remains available and is not blocked.

Not changed:
- server.py
- database or existing data
- APIs
- Windows/Linux clients
- heartbeat/offline rules
- inventory logic
- notifications
- monitoring collection interval

Install:
1) Check only:
   powershell -ExecutionPolicy Bypass -File .\APPLY_V30_TYPING_PROTECTED_SILENT_REFRESH.ps1 -CheckOnly
2) Apply only after check passes:
   powershell -ExecutionPolicy Bypass -File .\APPLY_V30_TYPING_PROTECTED_SILENT_REFRESH.ps1 -Apply
3) Ctrl+F5 once.

Rollback:
   powershell -ExecutionPolicy Bypass -File .\APPLY_V30_TYPING_PROTECTED_SILENT_REFRESH.ps1 -Rollback
