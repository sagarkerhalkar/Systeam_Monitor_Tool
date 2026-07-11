# Machine Fleet Merge/Delete No Flicker V5

This is the correct Machine Fleet fix after the flickering V3/V4 UI patches.

## What changed

- Removed old Machine Fleet DOM observer/interval patches that caused screen flicker.
- Backend now cleans the latest current-machine table.
- Same stable hardware/client identity: newest row is kept, old duplicate is deleted from latest.
- Same hostname: newest row is kept, old duplicate is deleted from latest.
- History table heartbeats is not deleted.
- Primary IP is corrected in backend summary when a real LAN IP exists and old primary IP is VirtualBox/Docker/VM.
- Machine Fleet responsive layout is CSS-only, so it should not flicker.

## Important

This cleans only the current Machine Fleet count. Historical data remains available.
