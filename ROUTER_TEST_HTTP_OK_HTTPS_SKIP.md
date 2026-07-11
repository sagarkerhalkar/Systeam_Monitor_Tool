# Router Test HTTP OK HTTPS Skip

The router test now treats this case correctly:

- HTTP `http://192.168.0.1` returns OK 200 = router reachable.
- HTTPS SSL handshake failure is normal for many local routers and is shown as skipped/not supported.
- This patch only changes router-test message logic.
- It does not change ISP box, dashboard, client, database, login, or other tabs.
