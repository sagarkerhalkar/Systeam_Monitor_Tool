# Emergency Undo Machine Fleet V5 V2

Reason: V5 Machine Fleet cleanup caused online clients not to show.

This V2 rollback:
- Restores server.py, app.js and styles.css from automatic V5 backup when available.
- Falls back to final-v2-hardening-cicd-security if backup is missing.
- Removes V3/V4/V5 Machine Fleet JS/CSS cleanup/flicker blocks.
- Removes V5 backend cleanup block.
- Does not delete database/history.
- Avoids PowerShell stopping on normal Git messages.

After running:
1. Restart the server.
2. Wait 5 to 15 seconds for client heartbeat.
3. Press Ctrl+F5 in browser.
