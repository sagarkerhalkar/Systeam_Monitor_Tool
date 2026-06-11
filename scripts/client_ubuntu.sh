#!/usr/bin/env bash
# Sagar Kerhalkar System Monitor Tool - Ubuntu/Linux Client
# Robust Python-backed collector. Sends heartbeat to SERVER_URL.
set -uo pipefail
SERVER_URL="${SERVER_URL:-http://127.0.0.1:2278}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-5}"
ROOT="${ROOT:-/var/lib/commercial-monitor-pro}"
RUN_ONCE="${RUN_ONCE:-0}"
mkdir -p "$ROOT"
export SERVER_URL INTERVAL_SECONDS ROOT RUN_ONCE

while true; do
python3 - <<'PYAGENT'
import os, sys, json, time, socket, platform, subprocess, re, datetime, urllib.request, urllib.error, traceback, pathlib
from pathlib import Path

SERVER_URL = os.environ.get('SERVER_URL','http://127.0.0.1:2278').rstrip('/')
INTERVAL_SECONDS = int(float(os.environ.get('INTERVAL_SECONDS','5') or 5))
ROOT = Path(os.environ.get('ROOT','/var/lib/commercial-monitor-pro'))
ROOT.mkdir(parents=True, exist_ok=True)
STATE_PATH = ROOT / 'state_ubuntu.json'
INV_PATH = ROOT / 'inventory_state.json'
ISP_PATH = ROOT / 'isp_state.json'
STATUS_PATH = ROOT / 'client_status.json'
ERROR_LOG = ROOT / 'client_error.log'
MESSAGE_LOG = ROOT / 'server_messages.log'

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def log(msg):
    try:
        with ERROR_LOG.open('a', encoding='utf-8') as f:
            f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass

def read_text(path, default=''):
    try:
        return Path(path).read_text(errors='ignore').strip()
    except Exception:
        return default

def run(cmd, timeout=8):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=timeout)
    except Exception:
        return ''

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default

def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def clean(v):
    return str(v or '').strip()

def get_os():
    pretty = ''
    try:
        for line in Path('/etc/os-release').read_text(errors='ignore').splitlines():
            if line.startswith('PRETTY_NAME='):
                pretty = line.split('=',1)[1].strip().strip('"')
                break
    except Exception:
        pass
    return {'name': pretty or platform.platform(), 'version': platform.release(), 'architecture': platform.machine()}

def get_identity():
    return {
        'hostname': socket.gethostname(),
        'motherboard_serial': read_text('/sys/class/dmi/id/board_serial'),
        'system_uuid': read_text('/sys/class/dmi/id/product_uuid'),
        'bios_serial': read_text('/sys/class/dmi/id/product_serial'),
        'manufacturer': read_text('/sys/class/dmi/id/sys_vendor'),
        'model': read_text('/sys/class/dmi/id/product_name')
    }

def read_cpu_times():
    parts = read_text('/proc/stat').splitlines()[0].split()[1:]
    vals = [int(float(x)) for x in parts[:8]]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    total = sum(vals)
    return idle, total

def get_cpu_percent():
    try:
        i1, t1 = read_cpu_times(); time.sleep(1); i2, t2 = read_cpu_times()
        dt = t2 - t1; di = i2 - i1
        return round(100.0 * (dt - di) / dt, 2) if dt > 0 else 0.0
    except Exception:
        return 0.0

def get_cpu_temp():
    candidates = list(Path('/sys/class/thermal').glob('thermal_zone*/temp')) + list(Path('/sys/class/hwmon').glob('hwmon*/temp*_input'))
    for p in candidates:
        try:
            v = float(p.read_text().strip()) / 1000.0
            if 0 < v < 130:
                return round(v, 1)
        except Exception:
            pass
    out = run(['sensors'], timeout=4)
    for m in re.finditer(r'(Package id 0|Tctl|CPU).*?\+([0-9.]+)°?C', out, flags=re.I):
        try: return round(float(m.group(2)), 1)
        except Exception: pass
    return None

def get_cpu():
    txt = read_text('/proc/cpuinfo')
    name = ''
    mhz = None
    for line in txt.splitlines():
        if not name and line.lower().startswith('model name'):
            name = line.split(':',1)[1].strip()
        if mhz is None and line.lower().startswith('cpu mhz'):
            try: mhz = round(float(line.split(':',1)[1].strip()), 1)
            except Exception: pass
    threads = len(re.findall(r'^processor\s*:', txt, flags=re.M)) or (os.cpu_count() or 0)
    core_ids = set(re.findall(r'^core id\s*:\s*(\S+)', txt, flags=re.M))
    cores = len(core_ids) if core_ids else threads
    return {'name': name or platform.processor(), 'cores': cores, 'threads': threads, 'current_mhz': mhz, 'max_mhz': None, 'usage_percent': get_cpu_percent(), 'temperature_c': get_cpu_temp()}

