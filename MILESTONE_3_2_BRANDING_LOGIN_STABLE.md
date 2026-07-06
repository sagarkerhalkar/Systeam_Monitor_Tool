# Milestone 3.2 - Branding Login Stable

Date: 07/06/2026 20:16:18

Tag:
milestone-3.2-branding-login-stable

Project:
Sagar Kerhalkar System Health Monitor Tool

Current stable decision:
This is the accepted/stable branding-login point after many UI attempts.
Do not redesign the login page again unless explicitly requested.

Current login page status:
- Login page is now clear enough to use.
- Left side has system-health story/content.
- Right side has visible login card.
- Company logo appears in login and branding places.
- Login tagline is controlled from Settings.
- Login background image is controlled from Settings.
- Person/team background image may not be fully clear, but that is accepted for now.
- Top text / left content must remain stable.
- Do not continue experimenting with login animation or layout.

Important user instruction:
- This section is last for now.
- Do not disturb working dashboard/tabs.
- Do not touch server/backend for UI-only requests.
- Future changes must be page-specific and small.

Branding Settings:
- Company Name
- Company Website
- Company Logo
- Login Background Image
- Login Tagline
- Tagline Font Size Percent

Important app files:
- public/index.html
- public/app.js
- public/styles.css
- public/branding/nexttoppers-logo.png
- public/branding/nexttoppers-team-bg.png
- server.py

Branding patch history:
- Earlier global branding patches were too broad and caused overlay/blank issues.
- Bad branding patches were removed.
- Exact static patch was created because login/sidebar elements were found in public/index.html.
- Final accepted login state uses exact static branding plus split photo/right-card style.
- Do not add more blind DOM polling or full-dashboard overlay.
- Avoid applying login background while dashboard is visible.

Known stable milestone chain:
- Milestone 1.0: milestone-1-stable-ui-cleanup
- Milestone 1.1: milestone-1.1-usb-software-cleanup
- Milestone 1.2: milestone-1.2-human-change-log-safe
- Milestone 2.0: milestone-2.0-history-fast-3d
- Milestone 3.0: milestone-3.0-universal-inventory-command-center
- Semi Milestone 3.1: milestone-3.1-branding-settings-foundation
- Milestone 3.2: milestone-3.2-branding-login-stable

Restore Milestone 3.2:
cd D:\SagarSystemHealthMonitor
git fetch --all --tags
git reset --hard milestone-3.2-branding-login-stable
powershell -ExecutionPolicy Bypass -File "D:\SagarSystemHealthMonitor\RUN_SERVER_2278.ps1"

Browser:
Press Ctrl + F5 after restart.

Next chat instruction:
Start from Milestone 3.2.
Do not rollback branding unless the user says it is broken.
Do not redesign login again.
Continue only with new requested tab/page.
