# Machine 360 Lock V6 No Source Clean

Scope: public/app.js only.

Fix:
- Removes old Machine 360 V2/V3/V4/V5 sync blocks.
- Does not globally replace mojibake characters in source code, because that corrupted regex in V5.
- Adds safe end-of-file override for selectedMachine.
- Saves selected Machine 360 dropdown into:
  - sagar_machineSelect
  - sagar_selected_machine
  - sagar_machine360_selected
  - sagar_machine360_lock_v6
- Auto-refresh should not jump back to old sup2pc2 after selecting another PC.
- Runtime visible text cleanup for bad encoded dot/arrow uses unicode escapes only.
- No backend/database/client/router/login change.
