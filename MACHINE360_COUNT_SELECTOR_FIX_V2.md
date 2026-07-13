# Machine 360 Count Selector Fix V2

Scope: frontend only.

Fixes:
- Fleet Status Total/Online/Offline/Attention counts are recalculated from the current machine list.
- Machine 360 dropdown and below details stay in sync.
- This version does not rewrite renderMachine360; it only syncs selection and calls the existing renderer.
- No backend/database/client/router/login changes.
