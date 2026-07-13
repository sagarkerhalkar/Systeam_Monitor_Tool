# Day History Usage 3D V2

Scope: public/app.js only.

Fix:
- Adds upload/download data usage panel to current 3D Day History page.
- Shows Total Download, Total Upload, Total Data, Machines, Days.
- Shows machine-wise usage totals table.
- Adds CSV download for machine-wise usage totals.
- Reads from existing `/api/history`.
- Does not touch server, database, client, router, login, or Machine 360.
