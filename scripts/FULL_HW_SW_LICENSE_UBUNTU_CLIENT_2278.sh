#!/usr/bin/env bash
set -euo pipefail
SERVER_URL="${SERVER_URL:-${1:-http://156.156.40.51:2278}}"
SAMPLES="${2:-${SAMPLES:-5}}"
INTERVAL_SECONDS="${3:-${INTERVAL_SECONDS:-5}}"
OUT_DIR="/var/lib/commercial-monitor-pro"
mkdir -p "$OUT_DIR"
PAYLOAD_PATH="$OUT_DIR/full_hw_sw_license_payload_latest.json"
STATUS_PATH="$OUT_DIR/full_hw_sw_license_client_status.json"
MSG_LOG="$OUT_DIR/server_messages.log"
ERR_LOG="$OUT_DIR/full_hw_sw_license_client_error.log"

python3 - "$SERVER_URL" "$SAMPLES" "$INTERVAL_SECONDS" "$PAYLOAD_PATH" "$STATUS_PATH" "$MSG_LOG" "$ERR_LOG" <<'PY'
import json, os, sys, time, socket, subprocess, urllib.request, platform, re
from datetime import datetime, timezone
server_url, samples, interval, payload_path, status_path, msg_log, err_log = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7]

def sh(cmd, timeout=10):
    try: return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=timeout, text=True, errors='replace')
    except Exception: return ''
def status(obj):
    os.makedirs(os.path.dirname(status_path), exist_ok=True)
    open(status_path,'w',encoding='utf-8').write(json.dumps(obj, indent=2, ensure_ascii=False))
def log(msg):
    try: open(err_log,'a',encoding='utf-8').write(datetime.now().isoformat()+" "+str(msg)+"\n")
    except Exception: pass
def read(path):
    try: return open(path,encoding='utf-8',errors='replace').read()
    except Exception: return ''
def fnum(x):
    try: return float(str(x).strip())
    except Exception: return None

def cpu_usage():
    def snap():
        vals=list(map(int, read('/proc/stat').splitlines()[0].split()[1:8])); idle=vals[3]+vals[4]; total=sum(vals); return idle,total
    try:
        i1,t1=snap(); time.sleep(1); i2,t2=snap(); return round((1-((i2-i1)/max(1,(t2-t1))))*100,2)
    except Exception: return None

def cpu_temp():
    temps=[]
    sens=sh('sensors 2>/dev/null', timeout=5)
    for m in re.finditer(r'(?:Package id 0|Tctl|Tdie|Core\s*\d+|CPU)[^\n+]*\+?([0-9]+(?:\.[0-9]+)?)°?C', sens, re.I):
        v=fnum(m.group(1));
        if v and 0<v<125: temps.append(v)
    for root, dirs, files in os.walk('/sys/class/thermal'):
        if 'temp' in files:
            try:
                v=int(read(os.path.join(root,'temp')).strip())/1000.0
                if 0 < v < 125: temps.append(v)
            except Exception: pass
    return {'value': round(sum(temps)/len(temps),2) if temps else None, 'source': 'sensors+sysfs' if temps else 'not_available', 'reason': '' if temps else 'CPU temperature sensor not exposed or lm-sensors not configured'}

def meminfo():
    d={}
    for line in read('/proc/meminfo').splitlines():
        if ':' in line:
            k,v=line.split(':',1); nums=re.findall(r'\d+',v); d[k]=int(nums[0])*1024 if nums else 0
    total=d.get('MemTotal',0); avail=d.get('MemAvailable',d.get('MemFree',0)); used=total-avail
    return {'total_gb':round(total/1024**3,2),'used_gb':round(used/1024**3,2),'free_gb':round(avail/1024**3,2),'used_percent':round(used*100/max(1,total),2),'temperature_c':None,'temperature_source':'not_available','temperature_reason':'RAM temperature is normally not exposed by Linux without special hardware/sensor support','source':'/proc/meminfo'}

