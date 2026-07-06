# New Chat Handoff - System Monitor Tool

## Start point

Use this restore point first:

$TagName

This is the accepted stable point for the branding/login section.

## What the user wants preserved

The user accepted the current login concept enough to stop this section. The top/left text section must stay stable. The team/person photo background is acceptable even if not fully clear. Do not keep trying to redesign the login page.

## Current state summary

- App folder: $RepoPath
- Branch: $Branch
- Server run script: D:\SagarSystemHealthMonitor\RUN_SERVER_2278.ps1
- Port: 2278
- Main frontend files:
  - public/index.html
  - public/app.js
  - public/styles.css
  - public/branding/
- Branding settings are available in Settings.
- User can change:
  - Company name
  - Company website
  - Company logo
  - Login background image
  - Login tagline
  - Tagline font size percent

## Accepted current login UI

- Left side: product/system-health content.
- Right side: login card is visible.
- Logo is Next Toppers.
- Background/person photo is present/subtle.
- It is okay if person photo is not very clear.
- Do not change animation logic again.
- Do not make login layout too large.
- Do not hide login card.

## Important warning from this chat

Many earlier branding attempts broke UI:
- Blank page
- Dashboard overlay
- Duplicate company pill
- Login card missing
- Too-large login layout
- Confusing login page

So in future:
- Do not use global broad DOM patches.
- Do not apply login background to dashboard.
- Do not touch backend/server for UI-only request.
- Do not touch other tabs unless user specifically asks.
- Always make a backup and syntax check.

## Git milestones

- milestone-1-stable-ui-cleanup
- milestone-1.1-usb-software-cleanup
- milestone-1.2-human-change-log-safe
- milestone-2.0-history-fast-3d
- milestone-3.0-universal-inventory-command-center
- milestone-3.1-branding-settings-foundation
- $TagName

## Restore command

`powershell
cd D:\SagarSystemHealthMonitor
git fetch --all --tags
git reset --hard milestone-3.2-branding-login-stable
powershell -ExecutionPolicy Bypass -File "D:\SagarSystemHealthMonitor\RUN_SERVER_2278.ps1"
`

Then press Ctrl + F5 in browser.

## User style and response preference

- Explain like child, step by step.
- Give exact PowerShell commands.
- Avoid high-level vague explanation.
- Do not say tested unless truly tested on his machine.
- Use one patch at a time.
- Do not disturb working tabs.

## Next work

Ask the user what new tab/page they want next.
Do not reopen login design unless user asks.
