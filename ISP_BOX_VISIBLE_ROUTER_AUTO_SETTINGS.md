# ISP Box Visible + Router Auto Settings

Fixes:
- ISP box hidden by previous broad hide logic.
- Hides only old Provider/Latency/Jitter cards, not the full ISP panel.
- Shows table only: Provider | Latency/Jitter/Loss | Down/Up Probe | Public IP.
- Settings asks only router connection details, not ISP names.
- Router password is local-only in config/router_isp_settings.local.json and ignored by Git.

Router note:
TP-Link ER8411 web login details are stored locally. Live WAN/VLAN automatic scraping needs a TP-Link connector after local router page/API inspection.