def get_memory():
    vals = {}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            k, v = line.split(':',1)
            vals[k] = float(v.strip().split()[0]) * 1024
    except Exception:
        pass
    total = vals.get('MemTotal', 0.0)
    avail = vals.get('MemAvailable', vals.get('MemFree', 0.0))
    used = max(0.0, total - avail)
    return {'total_gb': round(total/1024**3, 2), 'used_gb': round(used/1024**3, 2), 'free_gb': round(avail/1024**3, 2), 'used_percent': round((used/total)*100, 2) if total else 0.0}

def get_disks():
    out = run(['df','-P','-B1'], timeout=8)
    rows = []
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) < 6: continue
        dev, size, used, avail, pct, mount = p[0], p[1], p[2], p[3], p[4], p[5]
        if mount.startswith(('/snap','/run','/dev')) and mount not in ('/','/home'): continue
        try:
            total = float(size); usedb = float(used); free = float(avail)
            rows.append({'device': dev, 'mount': mount, 'type': '', 'total_gb': round(total/1024**3,2), 'used_gb': round(usedb/1024**3,2), 'free_gb': round(free/1024**3,2), 'used_percent': float(pct.rstrip('%'))})
        except Exception:
            pass
    return rows

def get_gpus():
    out = []
    smi = run(['nvidia-smi','--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'], timeout=8)
    if smi.strip():
        for line in smi.splitlines():
            p = [x.strip() for x in line.split(',')]
            if len(p) >= 5:
                def f(x):
                    try: return float(x)
                    except Exception: return None
                out.append({'name':p[0], 'memory_total_mb':f(p[1]), 'memory_used_mb':f(p[2]), 'usage_percent':f(p[3]), 'temperature_c':f(p[4]), 'source':'nvidia-smi'})
        return out
    lspci = run(['lspci'], timeout=6)
    for line in lspci.splitlines():
        if re.search(r'vga|3d|display', line, flags=re.I):
            out.append({'name': line.strip(), 'memory_total_mb': None, 'usage_percent': None, 'temperature_c': None, 'source':'lspci'})
    return out

def get_public_internet():
    cache = load_json(ISP_PATH, {})
    try:
        ts = datetime.datetime.fromisoformat(str(cache.get('checked_at','')).replace('Z','+00:00'))
        if (datetime.datetime.now(datetime.timezone.utc)-ts).total_seconds() < 1800 and (cache.get('public_ip') or cache.get('isp')):
            return cache
    except Exception:
        pass
    errors = []
    targets = [('ipinfo','https://ipinfo.io/json'), ('ip-api','http://ip-api.com/json/?fields=status,query,isp,org,as,country,city'), ('ipify','https://api.ipify.org?format=json')]
    for source, url in targets:
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'SagarMonitor-Ubuntu/6.2'})
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.loads(r.read().decode('utf-8', errors='replace'))
            if source == 'ipinfo':
                obj = {'public_ip':d.get('ip',''), 'isp':d.get('org',''), 'org':d.get('org',''), 'as':d.get('org',''), 'country':d.get('country',''), 'city':d.get('city',''), 'checked_at':now_iso(), 'source':'ipinfo', 'ok':True}
            elif source == 'ip-api':
                obj = {'public_ip':d.get('query',''), 'isp':d.get('isp') or d.get('org') or d.get('as') or '', 'org':d.get('org',''), 'as':d.get('as',''), 'country':d.get('country',''), 'city':d.get('city',''), 'checked_at':now_iso(), 'source':'ip-api', 'ok':True}
            else:
                obj = {'public_ip':d.get('ip',''), 'isp':'', 'org':'', 'as':'', 'country':'', 'city':'', 'checked_at':now_iso(), 'source':'ipify', 'ok':True}
            save_json(ISP_PATH, obj)
            return obj
        except Exception as e:
            errors.append(f'{source}: {e}')
    obj = cache if cache else {'public_ip':'','isp':'','org':'','as':'','country':'','city':'','checked_at':now_iso(),'source':'unavailable','ok':False,'errors':errors[-3:]}
    save_json(ISP_PATH, obj)
    return obj