def smart_for(dev):
    out={'temperature_c':None,'health':'N/A','wear_percent':None,'source':'not_available','reason':'smartctl/nvme-cli not installed or permission/device unsupported'}
    if sh('command -v smartctl'):
        txt=sh(f'smartctl -a {dev} 2>/dev/null', timeout=10)
        if txt:
            out['source']='smartctl'
            if re.search(r'SMART overall-health self-assessment test result:\s*(\w+)', txt, re.I): out['health']=re.search(r'SMART overall-health self-assessment test result:\s*(\w+)', txt, re.I).group(1)
            elif re.search(r'NVMe Status:\s*([^\n]+)', txt, re.I): out['health']=re.search(r'NVMe Status:\s*([^\n]+)', txt, re.I).group(1).strip()
            for pat in [r'Temperature_Celsius\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)', r'Current Drive Temperature:\s*(\d+)', r'Temperature:\s*(\d+)\s+Celsius']:
                m=re.search(pat, txt, re.I)
                if m: out['temperature_c']=fnum(m.group(1)); break
            m=re.search(r'Percentage Used:\s*(\d+)%', txt, re.I)
            if m: out['wear_percent']=fnum(m.group(1))
            out['reason']='' if out['temperature_c'] is not None else 'SMART data available but temperature not exposed for this disk'
    if out['temperature_c'] is None and sh('command -v nvme') and os.path.basename(dev).startswith('nvme'):
        txt=sh(f'nvme smart-log {dev} 2>/dev/null', timeout=10)
        if txt:
            out['source']='nvme-cli'
            m=re.search(r'temperature\s*:\s*(\d+)\s+C', txt, re.I)
            if m: out['temperature_c']=fnum(m.group(1)); out['reason']=''
            m=re.search(r'percentage_used\s*:\s*(\d+)%', txt, re.I)
            if m: out['wear_percent']=fnum(m.group(1))
            out['health']='OK'
    return out

def disk_info():
    disks=[]
    out=sh('df -P -B1 -x tmpfs -x devtmpfs -x squashfs')
    for line in out.splitlines()[1:]:
        p=line.split()
        if len(p)>=6:
            total=int(p[1]); used=int(p[2]); free=int(p[3]); mount=p[5]
            disks.append({'name':p[0],'mount':mount,'total_gb':round(total/1024**3,2),'used_gb':round(used/1024**3,2),'free_gb':round(free/1024**3,2),'used_percent':round(used*100/max(1,total),2),'is_root':mount=='/','type':'filesystem','source':'df'})
    phys=[]
    try:
        ls=json.loads(sh('lsblk -J -b -o NAME,MODEL,SERIAL,SIZE,TYPE,ROTA,MOUNTPOINT,FSTYPE', timeout=8) or '{}')
        def walk(items):
            for x in items or []:
                if x.get('type')=='disk':
                    dev='/dev/'+x.get('name','')
                    sm=smart_for(dev)
                    phys.append({'name':x.get('name',''),'device':dev,'model':x.get('model') or '', 'serial_number':x.get('serial') or '', 'size_gb':round((x.get('size') or 0)/1024**3,2), 'media_type':'HDD' if x.get('rota') else 'SSD/NVMe', 'temperature_c':sm.get('temperature_c'), 'health':sm.get('health'), 'wear_percent':sm.get('wear_percent'), 'sensor_source':sm.get('source'), 'sensor_reason':sm.get('reason'), 'source':'lsblk+smart'} )
                walk(x.get('children'))
        walk(ls.get('blockdevices'))
    except Exception as e: log(e)
    return {'disks':disks,'physical_disks':phys,'source':'df+lsblk+smartctl/nvme'}

def gpu_info():
    gpus=[]
    if sh('command -v nvidia-smi'):
        out=sh("nvidia-smi --query-gpu=name,utilization.gpu,memory.total,memory.used,memory.free,temperature.gpu,driver_version --format=csv,noheader,nounits", timeout=8)
        for line in out.splitlines():
            p=[x.strip() for x in line.split(',')]
            if len(p)>=6:
                gpus.append({'name':p[0],'usage_percent':fnum(p[1]),'memory_total_mb':fnum(p[2]),'memory_used_mb':fnum(p[3]),'memory_free_mb':fnum(p[4]),'temperature_c':fnum(p[5]),'driver_version':p[6] if len(p)>6 else '', 'source':'nvidia-smi','confidence':'exact_vendor_tool'})
    lspci=sh('lspci 2>/dev/null | egrep -i "vga|3d|display"')
    for line in lspci.splitlines():
        name=line.split(': ',1)[-1]
        if name and not any(name in (g.get('name') or '') or (g.get('name') or '') in name for g in gpus):
            gpus.append({'name':name,'usage_percent':None,'memory_total_mb':None,'memory_used_mb':None,'temperature_c':None,'source':'lspci','confidence':'device_name_only','missing_reason':'Usage/temp requires vendor tool such as nvidia-smi or driver telemetry'})
    return gpus

