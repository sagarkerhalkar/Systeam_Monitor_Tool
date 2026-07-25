param([string]$RepoPath="D:\SagarSystemHealthMonitor")
cd $RepoPath
"=== SYNTAX ==="
python -m py_compile server.py
if (Get-Command node -ErrorAction SilentlyContinue) { node --check public\app.js }
"=== STATIC PROOF ==="
Select-String -Path server.py -Pattern "DELETE FROM latest|EMERGENCY_ASSET_SAVE_SEARCH_FIX_V1|GET save disabled" -Context 1,1
Select-String -Path public\app.js -Pattern "apiGet\('/api/hardware-inventory-save\?|apiGet\('/api/software-inventory-save\?|EMERGENCY_ASSET_SAVE_SEARCH_FIX_V1|easGlobalSearch" -Context 1,1
"=== DB TABLES ==="
python -c "import sqlite3, os; con=sqlite3.connect(r'data\monitor.db'); cur=con.cursor(); print('DB MB', round(os.path.getsize(r'data\monitor.db')/1024/1024,2)); print('latest', cur.execute('select count(*) from latest').fetchone()[0]); print('hardware_inventory table', cur.execute(\"select count(*) from sqlite_master where type='table' and name='hardware_inventory'\").fetchone()[0]); print('software_inventory table', cur.execute(\"select count(*) from sqlite_master where type='table' and name='software_inventory'\").fetchone()[0]); con.close()"
