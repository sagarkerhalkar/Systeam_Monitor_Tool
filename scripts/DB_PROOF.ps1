param([string]$RepoPath = "D:\SagarSystemHealthMonitor")
$ErrorActionPreference = "Stop"
cd $RepoPath
$py = @'
import sqlite3, os
con=sqlite3.connect(r"data\monitor.db")
cur=con.cursor()
def table_count(name):
    exists=cur.execute("select count(*) from sqlite_master where type='table' and name=?", (name,)).fetchone()[0]
    return cur.execute("select count(*) from " + name).fetchone()[0] if exists else 'missing'
print('DB MB', round(os.path.getsize(r'data\monitor.db')/1024/1024,2))
for t in ['latest','heartbeats','hardware_inventory','software_inventory','notifications','change_events']:
    print(t, table_count(t))
con.close()
'@
python -c $py
