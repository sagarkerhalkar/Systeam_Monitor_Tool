# V28 Test Report

Reference build used:

- Google Drive `app.js` SHA256: `70947bec8ef1f61766eeb87237e50045e3a4109ce9a428a71e300d1ec74bf5b8`
- plus V25 block
- plus V26 block
- plus V27 block

Static validation completed:

- Required section anchors: PASS
- Each scoped old interval pattern count: exactly 1
- Replacement count: exactly 5
- V28 marker count after simulated patch: 1
- `node --check` after simulated patch: PASS

Performance intent:

- keeps normal 5-second monitoring refresh unchanged
- reduces five repeated UI fallback loops to 12-15 seconds
- adds no new timer
- changes no API/server/client/database logic
