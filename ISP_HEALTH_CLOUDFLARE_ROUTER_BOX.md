# ISP Health Cloudflare Router Box

Scope: only the ISP Health For Live Classes box.

Added:
- Provider / ISP
- ASN / org
- Public IP
- Location
- Cloudflare trace: colo, TLS, WARP
- Router gateway from server OS route
- Server local LAN IP
- Cloudflared service/process status
- Latency / jitter / loss
- Down / up probe
- Client ISP samples from live clients

Not changed:
- Background design
- Login page
- Machine Fleet
- Client collector
- Database cleanup
- Other tabs

Router note:
This patch does not require router login. It can detect gateway/local IP from OS. True router WAN/interface/SNMP statistics need router IP, brand/model, and read-only router/SNMP/API access.
