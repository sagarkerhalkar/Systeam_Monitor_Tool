V31 - STABLE INPUT / BACKGROUND POLL

Purpose
- Fix the critical issue where automatic refresh rebuilds the active page and interrupts typing/search/reading.

Behavior
- Keeps the existing 5-second /api/overview polling.
- Automatic poll updates state.overview/state.machines in memory.
- Automatic poll DOES NOT call renderAll(), hydrateSelectors(), or page renderers.
- It only updates a few stable leaf indicators (online/offline/total/critical/status timestamp).
- Manual Refresh still performs the original full refresh/render.
- Tab/page changes still use existing render logic.
- Permanently suppresses the legacy "New data arrived / Update view" banner.

Not changed
- server.py
- database/data
- APIs
- Windows/Linux clients
- heartbeat/offline logic
- inventory save/import/delete
- notifications
- port 2278

This is intentionally a stability-first step. Full incremental DOM live updates should follow after typing/search are confirmed stable.