def usb_info():
    devices=[]
    out=sh('lsusb 2>/dev/null')
    for line in out.splitlines():
        m=re.search(r'ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)$', line)
        devices.append({'name':m.group(3).strip() if m else line, 'display_name':m.group(3).strip() if m else line, 'type':'USB Peripheral', 'class':'USB', 'vid':m.group(1) if m else '', 'pid':m.group(2) if m else '', 'device_id':line, 'source':'lsusb'})
    return {'count':len(devices),'devices':devices}

def software_info():
    apps=[]
    out=sh("dpkg-query -W -f='${binary:Package}\t${Version}\t${Maintainer}\n' 2>/dev/null", timeout=20)
    for line in out.splitlines():
        p=line.split('\t')
        if len(p)>=2: apps.append({'name':p[0],'version':p[1],'publisher':p[2] if len(p)>2 else '', 'source':'dpkg'})
    snap=sh('snap list 2>/dev/null', timeout=8)
    for line in snap.splitlines()[1:]:
        p=line.split()
        if len(p)>=2: apps.append({'name':p[0],'version':p[1],'publisher':'snap','source':'snap'})
    flat=sh('flatpak list --app --columns=application,version 2>/dev/null', timeout=8)
    for line in flat.splitlines():
        p=line.split('\t')
        if p and p[0]: apps.append({'name':p[0],'version':p[1] if len(p)>1 else '', 'publisher':'flatpak','source':'flatpak'})
    return {'installed':apps,'count':len(apps),'source':'dpkg+snap+flatpak'}

def traffic_sample(sec=1):
    def snap():
        rx=tx=0
        for iface in os.listdir('/sys/class/net') if os.path.isdir('/sys/class/net') else []:
            if iface=='lo': continue
            try:
                rx+=int(read(f'/sys/class/net/{iface}/statistics/rx_bytes').strip() or 0); tx+=int(read(f'/sys/class/net/{iface}/statistics/tx_bytes').strip() or 0)
            except Exception: pass
        return rx,tx
    try:
        a=snap(); time.sleep(sec); b=snap(); return {'current_download_mbps':round(((b[0]-a[0])*8/1000000)/sec,2),'current_upload_mbps':round(((b[1]-a[1])*8/1000000)/sec,2),'today_download_gb':0,'today_upload_gb':0,'source':'/sys/class/net sample'}
    except Exception: return {'current_download_mbps':0,'current_upload_mbps':0,'today_download_gb':0,'today_upload_gb':0,'source':'traffic_sample_failed'}

def network_info():
    adapters=[]; primary=''
    for iface in os.listdir('/sys/class/net') if os.path.isdir('/sys/class/net') else []:
        if iface=='lo': continue
        mac=read(f'/sys/class/net/{iface}/address').strip(); ips=[]
        out=sh(f"ip -o -4 addr show dev {iface} 2>/dev/null")
        for m in re.finditer(r'inet\s+([0-9.]+)', out): ips.append(m.group(1))
        if not primary and ips: primary=ips[0]
        adapters.append({'name':iface,'description':iface,'mac':mac,'ips':ips,'is_virtual': bool(re.search(r'veth|docker|br-|virbr|tun|tap|wg|tailscale', iface, re.I))})
    pub={'public_ip':'','isp':'','org':'','country':'','city':'','source':'not_checked'}
    try:
        info=json.loads(urllib.request.urlopen('https://ipinfo.io/json',timeout=5).read().decode()); pub.update({'public_ip':info.get('ip',''), 'isp':info.get('org',''), 'org':info.get('org',''), 'country':info.get('country',''), 'city':info.get('city',''), 'source':'ipinfo'})
    except Exception:
        try: pub['public_ip']=urllib.request.urlopen('https://api.ipify.org',timeout=4).read().decode().strip(); pub['source']='api.ipify'
        except Exception: pass
    links=sh('ip link 2>/dev/null')
    vpn_active=bool(re.search(r'tun|tap|wg|tailscale|zerotier', links, re.I))
    procs=sh("ps ax -o comm= 2>/dev/null | egrep -i 'openvpn|wireguard|wg-quick|tailscale|zerotier|forti|anyconnect|vpn' | head -50")
    return {'primary_ip':primary,'adapters':adapters,'public_internet':pub,'vpn':{'active':vpn_active,'installed_count':len([x for x in procs.splitlines() if x.strip()]),'installed':[{'name':x.strip(),'source':'process'} for x in procs.splitlines() if x.strip()]},'traffic':traffic_sample(1)}

