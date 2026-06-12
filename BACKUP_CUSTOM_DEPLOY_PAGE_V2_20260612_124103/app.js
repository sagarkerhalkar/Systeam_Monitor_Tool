const $ = (q) => document.querySelector(q);
const $$ = (q) => Array.from(document.querySelectorAll(q));

const state = {
  overview: null,
  machines: [],
  changes: [],
  rules: [],
  users: [],
  selected: localStorage.getItem('sagar_selected_machine') || '',
  page: 'dashboard',
  query: '',
  authenticated: false,
  username: '',
  role: 'viewer',
  autoRefresh: localStorage.getItem('sagar_auto_refresh') !== '0',
  pendingUpdate: false,
  lastRefresh: null
};

const quietPages = new Set(['machine360','network','hardware','software','usb','changes','history','deploy','settings','messages','notifications']);
const DASHBOARD_POLL_SECONDS = 5;
const OFFLINE_EXPECTED_SECONDS = 12;
const selectorIds = ['dashboardMachine','machineSelect','softwareMachine','usbMachine','historyMachine','messageMachine','changeMachine'];
const metrics = ['cpu_percent','ram_percent','ram_total_gb','disk_max_percent','cpu_temp_c','gpu_max_temp_c','gpu_max_usage','wan_download_mbps','wan_upload_mbps','offline_minutes','today_download_gb','today_upload_gb','software_count','usb_count','change_usb','change_hardware','change_software','change_ip','change_vpn'];