def get_network():
    adapters = []
    rx_total = tx_total = 0
    for name in sorted(os.listdir('/sys/class/net') if Path('/sys/class/net').exists() else []):
        if name == 'lo': continue
        base = Path('/sys/class/net') / name
        mac = read_text(base/'address')
        status = read_text(base/'operstate')
        try: rx = int(read_text(base/'statistics/rx_bytes','0') or 0)
        except Exception: rx = 0
        try: tx = int(read_text(base/'statistics/tx_bytes','0') or 0)
        except Exception: tx = 0
        rx_total += rx; tx_total += tx
        ips = re.findall(r'inet (\d+\.\d+\.\d+\.\d+)', run(['ip','-4','addr','show',name], timeout=4))
        low = name.lower()
        adapters.append({'name':name, 'description':name, 'status':status, 'mac':mac, 'ips':ips, 'is_virtual':bool(re.search(r'veth|docker|br-|virbr|vmnet|vbox|tun|tap',low)), 'is_vpn':bool(re.search(r'tun|tap|wg|vpn|ppp|tailscale|zt',low)), 'rx_bytes':rx, 'tx_bytes':tx})
    state = load_json(STATE_PATH, {})
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    prev_date = state.get('date')
    prev_rx = int(state.get('rx_total_bytes', rx_total) or rx_total)
    prev_tx = int(state.get('tx_total_bytes', tx_total) or tx_total)
    prev_ts = float(state.get('ts', time.time()) or time.time())
    today_rx = int(state.get('today_rx_bytes', 0) or 0)
    today_tx = int(state.get('today_tx_bytes', 0) or 0)
    now = time.time()
    if prev_date != today:
        prev_rx, prev_tx, today_rx, today_tx, prev_ts = rx_total, tx_total, 0, 0, now
    elapsed = max(1.0, now - prev_ts)
    drx = max(0, rx_total - prev_rx); dtx = max(0, tx_total - prev_tx)
    today_rx += drx; today_tx += dtx
    cur_down = round((drx*8/1_000_000)/elapsed, 2)
    cur_up = round((dtx*8/1_000_000)/elapsed, 2)
    save_json(STATE_PATH, {'date':today, 'rx_total_bytes':rx_total, 'tx_total_bytes':tx_total, 'today_rx_bytes':today_rx, 'today_tx_bytes':today_tx, 'ts':now})
    ips = []
    for a in adapters:
        ips.extend(a.get('ips') or [])
    primary = ips[0] if ips else ''
    vpn_active = any(a.get('is_vpn') and a.get('status') == 'up' for a in adapters)
    public = get_public_internet()
    traffic = {'date': today, 'current_download_mbps': cur_down, 'current_upload_mbps': cur_up, 'today_download_gb': round(today_rx/1024**3,2), 'today_upload_gb': round(today_tx/1024**3,2), 'rx_total_bytes': rx_total, 'tx_total_bytes': tx_total, 'sample_seconds': round(elapsed,1), 'note':'Current adapter traffic since previous heartbeat; day totals reset at local midnight.'}
    return {'primary_ip': primary, 'adapters': adapters, 'vpn': {'active': vpn_active, 'detected_adapters':[a['name'] for a in adapters if a.get('is_vpn')]}, 'public_internet': public, 'internet_speed': {'download_mbps':cur_down, 'upload_mbps':cur_up, 'source':'live_adapter_delta', 'note':'Current client traffic usage, not forced bandwidth capacity test'}, 'traffic': traffic, 'current_download_mbps':cur_down, 'current_upload_mbps':cur_up, 'today_download_gb':traffic['today_download_gb'], 'today_upload_gb':traffic['today_upload_gb'], 'traffic_date':today}

def get_software():
    rows = []
    out = run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${Maintainer}\n'], timeout=20)
    for line in out.splitlines()[:5000]:
        p = line.split('\t')
        if p and p[0]:
            rows.append({'name':p[0], 'version':p[1] if len(p)>1 else '', 'publisher':p[2] if len(p)>2 else '', 'install_date':''})
    return rows

def classify_usb(name):
    l = (name or '').lower()
    if 'keyboard' in l: return 'Keyboard'
    if 'mouse' in l: return 'Mouse'
    if any(x in l for x in ['headset','audio','microphone','speaker','sound']): return 'Audio'
    if any(x in l for x in ['camera','webcam','video']): return 'Camera'
    if any(x in l for x in ['flash','storage','disk','mass storage','card reader']): return 'Storage'
    if 'bluetooth' in l: return 'Bluetooth'
    if 'hub' in l: return 'Hub'
    if any(x in l for x in ['printer','scanner']): return 'Printer/Scanner'
    if any(x in l for x in ['ethernet','network','wifi','802.11','wireless']): return 'Network'
    return 'Peripheral'