def build_payload():
    cpu_model=''
    for line in read('/proc/cpuinfo').splitlines():
        if 'model name' in line: cpu_model=line.split(':',1)[1].strip(); break
    sw=software_info(); commercial=[a for a in sw['installed'] if re.search(r'microsoft|adobe|teamviewer|anydesk|zoom|autodesk|bricscad|matlab|oracle|vmware', a.get('name',''), re.I)][:200]
    ct=cpu_temp()
    return {
        'hostname': socket.gethostname(),
        'identity': {'hostname':socket.gethostname(),'bios_serial':sh('cat /sys/class/dmi/id/product_serial 2>/dev/null').strip(),'motherboard_serial':sh('cat /sys/class/dmi/id/board_serial 2>/dev/null').strip(),'system_uuid':sh('cat /sys/class/dmi/id/product_uuid 2>/dev/null').strip(),'vendor':sh('cat /sys/class/dmi/id/sys_vendor 2>/dev/null').strip(),'model':sh('cat /sys/class/dmi/id/product_name 2>/dev/null').strip()},
        'os': {'name': platform.platform(), 'version': platform.release(), 'architecture': platform.machine()},
        'hardware': {'cpu': {'name':cpu_model,'manufacturer':'','cores':os.cpu_count(),'threads':os.cpu_count(),'usage_percent':cpu_usage(),'temperature_c':ct['value'],'temperature_source':ct['source'],'temperature_reason':ct['reason'],'source':'/proc+sensors'}, 'memory': meminfo(), 'gpus': gpu_info()},
        'storage': disk_info(), 'network': network_info(), 'usb': usb_info(), 'software': sw,
        'windows_license': {'not_applicable': True, 'source':'ubuntu'}, 'office_license': [], 'antivirus_products': [],
        'software_license_register': {'commercial_software_review':commercial, 'fields_supported':['software_name','version','publisher','assigned_user','license_type','seats','renewal_expiry','bill_invoice_po_no','proof_link','password_vault_reference','partial_key_or_reference','compliance_status'], 'note':'No plaintext full product keys or passwords are exported.'},
        'changes': [], 'collector': {'name':'Sagar Y8 Real Sensor Full HW SW License Collector','version':'20260627-y8-real-sensors','generated_at':datetime.now(timezone.utc).isoformat()}
    }

def post(payload):
    data=json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(server_url.rstrip('/')+'/api/heartbeat', data=data, headers={'Content-Type':'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(req, timeout=45).read().decode())

status({'ok':False,'stage':'starting','server_url':server_url,'time':datetime.now(timezone.utc).isoformat(),'collector':'Y8'})
for i in range(1, max(1,samples)+1):
    try:
        payload=build_payload(); open(payload_path,'w',encoding='utf-8').write(json.dumps(payload, ensure_ascii=False, indent=2))
        resp=post(payload)
        for m in resp.get('pending_messages') or []: open(msg_log,'a',encoding='utf-8').write(datetime.now().isoformat()+" "+json.dumps(m,ensure_ascii=False)+"\n")
        status({'ok':True,'stage':'posted','sample':i,'samples':samples,'machine_id':resp.get('machine_id'),'server_url':server_url,'payload':payload_path,'time':datetime.now(timezone.utc).isoformat(),'collector':'Y8'})
        print(f"Posted Y8 real sensor H/W + S/W + license payload sample {i}/{samples} to {server_url}/api/heartbeat")
    except Exception as e:
        log(e); status({'ok':False,'stage':'error','error':str(e),'server_url':server_url,'time':datetime.now(timezone.utc).isoformat(),'collector':'Y8'}); raise
    if i < samples: time.sleep(interval)
print('Payload saved:', payload_path)
print('Status saved:', status_path)
PY