function esc(v){return String(v ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function fmt(n,suffix='',digits=1){if(n===null||n===undefined||n==='')return'N/A';const x=Number(n);if(Number.isNaN(x))return esc(n);return x.toFixed(digits).replace(/\.0$/,'')+suffix;}
function ago(iso){if(!iso)return'N/A';const t=new Date(iso).getTime();if(!t)return'N/A';const s=(Date.now()-t)/1000;if(s<60)return`${Math.max(0,Math.round(s))}s ago`;if(s<3600)return`${Math.round(s/60)}m ago`;if(s<86400)return`${Math.round(s/3600)}h ago`;return new Date(iso).toLocaleString();}
function host(m){return m?.hostname || String(m?.machine_id||'').replace(/^[A-Z_]+:/,'') || 'UNKNOWN';}
function payload(m){return m?.payload || {};}
function nested(o,path,def){try{return path.split('.').reduce((a,k)=>a&&a[k]!==undefined?a[k]:undefined,o) ?? def;}catch(e){return def;}}
function isAdmin(){return state.role === 'admin';}
function statusPill(m){return `<span class="pill ${m?.online?'online':'offline'}">${m?.online?'Online':'Offline'}</span>`;}
function attention(m){return Number(m?.cpu_percent||0)>=90 || Number(m?.ram_percent||0)>=90 || Number(m?.disk_max_percent||0)>=90;}
function queryString(obj){return Object.entries(obj).filter(([k,v])=>v!==undefined&&v!==null&&v!=='').map(([k,v])=>encodeURIComponent(k)+'='+encodeURIComponent(v)).join('&');}
function cleanText(v){return String(v??'').trim().replace(/\s+/g,' ');}
function shortId(id){id=String(id||''); if(!id)return''; return id.length>80?id.slice(0,80)+'…':id;}
function roleLabel(){return `${state.username||'user'} • ${state.role||'viewer'}`;}

async function api(url, opts={}){
  const r = await fetch(url, {credentials:'same-origin', headers:{'Content-Type':'application/json'}, ...opts});
  if(!r.ok){
    const text = await r.text();
    if(r.status===401 || text.includes('login_required')) showLogin('Login required.');
    throw new Error(text || r.statusText);
  }
  return r.json();
}

function showLogin(msg=''){
  $('#loginScreen')?.classList.remove('hidden');
  $('#appShell')?.classList.add('locked');
  if($('#loginError')) $('#loginError').textContent = msg;
}
function hideLogin(){
  $('#loginScreen')?.classList.add('hidden');
  $('#appShell')?.classList.remove('locked');
}
async function login(){
  try{
    const d = await api('/api/auth/login',{method:'POST', body:JSON.stringify({username:$('#adminUsername')?.value||'admin', password:$('#adminPassword')?.value||''})});
    if(d.ok){ state.authenticated=true; state.username=d.username||'admin'; state.role=d.role||'admin'; hideLogin(); applyRoleControls(); await refresh(true); await loadRules(); if(isAdmin()) await loadUsers(); }
  }catch(e){ showLogin('Wrong username/password or server error.'); }
}
async function logout(){try{await api('/api/auth/logout',{method:'POST',body:'{}'});}catch(e){} state.authenticated=false; state.role='viewer'; showLogin('Logged out.');}
async function checkAuth(){
  try{ const d=await api('/api/auth/status'); if(d.authenticated){state.authenticated=true; state.username=d.username||'admin'; state.role=d.role||'admin'; hideLogin(); applyRoleControls(); await refresh(true); await loadRules(); if(isAdmin()) await loadUsers();} else showLogin(); }
  catch(e){showLogin('Server not reachable.');}
}
function applyRoleControls(){
  if($('#roleBadge')) $('#roleBadge').textContent = roleLabel();
  $$('.admin-only,.download-only').forEach(el => { el.style.display = isAdmin() ? '' : 'none'; });
  $$('.viewer-note').forEach(el => { el.style.display = isAdmin() ? 'none' : ''; });
}

function setLiveButtons(){
  const txt = state.autoRefresh ? 'Live: On' : 'Live: Paused';
  if($('#autoRefreshBtn')) $('#autoRefreshBtn').textContent = txt;
  if($('#settingsAutoBtn')) $('#settingsAutoBtn').textContent = 'Live Refresh: ' + (state.autoRefresh?'On':'Paused');
}
function toggleAutoRefresh(){state.autoRefresh=!state.autoRefresh; localStorage.setItem('sagar_auto_refresh', state.autoRefresh?'1':'0'); setLiveButtons();}
function showBanner(show){ $('#newDataBanner')?.classList.toggle('hidden', !show); }

async function refresh(manual=false){
  try{
    const data = await api('/api/overview');
    state.overview = data; state.machines = data.machines || []; state.lastRefresh = new Date();
    $('#apiStatus')?.classList.add('ok'); if($('#statusText')) $('#statusText').textContent='Live'; if($('#lastRefreshText')) $('#lastRefreshText').textContent='Updated '+state.lastRefresh.toLocaleTimeString();
    if(!manual && quietPages.has(state.page)){ state.pendingUpdate=true; showBanner(true); return; }
    hydrateSelectors(); state.pendingUpdate=false; showBanner(false); renderAll(); applyRoleControls();
  }catch(e){ console.error(e); $('#apiStatus')?.classList.remove('ok'); if($('#statusText')) $('#statusText').textContent='Offline'; }
}

function machineLabel(m){return `${host(m)} • ${m.primary_ip||((m.all_ips||[])[0]||'No IP')}`;}
function selectedMachine(selectId){
  const v = $('#'+selectId)?.value || localStorage.getItem('sagar_'+selectId) || state.selected || '';
  return state.machines.find(m => m.machine_id === v) || state.machines[0] || null;
}
function hydrateSelectors(){
  selectorIds.forEach(id=>{
    const el=$('#'+id); if(!el) return;
    const keep = localStorage.getItem('sagar_'+id) || (id==='historyMachine'||id==='changeMachine' ? '' : state.selected);
    const first = (id==='historyMachine'||id==='changeMachine') ? '<option value="">All machines</option>' : '';
    el.innerHTML = first + state.machines.map(m=>`<option value="${esc(m.machine_id)}">${esc(machineLabel(m))}</option>`).join('');
    if(keep && state.machines.some(m=>m.machine_id===keep)) el.value=keep;
    else if(id!=='historyMachine' && id!=='changeMachine' && state.machines[0]) el.value=state.machines[0].machine_id;
  });
}
function onMachineSelect(id){
  const v=$('#'+id)?.value||'';
  localStorage.setItem('sagar_'+id,v);
  if(v){state.selected=v; localStorage.setItem('sagar_selected_machine',v);}
  renderAll(); if(state.page==='history') renderHistory(); if(state.page==='changes') renderChanges(false);
}

function parseRawObjectString(s){
  if(typeof s !== 'string') return s;
  const t=s.trim(); if(!t) return s;
  try{return JSON.parse(t);}catch(e){}
  try{return JSON.parse(t.replace(/([{,]\s*)'([^']+)'\s*:/g,'$1"$2":').replace(/:\s*'([^']*)'/g,':"$1"'));}catch(e){}
  if(!/name|display_name|device_id|vid|pid/i.test(t)) return s;
  const body=t.replace(/^\[/,'').replace(/\]$/,'');
  const chunks=body.split(/}\s*,\s*{/).map((p,i,a)=>(i?'{':'')+p+(i<a.length-1?'}':''));
  const out=[];
  const keys=['name','display_name','friendly_name','class','type','vid','pid','device_id','manufacturer','status','source','connection'];
  for(const ch of chunks.slice(0,200)){
    const obj={};
    keys.forEach(k=>{
      let re=new RegExp(`["']${k}["']\\s*:\\s*(["'])([\\s\\S]*?)\\1`,'i'); let m=ch.match(re);
      if(m) obj[k]=String(m[2]).replace(/\\\\/g,'\\').trim();
    });
    if(obj.name||obj.display_name||obj.device_id) out.push(obj);
  }
  return out.length ? out : s;
}
function arr(v){
  v=parseRawObjectString(v);
  if(v===null||v===undefined||v==='') return [];
  if(Array.isArray(v)) return v.flatMap(x=>arr(x));
  if(typeof v==='object'){
    const direct=['name','display_name','class','type','device_id','vid','pid','version','publisher','mount','total_gb'];
    if(direct.some(k=>Object.prototype.hasOwnProperty.call(v,k))) return [v];
    return Object.values(v).flatMap(x=>arr(x));
  }
  return [v];
}
function usbType(u){ const s=`${u.type||''} ${u.class||''} ${u.name||''} ${u.display_name||''}`.toLowerCase(); if(s.includes('keyboard'))return'Keyboard'; if(s.includes('mouse'))return'Mouse'; if(/headset|headphone|speaker|microphone|audio|sound/.test(s))return'Audio'; if(/camera|webcam|image/.test(s))return'Camera'; if(/storage|disk|flash|mass/.test(s))return'Storage'; if(s.includes('bluetooth'))return'Bluetooth'; if(/network|ethernet|wi-fi|wifi|wireless|802\.11/.test(s))return'USB Network'; if(s.includes('hub'))return'Hub'; return u.type||'Peripheral'; }
function isNoisyUsb(u){ const text=`${u.name||''} ${u.display_name||''} ${u.class||''} ${u.device_id||''}`.toLowerCase(); const keep=/keyboard|mouse|razer|logitech|headset|headphone|speaker|microphone|audio|camera|webcam|printer|storage|flash|disk|bluetooth|realtek|tp-link|wi-fi|wifi|ethernet|wireless|802\.11/; if(keep.test(text)) return false; return /hid button|hid-compliant system|hid-compliant consumer|hid-compliant vendor|usb composite device|usb input device|root hub|generic usb hub|tap-windows|wan miniport|virtual adapter|loopback|acpi\\|root\\|swd\\|swc\\|display\\/.test(text); }
function cleanUsbItems(items){
  const seen=new Set(), out=[];
  arr(items).forEach(raw=>{
    let u = typeof raw==='object' ? {...raw} : {name:String(raw), display_name:String(raw), source:'raw'};
    u.name = cleanText(u.display_name || u.friendly_name || u.name || u.device_name || u.description || 'Unknown USB / Peripheral');
    u.display_name = u.name;
    u.class = cleanText(u.class || u.pnp_class || '');
    u.type = usbType(u);
    u.vid = cleanText(u.vid || u.vendor_id || ((String(u.device_id||'').match(/VID_([0-9A-F]{4})/i)||[])[1]) || '').toUpperCase();
    u.pid = cleanText(u.pid || u.product_id || ((String(u.device_id||'').match(/PID_([0-9A-F]{4})/i)||[])[1]) || '').toUpperCase();
    u.device_id = cleanText(u.device_id || u.instance_id || u.id || '');
    if(isNoisyUsb(u)) return;
    const key=`${u.type}|${u.name}|${u.vid}|${u.pid}|${u.device_id.slice(0,70)}`;
    if(seen.has(key)) return; seen.add(key); out.push(u);
  });
  return out.sort((a,b)=>(a.type+a.name).localeCompare(b.type+b.name));
}

function filteredMachines(){
  const q=state.query.toLowerCase();
  return state.machines.filter(m=>{
    if(q && !JSON.stringify({h:host(m),ip:m.primary_ip,os:m.os,g:m.gpu_names}).toLowerCase().includes(q)) return false;
    const st=$('#fleetStatus')?.value||'all'; if(st==='online'&&!m.online)return false; if(st==='offline'&&m.online)return false; if(st==='attention'&&!attention(m))return false;
    const os=$('#fleetOs')?.value||'all'; if(os==='windows'&&!String(m.os||'').toLowerCase().includes('win'))return false; if(os==='linux'&&!/ubuntu|linux/i.test(String(m.os||'')))return false;
    return true;
  });
}

function renderDashboard(){
  const o=state.overview||{}; const ih=o.internet_health||{}; const isp=(o.isp_names||[])[0] || (o.server_isp||{}).isp || 'ISP not detected';
  const latency = ih.avg_latency_ms ?? ih.latency_ms ?? (Array.isArray(ih.latency)?(ih.latency.find(x=>x.tcp_ms!==null&&x.tcp_ms!==undefined)||{}).tcp_ms:null);
  const loss = ih.loss_percent ?? ih.packet_loss_percent;
  const hasLatency = latency !== null && latency !== undefined && latency !== '';
  const hasLoss = loss !== null && loss !== undefined && loss !== '';
  $('#kHealthTitle').textContent = Number(loss||0) > 10 || Number(latency||0) > 120 ? 'Internet Risk for Live Classes' : 'Internet Healthy for Live Classes';
  $('#kHealthNote').textContent = `${isp} • live server probe • clients every 5 sec • offline after about ${OFFLINE_EXPECTED_SECONDS} sec`;
  $('#kIspNameHero').textContent=isp; $('#kLatency').textContent=hasLatency?fmt(latency,' ms',0):'Probe blocked'; $('#kJitter').textContent=fmt(ih.jitter_ms,' ms',0); $('#kLoss').textContent=hasLoss?fmt(loss,'%',0):'Probe blocked'; $('#kProbeDown').textContent=fmt(ih.probe_download_mbps,' Mbps',2); $('#kProbeUp').textContent=fmt(ih.probe_upload_mbps,' Mbps',2);
  if($('#clientIntervalLabel')){ const intervals = state.machines.map(m=>Number(nested(payload(m),'agent.interval_seconds',0)||0)).filter(Boolean); const minInt = intervals.length ? Math.min(...intervals) : 5; $('#clientIntervalLabel').textContent = minInt + ' sec live'; } if($('#serverPollLabel')) $('#serverPollLabel').textContent = DASHBOARD_POLL_SECONDS + ' sec';
  $('#kTotal').textContent=o.total||0; $('#kOnline').textContent=o.online||0; $('#kOffline').textContent=o.offline||0; $('#kCritical').textContent=o.critical||0;
  $('#kDownToday').textContent=fmt(o.today_download_gb,' GB',2); $('#kUpToday').textContent=fmt(o.today_upload_gb,' GB',2); $('#kDownNow').textContent=fmt(o.current_download_mbps,' Mbps',2); $('#kUpNow').textContent=fmt(o.current_upload_mbps,' Mbps',2); $('#kUsbTotal').textContent=state.machines.reduce((a,m)=>a+Number(m.usb_count||0),0); if($('#kSoftwareTotal')) $('#kSoftwareTotal').textContent=state.machines.reduce((a,m)=>a+Number(m.software_count||0),0);
  const selected = selectedMachine('dashboardMachine');
  renderCommandSystemSpotlight(selected);
  renderCommandPageSummary();
  $('#topUsage').innerHTML = [...state.machines].sort((a,b)=>(Number(b.ram_percent||0)+Number(b.cpu_percent||0))-(Number(a.ram_percent||0)+Number(a.cpu_percent||0))).slice(0,5).map(m=>`<div class="usage-row"><div><strong>${esc(host(m))}</strong><small>${esc(m.primary_ip||'No IP')} • ${esc(m.os||'')}</small></div><div class="usage-mini"><span>CPU ${fmt(m.cpu_percent,'%')} · RAM ${fmt(m.ram_percent,'%')} · Disk ${fmt(m.disk_max_percent,'%')}</span><div class="bar"><i style="width:${Math.min(100,Number(m.disk_max_percent||0))}%"></i></div></div></div>`).join('') || '<div class="empty">No machine data yet.</div>';
  const latest=(o.changes||[]).slice(0,5); $('#latestChanges').innerHTML = latest.map(ch=>`<div class="change-mini"><strong>${esc(ch.human_title||ch.title||'Change')}</strong><small>${esc(ch.hostname||'')} • ${ago(ch.created_at)}</small><span>${esc(ch.human_message||ch.message||'')}</span></div>`).join('') || '<div class="empty">No changes yet.</div>';
  $('#latestAlerts').innerHTML=(o.notifications||[]).map(a=>`<div class="item"><div><strong>${esc(a.title)}</strong><small>${esc(a.hostname||'Server')} • ${ago(a.created_at)}</small><div>${esc(a.message||'')}</div></div><span class="pill ${esc(a.severity||'info')}">${esc(a.severity||'info')}</span></div>`).join('') || '<div class="empty">No alerts yet. Go to Notifications and press Send Test to verify delivery.</div>';
  const nh=$('#notificationHealthBox'); if(nh){ const count=(o.notifications||[]).length; const webhook=(o.settings||{}).google_chat_webhook ? 'Webhook configured' : 'Webhook missing'; nh.innerHTML=`<strong>${count?count+' recent alert'+(count>1?'s':''):'Ready to test'}</strong><small>${webhook}. Open Notifications and press Send Test to verify delivery.</small>`; }
}
function ring(label, value, suffix='%'){
  const v=Math.max(0, Math.min(100, Number(value||0)));
  return `<div class="metric-ring" style="--v:${v}"><div><strong>${fmt(value,suffix,0)}</strong><span>${esc(label)}</span></div></div>`;
}
function renderCommandSystemSpotlight(m){
  const el=$('#commandSystemSpotlight'); if(!el) return;
  if(!m){ el.innerHTML='<div class="empty">No client data yet.</div>'; return; }
  el.innerHTML=`<div class="spot-head"><div><span class="eyebrow">Selected System Analytics</span><h2>${esc(host(m))}</h2><p>${esc(m.primary_ip||'No IP')} • ${esc(m.os||'')}</p></div>${statusPill(m)}</div><div class="ring-row">${ring('CPU',m.cpu_percent)}${ring('RAM',m.ram_percent)}${ring('Disk',m.disk_max_percent)}</div><div class="spot-kv"><div><span>Download now</span><strong>${fmt(m.wan_download_mbps,' Mbps',2)}</strong></div><div><span>Upload now</span><strong>${fmt(m.wan_upload_mbps,' Mbps',2)}</strong></div><div><span>Today data</span><strong>↓ ${fmt(m.today_download_gb,' GB',2)} / ↑ ${fmt(m.today_upload_gb,' GB',2)}</strong></div><div><span>Inventory</span><strong>${esc(m.usb_count||0)} USB • ${esc(m.software_count||0)} apps</strong></div></div><div class="spot-actions"><button class="btn small" onclick="switchPage('machine360')">Open 360</button><button class="btn small download-only" onclick="downloadCurrentMachine()">Download selected CSV</button></div>`;
}
function renderCommandPageSummary(){
  const el=$('#commandPageSummary'); if(!el) return;
  const totalUsb=state.machines.reduce((a,m)=>a+Number(m.usb_count||0),0), totalApps=state.machines.reduce((a,m)=>a+Number(m.software_count||0),0);
  const cards=[
    ['Fleet', `${state.machines.length} systems`, `${(state.overview||{}).online||0} online`, 'fleet'],
    ['Hardware', `${state.machines.filter(attention).length} need attention`, 'CPU/RAM/Disk/GPU analytics', 'hardware'],
    ['Software', `${totalApps} app entries`, 'System-wise inventory export', 'software'],
    ['USB', `${totalUsb} peripherals`, 'Keyboard, mouse, headset, storage', 'usb'],
    ['History', `${fmt((state.overview||{}).today_download_gb,' GB',2)} today`, 'Date range + system-wise CSV', 'history'],
    ['Notifications', `${((state.overview||{}).notifications||[]).length} recent alerts`, 'Rules, webhook, test alerts', 'notifications']
  ];
  el.innerHTML=cards.map(([t,b,s,p])=>`<button class="summary-tile" onclick="switchPage('${p}')"><span>${esc(t)}</span><strong>${esc(b)}</strong><small>${esc(s)}</small></button>`).join('');
}
function renderFleet(){ const tb=$('#fleetTable tbody'); if(!tb)return; tb.innerHTML=filteredMachines().map(m=>`<tr><td>${statusPill(m)}</td><td><strong>${esc(host(m))}</strong><small>${esc(m.machine_id||'')}</small></td><td>${esc(m.primary_ip||'')}</td><td>${esc(m.os||'')}</td><td>${fmt(m.cpu_percent,'%')}</td><td>${fmt(m.ram_percent,'%')}<small>${fmt(m.ram_total_gb,' GB')}</small></td><td>${fmt(m.disk_max_percent,'%')}</td><td>↓ ${fmt(m.wan_download_mbps,' Mbps',2)}<br>↑ ${fmt(m.wan_upload_mbps,' Mbps',2)}</td><td>${esc((m.gpu_names||[]).join(', ')||'N/A')}</td><td>${esc(m.usb_count||0)}</td><td>${ago(m.updated_at)}</td></tr>`).join('') || '<tr><td colspan="11" class="empty">No matching machines.</td></tr>'; }
function detail(title, rows){return `<article class="detail-card"><h3>${esc(title)}</h3>${rows.map(([k,v])=>`<div><span>${esc(k)}</span><strong>${v}</strong></div>`).join('')}</article>`;}
function renderMachine360(){ const m=selectedMachine('machineSelect'); const el=$('#machineDetails'); if(!el)return; if(!m){el.innerHTML='<div class="empty">Select one machine.</div>';return;} const p=payload(m); el.innerHTML=[detail('Identity',[['Status',statusPill(m)],['Machine',esc(host(m))],['Machine ID',`<code>${esc(m.machine_id)}</code>`],['OS',esc(m.os||'')],['Last Seen',ago(m.updated_at)]]),detail('Live Usage',[['CPU',fmt(m.cpu_percent,'%')],['CPU Temp',fmt(m.cpu_temp_c,'°C')],['RAM',`${fmt(m.ram_used_gb,' GB')} / ${fmt(m.ram_total_gb,' GB')} (${fmt(m.ram_percent,'%')})`],['Disk Max',fmt(m.disk_max_percent,'%')],['Network Now',`↓ ${fmt(m.wan_download_mbps,' Mbps',2)} / ↑ ${fmt(m.wan_upload_mbps,' Mbps',2)}`]]),detail('Network',[['Primary IP',esc(m.primary_ip||'')],['Public IP',esc(m.public_ip||'')],['ISP',esc(m.isp_name||'')],['VPN',m.vpn_active?'Active':'Not detected'],['All IPs',esc((m.all_ips||[]).join(', '))]]),detail('Inventory',[['USB / Peripherals',esc(m.usb_count||0)],['Installed Apps',esc(m.software_count||0)],['GPU',esc((m.gpu_names||[]).join(', ')||'N/A')],['GPU Temp',fmt(m.gpu_max_temp_c,'°C')],['Agent',esc(nested(p,'agent.version',''))]])].join(''); }
function renderNetwork(){ const el=$('#networkCards'); if(!el)return; el.innerHTML=state.machines.map(m=>{const p=payload(m); const adapters=arr(nested(p,'network.adapters',[])).slice(0,20); return `<article class="net-card"><h3>${statusPill(m)} ${esc(host(m))}</h3><div class="kv"><span>Primary IP</span><strong>${esc(m.primary_ip||'')}</strong></div><div class="kv"><span>VPN</span><strong>${m.vpn_active?'Active':'Not detected'}</strong></div><div class="kv"><span>ISP</span><strong>${esc(m.isp_name||'')}</strong></div><hr>${adapters.map(a=>`<p><strong>${esc(a.name||'Adapter')}</strong><br><span>${esc(a.description||'')}</span><br><span>MAC ${esc(a.mac||'')} · IP ${esc((a.ips||[]).join(', '))}</span></p>`).join('')}</article>`}).join('') || '<div class="empty">No network data.</div>'; }
function renderHardware(){ const el=$('#hardwareCards'); if(!el)return; el.innerHTML=state.machines.map(m=>{const p=payload(m); const cpu=nested(p,'hardware.cpu',{}), mem=nested(p,'hardware.memory',{}), disks=arr(nested(p,'storage.disks',[])), gpus=arr(nested(p,'hardware.gpus',[])); return `<article class="hw-card"><h3>${esc(host(m))}</h3><div class="kv"><span>CPU</span><strong>${esc(cpu.name||'')}</strong></div><div class="kv"><span>Cores / Threads</span><strong>${esc(cpu.cores||'')} / ${esc(cpu.threads||'')}</strong></div><div class="kv"><span>RAM</span><strong>${fmt(mem.used_gb,' GB')} / ${fmt(mem.total_gb,' GB')}</strong></div><div class="kv"><span>CPU Temp</span><strong>${fmt(cpu.temperature_c,'°C')}</strong></div><h4>Disks</h4>${disks.map(d=>`<p>${esc(d.mount||d.name)}: ${fmt(d.used_percent,'%')} of ${fmt(d.total_gb,' GB')}</p>`).join('')||'<p>No disk data</p>'}<h4>GPU</h4>${gpus.map(g=>`<p>${esc(g.name||'GPU')} · ${fmt(g.memory_total_mb,' MB',0)} · ${fmt(g.usage_percent,'%')} · ${fmt(g.temperature_c,'°C')}</p>`).join('')||'<p>No GPU data</p>'}</article>`;}).join('') || '<div class="empty">No hardware data.</div>'; }
function renderSoftware(){ const m=selectedMachine('softwareMachine'); const tb=$('#softwareTable tbody'); if(!tb)return; const apps=arr(nested(payload(m),'software.installed',[])).filter(x=>typeof x==='object'); tb.innerHTML=apps.map(a=>`<tr><td><strong>${esc(a.name||a.display_name||'')}</strong></td><td>${esc(a.version||'')}</td><td>${esc(a.publisher||'')}</td><td>${esc(a.install_date||'')}</td></tr>`).join('') || '<tr><td colspan="4" class="empty">No software data for selected system.</td></tr>'; }
function renderUsb(){ const m=selectedMachine('usbMachine'); const el=$('#usbCards'); if(!el)return; if(!m){el.innerHTML='<div class="empty">Select one machine.</div>';return;} const devices=cleanUsbItems(nested(payload(m),'usb.devices',[])); const groups={}; devices.forEach(u=>{(groups[u.type] ||= []).push(u)}); el.innerHTML=Object.keys(groups).sort().map(type=>`<section class="usb-group"><h3>${esc(type)} <span>${groups[type].length}</span></h3><div class="device-grid">${groups[type].map(u=>`<article class="device-card"><div class="device-icon">${esc(type[0]||'P')}</div><div><strong>${esc(u.display_name||u.name)}</strong><small>${esc(u.manufacturer||u.class||'Peripheral')} ${u.status?('• '+esc(u.status)):''}</small><div class="device-meta"><span>${u.vid||u.pid?`VID ${esc(u.vid||'')} PID ${esc(u.pid||'')}`:'No VID/PID'}</span><span>${esc(u.source||'client')}</span></div>${u.device_id?`<details><summary>Technical ID</summary><code>${esc(u.device_id)}</code></details>`:''}</div></article>`).join('')}</div></section>`).join('') || '<div class="empty">No clean USB/peripheral data for this Windows client yet. Update client once from Deploy, then wait one heartbeat. If still blank, run Windows test command.</div>'; }
async function renderChanges(force=false){ const el=$('#changeHistory'); if(!el)return; try{ if(force || !state.changes.length){ const d=await api('/api/changes'); state.changes=d.changes||[]; } const mid=$('#changeMachine')?.value||''; const rows=state.changes.filter(c=>!mid || c.machine_id===mid).slice(0,200); el.innerHTML=rows.map(c=>`<article class="timeline-card"><div class="timeline-dot ${esc(c.change_type||'info')}"></div><div><h3>${esc(c.human_title||c.title||'Change')}</h3><small>${esc(c.hostname||'')} • ${new Date(c.created_at).toLocaleString()}</small><p>${esc(c.human_message||c.message||'')}</p>${(c.added_items||[]).length?`<details><summary>Added ${c.added_count||c.added_items.length}</summary><pre>${esc((c.added_items||[]).join('\n'))}</pre></details>`:''}${(c.removed_items||[]).length?`<details><summary>Removed ${c.removed_count||c.removed_items.length}</summary><pre>${esc((c.removed_items||[]).join('\n'))}</pre></details>`:''}</div></article>`).join('') || '<div class="empty">No change log for selected system.</div>'; }catch(e){el.innerHTML='<div class="empty">Change API unavailable.</div>'} }
function historyQs(){return queryString({days:$('#historyDays')?.value||30,date_from:$('#historyDateFrom')?.value||'',date_to:$('#historyDateTo')?.value||'',machine_id:$('#historyMachine')?.value||''});}
async function renderHistory(){ try{ const d=await api('/api/history?'+historyQs()+'&samples=1'); const daily=$('#historyDailyTable tbody'), mt=$('#historyMachineTable tbody'), st=$('#historySampleTable tbody'); if(daily) daily.innerHTML=(d.daily||[]).map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(x.machines_seen)}</td><td>${esc(x.heartbeat_count)}</td><td>${fmt(x.download_gb,' GB',2)}</td><td>${fmt(x.upload_gb,' GB',2)}</td><td>${fmt(x.max_current_download_mbps,' Mbps',2)}</td><td>${fmt(x.max_current_upload_mbps,' Mbps',2)}</td><td>${fmt(x.avg_cpu_percent,'%')}</td><td>${fmt(x.avg_ram_percent,'%')}</td><td>${esc(x.usb_max||0)}</td><td>${esc(x.software_max||0)}</td></tr>`).join('')||'<tr><td colspan="11" class="empty">No history.</td></tr>'; if(mt) mt.innerHTML=(d.per_machine||[]).map(x=>`<tr><td>${esc(x.date)}</td><td><strong>${esc(x.hostname)}</strong></td><td>${esc(x.heartbeat_count)}</td><td>${esc(x.public_ip||'')}</td><td>${esc(x.isp_name||'')}</td><td>${fmt(x.download_gb,' GB',2)}</td><td>${fmt(x.upload_gb,' GB',2)}</td><td>${fmt(x.max_current_download_mbps,' Mbps',2)}</td><td>${fmt(x.max_current_upload_mbps,' Mbps',2)}</td><td>${fmt(x.cpu_max,'%')}</td><td>${fmt(x.ram_max,'%')}</td><td>${fmt(x.ram_total_gb,' GB')}</td><td>${esc(x.usb_count||0)}</td><td>${esc(x.software_count||0)}</td><td>${ago(x.last_seen)}</td></tr>`).join('')||'<tr><td colspan="15" class="empty">No system-wise records.</td></tr>'; if(st) st.innerHTML=(d.samples||[]).map(x=>`<tr><td>${new Date(x.received_at).toLocaleString()}</td><td>${esc(x.hostname||'')}</td><td>${esc(x.primary_ip||'')}</td><td>${esc(x.public_ip||'')}</td><td>${esc(x.isp_name||'')}</td><td>${fmt(x.cpu_percent,'%')}</td><td>${fmt(x.ram_percent,'%')}</td><td>${fmt(x.ram_total_gb,' GB')}</td><td>${fmt(x.current_download_mbps,' Mbps',2)}</td><td>${fmt(x.current_upload_mbps,' Mbps',2)}</td><td>${fmt(x.today_download_gb,' GB',2)}</td><td>${fmt(x.today_upload_gb,' GB',2)}</td><td>${esc(x.usb_count||0)}</td><td>${esc(x.software_count||0)}</td></tr>`).join('')||'<tr><td colspan="14" class="empty">No samples.</td></tr>'; }catch(e){console.error(e);} }
async function renderMessages(){ const el=$('#messageHistory'); if(!el)return; try{ const d=await api('/api/messages'); el.innerHTML=(d.messages||[]).map(m=>`<div class="message-card"><strong>${esc(m.title||'Admin message')}</strong><small>${esc(m.target_hostname||m.target_machine_id||'All machines')} • ${esc(m.status_label||m.status||'pending')} • delivered ${esc(m.delivered_count||0)}</small><p>${esc(m.message||'')}</p></div>`).join('')||'<div class="empty">No messages sent yet.</div>'; }catch(e){el.innerHTML='<div class="empty">Message API unavailable.</div>';} }
async function sendClientMessage(){ const body={target_machine_id:$('#messageMachine')?.value||'', title:$('#msgTitle')?.value||'Admin message', message:$('#msgBody')?.value||'', priority:$('#msgPriority')?.value||'normal'}; const m=state.machines.find(x=>x.machine_id===body.target_machine_id); body.target_hostname=m?host(m):''; if(!body.message.trim())return alert('Type message first'); await api('/api/messages',{method:'POST',body:JSON.stringify(body)}); $('#msgBody').value=''; await renderMessages(); alert('Message queued. Client receives it on next heartbeat and shows popup/log.'); }
async function loadRules(){ try{ const d=await api('/api/notifications/rules'); state.rules=d.rules||[]; renderRules(d.settings||{}); }catch(e){} }
function renderRules(settings={}){ if($('#ruleMetric')) $('#ruleMetric').innerHTML=metrics.map(m=>`<option>${m}</option>`).join(''); if($('#webhook')) $('#webhook').value=settings.google_chat_webhook||''; if($('#offlineTimeout')) $('#offlineTimeout').value=settings.offline_timeout_minutes||1; const tb=$('#rulesTable tbody'); if(tb) tb.innerHTML=state.rules.map(r=>`<tr><td>${r.enabled?'Yes':'No'}</td><td><strong>${esc(r.name)}</strong><small>${esc(r.id)}</small></td><td>${esc(r.metric)}</td><td>${esc(r.op)} ${esc(r.threshold)}</td><td>${esc(r.severity)}</td><td>${esc(r.cooldown_minutes)} min</td><td><button class="btn small" onclick='editRule(${JSON.stringify(r).replace(/'/g,"&#39;")})'>Edit</button><button class="btn small danger" onclick="deleteRule('${esc(r.id)}')">Delete</button></td></tr>`).join('')||'<tr><td colspan="7" class="empty">No rules.</td></tr>'; renderAlertHistory(); }
async function renderAlertHistory(){ const el=$('#alertHistory'); if(!el)return; try{ const d=await api('/api/notifications'); el.innerHTML=(d.notifications||[]).map(a=>`<div class="item"><div><strong>${esc(a.title)}</strong><small>${esc(a.hostname||'')} • ${ago(a.created_at)}</small><div>${esc(a.message||'')}</div></div><span class="pill ${esc(a.severity||'info')}">${esc(a.severity||'info')}</span></div>`).join('')||'<div class="empty">No notification history.</div>'; }catch(e){} }
async function saveSettings(){ await api('/api/settings',{method:'POST',body:JSON.stringify({google_chat_webhook:$('#webhook').value,offline_timeout_minutes:$('#offlineTimeout').value})}); alert('Settings saved'); await loadRules(); }
function editRule(r){ ['ruleId','ruleName','ruleMetric','ruleOp','ruleThreshold','ruleSeverity','ruleCooldown'].forEach(id=>{if($('#'+id)) $('#'+id).value = r[{ruleId:'id',ruleName:'name',ruleMetric:'metric',ruleOp:'op',ruleThreshold:'threshold',ruleSeverity:'severity',ruleCooldown:'cooldown_minutes'}[id]] ?? '';}); if($('#ruleEnabled')) $('#ruleEnabled').checked=!!r.enabled; }
async function saveRule(){ const body={id:$('#ruleId').value,name:$('#ruleName').value,metric:$('#ruleMetric').value,op:$('#ruleOp').value,threshold:Number($('#ruleThreshold').value||0),severity:$('#ruleSeverity').value,cooldown_minutes:Number($('#ruleCooldown').value||15),enabled:$('#ruleEnabled').checked}; await api('/api/notifications/rule',{method:'POST',body:JSON.stringify(body)}); await loadRules(); alert('Rule saved'); }
async function deleteRule(id){ if(confirm('Delete rule?')){await api('/api/notifications/rule?id='+encodeURIComponent(id),{method:'DELETE'}); await loadRules();} }
async function testNotification(){ await api('/api/notifications/test',{method:'POST',body:'{}'}); alert('Test notification created'); await renderAlertHistory(); }
async function clearAlerts(){ if(confirm('Clear alert history?')){ await api('/api/notifications/clear',{method:'POST',body:'{}'}); await renderAlertHistory(); }}
async function loadUsers(){ if(!isAdmin())return; try{ const d=await api('/api/users'); state.users=d.users||[]; renderUsers(); }catch(e){console.error(e);} }
function renderUsers(){ const tb=$('#usersTable tbody'); if(!tb)return; tb.innerHTML=(state.users||[]).map(u=>`<tr><td><strong>${esc(u.username)}</strong></td><td>${esc(u.role)}</td><td>${u.enabled?'Yes':'No'}</td><td>${ago(u.updated_at)}</td><td>${u.username==='admin'?'Built-in':`<button class="btn small danger" onclick="deleteUser('${esc(u.username)}')">Delete</button>`}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">No users.</td></tr>'; }
async function saveUser(){ if(!isAdmin())return alert('Only admin'); const body={username:$('#newUserName')?.value||'',password:$('#newUserPass')?.value||'',role:$('#newUserRole')?.value||'viewer',enabled:true}; if(!body.username||body.password.length<8)return alert('Username and password min 8 chars required'); const r=await api('/api/users',{method:'POST',body:JSON.stringify(body)}); state.users=r.users||[]; $('#newUserName').value=''; $('#newUserPass').value=''; renderUsers(); alert('User saved'); }
async function deleteUser(username){ if(confirm('Delete user '+username+'?')){const r=await api('/api/users?username='+encodeURIComponent(username),{method:'DELETE'}); state.users=r.users||[]; renderUsers();}}
async function changePassword(){ const old_password=$('#oldPassword')?.value||'', new_password=$('#newPassword')?.value||'', confirm=$('#confirmPassword')?.value||''; if(new_password.length<8)return alert('New password min 8 chars'); if(new_password!==confirm)return alert('Confirm password does not match'); try{await api('/api/auth/change-password',{method:'POST',body:JSON.stringify({old_password,new_password})}); alert('Password changed'); ['oldPassword','newPassword','confirmPassword'].forEach(id=>$('#'+id).value='');}catch(e){alert('Password change failed: '+e.message);} }
async function runServerSpeedTest(full=false){ try{ const d=await api('/api/server-speed-test?full='+(full?'1':'0')); alert(`${full?'Full ISP Test':'Quick Probe'}\nProvider: ${d.isp?.isp||'N/A'}\nDownload: ${fmt(d.download_mbps,' Mbps',2)}\nUpload: ${fmt(d.upload_mbps,' Mbps',2)}\nLatency: ${fmt(d.latency_ms,' ms',0)}`); await refresh(true);}catch(e){alert('Speed test failed: '+e.message);} }
function requireAdminDownload(){ if(!isAdmin()){alert('Download is admin-only. Viewer users can see data but cannot download.'); return false;} return true; }
function exportCsv(){ if(requireAdminDownload()) location.href='/api/export/machines.csv'; }
function midFrom(id){ return $('#'+id)?.value || ''; }
function downloadCurrentMachine(){ if(requireAdminDownload()) location.href='/api/export/machine_current.csv?machine_id='+encodeURIComponent(midFrom('machineSelect')); }
function downloadSoftwareSelected(){ if(requireAdminDownload()) location.href='/api/export/software.csv?machine_id='+encodeURIComponent(midFrom('softwareMachine')); }
function downloadSoftwareAll(){ if(requireAdminDownload()) location.href='/api/export/software.csv'; }
function downloadUsbSelected(){ if(requireAdminDownload()) location.href='/api/export/usb.csv?machine_id='+encodeURIComponent(midFrom('usbMachine')); }
function downloadUsbAll(){ if(requireAdminDownload()) location.href='/api/export/usb.csv'; }
function downloadChangesSelected(){ if(requireAdminDownload()) location.href='/api/export/changes.csv?machine_id='+encodeURIComponent(midFrom('changeMachine')); }
function downloadChangesAll(){ if(requireAdminDownload()) location.href='/api/export/changes.csv'; }
function downloadChanges(){ downloadChangesAll(); }
function downloadDailyHistory(){ if(requireAdminDownload()) location.href='/api/export/history_daily.csv?'+historyQs(); }
function downloadMachineHistory(){ if(requireAdminDownload()) location.href='/api/export/history_machine.csv?'+historyQs(); }
function downloadSelectedSystemDateRange(){ if(!midFrom('historyMachine')){ alert('Please select a system first.'); return; } downloadMachineHistory(); }
function downloadHistorySamples(){ if(requireAdminDownload()) location.href='/api/export/history_samples.csv?'+historyQs(); }
function renderAll(){ renderDashboard(); renderFleet(); renderMachine360(); renderNetwork(); renderHardware(); renderSoftware(); renderUsb(); if(state.page==='changes') renderChanges(false); if(state.page==='history') renderHistory(); if(state.page==='messages') renderMessages(); }
function switchPage(page){ state.page=page; $$('.page').forEach(p=>p.classList.remove('active')); $('#page-'+page)?.classList.add('active'); $$('.nav').forEach(n=>n.classList.toggle('active',n.dataset.page===page)); const titles={dashboard:['Command Center','Colorful system-wise command analysis, ISP health, downloads, alerts and history.'],fleet:['Machine Fleet','All Windows and Ubuntu systems, stable and searchable.'],machine360:['Machine 360','Select one system and export its current details.'],network:['Network + VPN','LAN, VLAN, Wi-Fi, virtual adapters and VPN visibility.'],hardware:['Hardware Analytics','CPU, RAM, disk, temperature and GPU inventory.'],software:['Software Inventory','System-wise installed applications with admin export.'],usb:['USB + Peripherals','Human-readable keyboard, mouse, headset, camera, storage and USB network devices.'],changes:['Human Change Log','Readable system-wise timeline for USB, software, hardware, IP and VPN changes.'],history:['Day History','Old day data with system-wise download/upload and exports.'],messages:['Client Messages','Send closeable popup messages to Windows and Ubuntu clients.'],notifications:['Notifications','Create, edit, delete and test alert rules.'],deploy:['Deploy','Copy-ready current commands for Windows and Ubuntu clients.'],settings:['Settings','Users, password and refresh control.']}; const [t,sub]=titles[page]||titles.dashboard; $('#pageTitle').textContent=t; $('#pageSubtitle').textContent=sub; showBanner(state.pendingUpdate && quietPages.has(page)); renderAll(); if(page==='notifications') loadRules(); if(page==='history') renderHistory(); if(page==='messages') renderMessages(); if(page==='changes') renderChanges(true); if(page==='settings' && isAdmin()) loadUsers(); applyRoleControls(); }

$$('.nav').forEach(b=>b.addEventListener('click',()=>switchPage(b.dataset.page)));
$('#refreshBtn')?.addEventListener('click',()=>refresh(true)); $('#autoRefreshBtn')?.addEventListener('click',toggleAutoRefresh);
$('#globalSearch')?.addEventListener('input',e=>{state.query=e.target.value;renderAll();});
['fleetStatus','fleetOs'].forEach(id=>$('#'+id)?.addEventListener('change',renderFleet));
selectorIds.forEach(id=>$('#'+id)?.addEventListener('change',()=>onMachineSelect(id)));
['historyDays','historyDateFrom','historyDateTo'].forEach(id=>$('#'+id)?.addEventListener('change',()=>renderHistory()));
$('#loginBtn')?.addEventListener('click',login); $('#adminPassword')?.addEventListener('keydown',e=>{if(e.key==='Enter')login();}); $('#logoutBtn')?.addEventListener('click',logout);
setLiveButtons(); checkAuth();
setInterval(()=>{ if(state.authenticated && state.autoRefresh) refresh(false); },DASHBOARD_POLL_SECONDS*1000);

/* deploy-mobile-fix-v1: copy buttons for Deploy page */
window.copyDeployCommand = async function(id, btn){
  const el = document.getElementById(id);
  if(!el) return;
  const text = (el.innerText || el.textContent || '').trim();
  const old = btn ? btn.textContent : '';
  try{
    if(navigator.clipboard && window.isSecureContext){
      await navigator.clipboard.writeText(text);
    }else{
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    if(btn){ btn.textContent = 'Copied'; setTimeout(()=>btn.textContent = old || 'Copy', 1200); }
  }catch(e){
    alert('Copy failed. Select the command text and copy manually.');
  }
};
