# Semi Milestone 3.1 - Branding UI Safe Point

Date: 07/06/2026 19:04:16

This is a semi-stable restore point after branding UI changes.

Milestone name:
Semi Milestone 3.1 - Branding UI Safe Point

Tag:
milestone-3.1-branding-ui-safe-point

What is included:
- Current working dashboard source.
- Branding fixes after Milestone 3.0.
- Company logo in SK/logo place.
- Only one company pill/block.
- Company website button.
- Login text reduced by 50%.
- Login page uses team background image.
- Branding files under public/branding.
- Current Notification / Client Messages / Inventory source state as present in working folder.

Important:
- Old milestones are not overwritten.
- This is a semi milestone, not replacing Milestone 3.0 as the main stable inventory milestone.
- Future risky UI changes should still be done page-specific.

Safe milestone tags:
- Milestone 1.0: milestone-1-stable-ui-cleanup
- Milestone 1.1: milestone-1.1-usb-software-cleanup
- Milestone 1.2: milestone-1.2-human-change-log-safe
- Milestone 2.0: milestone-2.0-history-fast-3d
- Milestone 3.0: milestone-3.0-universal-inventory-command-center
- Semi Milestone 3.1: milestone-3.1-branding-ui-safe-point

Restore Semi Milestone 3.1:
cd D:\SagarSystemHealthMonitor
git fetch --all --tags
git reset --hard milestone-3.1-branding-ui-safe-point
powershell -ExecutionPolicy Bypass -File "D:\SagarSystemHealthMonitor\RUN_SERVER_2278.ps1"

Browser:
Press Ctrl + F5 after restart.
