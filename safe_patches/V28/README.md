# V28 UI Timer Smoothness Safe Fix

Purpose: reduce repeated UI-only DOM maintenance work that currently runs every 1.5-2.5 seconds.

This patch **does not change the real monitoring poll interval**. The normal 5-second `/api/overview` refresh remains unchanged.

## What V28 changes

1. Branding Settings self-heal: 2.5 sec → 15 sec
2. Login layout self-heal: 2 sec → 15 sec, only while visible/login is shown
3. Machine 360 UI self-heal: 1.5 sec → 12 sec
4. V16 hostname-search self-heal: 1.8 sec → 12 sec
5. V17 USB/Software UI self-heal: 2 sec → 12 sec

## Why this is safe

These areas already have page-switch, render, MutationObserver and input/user-event hooks. The short intervals are fallback/self-heal loops, not the monitoring data collector.

## Not changed

- `server.py`
- database/data
- API endpoints
- Windows/Ubuntu clients
- heartbeat/offline calculations
- 5-second overview refresh
- inventory save/import/delete logic
- notifications
- machine identity

## Required baseline

V25 + V26 + V27 markers must exist. The installer refuses to apply if they are missing or if exact scoped anchors do not match.

## Commands

Check only:

```powershell
powershell -ExecutionPolicy Bypass -File .\APPLY_UI_TIMER_SMOOTHNESS_V28.ps1 -CheckOnly
```

Apply:

```powershell
powershell -ExecutionPolicy Bypass -File .\APPLY_UI_TIMER_SMOOTHNESS_V28.ps1 -Apply
```

Rollback:

```powershell
powershell -ExecutionPolicy Bypass -File .\APPLY_UI_TIMER_SMOOTHNESS_V28.ps1 -Rollback
```
