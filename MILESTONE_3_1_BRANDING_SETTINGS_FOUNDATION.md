# Semi Milestone 3.1 - Branding Settings Foundation

Date: 07/06/2026 19:29:26

Tag:
milestone-3.1-branding-settings-foundation

Status:
This is a semi-stable branding foundation point.

Working / included:
- Company Branding Settings card added in Settings.
- Branding fields available:
  - Company Name
  - Company Website
  - Company Logo
  - Login Background Image
  - Login Tagline
  - Tagline Font Size Percent
- Branding image files stored under public/branding.
- Current working app source preserved.
- No dashboard overlay issue should be present.
- Old major milestones are not overwritten.

Known pending items:
- Login Tagline apply is not fully working yet.
- Login Background Image apply is not fully working yet.
- These pending items will be handled in next patch after this save.

Safe milestone tags:
- Milestone 1.0: milestone-1-stable-ui-cleanup
- Milestone 1.1: milestone-1.1-usb-software-cleanup
- Milestone 1.2: milestone-1.2-human-change-log-safe
- Milestone 2.0: milestone-2.0-history-fast-3d
- Milestone 3.0: milestone-3.0-universal-inventory-command-center
- Semi Milestone 3.1: milestone-3.1-branding-settings-foundation

Restore Semi Milestone 3.1:
cd D:\SagarSystemHealthMonitor
git fetch --all --tags
git reset --hard milestone-3.1-branding-settings-foundation
powershell -ExecutionPolicy Bypass -File "D:\SagarSystemHealthMonitor\RUN_SERVER_2278.ps1"

Browser:
Press Ctrl + F5 after restart.
