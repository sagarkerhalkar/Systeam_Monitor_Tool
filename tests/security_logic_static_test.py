from pathlib import Path
import re, sys
root = Path(__file__).resolve().parents[1]
server = (root / 'server.py').read_text(encoding='utf-8-sig', errors='ignore')
app = (root / 'public' / 'app.js').read_text(encoding='utf-8', errors='ignore')
errors = []
if 'REAL_FIX_V3_START' not in server:
    errors.append('server REAL_FIX_V3 block missing')
if 'REAL_FIX_V3_START' not in app:
    errors.append('app REAL_FIX_V3 block missing')
if 'DELETE FROM latest WHERE' in server:
    errors.append('dangerous DELETE FROM latest still present')
if 'Access-Control-Allow-Origin", "*"' in server or "Access-Control-Allow-Origin', '*'" in server:
    errors.append('wildcard CORS still present')
if '/api/history-usage-fast' not in server:
    errors.append('fast history endpoint missing')
if 'GET save disabled for security' not in server:
    errors.append('GET save security block missing')
if 'cpu_ram_combined_percent' not in app or 'ram_gpu_usage_combined_percent' not in app:
    errors.append('combined notification metrics missing from app')
if 'rf3-machine-search' not in app:
    errors.append('client selector search missing')
if 'rf3Editing' not in app:
    errors.append('typing refresh guard missing')
if errors:
    print('STATIC TEST FAILED')
    for e in errors:
        print('-', e)
    sys.exit(1)
print('STATIC SECURITY LOGIC TEST OK')
