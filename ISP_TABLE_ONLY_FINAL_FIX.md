# ISP Table Only Final Fix

Scope: only ISP Health For Live Classes box.

Fix:
- Force hides old big cards: Provider, Latency, Jitter, Loss, Down Probe, Up Probe.
- Shows only one table:
  Provider | Latency / Jitter / Loss | Down / Up Probe | Public IP
- Same provider is merged on frontend again as safety.
- Existing background is untouched.
- Other tabs are untouched.

Missing ISP:
- Any ISP missing from router must be added in config/isp_router_sources.json until router API/SNMP is connected.
