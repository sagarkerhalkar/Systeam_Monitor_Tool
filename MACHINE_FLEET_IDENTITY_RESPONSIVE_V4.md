# Machine Fleet Identity + Responsive V4

Page-specific patch.

## What it fixes

- Machine Fleet identity display is clearer.
- Asset/Client ID are shown separately under machine name.
- Real LAN IP is preferred over Docker/VM/VirtualBox IP when available.
- Machine Fleet becomes responsive card layout on tablet/mobile.
- No backend, login page, dashboard tabs, database or client collector changed.

## Important

If a client sends only a virtual IP, the dashboard can only warn. Then the next required fix is the Windows/Ubuntu client collector IP logic.

## Restore

git reset --hard final-v2-machine-fleet-identity-responsive-v4