def get_usb():
    rows = []
    out = run(['lsusb'], timeout=8)
    for line in out.splitlines():
        m = re.search(r'ID ([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)', line)
        if m:
            name = m.group(3).strip() or line.strip()
            rows.append({'name':name, 'type':classify_usb(name), 'class':'USB', 'vid':m.group(1), 'pid':m.group(2), 'device_id':line.strip()})
    if rows:
        return rows
    # Fallback when usbutils/lsusb is missing.
    for d in Path('/sys/bus/usb/devices').glob('*'):
        vid = read_text(d/'idVendor'); pid = read_text(d/'idProduct')
        if not vid or not pid: continue
        product = read_text(d/'product'); maker = read_text(d/'manufacturer')
        name = (maker + ' ' + product).strip() or f'USB {vid}:{pid}'
        rows.append({'name':name, 'type':classify_usb(name), 'class':'USB', 'vid':vid, 'pid':pid, 'device_id':str(d.name)})
    return rows

def norm(x): return str(x or '').strip()
def uniq(xs): return sorted(set(x for x in xs if x))

def add_changes(payload):
    sw = [norm(a.get('name'))+'|'+norm(a.get('version')) for a in payload.get('software',{}).get('installed',[]) if isinstance(a,dict)]
    usb = [norm(u.get('type'))+'|'+norm(u.get('name'))+'|'+norm(u.get('vid'))+':'+norm(u.get('pid'))+'|'+norm(u.get('device_id')) for u in payload.get('usb',{}).get('devices',[]) if isinstance(u,dict)]
    cpu = payload.get('hardware',{}).get('cpu',{}) or {}; mem = payload.get('hardware',{}).get('memory',{}) or {}
    hw = ['cpu='+norm(cpu.get('name')), 'cores='+norm(cpu.get('cores')), 'threads='+norm(cpu.get('threads')), 'ram_gb='+norm(mem.get('total_gb'))]
    for g in payload.get('hardware',{}).get('gpus',[]) or []:
        if isinstance(g,dict): hw.append('gpu='+norm(g.get('name'))+'|'+norm(g.get('memory_total_mb')))
    for d in payload.get('storage',{}).get('disks',[]) or []:
        if isinstance(d,dict): hw.append('disk='+norm(d.get('device') or d.get('name') or d.get('mount'))+'|'+norm(d.get('total_gb'))+'|'+norm(d.get('type')))
    ips = []
    for a in payload.get('network',{}).get('adapters',[]) or []:
        if isinstance(a,dict): ips += [norm(x) for x in a.get('ips',[]) or []]
    snap = {'software':uniq(sw), 'usb':uniq(usb), 'hardware':uniq(hw), 'ips':uniq(ips), 'vpn_active':bool(payload.get('network',{}).get('vpn',{}).get('active'))}
    old = load_json(INV_PATH, None)
    changes = []
    def event(t,title,msg,add,rem):
        changes.append({'type':t, 'title':title, 'message':msg, 'added':add[:25], 'removed':rem[:25], 'created_at':now_iso()})
    if old:
        for key,title,msgname in [('usb','USB/peripheral changed','USB/peripheral'),('hardware','Hardware changed','Hardware inventory'),('software','Software changed','Software/app list'),('ips','IP address changed','IP address list')]:
            add = sorted(set(snap.get(key,[]))-set(old.get(key,[]))); rem = sorted(set(old.get(key,[]))-set(snap.get(key,[])))
            if add or rem:
                ctype = 'ip' if key == 'ips' else key
                msg = f'{msgname} changed: +{len(add)} / -{len(rem)}'
                event(ctype, title, msg, add, rem)
        if bool(old.get('vpn_active')) != bool(snap.get('vpn_active')):
            event('vpn','VPN status changed',f"VPN is now {snap.get('vpn_active')}",[str(snap.get('vpn_active'))],[str(old.get('vpn_active'))])
    save_json(INV_PATH, snap)
    payload['changes'] = changes
    return payload

