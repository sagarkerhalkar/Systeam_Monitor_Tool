# Machine 360 Selected Dropdown V3

Scope: public/app.js only.

Fix:
- Replaces selectedMachine() so it always returns the machine selected in #machineSelect.
- On dropdown change, state.selected and localStorage are updated, then Machine 360 is re-rendered.
- Removes older failed/safe V1/V2 Machine 360 sync blocks.
- No backend/database/client/router/login change.

Expected:
If dropdown says `sup2pc2-H310MHP - 156.156.20.175`, the details below must also show that same machine.
