# ISP Health Grouped Cloudflare Rows

Scope: only ISP Health For Live Classes box.

Fixed:
- Same ISP/provider name is merged into one row.
- Rows are exactly:
  Provider | Latency / Jitter / Loss | Down / Up Probe | Public IP
- All ISP groups from server + clients are shown.
- Public IPs for same ISP are merged.
- If client Cloudflare probe is missing, row says it needs client probe instead of hiding the ISP.
- Background and other tabs are untouched.

Important:
Cloudflare speed test can only measure the internet line where it runs. Server ISP speed comes from server probe. Other ISP speed requires client agent probe from that ISP line.
