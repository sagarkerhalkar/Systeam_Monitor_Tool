This package restores the previously working V8.4 Windows client scripts, with only one safe fix:
- network byte counters use Double/Int64-safe delta, avoiding the Int32 crash.
It does NOT redesign UI and does NOT change monitor logic.