def collect_payload():
    return add_changes({
        'schema_version':'pro-v3-linux',
        'timestamp':now_iso(),
        'agent':{'name':'SagarMonitor-Ubuntu','version':'8.3-realtime-popup','interval_seconds':INTERVAL_SECONDS,'mode':'realtime_inventory_changes'},
        'identity':get_identity(),
        'hostname':socket.gethostname(),
        'os':get_os(),
        'hardware':{'cpu':get_cpu(), 'memory':get_memory(), 'gpus':get_gpus()},
        'storage':{'disks':get_disks()},
        'network':get_network(),
        'software':{'installed':get_software()},
        'usb':{'devices':get_usb()}
    })

def send_payload(payload):
    raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(SERVER_URL + '/api/heartbeat', data=raw, headers={'Content-Type':'application/json','User-Agent':'SagarMonitor-Ubuntu/6.2'}, method='POST')
    with urllib.request.urlopen(req, timeout=35) as r:
        resp = json.loads(r.read().decode('utf-8', errors='replace') or '{}')
    return resp, len(raw)

def handle_messages(resp):
    count = 0
    for m in resp.get('pending_messages') or []:
        title = m.get('title','Admin Message') or 'Admin Message'
        msg = m.get('message','') or ''
        pri = m.get('priority','normal') or 'normal'
        line = f"{datetime.datetime.now().isoformat()} [{pri}] {title} - {msg}"
        try:
            with MESSAGE_LOG.open('a', encoding='utf-8') as f: f.write(line+'\n')
        except Exception: pass
        # Always leave a visible local file for proof of delivery.
        try:
            pathlib.Path('/tmp/sagar_monitor_last_message.txt').write_text(line+'\n', encoding='utf-8')
        except Exception: pass
        # Terminal broadcast if users have terminals open.
        try:
            subprocess.run(['wall', line[:350]], timeout=3, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except Exception: pass
        # Best-effort GUI notification for active desktop users.
        try:
            users = subprocess.check_output(['bash','-lc', "who | awk '{print $1}' | sort -u"], timeout=3, text=True).split()
            for u in users:
                uid = subprocess.check_output(['id','-u',u], timeout=2, text=True).strip()
                env = os.environ.copy()
                env['DISPLAY'] = env.get('DISPLAY') or ':0'
                env['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path=/run/user/{uid}/bus'
                full = f'{title}: {msg}'[:900]
                # Normal desktop notification for 2 minutes
                subprocess.run(['sudo','-u',u,'DISPLAY='+env['DISPLAY'],'DBUS_SESSION_BUS_ADDRESS='+env['DBUS_SESSION_BUS_ADDRESS'],'notify-send','-t','120000','Sagar Monitor', full], timeout=4, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # If zenity is installed, show a closeable popup for non-technical users.
                if subprocess.run(['bash','-lc','command -v zenity >/dev/null 2>&1']).returncode == 0:
                    subprocess.Popen(['sudo','-u',u,'DISPLAY='+env['DISPLAY'],'DBUS_SESSION_BUS_ADDRESS='+env['DBUS_SESSION_BUS_ADDRESS'],'zenity','--info','--timeout=120','--width=420','--title','Sagar Monitor Admin Message','--text',full], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception: pass
        count += 1
    return count

try:
    payload = collect_payload()
    resp, payload_bytes = send_payload(payload)
    msg_count = handle_messages(resp)
    status = {'ok': True, 'message':'Heartbeat sent successfully', 'server_url':SERVER_URL, 'computer':socket.gethostname(), 'time':now_iso(), 'extra':{'response':resp, 'payload_bytes':payload_bytes, 'hostname':socket.gethostname(), 'ram_total_gb':payload.get('hardware',{}).get('memory',{}).get('total_gb'), 'usb_count':len(payload.get('usb',{}).get('devices',[]) or []), 'software_count':len(payload.get('software',{}).get('installed',[]) or []), 'isp':payload.get('network',{}).get('public_internet',{}).get('isp'), 'messages_received':msg_count, 'message_log':str(MESSAGE_LOG)}}
    save_json(STATUS_PATH, status)
    print(json.dumps(status, indent=2))
except Exception as e:
    status = {'ok':False, 'message':str(e), 'server_url':SERVER_URL, 'computer':socket.gethostname(), 'time':now_iso(), 'extra':{'error_type':type(e).__name__}}
    save_json(STATUS_PATH, status)
    log(traceback.format_exc())
    print(json.dumps(status, indent=2), file=sys.stderr)
    sys.exit(2)
PYAGENT
  rc=$?
  if [ "${RUN_ONCE}" = "1" ]; then exit "$rc"; fi
  sleep "$INTERVAL_SECONDS"
done
