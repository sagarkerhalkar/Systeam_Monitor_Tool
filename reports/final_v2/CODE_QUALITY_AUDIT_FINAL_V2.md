# Code Quality Audit - Final V2

Time: 2026-07-10 16:37:20.358198
Source files scanned: 172
Total source lines: 74650
Function-like definitions found: 2053

## Source files

| File | Lines | Bytes | SHA256 |
|---|---:|---:|---|
| BUILD_WINDOWS_CLIENT_EXE.ps1 | 66 | 2542 | `257b4139beada542...` |
| COPY_DATA_FROM_OLD_BUILD.ps1 | 12 | 572 | `3ea2ade71d3ffc42...` |
| FINAL_V2_MILESTONE.md | 337 | 9020 | `a2ab0e5ec3afba56...` |
| IMPLEMENTATION_PLAN_FINAL_V2.md | 1 | 5 | `f01a374e9c81e3db...` |
| INSTALL_DUCKDNS_FIXED_DOMAIN.ps1 | 46 | 2716 | `7409d0c61e488b23...` |
| INSTALL_PUBLIC_DOMAIN_AND_AUTOSTART.ps1 | 11 | 689 | `061427c708eb6da4...` |
| INSTALL_SERVER_AUTOSTART_TASK.ps1 | 34 | 1826 | `d98d8aa8a8250b13...` |
| MILESTONE_1_1_STABLE_RESTORE_POINT.md | 29 | 897 | `5a96843208e1c824...` |
| MILESTONE_1_2_STABLE_RESTORE_POINT.md | 37 | 1104 | `dff104871f2040fc...` |
| MILESTONE_1_STABLE_RESTORE_POINT.md | 21 | 545 | `fb3aa530298b9240...` |
| MILESTONE_2_0_STABLE_RESTORE_POINT.md | 42 | 1383 | `bd9363100a5361b3...` |
| MILESTONE_3_0_STABLE_RESTORE_POINT.md | 56 | 1766 | `ba0f7741e7aa2912...` |
| MILESTONE_3_1_BRANDING_SETTINGS_FOUNDATION.md | 45 | 1429 | `41c5a2a78f74c129...` |
| MILESTONE_3_1_SEMI_STABLE_RESTORE_POINT.md | 44 | 1457 | `be1262396da10c2c...` |
| MILESTONE_3_2_BRANDING_LOGIN_STABLE.md | 78 | 2657 | `86ad4cb351a35a43...` |
| NEW_CHAT_HANDOFF_FINAL_V2.md | 194 | 4105 | `85f9227d011d62be...` |
| NEW_CHAT_HANDOFF_MILESTONE_3_2_BRANDING_LOGIN_STABLE.md | 96 | 2581 | `78a1cd65b3aa727b...` |
| README.md | 6772 | 44648 | `eb2e13fd272c67b6...` |
| RUN_SERVER_2278.bat | 4 | 74 | `b282aa69e90ca617...` |
| RUN_SERVER_2278.ps1 | 8 | 569 | `1d7b3130bd8ed6f3...` |
| RUN_SERVER_2278_BOOT_SYSTEM.ps1 | 32 | 1484 | `8ae4d3afa437f741...` |
| RUN_SERVER_BACKGROUND_2278.ps1 | 10 | 577 | `0c85d4a1ed5335b0...` |
| RUN_TRYCLOUDFLARE_TUNNEL_2278.ps1 | 13 | 794 | `009a775d85427b69...` |
| server.py | 3097 | 170709 | `569f904b7502a698...` |
| SERVER_WATCHDOG_2278.ps1 | 151 | 3976 | `ece1a6882aff783d...` |
| TEST_PUBLIC_DOMAIN.ps1 | 7 | 1002 | `e0dc75c79a83a8e5...` |
| UNINSTALL_SERVER_AUTOSTART_TASK.ps1 | 4 | 259 | `8d4263ce47e1533a...` |
| UPDATE_DEPLOY_PAGE_TO_DOMAIN.ps1 | 61 | 2803 | `09e43dc29f4bf594...` |
| UPDATE_DUCKDNS_IP.ps1 | 13 | 670 | `c913f77ed700edf7...` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 299 | 39659 | `7102c4df40bb6dc7...` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/index.html | 278 | 28057 | `edc9556d38598e42...` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1987 | 105795 | `5c8de0db7f37a797...` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/styles.css | 150 | 36700 | `f387783659bf4d7d...` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 273 | 38777 | `d8e2bcdcd6466887...` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/index.html | 177 | 24239 | `0adf01366ea70fbc...` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/styles.css | 92 | 33451 | `5ad8148567b11a2f...` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 517 | 50755 | `a348eb66067e4425...` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/styles.css | 200 | 49025 | `8d8b0d1cc23e6a38...` |
| BACKUP_GPU_MEMORY_32GB_FIX_20260612_144248/client_windows.ps1 | 558 | 31177 | `43cda1cb7de9ef88...` |
| BACKUP_GPU_MEMORY_32GB_FIX_20260612_144248/server.py | 1988 | 105824 | `b5687bceddbbb706...` |
| BACKUP_GPU_MOJIBAKE_FIX_20260612_140624/app.js | 517 | 50755 | `a348eb66067e4425...` |
| BACKUP_GPU_MOJIBAKE_FIX_20260612_140624/client_windows.ps1 | 488 | 28986 | `de25bb4b09bbc619...` |
| BACKUP_GPU_MOJIBAKE_FIX_20260612_140624/index.html | 210 | 23295 | `a9cbe8184210cf8d...` |
| BACKUP_GPU_MOJIBAKE_FIX_20260612_140624/styles.css | 200 | 49025 | `8d8b0d1cc23e6a38...` |
| BACKUP_LOGIN_EXPERIENCE_20260612_133516/app.js | 513 | 50578 | `dc28db3df7e18ce2...` |
| BACKUP_LOGIN_EXPERIENCE_20260612_133516/index.html | 194 | 22614 | `1033fcb6c3b0f348...` |
| BACKUP_LOGIN_EXPERIENCE_20260612_133516/styles.css | 185 | 39504 | `15346b523ac4581e...` |
| BACKUP_STRICT_GPU_ACTUAL_DATA_20260612_150200/app.js | 596 | 56922 | `eedca01757cb18ea...` |
| BACKUP_STRICT_GPU_ACTUAL_DATA_20260612_150200/client_windows.ps1 | 569 | 31473 | `61055de57a2b09e9...` |
| BACKUP_STRICT_GPU_ACTUAL_DATA_20260612_150200/server.py | 1994 | 108200 | `b7d4d5fe54626fe8...` |
| BACKUP_STRICT_GPU_ACTUAL_DATA_20260612_150200/styles.css | 208 | 49347 | `1ce819af152098d8...` |
| BACKUP_UI_READABILITY_HISTORY_V2_20260612_130548/app.js | 463 | 47806 | `9428f172d38fb49d...` |
| BACKUP_UI_READABILITY_HISTORY_V2_20260612_130548/index.html | 194 | 22427 | `509e5387e3b34e90...` |
| BACKUP_UI_READABILITY_HISTORY_V2_20260612_130548/styles.css | 172 | 38501 | `6f23baa51928cfc8...` |
| data/hardware_inventory_seed.json | 11452 | 324212 | `8d6d966c528590a4...` |
| data/retention_settings.json | 4 | 75 | `f3c637cf19d46bdb...` |
| data/server_isp_cache.json | 11 | 361 | `73f1170a1558b1d2...` |
| docs/FINAL_V2_HARDENING_CICD_SECURITY.md | 142 | 1983 | `6c012d283c76bc67...` |
| INCREMENTAL_SOURCE_BACKUPS/manifest_latest.json | 68 | 7683 | `3bd38836897f89b6...` |
| public/app.js | 5765 | 359982 | `7fd7565f28241c94...` |
| public/index.html | 213 | 24264 | `d71c26e976709da6...` |
| public/retention-manager.html | 99 | 4796 | `dbed6e27ee5544db...` |
| public/styles.css | 1912 | 66995 | `0d21734cd0a08781...` |
| Restore_Working_V8_Client_Only_Int64_Fix/RESTORE_WORKING_WINDOWS_CLIENT_ONLY.ps1 | 33 | 1552 | `4d239fec75d220c7...` |
| RETENTION_REPORTS/EMERGENCY_KEEP_10_DAYS_20260701_142307.json | 27 | 719 | `8a98aae5894d2995...` |
| RETENTION_REPORTS/EMERGENCY_KEEP_10_DAYS_20260701_145612.json | 27 | 713 | `a5c3f640f967cc19...` |
| RETENTION_REPORTS/EMERGENCY_KEEP_10_DAYS_20260701_145818.json | 27 | 712 | `e832bbcda43022b3...` |
| RETENTION_REPORTS/EMERGENCY_KEEP_10_DAYS_20260702_023006.json | 19 | 517 | `426d73c75c141bf4...` |
| RETENTION_REPORTS/EMERGENCY_KEEP_10_DAYS_20260703_023009.json | 19 | 519 | `97038e003f75eb40...` |
| RETENTION_REPORTS/EMERGENCY_KEEP_10_DAYS_20260704_023003.json | 19 | 519 | `04e68e52429ebf48...` |
| RETENTION_REPORTS/EMERGENCY_KEEP_5_DAYS_20260701_153508.json | 16 | 406 | `5122ef9c4f8fde16...` |
| RETENTION_REPORTS/EMERGENCY_KEEP_5_DAYS_20260701_160149.json | 27 | 719 | `40ba6e3bb4feba2f...` |
| RETENTION_REPORTS/RETENTION_KEEP_DAYS_20260702_023011.json | 22 | 543 | `8861fb55187569cd...` |
| RETENTION_REPORTS/RETENTION_KEEP_DAYS_20260703_023012.json | 22 | 545 | `9a93aa366150777c...` |
| RETENTION_REPORTS/RETENTION_KEEP_DAYS_20260704_023006.json | 22 | 545 | `f03ecdbdacc67f3d...` |
| SagarSystemHealthMonitor_README_A_to_Z/README.md | 1673 | 35436 | `d62f2b2a827e3f35...` |
| scripts/APPLY_RETENTION_FROM_SETTINGS.ps1 | 138 | 4818 | `dcb3bfc1ebe56eac...` |
| scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 | 20 | 1705 | `c34a79fa6e0719a3...` |
| scripts/check_all.ps1 | 48 | 984 | `ac5210ccdd695b27...` |
| scripts/CHECK_SERVER_AND_CLIENT_ISP_2278.ps1 | 9 | 604 | `00c4af8a4f6cdccc...` |
| scripts/CHECK_SERVER_HISTORY_2278.ps1 | 6 | 479 | `6f98385a19409acb...` |
| scripts/CHECK_WINDOWS_CLIENT_LOCAL_ISP.ps1 | 22 | 1388 | `697efa0efdc50c3f...` |
| scripts/CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1 | 29 | 1904 | `1e33d735e4f670cf...` |
| scripts/CHECK_WINDOWS_USB_MESSAGES.ps1 | 22 | 1255 | `b93b4bb0dbf91107...` |
| scripts/CLEAN_CLIENT_IP_LIST.ps1 | 18 | 871 | `eddf1f2cc3415ec6...` |
| scripts/client_windows.ps1 | 629 | 34462 | `a67c90fb65cd7826...` |
| scripts/COMPACT_MONITOR_DB_WITH_EXTERNAL_WORKSPACE.ps1 | 70 | 2781 | `8a8927e348f4ad81...` |
| scripts/DIAGNOSE_SERVER_2278.ps1 | 15 | 1286 | `df335b0572903240...` |
| scripts/DIAGNOSE_WINDOWS_CLIENT_2278.ps1 | 40 | 2273 | `c50f46187c9947bc...` |
| scripts/ENABLE_WINRM_ON_WINDOWS_CLIENT_ONE_TIME.ps1 | 6 | 358 | `5d17e4c5817a8eb6...` |
| scripts/FULL_HW_SW_LICENSE_WINDOWS_CLIENT_2278.ps1 | 286 | 20803 | `f41f43bd058feac7...` |
| scripts/INCREMENTAL_SOURCE_BACKUP_MAIN_2278.ps1 | 54 | 1840 | `cd2167d08e33fa5a...` |
| scripts/install_windows_client_2278.ps1 | 45 | 2692 | `e2dba0892a53744a...` |
| scripts/PREPARE_SERVER_TRUSTEDHOSTS.ps1 | 11 | 548 | `66e42f4a63254ebc...` |
| scripts/running_check.ps1 | 92 | 1570 | `d80b63c1bc23a64a...` |
| scripts/safe_cleanup_quarantine.ps1 | 118 | 2253 | `f1f0f6c8f90fd8d4...` |
| scripts/security_scan.py | 164 | 2939 | `a27726e27b23d1a0...` |
| scripts/startup_check.ps1 | 156 | 2300 | `8e238f4a01064a02...` |
| scripts/uninstall_windows_client.ps1 | 4 | 257 | `3261f6b49efe0db4...` |
| scripts/UPDATE_UBUNTU_CLIENTS_FROM_SERVER.ps1 | 12 | 723 | `b8272a45486b408c...` |
| scripts/UPDATE_WINDOWS_CLIENTS_FROM_SERVER.ps1 | 25 | 1400 | `a7cd87dd1836c493...` |
| Restore_Working_V8_Client_Only_Int64_Fix/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 | 20 | 1705 | `c34a79fa6e0719a3...` |
| Restore_Working_V8_Client_Only_Int64_Fix/scripts/CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1 | 29 | 1904 | `1e33d735e4f670cf...` |
| Restore_Working_V8_Client_Only_Int64_Fix/scripts/CHECK_WINDOWS_USB_MESSAGES.ps1 | 22 | 1255 | `b93b4bb0dbf91107...` |
| Restore_Working_V8_Client_Only_Int64_Fix/scripts/client_windows.ps1 | 488 | 28986 | `de25bb4b09bbc619...` |
| Restore_Working_V8_Client_Only_Int64_Fix/scripts/DIAGNOSE_WINDOWS_CLIENT_2278.ps1 | 40 | 2273 | `c50f46187c9947bc...` |
| Restore_Working_V8_Client_Only_Int64_Fix/scripts/install_windows_client_2278.ps1 | 45 | 2692 | `e2dba0892a53744a...` |
| reports/final_v2/CLEANUP_QUARANTINE_MANIFEST_FINAL_V2.json | 931 | 49314 | `43aa759e290cf75c...` |
| reports/final_v2/CODE_QUALITY_AUDIT_FINAL_V2.json | 11202 | 290827 | `2514eff56a45ef10...` |
| reports/final_v2/CODE_QUALITY_AUDIT_FINAL_V2.md | 694 | 52168 | `b945dcd03bdb5afd...` |
| reports/final_v2/SECURITY_SCAN_REPORT.json | 86 | 3044 | `b3ae7693c6a77b41...` |
| reports/final_v2/SECURITY_SCAN_REPORT.md | 23 | 2098 | `1ce2fa4ab766bf01...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/BUILD_WINDOWS_CLIENT_EXE.ps1 | 66 | 2542 | `257b4139beada542...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/COPY_DATA_FROM_OLD_BUILD.ps1 | 12 | 572 | `3ea2ade71d3ffc42...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/incremental_backup_report.json | 17 | 544 | `4888d4929f69c888...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/INSTALL_DUCKDNS_FIXED_DOMAIN.ps1 | 46 | 2716 | `7409d0c61e488b23...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/INSTALL_PUBLIC_DOMAIN_AND_AUTOSTART.ps1 | 11 | 689 | `061427c708eb6da4...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/INSTALL_SERVER_AUTOSTART_TASK.ps1 | 34 | 1826 | `d98d8aa8a8250b13...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/README.md | 1673 | 35436 | `d62f2b2a827e3f35...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/RUN_SERVER_2278.bat | 4 | 74 | `b282aa69e90ca617...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/RUN_SERVER_2278.ps1 | 8 | 569 | `1d7b3130bd8ed6f3...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/RUN_SERVER_2278_BOOT_SYSTEM.ps1 | 32 | 1484 | `8ae4d3afa437f741...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/RUN_SERVER_BACKGROUND_2278.ps1 | 10 | 577 | `0c85d4a1ed5335b0...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/RUN_TRYCLOUDFLARE_TUNNEL_2278.ps1 | 13 | 794 | `009a775d85427b69...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/server.py | 2117 | 114069 | `6d0c135da7f5e3c5...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/SERVER_WATCHDOG_2278.ps1 | 151 | 3976 | `ece1a6882aff783d...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/TEST_PUBLIC_DOMAIN.ps1 | 7 | 1002 | `e0dc75c79a83a8e5...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/UNINSTALL_SERVER_AUTOSTART_TASK.ps1 | 4 | 259 | `8d4263ce47e1533a...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/UPDATE_DEPLOY_PAGE_TO_DOMAIN.ps1 | 61 | 2803 | `09e43dc29f4bf594...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/UPDATE_DUCKDNS_IP.ps1 | 13 | 670 | `c913f77ed700edf7...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_160022/incremental_backup_report.json | 17 | 542 | `a7dbffc3749179f0...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_163551/incremental_backup_report.json | 17 | 542 | `52f49d351b1302f0...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_163603/incremental_backup_report.json | 17 | 542 | `afb3002da9260e63...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260705_221203/incremental_backup_report.json | 17 | 542 | `37eb0eb965469861...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260705_221203/server.py | 2207 | 115937 | `f771118e8b42a045...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260705_221204/incremental_backup_report.json | 17 | 542 | `5d105f7b559cf618...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260705_221207/incremental_backup_report.json | 17 | 542 | `9c0d7b72ac7cdc43...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260705_221203/public/app.js | 1257 | 87489 | `1a8bdc15fb61dcfe...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/public/app.js | 675 | 63129 | `1414f23f8a26bce7...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/public/index.html | 211 | 23491 | `c6390d578d13ac8e...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/public/retention-manager.html | 99 | 4796 | `dbed6e27ee5544db...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/public/styles.css | 216 | 49661 | `96ced90242f7c487...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/Restore_Working_V8_Client_Only_Int64_Fix/RESTORE_WORKING_WINDOWS_CLIENT_ONLY.ps1 | 33 | 1552 | `4d239fec75d220c7...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/SagarSystemHealthMonitor_README_A_to_Z/README.md | 1673 | 35436 | `d62f2b2a827e3f35...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/APPLY_RETENTION_FROM_SETTINGS.ps1 | 138 | 4818 | `dcb3bfc1ebe56eac...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 | 20 | 1705 | `c34a79fa6e0719a3...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/CHECK_SERVER_AND_CLIENT_ISP_2278.ps1 | 9 | 604 | `00c4af8a4f6cdccc...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/CHECK_SERVER_HISTORY_2278.ps1 | 6 | 479 | `6f98385a19409acb...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/CHECK_WINDOWS_CLIENT_LOCAL_ISP.ps1 | 22 | 1388 | `697efa0efdc50c3f...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1 | 29 | 1904 | `1e33d735e4f670cf...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/CHECK_WINDOWS_USB_MESSAGES.ps1 | 22 | 1255 | `b93b4bb0dbf91107...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/CLEAN_CLIENT_IP_LIST.ps1 | 18 | 871 | `eddf1f2cc3415ec6...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/client_windows.ps1 | 629 | 34462 | `a67c90fb65cd7826...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/COMPACT_MONITOR_DB_WITH_EXTERNAL_WORKSPACE.ps1 | 70 | 2781 | `8a8927e348f4ad81...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/DIAGNOSE_SERVER_2278.ps1 | 15 | 1286 | `df335b0572903240...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/DIAGNOSE_WINDOWS_CLIENT_2278.ps1 | 40 | 2273 | `c50f46187c9947bc...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/ENABLE_WINRM_ON_WINDOWS_CLIENT_ONE_TIME.ps1 | 6 | 358 | `5d17e4c5817a8eb6...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/FULL_HW_SW_LICENSE_WINDOWS_CLIENT_2278.ps1 | 286 | 20803 | `f41f43bd058feac7...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/INCREMENTAL_SOURCE_BACKUP_MAIN_2278.ps1 | 54 | 1840 | `cd2167d08e33fa5a...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/install_windows_client_2278.ps1 | 45 | 2692 | `e2dba0892a53744a...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/PREPARE_SERVER_TRUSTEDHOSTS.ps1 | 11 | 548 | `66e42f4a63254ebc...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/uninstall_windows_client.ps1 | 4 | 257 | `3261f6b49efe0db4...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/UPDATE_UBUNTU_CLIENTS_FROM_SERVER.ps1 | 12 | 723 | `b8272a45486b408c...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/scripts/UPDATE_WINDOWS_CLIENTS_FROM_SERVER.ps1 | 25 | 1400 | `a7cd87dd1836c493...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/Restore_Working_V8_Client_Only_Int64_Fix/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 | 20 | 1705 | `c34a79fa6e0719a3...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/Restore_Working_V8_Client_Only_Int64_Fix/scripts/CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1 | 29 | 1904 | `1e33d735e4f670cf...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/Restore_Working_V8_Client_Only_Int64_Fix/scripts/CHECK_WINDOWS_USB_MESSAGES.ps1 | 22 | 1255 | `b93b4bb0dbf91107...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/Restore_Working_V8_Client_Only_Int64_Fix/scripts/client_windows.ps1 | 488 | 28986 | `de25bb4b09bbc619...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/Restore_Working_V8_Client_Only_Int64_Fix/scripts/DIAGNOSE_WINDOWS_CLIENT_2278.ps1 | 40 | 2273 | `c50f46187c9947bc...` |
| INCREMENTAL_SOURCE_BACKUPS/INC_20260701_155955/Restore_Working_V8_Client_Only_Int64_Fix/scripts/install_windows_client_2278.ps1 | 45 | 2692 | `e2dba0892a53744a...` |
| .github/workflows/ci.yml | 148 | 1960 | `d408bb1fb47c4b63...` |
| .github/workflows/release-package.yml | 64 | 1198 | `8429687dccb78a71...` |

## Function-like definitions

| File | Line | Name |
|---|---:|---|
| server.py | 35 | `_sk_num` |
| server.py | 46 | `_sk_walk_values` |
| server.py | 60 | `_sk_enrich_notification_metrics` |
| server.py | 76 | `first_metric` |
| server.py | 203 | `now_iso` |
| server.py | 207 | `log` |
| server.py | 216 | `_b64` |
| server.py | 220 | `hash_password` |
| server.py | 226 | `verify_password` |
| server.py | 237 | `parse_cookies` |
| server.py | 246 | `is_local_request` |
| server.py | 251 | `new_session` |
| server.py | 257 | `session_info` |
| server.py | 278 | `valid_session` |
| server.py | 282 | `auth_required_path` |
| server.py | 295 | `tcp_latency_ms` |
| server.py | 305 | `run_ping_probe` |
| server.py | 328 | `server_internet_health` |
| server.py | 395 | `fetch_json_url` |
| server.py | 402 | `_server_public_internet_lookup` |
| server.py | 425 | `_refresh_server_isp_background` |
| server.py | 440 | `server_cloudflare_speed_test` |
| server.py | 467 | `server_public_internet_info` |
| server.py | 501 | `clean_str` |
| server.py | 507 | `valid_machine_id_part` |
| server.py | 528 | `first_physical_mac` |
| server.py | 553 | `_safe_id` |
| server.py | 557 | `machine_fingerprint_value` |
| server.py | 594 | `make_machine_identity` |
| server.py | 598 | `stable_machine_merge_key` |
| server.py | 628 | `cleanup_duplicate_latest_rows` |
| server.py | 658 | `get_nested` |
| server.py | 673 | `to_float` |
| server.py | 682 | `safe_json_loads` |
| server.py | 689 | `parse_usb_repr_string` |
| server.py | 725 | `loose_json_or_python` |
| server.py | 748 | `listify` |
| server.py | 770 | `is_noisy_windows_usb_name` |
| server.py | 790 | `normalize_usb_device` |
| server.py | 835 | `normalize_usb_list` |
| server.py | 844 | `walk` |
| server.py | 877 | `normalize_payload_inplace` |
| server.py | 917 | `summarize_payload` |
| server.py | 1039 | `db_connect` |
| server.py | 1045 | `init_db` |
| server.py | 1153 | `get_settings` |
| server.py | 1159 | `set_settings` |
| server.py | 1167 | `list_users_public` |
| server.py | 1173 | `get_user_row` |
| server.py | 1178 | `upsert_user` |
| server.py | 1204 | `delete_user` |
| server.py | 1214 | `public_settings` |
| server.py | 1219 | `rules_list` |
| server.py | 1230 | `eval_rule` |
| server.py | 1243 | `can_send_alert` |
| server.py | 1252 | `send_google_chat` |
| server.py | 1265 | `record_notification` |
| server.py | 1271 | `evaluate_notifications` |
| server.py | 1284 | `process_change_events` |
| server.py | 1306 | `format_change_value` |
| server.py | 1346 | `humanize_change_row` |
| server.py | 1377 | `latest_change_events` |
| server.py | 1386 | `change_events_for_export` |
| server.py | 1409 | `latest_payload_for_machine` |
| server.py | 1416 | `export_software_rows` |
| server.py | 1436 | `export_usb_rows` |
| server.py | 1458 | `check_offline_notifications` |
| server.py | 1483 | `create_client_message` |
| server.py | 1492 | `list_client_messages` |
| server.py | 1512 | `take_pending_messages` |
| server.py | 1537 | `upsert_heartbeat` |
| server.py | 1564 | `load_latest` |
| server.py | 1644 | `overview` |
| server.py | 1695 | `daily_history` |
| server.py | 1701 | `parse_day` |
| server.py | 1788 | `csv_response` |
| server.py | 1805 | `log_message` |
| server.py | 1808 | `current_session` |
| server.py | 1812 | `is_authenticated` |
| server.py | 1815 | `current_role` |
| server.py | 1818 | `current_username` |
| server.py | 1821 | `is_admin` |
| server.py | 1824 | `require_admin` |
| server.py | 1831 | `require_auth` |
| server.py | 1839 | `_send` |
| server.py | 1852 | `send_json` |
| server.py | 1855 | `read_json` |
| server.py | 1860 | `do_OPTIONS` |
| server.py | 1863 | `do_GET` |
| server.py | 1940 | `_hrcl_send` |
| server.py | 1948 | `_hrcl_q` |
| server.py | 1950 | `_hrcl_day_start` |
| server.py | 1953 | `_hrcl_day_end` |
| server.py | 1956 | `_hrcl_limit` |
| server.py | 2026 | `_hist_send` |
| server.py | 2034 | `_hist_q` |
| server.py | 2039 | `_hist_limit` |
| server.py | 2045 | `_day_start` |
| server.py | 2048 | `_day_end` |
| server.py | 2051 | `_cat_sql` |
| server.py | 2155 | `_hw_send` |
| server.py | 2163 | `_hw_q` |
| server.py | 2168 | `_hw_db_path` |
| server.py | 2171 | `_hw_now` |
| server.py | 2173 | `_hw_ensure` |
| server.py | 2187 | `_hw_seed_if_empty` |
| server.py | 2209 | `_hw_text` |
| server.py | 2211 | `_hw_live_rows` |
| server.py | 2227 | `_hw_rows` |
| server.py | 2303 | `_hw_send` |
| server.py | 2311 | `_hw_q` |
| server.py | 2316 | `_hw_db_path` |
| server.py | 2319 | `_hw_now` |
| server.py | 2321 | `_hw_ensure` |
| server.py | 2379 | `_hw_del_send` |
| server.py | 2387 | `_hw_del_q` |
| server.py | 2421 | `_sw_send` |
| server.py | 2429 | `_sw_q` |
| server.py | 2434 | `_sw_db` |
| server.py | 2437 | `_sw_cols` |
| server.py | 2439 | `_sw_ensure` |
| server.py | 2492 | `_sw_save_send` |
| server.py | 2500 | `_sw_save_q` |
| server.py | 2505 | `_sw_save_db` |
| server.py | 2508 | `_sw_cols` |
| server.py | 2510 | `_sw_ensure` |
| server.py | 2566 | `_sw_del_send` |
| server.py | 2574 | `_sw_del_q` |
| server.py | 2607 | `_sk_notif_send` |
| server.py | 2814 | `serve_static` |
| server.py | 2845 | `do_POST` |
| server.py | 2931 | `do_DELETE` |
| server.py | 2966 | `_ret_s` |
| server.py | 2969 | `_ret_load_settings` |
| server.py | 2980 | `_ret_save_settings` |
| server.py | 2988 | `_ret_drive_free_bytes` |
| server.py | 2995 | `_ret_table_count` |
| server.py | 3004 | `_ret_status` |
| server.py | 3041 | `_ret_read_body` |
| server.py | 3046 | `_ret_get` |
| server.py | 3057 | `_ret_post` |
| server.py | 3078 | `main` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 1 | `$` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 2 | `$$` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 27 | `esc` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 28 | `fmt` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 29 | `ago` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 30 | `host` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 31 | `payload` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 32 | `nested` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 33 | `isAdmin` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 34 | `statusPill` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 35 | `attention` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 36 | `queryString` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 37 | `cleanText` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 38 | `shortId` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 39 | `roleLabel` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 41 | `api` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 51 | `showLogin` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 56 | `hideLogin` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 60 | `login` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 66 | `logout` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 67 | `checkAuth` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 71 | `applyRoleControls` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 77 | `setLiveButtons` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 82 | `toggleAutoRefresh` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 83 | `showBanner` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 85 | `refresh` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 95 | `machineLabel` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 96 | `selectedMachine` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 100 | `hydrateSelectors` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 104 | `first` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 110 | `onMachineSelect` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 117 | `parseRawObjectString` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 137 | `arr` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 148 | `usbType` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 149 | `isNoisyUsb` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 150 | `cleanUsbItems` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 168 | `filteredMachines` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 178 | `renderDashboard` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 194 | `latest` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 198 | `ring` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 202 | `renderCommandSystemSpotlight` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 207 | `renderCommandPageSummary` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 220 | `renderFleet` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 221 | `detail` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 222 | `renderMachine360` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 223 | `renderNetwork` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 224 | `renderHardware` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 225 | `renderSoftware` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 226 | `renderUsb` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 227 | `renderChanges` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 228 | `historyQs` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 229 | `renderHistory` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 230 | `renderMessages` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 231 | `sendClientMessage` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 232 | `loadRules` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 233 | `renderRules` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 234 | `renderAlertHistory` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 235 | `saveSettings` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 236 | `editRule` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 237 | `saveRule` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 238 | `deleteRule` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 239 | `testNotification` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 240 | `clearAlerts` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 241 | `loadUsers` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 242 | `renderUsers` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 243 | `saveUser` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 244 | `deleteUser` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 245 | `changePassword` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 246 | `runServerSpeedTest` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 247 | `requireAdminDownload` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 248 | `exportCsv` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 249 | `midFrom` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 250 | `downloadCurrentMachine` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 251 | `downloadSoftwareSelected` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 252 | `downloadSoftwareAll` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 253 | `downloadUsbSelected` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 254 | `downloadUsbAll` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 255 | `downloadChangesSelected` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 256 | `downloadChangesAll` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 257 | `downloadChanges` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 258 | `downloadDailyHistory` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 259 | `downloadMachineHistory` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 260 | `downloadSelectedSystemDateRange` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 261 | `downloadHistorySamples` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 262 | `renderAll` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 263 | `switchPage` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/app.js | 279 | `text` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 97 | `now_iso` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 101 | `log` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 112 | `_b64` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 116 | `hash_password` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 122 | `verify_password` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 133 | `parse_cookies` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 142 | `is_local_request` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 147 | `new_session` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 153 | `session_info` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 174 | `valid_session` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 178 | `auth_required_path` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 191 | `tcp_latency_ms` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 201 | `run_ping_probe` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 224 | `server_internet_health` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 291 | `fetch_json_url` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 298 | `_server_public_internet_lookup` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 321 | `_refresh_server_isp_background` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 338 | `server_cloudflare_speed_test` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 365 | `server_public_internet_info` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 399 | `clean_str` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 405 | `valid_machine_id_part` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 426 | `first_physical_mac` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 451 | `_safe_id` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 455 | `machine_fingerprint_value` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 493 | `make_machine_identity` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 496 | `get_nested` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 511 | `to_float` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 520 | `safe_json_loads` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 527 | `parse_usb_repr_string` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 563 | `loose_json_or_python` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 586 | `listify` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 608 | `is_noisy_windows_usb_name` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 628 | `normalize_usb_device` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 673 | `normalize_usb_list` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 682 | `walk` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 715 | `normalize_payload_inplace` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 755 | `summarize_payload` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 871 | `db_connect` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 877 | `init_db` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 985 | `get_settings` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 991 | `set_settings` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 999 | `list_users_public` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1005 | `get_user_row` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1010 | `upsert_user` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1036 | `delete_user` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1046 | `public_settings` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1051 | `rules_list` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1062 | `eval_rule` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1075 | `can_send_alert` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1084 | `send_google_chat` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1097 | `record_notification` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1103 | `evaluate_notifications` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1116 | `process_change_events` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1139 | `format_change_value` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1179 | `humanize_change_row` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1210 | `latest_change_events` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1219 | `change_events_for_export` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1242 | `latest_payload_for_machine` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1249 | `export_software_rows` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1269 | `export_usb_rows` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1291 | `check_offline_notifications` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1317 | `create_client_message` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1327 | `list_client_messages` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1347 | `take_pending_messages` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1372 | `upsert_heartbeat` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1394 | `load_latest` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1445 | `overview` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1496 | `daily_history` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1502 | `parse_day` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1589 | `csv_response` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1606 | `log_message` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1609 | `current_session` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1613 | `is_authenticated` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1616 | `current_role` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1619 | `current_username` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1622 | `is_admin` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1625 | `require_admin` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1632 | `require_auth` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1640 | `_send` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1653 | `send_json` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1656 | `read_json` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1661 | `do_OPTIONS` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1664 | `do_GET` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1830 | `serve_static` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1861 | `do_POST` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1947 | `do_DELETE` |
| BACKUP_CUSTOM_DEPLOY_PAGE_V2_20260612_124103/server.py | 1971 | `main` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 1 | `$` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 2 | `$$` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 27 | `esc` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 28 | `fmt` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 29 | `ago` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 30 | `host` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 31 | `payload` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 32 | `nested` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 33 | `isAdmin` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 34 | `statusPill` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 35 | `attention` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 36 | `queryString` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 37 | `cleanText` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 38 | `shortId` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 39 | `roleLabel` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 41 | `api` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 51 | `showLogin` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 56 | `hideLogin` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 60 | `login` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 66 | `logout` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 67 | `checkAuth` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 71 | `applyRoleControls` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 77 | `setLiveButtons` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 82 | `toggleAutoRefresh` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 83 | `showBanner` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 85 | `refresh` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 95 | `machineLabel` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 96 | `selectedMachine` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 100 | `hydrateSelectors` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 104 | `first` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 110 | `onMachineSelect` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 117 | `parseRawObjectString` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 137 | `arr` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 148 | `usbType` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 149 | `isNoisyUsb` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 150 | `cleanUsbItems` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 168 | `filteredMachines` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 178 | `renderDashboard` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 194 | `latest` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 198 | `ring` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 202 | `renderCommandSystemSpotlight` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 207 | `renderCommandPageSummary` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 220 | `renderFleet` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 221 | `detail` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 222 | `renderMachine360` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 223 | `renderNetwork` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 224 | `renderHardware` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 225 | `renderSoftware` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 226 | `renderUsb` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 227 | `renderChanges` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 228 | `historyQs` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 229 | `renderHistory` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 230 | `renderMessages` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 231 | `sendClientMessage` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 232 | `loadRules` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 233 | `renderRules` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 234 | `renderAlertHistory` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 235 | `saveSettings` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 236 | `editRule` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 237 | `saveRule` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 238 | `deleteRule` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 239 | `testNotification` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 240 | `clearAlerts` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 241 | `loadUsers` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 242 | `renderUsers` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 243 | `saveUser` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 244 | `deleteUser` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 245 | `changePassword` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 246 | `runServerSpeedTest` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 247 | `requireAdminDownload` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 248 | `exportCsv` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 249 | `midFrom` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 250 | `downloadCurrentMachine` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 251 | `downloadSoftwareSelected` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 252 | `downloadSoftwareAll` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 253 | `downloadUsbSelected` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 254 | `downloadUsbAll` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 255 | `downloadChangesSelected` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 256 | `downloadChangesAll` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 257 | `downloadChanges` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 258 | `downloadDailyHistory` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 259 | `downloadMachineHistory` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 260 | `downloadSelectedSystemDateRange` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 261 | `downloadHistorySamples` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 262 | `renderAll` |
| BACKUP_DEPLOY_MOBILE_UI_20260612_121629/app.js | 263 | `switchPage` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 1 | `$` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 2 | `$$` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 27 | `esc` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 28 | `fmt` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 31 | `fmtInstallDate` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 42 | `fmtMemMb` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 47 | `cleanGpuName` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 50 | `gpuBrief` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 55 | `gpuDetailsHtml` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 72 | `ramFleetCell` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 75 | `netNowCell` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 79 | `ago` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 80 | `host` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 81 | `payload` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 82 | `nested` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 83 | `isAdmin` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 84 | `statusPill` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 85 | `attention` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 86 | `queryString` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 87 | `cleanText` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 88 | `shortId` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 89 | `roleLabel` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 91 | `api` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 101 | `showLogin` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 106 | `hideLogin` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 110 | `login` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 116 | `logout` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 117 | `checkAuth` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 121 | `applyRoleControls` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 127 | `setLiveButtons` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 132 | `toggleAutoRefresh` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 133 | `showBanner` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 135 | `refresh` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 145 | `machineLabel` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 146 | `selectedMachine` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 150 | `hydrateSelectors` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 154 | `first` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 160 | `onMachineSelect` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 167 | `parseRawObjectString` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 187 | `arr` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 198 | `usbType` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 199 | `isNoisyUsb` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 200 | `cleanUsbItems` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 219 | `filteredMachines` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 228 | `renderDashboard` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 244 | `latest` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 248 | `ring` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 252 | `renderCommandSystemSpotlight` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 257 | `renderCommandPageSummary` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 270 | `renderFleet` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 271 | `detail` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 272 | `renderMachine360` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 273 | `renderNetwork` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 274 | `renderHardware` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 275 | `renderSoftware` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 276 | `renderUsb` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 277 | `renderChanges` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 278 | `historyQs` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 279 | `renderHistory` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 280 | `renderMessages` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 281 | `sendClientMessage` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 282 | `loadRules` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 283 | `renderRules` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 284 | `renderAlertHistory` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 285 | `saveSettings` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 286 | `editRule` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 287 | `saveRule` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 288 | `deleteRule` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 289 | `testNotification` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 290 | `clearAlerts` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 291 | `loadUsers` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 292 | `renderUsers` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 293 | `saveUser` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 294 | `deleteUser` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 295 | `changePassword` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 296 | `runServerSpeedTest` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 297 | `requireAdminDownload` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 298 | `exportCsv` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 299 | `midFrom` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 300 | `downloadCurrentMachine` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 301 | `downloadSoftwareSelected` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 302 | `downloadSoftwareAll` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 303 | `downloadUsbSelected` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 304 | `downloadUsbAll` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 305 | `downloadChangesSelected` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 306 | `downloadChangesAll` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 307 | `downloadChanges` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 308 | `downloadDailyHistory` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 309 | `downloadMachineHistory` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 310 | `downloadSelectedSystemDateRange` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 311 | `downloadHistorySamples` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 312 | `renderAll` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 313 | `switchPage` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 329 | `text` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 426 | `getDeployCommands` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 437 | `renderDeployCommands` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 465 | `copyDeployCommandV2` |
| BACKUP_DISPLAY_ONLY_GPU_TEXT_FIX_20260612_145003/app.js | 484 | `saveDeployCommands` |
| ... | ... | 1553 more in JSON report |

## Large files over 5 MB

| File | Bytes |
|---|---:|
| data/monitor.db | 452676583424 |
| data/server.log | 281707269 |
| data/server_boot_stderr.log | 34024538 |