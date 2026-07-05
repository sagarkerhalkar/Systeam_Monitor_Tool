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

/* ui-readable-history-fix-v2: display-only helpers, no client/server/client-script logic change */
function fmtInstallDate(v){
  const s = String(v ?? '').trim();
  if(!s) return '';
  let m = s.match(/^(\d{4})(\d{2})(\d{2})$/);
  if(m) return `${m[3]}-${m[2]}-${m[1]}`;
  m = s.match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/);
  if(m) return `${m[3]}-${m[2]}-${m[1]} ${m[4]}:${m[5]}:${m[6]}`;
  m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if(m) return `${m[3]}-${m[2]}-${m[1]}`;
  return s;
}
function fmtMemMb(mb){
  const x = Number(mb);
  if(!Number.isFinite(x) || x <= 0) return 'N/A';
  return x >= 1024 ? `${(x/1024).toFixed(1).replace(/\.0$/,'')} GB` : `${Math.round(x)} MB`;
}
function cleanGpuName(n){
  return String(n || 'GPU').replace(/^\s*\d{2}:\d{2}\.\d+\s+[^:]+:\s*/,'').replace(/\s+/g,' ').trim();
}
function gpuBrief(m){
  const names = Array.isArray(m?.gpu_names) ? m.gpu_names : [];
  const cleaned = names.map(cleanGpuName).filter(Boolean);
  return cleaned.length ? cleaned.join(', ') : 'N/A';
}
function gpuDetailsHtml(m){
  const p = payload(m);
  const gpus = arr(nested(p,'hardware.gpus',[])).filter(x=>typeof x==='object');
  if(gpus.length){
    return gpus.map(g=>{
      const name = esc(cleanGpuName(g.name || g.gpu_name || 'GPU'));
      const total = fmtMemMb(g.memory_total_mb || g.adapter_ram_mb || g.memoryTotalMB);
      const used = fmtMemMb(g.memory_used_mb || g.memoryUsedMB);
      const usage = fmt(g.usage_percent ?? g.utilization_gpu ?? g.load_percent, '%');
      const temp = fmt(g.temperature_c ?? g.temp_c, ' C');
      return `<div class="gpu-line"><strong>${name}</strong><small>Memory: ${total}${used !== 'N/A' ? ' / Used '+used : ''} | Usage: ${usage} | Temp: ${temp}</small></div>`;
    }).join('');
  }
  const names = gpuBrief(m);
  if(names !== 'N/A') return `<div class="gpu-line"><strong>${esc(names)}</strong><small>Usage: ${fmt(m.gpu_max_usage,'%')} | Temp: ${fmt(m.gpu_max_temp_c,' C')} | Total memory: ${fmtMemMb(m.gpu_total_memory_mb)}</small></div>`;
  return '<p>No GPU data</p>';
}
function ramFleetCell(m){
  return `<div class="ram-cell"><strong>Usage ${fmt(m.ram_percent,'%')}</strong><small>Capacity ${fmt(m.ram_total_gb,' GB')}</small><small>Used ${fmt(m.ram_used_gb,' GB')}</small></div>`;
}
function netNowCell(m){
  return `<span>Down ${fmt(m.wan_download_mbps,' Mbps',2)}</span><br><span>Up ${fmt(m.wan_upload_mbps,' Mbps',2)}</span>`;
}

function ago(iso){if(!iso)return'N/A';const t=new Date(iso).getTime();if(!t)return'N/A';const s=(Date.now()-t)/1000;if(s<60)return`${Math.max(0,Math.round(s))}s ago`;if(s<3600)return`${Math.round(s/60)}m ago`;if(s<86400)return`${Math.round(s/3600)}h ago`;return new Date(iso).toLocaleString();}
function host(m){return m?.hostname || String(m?.machine_id||'').replace(/^[A-Z_]+:/,'') || 'UNKNOWN';}
function payload(m){return m?.payload || {};}
function nested(o,path,def){try{return path.split('.').reduce((a,k)=>a&&a[k]!==undefined?a[k]:undefined,o) ?? def;}catch(e){return def;}}
function isAdmin(){return state.role === 'admin';}
function statusPill(m){return `<span class="pill ${m?.online?'online':'offline'}">${m?.online?'Online':'Offline'}</span>`;}
function attention(m){return Number(m?.cpu_percent||0)>=90 || Number(m?.ram_percent||0)>=90 || Number(m?.disk_max_percent||0)>=90;}
function attentionReason(m){
  const r=[];
  if(Number(m?.cpu_percent||0)>=90) r.push(`CPU ${fmt(m.cpu_percent,'%')}`);
  if(Number(m?.ram_percent||0)>=90) r.push(`RAM ${fmt(m.ram_percent,'%')}`);
  if(Number(m?.disk_max_percent||0)>=90) r.push(`Disk ${fmt(m.disk_max_percent,'%')}`);
  return r.join(' | ') || 'Needs attention';
}
function openAttentionMachines(){
  switchPage('fleet');
  setTimeout(()=>{
    const fs=$('#fleetStatus');
    if(fs) fs.value='attention';
    renderFleet();
    const table=$('#fleetTable');
    if(table) table.scrollIntoView({behavior:'smooth', block:'start'});
  },80);
}
function bindAttentionClick(){
  const k=$('#kCritical');
  if(!k) return;
  const box=k.closest('div');
  if(!box || box.dataset.attentionClick==='1') return;
  box.dataset.attentionClick='1';
  box.title='Click to open PCs needing attention';
  box.style.cursor='pointer';
  box.addEventListener('click', openAttentionMachines);
}
function queryString(obj){return Object.entries(obj).filter(([k,v])=>v!==undefined&&v!==null&&v!=='').map(([k,v])=>encodeURIComponent(k)+'='+encodeURIComponent(v)).join('&');}
function cleanText(v){return String(v??'').trim().replace(/\s+/g,' ');}
function shortId(id){id=String(id||''); if(!id)return''; return id.length>80?id.slice(0,80)+'â€¦':id;}
function roleLabel(){return `${state.username||'user'} - ${state.role||'viewer'}`;}

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

function machineLabel(m){return `${host(m)} - ${m.primary_ip||((m.all_ips||[])[0]||'No IP')}`;}
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
  }).sort((a,b)=>(host(a)||'').localeCompare(host(b)||'') || String(a.primary_ip||'').localeCompare(String(b.primary_ip||'')));
}
function renderDashboard(){
  const o=state.overview||{}; const ih=o.internet_health||{}; const isp=(o.isp_names||[])[0] || (o.server_isp||{}).isp || 'ISP not detected';
  const latency = ih.avg_latency_ms ?? ih.latency_ms ?? (Array.isArray(ih.latency)?(ih.latency.find(x=>x.tcp_ms!==null&&x.tcp_ms!==undefined)||{}).tcp_ms:null);
  const loss = ih.loss_percent ?? ih.packet_loss_percent;
  const hasLatency = latency !== null && latency !== undefined && latency !== '';
  const hasLoss = loss !== null && loss !== undefined && loss !== '';
  $('#kHealthTitle').textContent = Number(loss||0) > 10 || Number(latency||0) > 120 ? 'Internet Risk for Live Classes' : 'Internet Healthy for Live Classes';
  $('#kHealthNote').textContent = `${isp} - live server probe - clients every 5 sec - offline after about ${OFFLINE_EXPECTED_SECONDS} sec`;
  $('#kIspNameHero').textContent=isp; $('#kLatency').textContent=hasLatency?fmt(latency,' ms',0):'Probe blocked'; $('#kJitter').textContent=fmt(ih.jitter_ms,' ms',0); $('#kLoss').textContent=hasLoss?fmt(loss,'%',0):'Probe blocked'; $('#kProbeDown').textContent=fmt(ih.probe_download_mbps,' Mbps',2); $('#kProbeUp').textContent=fmt(ih.probe_upload_mbps,' Mbps',2);
  if($('#clientIntervalLabel')){ const intervals = state.machines.map(m=>Number(nested(payload(m),'agent.interval_seconds',0)||0)).filter(Boolean); const minInt = intervals.length ? Math.min(...intervals) : 5; $('#clientIntervalLabel').textContent = minInt + ' sec live'; } if($('#serverPollLabel')) $('#serverPollLabel').textContent = DASHBOARD_POLL_SECONDS + ' sec';
  $('#kTotal').textContent=o.total||0; $('#kOnline').textContent=o.online||0; $('#kOffline').textContent=o.offline||0; $('#kCritical').textContent=o.critical||0;
  $('#kDownToday').textContent=fmt(o.today_download_gb,' GB',2); $('#kUpToday').textContent=fmt(o.today_upload_gb,' GB',2); $('#kDownNow').textContent=fmt(o.current_download_mbps,' Mbps',2); $('#kUpNow').textContent=fmt(o.current_upload_mbps,' Mbps',2); $('#kUsbTotal').textContent=state.machines.reduce((a,m)=>a+Number(m.usb_count||0),0); if($('#kSoftwareTotal')) $('#kSoftwareTotal').textContent=state.machines.reduce((a,m)=>a+Number(m.software_count||0),0);
  const selected = selectedMachine('dashboardMachine');
  renderCommandSystemSpotlight(selected);
  renderCommandPageSummary();
  $('#topUsage').innerHTML = [...state.machines].sort((a,b)=>(Number(b.ram_percent||0)+Number(b.cpu_percent||0))-(Number(a.ram_percent||0)+Number(a.cpu_percent||0))).slice(0,5).map(m=>`<div class="usage-row"><div><strong>${esc(host(m))}</strong><small>${esc(m.primary_ip||'No IP')} - ${esc(m.os||'')}</small></div><div class="usage-mini"><span>CPU ${fmt(m.cpu_percent,'%')}  /  RAM ${fmt(m.ram_percent,'%')}  /  Disk ${fmt(m.disk_max_percent,'%')}</span><div class="bar"><i style="width:${Math.min(100,Number(m.disk_max_percent||0))}%"></i></div></div></div>`).join('') || '<div class="empty">No machine data yet.</div>';
  const latest=(o.changes||[]).slice(0,5); $('#latestChanges').innerHTML = latest.map(ch=>`<div class="change-mini"><strong>${esc(ch.human_title||ch.title||'Change')}</strong><small>${esc(ch.hostname||'')} - ${ago(ch.created_at)}</small><span>${esc(ch.human_message||ch.message||'')}</span></div>`).join('') || '<div class="empty">No changes yet.</div>';
  $('#latestAlerts').innerHTML=(o.notifications||[]).map(a=>`<div class="item"><div><strong>${esc(a.title)}</strong><small>${esc(a.hostname||'Server')} - ${ago(a.created_at)}</small><div>${esc(a.message||'')}</div></div><span class="pill ${esc(a.severity||'info')}">${esc(a.severity||'info')}</span></div>`).join('') || '<div class="empty">No alerts yet. Go to Notifications and press Send Test to verify delivery.</div>';
  const nh=$('#notificationHealthBox'); if(nh){ const count=(o.notifications||[]).length; const webhook=(o.settings||{}).google_chat_webhook ? 'Webhook configured' : 'Webhook missing'; nh.innerHTML=`<strong>${count?count+' recent alert'+(count>1?'s':''):'Ready to test'}</strong><small>${webhook}. Open Notifications and press Send Test to verify delivery.</small>`; }
}
function ring(label, value, suffix='%'){
  const v=Math.max(0, Math.min(100, Number(value||0)));
  return `<div class="metric-ring" style="--v:${v}"><div><strong>${fmt(value,suffix,0)}</strong><span>${esc(label)}</span></div></div>`;
}
function renderCommandSystemSpotlight(m){
  const el=$('#commandSystemSpotlight'); if(!el) return;
  if(!m){ el.innerHTML='<div class="empty">No client data yet.</div>'; return; }
  el.innerHTML=`<div class="spot-head"><div><span class="eyebrow">Selected System Analytics</span><h2>${esc(host(m))}</h2><p>${esc(m.primary_ip||'No IP')} - ${esc(m.os||'')}</p></div>${statusPill(m)}</div><div class="ring-row">${ring('CPU',m.cpu_percent)}${ring('RAM',m.ram_percent)}${ring('Disk',m.disk_max_percent)}</div><div class="spot-kv"><div><span>Download now</span><strong>${fmt(m.wan_download_mbps,' Mbps',2)}</strong></div><div><span>Upload now</span><strong>${fmt(m.wan_upload_mbps,' Mbps',2)}</strong></div><div><span>Today data</span><strong>Down ${fmt(m.today_download_gb,' GB',2)} / Up ${fmt(m.today_upload_gb,' GB',2)}</strong></div><div><span>Inventory</span><strong>${esc(m.usb_count||0)} USB - ${esc(m.software_count||0)} apps</strong></div></div><div class="spot-actions"><button class="btn small" onclick="switchPage('machine360')">Open 360</button><button class="btn small download-only" onclick="downloadCurrentMachine()">Download selected CSV</button></div>`;
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
function renderFleet(){ const tb=$('#fleetTable tbody'); if(!tb)return; tb.innerHTML=filteredMachines().map(m=>`<tr><td>${statusPill(m)}</td><td><strong>${esc(host(m))}</strong><small>${esc(m.machine_id||'')}</small>${attention(m)?`<small class="warn-text">${esc(attentionReason(m))}</small>`:''}</td><td>${esc(m.primary_ip||'')}</td><td>${esc(m.os||'')}</td><td>${fmt(m.cpu_percent,'%')}</td><td>${ramFleetCell(m)}</td><td>${fmt(m.disk_max_percent,'%')}</td><td>${netNowCell(m)}</td><td>${esc(gpuBrief(m))}</td><td>${esc(m.usb_count||0)}</td><td>${ago(m.updated_at)}</td></tr>`).join('') || '<tr><td colspan="11" class="empty">No matching machines.</td></tr>'; }
function detail(title, rows){return `<article class="detail-card"><h3>${esc(title)}</h3>${rows.map(([k,v])=>`<div><span>${esc(k)}</span><strong>${v}</strong></div>`).join('')}</article>`;}
function renderMachine360(){ const m=selectedMachine('machineSelect'); const el=$('#machineDetails'); if(!el)return; if(!m){el.innerHTML='<div class="empty">Select one machine.</div>';return;} const p=payload(m); el.innerHTML=[detail('Identity',[['Status',statusPill(m)],['Machine',esc(host(m))],['Machine ID',`<code>${esc(m.machine_id)}</code>`],['OS',esc(m.os||'')],['Last Seen',ago(m.updated_at)]]),detail('Live Usage',[['CPU',fmt(m.cpu_percent,'%')],['CPU Temp',fmt(m.cpu_temp_c,' C')],['RAM Usage',fmt(m.ram_percent,'%')],['RAM Capacity',fmt(m.ram_total_gb,' GB')],['RAM Used',fmt(m.ram_used_gb,' GB')],['Disk Max',fmt(m.disk_max_percent,'%')],['Network Now',`Down ${fmt(m.wan_download_mbps,' Mbps',2)} / Up ${fmt(m.wan_upload_mbps,' Mbps',2)}`]]),detail('Network',[['Primary IP',esc(m.primary_ip||'')],['Public IP',esc(m.public_ip||'')],['ISP',esc(m.isp_name||'')],['VPN',m.vpn_active?'Active':'Not detected'],['All IPs',esc((m.all_ips||[]).join(', '))]]),detail('Inventory',[['USB / Peripherals',esc(m.usb_count||0)],['Installed Apps',esc(m.software_count||0)],['GPU Count',esc(m.gpu_count||0)],['GPU Max Usage',fmt(m.gpu_max_usage,'%')],['GPU Temp',fmt(m.gpu_max_temp_c,' C')],['GPU Memory Total',fmtMemMb(m.gpu_total_memory_mb)],['Agent',esc(nested(p,'agent.version',''))]]),`<article class="detail-card machine-gpu-detail"><h3>GPU Details</h3>${gpuDetailsHtml(m)}</article>`].join(''); }
function renderNetwork(){ const el=$('#networkCards'); if(!el)return; el.innerHTML=state.machines.map(m=>{const p=payload(m); const adapters=arr(nested(p,'network.adapters',[])).slice(0,20); return `<article class="net-card"><h3>${statusPill(m)} ${esc(host(m))}</h3><div class="kv"><span>Primary IP</span><strong>${esc(m.primary_ip||'')}</strong></div><div class="kv"><span>VPN</span><strong>${m.vpn_active?'Active':'Not detected'}</strong></div><div class="kv"><span>ISP</span><strong>${esc(m.isp_name||'')}</strong></div><hr>${adapters.map(a=>`<p><strong>${esc(a.name||'Adapter')}</strong><br><span>${esc(a.description||'')}</span><br><span>MAC ${esc(a.mac||'')}  /  IP ${esc((a.ips||[]).join(', '))}</span></p>`).join('')}</article>`}).join('') || '<div class="empty">No network data.</div>'; }
function renderHardware(){ const el=$('#hardwareCards'); if(!el)return; el.innerHTML=state.machines.map(m=>{const p=payload(m); const cpu=nested(p,'hardware.cpu',{}), mem=nested(p,'hardware.memory',{}), disks=arr(nested(p,'storage.disks',[])); return `<article class="hw-card"><h3>${esc(host(m))}</h3><div class="kv"><span>CPU</span><strong>${esc(cpu.name||'')}</strong></div><div class="kv"><span>Cores / Threads</span><strong>${esc(cpu.cores||'')} / ${esc(cpu.threads||'')}</strong></div><div class="kv"><span>RAM Usage</span><strong>${fmt(mem.used_percent ?? m.ram_percent,'%')}</strong></div><div class="kv"><span>RAM Capacity</span><strong>${fmt(mem.total_gb ?? m.ram_total_gb,' GB')}</strong></div><div class="kv"><span>RAM Used</span><strong>${fmt(mem.used_gb ?? m.ram_used_gb,' GB')}</strong></div><div class="kv"><span>CPU Temp</span><strong>${fmt(cpu.temperature_c ?? m.cpu_temp_c,' C')}</strong></div><h4>Disks</h4>${disks.map(d=>`<p>${esc(d.mount||d.name||d.device)}: ${fmt(d.used_percent,'%')} of ${fmt(d.total_gb,' GB')}</p>`).join('')||'<p>No disk data</p>'}<h4>GPU</h4>${gpuDetailsHtml(m)}</article>`;}).join('') || '<div class="empty">No hardware data.</div>'; }
function renderSoftware(){ const m=selectedMachine('softwareMachine'); const tb=$('#softwareTable tbody'); if(!tb)return; const apps=arr(nested(payload(m),'software.installed',[])).filter(x=>typeof x==='object'); tb.innerHTML=apps.map(a=>`<tr><td><strong>${esc(a.name||a.display_name||'')}</strong></td><td>${esc(a.version||'')}</td><td>${esc(a.publisher||'')}</td><td>${esc(fmtInstallDate(a.install_date||''))}</td></tr>`).join('') || '<tr><td colspan="4" class="empty">No software data for selected system.</td></tr>'; }
function renderUsb(){ const m=selectedMachine('usbMachine'); const el=$('#usbCards'); if(!el)return; if(!m){el.innerHTML='<div class="empty">Select one machine.</div>';return;} const devices=cleanUsbItems(nested(payload(m),'usb.devices',[])); const groups={}; devices.forEach(u=>{(groups[u.type] ||= []).push(u)}); el.innerHTML=Object.keys(groups).sort().map(type=>`<section class="usb-group"><h3>${esc(type)} <span>${groups[type].length}</span></h3><div class="device-grid">${groups[type].map(u=>`<article class="device-card"><div class="device-icon">${esc(type[0]||'P')}</div><div><strong>${esc(u.display_name||u.name)}</strong><small>${esc(u.manufacturer||u.class||'Peripheral')} ${u.status?('- '+esc(u.status)):''}</small><div class="device-meta"><span>${u.vid||u.pid?`VID ${esc(u.vid||'')} PID ${esc(u.pid||'')}`:'No VID/PID'}</span><span>${esc(u.source||'client')}</span></div>${u.device_id?`<details><summary>Technical ID</summary><code>${esc(u.device_id)}</code></details>`:''}</div></article>`).join('')}</div></section>`).join('') || '<div class="empty">No clean USB/peripheral data for this Windows client yet. Update client once from Deploy, then wait one heartbeat. If still blank, run Windows test command.</div>'; }
async function renderChanges(force=false){ const el=$('#changeHistory'); if(!el)return; try{ if(force || !state.changes.length){ const d=await api('/api/changes'); state.changes=d.changes||[]; } const mid=$('#changeMachine')?.value||''; const rows=state.changes.filter(c=>!mid || c.machine_id===mid).slice(0,200); el.innerHTML=rows.map(c=>`<article class="timeline-card"><div class="timeline-dot ${esc(c.change_type||'info')}"></div><div><h3>${esc(c.human_title||c.title||'Change')}</h3><small>${esc(c.hostname||'')} - ${new Date(c.created_at).toLocaleString()}</small><p>${esc(c.human_message||c.message||'')}</p>${(c.added_items||[]).length?`<details><summary>Added ${c.added_count||c.added_items.length}</summary><pre>${esc((c.added_items||[]).join('\n'))}</pre></details>`:''}${(c.removed_items||[]).length?`<details><summary>Removed ${c.removed_count||c.removed_items.length}</summary><pre>${esc((c.removed_items||[]).join('\n'))}</pre></details>`:''}</div></article>`).join('') || '<div class="empty">No change log for selected system.</div>'; }catch(e){el.innerHTML='<div class="empty">Change API unavailable.</div>'} }
function historyQs(){return queryString({days:$('#historyDays')?.value||30,date_from:$('#historyDateFrom')?.value||'',date_to:$('#historyDateTo')?.value||'',machine_id:$('#historyMachine')?.value||''});}
async function renderHistory(){ try{ const d=await api('/api/history?'+historyQs()+'&samples=0'); const daily=$('#historyDailyTable tbody'), mt=$('#historyMachineTable tbody'), st=$('#historySampleTable tbody'); if(daily) daily.innerHTML=(d.daily||[]).map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(x.machines_seen)}</td><td>${esc(x.heartbeat_count)}</td><td>${fmt(x.download_gb,' GB',2)}</td><td>${fmt(x.upload_gb,' GB',2)}</td><td>${fmt(x.max_current_download_mbps,' Mbps',2)}</td><td>${fmt(x.max_current_upload_mbps,' Mbps',2)}</td><td>${fmt(x.avg_cpu_percent,'%')}</td><td>${fmt(x.avg_ram_percent,'%')}</td><td>${esc(x.usb_max||0)}</td><td>${esc(x.software_max||0)}</td></tr>`).join('')||'<tr><td colspan="11" class="empty">No history.</td></tr>'; if(mt) mt.innerHTML=(d.per_machine||[]).map(x=>`<tr><td>${esc(x.date)}</td><td><strong>${esc(x.hostname)}</strong></td><td>${esc(x.heartbeat_count)}</td><td>${esc(x.public_ip||'')}</td><td>${esc(x.isp_name||'')}</td><td>${fmt(x.download_gb,' GB',2)}</td><td>${fmt(x.upload_gb,' GB',2)}</td><td>${fmt(x.max_current_download_mbps,' Mbps',2)}</td><td>${fmt(x.max_current_upload_mbps,' Mbps',2)}</td><td>${fmt(x.cpu_max,'%')}</td><td>${fmt(x.ram_max,'%')}</td><td>${fmt(x.ram_total_gb,' GB')}</td><td>${esc(x.usb_count||0)}</td><td>${esc(x.software_count||0)}</td><td>${ago(x.last_seen)}</td></tr>`).join('')||'<tr><td colspan="15" class="empty">No system-wise records.</td></tr>'; if(st) st.innerHTML='<tr><td colspan="14" class="empty">Heartbeat samples are not auto-loaded to prevent browser hang. Use Download All Heartbeats, or select a small date range before export.</td></tr>'; }catch(e){console.error(e); const st=$('#historySampleTable tbody'); if(st) st.innerHTML='<tr><td colspan="14" class="empty">History API error. Check server console.</td></tr>'; } }
async function renderMessages(){ const el=$('#messageHistory'); if(!el)return; try{ const d=await api('/api/messages'); el.innerHTML=(d.messages||[]).map(m=>`<div class="message-card"><strong>${esc(m.title||'Admin message')}</strong><small>${esc(m.target_hostname||m.target_machine_id||'All machines')} - ${esc(m.status_label||m.status||'pending')} - delivered ${esc(m.delivered_count||0)}</small><p>${esc(m.message||'')}</p></div>`).join('')||'<div class="empty">No messages sent yet.</div>'; }catch(e){el.innerHTML='<div class="empty">Message API unavailable.</div>';} }
async function sendClientMessage(){ const body={target_machine_id:$('#messageMachine')?.value||'', title:$('#msgTitle')?.value||'Admin message', message:$('#msgBody')?.value||'', priority:$('#msgPriority')?.value||'normal'}; const m=state.machines.find(x=>x.machine_id===body.target_machine_id); body.target_hostname=m?host(m):''; if(!body.message.trim())return alert('Type message first'); await api('/api/messages',{method:'POST',body:JSON.stringify(body)}); $('#msgBody').value=''; await renderMessages(); alert('Message queued. Client receives it on next heartbeat and shows popup/log.'); }
async function loadRules(){ try{ const d=await api('/api/notifications/rules'); state.rules=d.rules||[]; renderRules(d.settings||{}); }catch(e){} }
function renderRules(settings={}){ if($('#ruleMetric')) $('#ruleMetric').innerHTML=metrics.map(m=>`<option>${m}</option>`).join(''); if($('#webhook')) $('#webhook').value=settings.google_chat_webhook||''; if($('#offlineTimeout')) $('#offlineTimeout').value=settings.offline_timeout_minutes||1; const tb=$('#rulesTable tbody'); if(tb) tb.innerHTML=state.rules.map(r=>`<tr><td>${r.enabled?'Yes':'No'}</td><td><strong>${esc(r.name)}</strong><small>${esc(r.id)}</small></td><td>${esc(r.metric)}</td><td>${esc(r.op)} ${esc(r.threshold)}</td><td>${esc(r.severity)}</td><td>${esc(r.cooldown_minutes)} min</td><td><button class="btn small" onclick='editRule(${JSON.stringify(r).replace(/'/g,"&#39;")})'>Edit</button><button class="btn small danger" onclick="deleteRule('${esc(r.id)}')">Delete</button></td></tr>`).join('')||'<tr><td colspan="7" class="empty">No rules.</td></tr>'; renderAlertHistory(); }
async function renderAlertHistory(){ const el=$('#alertHistory'); if(!el)return; try{ const d=await api('/api/notifications'); el.innerHTML=(d.notifications||[]).map(a=>`<div class="item"><div><strong>${esc(a.title)}</strong><small>${esc(a.hostname||'')} - ${ago(a.created_at)}</small><div>${esc(a.message||'')}</div></div><span class="pill ${esc(a.severity||'info')}">${esc(a.severity||'info')}</span></div>`).join('')||'<div class="empty">No notification history.</div>'; }catch(e){} }
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
function renderAll(){ renderDeployCommands();  renderDashboard(); renderFleet(); renderMachine360(); renderNetwork(); renderHardware(); renderSoftware(); renderUsb(); if(state.page==='changes') renderChanges(false); if(state.page==='history') renderHistory(); if(state.page==='messages') renderMessages(); }
function switchPage(page){ state.page=page; $$('.page').forEach(p=>p.classList.remove('active')); $('#page-'+page)?.classList.add('active'); $$('.nav').forEach(n=>n.classList.toggle('active',n.dataset.page===page)); const titles={dashboard:['Command Center','Colorful system-wise command analysis, ISP health, downloads, alerts and history.'],fleet:['Machine Fleet','All Windows and Ubuntu systems, stable and searchable.'],machine360:['Machine 360','Select one system and export its current details.'],network:['Network + VPN','LAN, VLAN, Wi-Fi, virtual adapters and VPN visibility.'],hardware:['Hardware Analytics','CPU, RAM, disk, temperature and GPU inventory.'],software:['Software Inventory','System-wise installed applications with admin export.'],usb:['USB + Peripherals','Human-readable keyboard, mouse, headset, camera, storage and USB network devices.'],changes:['Human Change Log','Readable system-wise timeline for USB, software, hardware, IP and VPN changes.'],history:['Day History','Old day data with system-wise download/upload and exports.'],messages:['Client Messages','Send closeable popup messages to Windows and Ubuntu clients.'],notifications:['Notifications','Create, edit, delete and test alert rules.'],deploy:['Deploy','Copy-ready current commands for Windows and Ubuntu clients.'],settings:['Settings','Users, password and refresh control.']}; const [t,sub]=titles[page]||titles.dashboard; $('#pageTitle').textContent=t; $('#pageSubtitle').textContent=sub; showBanner(state.pendingUpdate && quietPages.has(page)); renderAll(); if(page==='notifications') loadRules(); if(page==='messages') renderMessages(); if(page==='changes') renderChanges(true); if(page==='settings' && isAdmin()) loadUsers(); applyRoleControls(); }

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

/* custom-deploy-v2: editable Deploy command cards only */
const DEFAULT_DEPLOY_COMMANDS_V2 = [
  {
    id:'win_install_domain',
    title:'Windows install / update - domain',
    note:'Run in PowerShell as Administrator on Windows client.',
    code:`mkdir C:\\Temp -Force
Remove-Item C:\\Temp\\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -Force -ErrorAction SilentlyContinue
iwr "https://monitor.sagarkerhalkar.com/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1?restore=v84fixed" -OutFile C:\\Temp\\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1
powershell -ExecutionPolicy Bypass -File C:\\Temp\\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -ServerUrl "https://monitor.sagarkerhalkar.com" -FileServerUrl "https://monitor.sagarkerhalkar.com" -IntervalSeconds 5`
  },
  {
    id:'win_install_ip',
    title:'Windows install / update - IP fallback',
    note:'Use when client DNS cannot resolve monitor.sagarkerhalkar.com.',
    code:`mkdir C:\\Temp -Force
Remove-Item C:\\Temp\\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -Force -ErrorAction SilentlyContinue
iwr "http://156.156.40.51:2278/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1?restore=v84fixed" -OutFile C:\\Temp\\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1
powershell -ExecutionPolicy Bypass -File C:\\Temp\\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -ServerUrl "http://156.156.40.51:2278" -FileServerUrl "http://156.156.40.51:2278" -IntervalSeconds 5`
  },
  {
    id:'win_test',
    title:'Windows test / diagnosis',
    note:'Check status, messages, visible data, USB and diagnosis.',
    code:`Copy-Item C:\\ProgramData\\SagarSystemMonitor\\client_status.json C:\\Temp\\client_status_copy.json -Force -ErrorAction SilentlyContinue
type C:\\Temp\\client_status_copy.json
type C:\\ProgramData\\SagarSystemMonitor\\server_messages.log
powershell -ExecutionPolicy Bypass -File C:\\Temp\\SagarSystemMonitor\\CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1 -ServerUrl "https://monitor.sagarkerhalkar.com"
powershell -ExecutionPolicy Bypass -File C:\\Temp\\SagarSystemMonitor\\CHECK_WINDOWS_USB_MESSAGES.ps1 -ServerUrl "https://monitor.sagarkerhalkar.com"
powershell -ExecutionPolicy Bypass -File C:\\Temp\\SagarSystemMonitor\\DIAGNOSE_WINDOWS_CLIENT_2278.ps1 -ServerUrl "https://monitor.sagarkerhalkar.com"`
  },
  {
    id:'ubuntu_install_domain',
    title:'Ubuntu install / update - domain',
    note:'Run in Ubuntu terminal. Installs/updates systemd service.',
    code:`PUBLIC_URL="https://monitor.sagarkerhalkar.com"
curl -fsSL "$PUBLIC_URL/scripts/BOOTSTRAP_UBUNTU_CLIENT_2278.sh?restore=v84fixed" -o /tmp/bootstrap.sh
sudo SERVER_URL="$PUBLIC_URL" FILE_SERVER_URL="$PUBLIC_URL" INTERVAL_SECONDS=5 bash /tmp/bootstrap.sh`
  },
  {
    id:'ubuntu_install_ip',
    title:'Ubuntu install / update - IP fallback',
    note:'Use when client DNS cannot resolve monitor.sagarkerhalkar.com.',
    code:`PUBLIC_URL="http://156.156.40.51:2278"
curl -fsSL "$PUBLIC_URL/scripts/BOOTSTRAP_UBUNTU_CLIENT_2278.sh?restore=v84fixed" -o /tmp/bootstrap.sh
sudo SERVER_URL="$PUBLIC_URL" FILE_SERVER_URL="$PUBLIC_URL" INTERVAL_SECONDS=5 bash /tmp/bootstrap.sh`
  },
  {
    id:'ubuntu_test',
    title:'Ubuntu test / diagnosis',
    note:'Check heartbeat, local message log, service, journal and server health.',
    code:`sudo cat /var/lib/commercial-monitor-pro/client_status.json
sudo cat /var/lib/commercial-monitor-pro/server_messages.log
sudo systemctl status sagar-system-monitor-client.service
sudo journalctl -u sagar-system-monitor-client.service -n 80 --no-pager
curl -fsSL https://monitor.sagarkerhalkar.com/api/health`
  },
  {
    id:'server_autostart',
    title:'Server autostart',
    note:'Run on server Windows machine from app folder.',
    code:`cd D:\\SagarSystemHealthMonitor
powershell -ExecutionPolicy Bypass -File .\\INSTALL_SERVER_AUTOSTART_TASK.ps1`
  },
  {
    id:'build_windows_exe',
    title:'Build Windows EXE',
    note:'Optional packaging command.',
    code:`cd D:\\SagarSystemHealthMonitor
powershell -ExecutionPolicy Bypass -File .\\BUILD_WINDOWS_CLIENT_EXE.ps1 -ServerUrl "https://monitor.sagarkerhalkar.com"`
  }
];

let deployEditModeV2 = false;

function getDeployCommands(){
  const raw = state?.overview?.settings?.deploy_commands_json || '';
  if(raw){
    try{
      const parsed = JSON.parse(raw);
      if(Array.isArray(parsed) && parsed.length) return parsed;
    }catch(e){}
  }
  return DEFAULT_DEPLOY_COMMANDS_V2;
}

function renderDeployCommands(editMode){
  const mount = $('#deployCommandsMount');
  if(!mount) return;
  if(typeof editMode === 'boolean') deployEditModeV2 = editMode;
  const cmds = getDeployCommands();
  const adminButtons = isAdmin() ? `<div class="deploy-save-row"><button class="btn primary" onclick="saveDeployCommands()">Save Commands</button><button class="btn" onclick="renderDeployCommands(false)">Cancel Edit</button></div>` : '';
  mount.innerHTML = (deployEditModeV2 ? adminButtons : '') + cmds.map((c,i)=>{
    const code = String(c.code || '');
    if(deployEditModeV2 && isAdmin()){
      return `<article class="deploy-command-card">
        <label class="label">Title</label>
        <input class="full deploy-title-input" data-i="${i}" value="${esc(c.title||'')}" />
        <label class="label">Note</label>
        <input class="full deploy-note-input" data-i="${i}" value="${esc(c.note||'')}" />
        <label class="label">Command</label>
        <textarea class="full deploy-code-input" data-i="${i}" rows="8">${esc(code)}</textarea>
      </article>`;
    }
    return `<article class="deploy-command-card">
      <div class="deploy-card-top">
        <div><h3>${esc(c.title||'Command')}</h3><p>${esc(c.note||'')}</p></div>
        <button class="btn small primary" onclick="copyDeployCommandV2(${i}, this)">Copy</button>
      </div>
      <pre>${esc(code)}</pre>
    </article>`;
  }).join('') + (deployEditModeV2 ? adminButtons : '');
}

async function copyDeployCommandV2(i, btn){
  const cmd = getDeployCommands()[i];
  if(!cmd) return;
  const text = String(cmd.code || '').trim();
  const old = btn ? btn.textContent : 'Copy';
  try{
    if(navigator.clipboard && window.isSecureContext){
      await navigator.clipboard.writeText(text);
    }else{
      const ta=document.createElement('textarea');
      ta.value=text; ta.style.position='fixed'; ta.style.left='-9999px';
      document.body.appendChild(ta); ta.focus(); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
    }
    if(btn){ btn.textContent='Copied'; setTimeout(()=>btn.textContent=old,1200); }
  }catch(e){
    alert('Copy failed. Select command text manually.');
  }
}

async function saveDeployCommands(){
  if(!isAdmin()) return alert('Admin login required.');
  const old = getDeployCommands();
  const next = old.map((c,i)=>({
    id: c.id || ('cmd_'+i),
    title: document.querySelector(`.deploy-title-input[data-i="${i}"]`)?.value || c.title || '',
    note: document.querySelector(`.deploy-note-input[data-i="${i}"]`)?.value || c.note || '',
    code: document.querySelector(`.deploy-code-input[data-i="${i}"]`)?.value || c.code || ''
  }));
  await api('/api/settings', {method:'POST', body:JSON.stringify({deploy_commands_json:JSON.stringify(next)})});
  if(!state.overview) state.overview = {};
  if(!state.overview.settings) state.overview.settings = {};
  state.overview.settings.deploy_commands_json = JSON.stringify(next);
  deployEditModeV2 = false;
  renderDeployCommands(false);
  alert('Deploy commands saved.');
}

async function resetDeployCommands(){
  if(!isAdmin()) return alert('Admin login required.');
  if(!confirm('Reset Deploy commands to default Windows/Ubuntu commands?')) return;
  await api('/api/settings', {method:'POST', body:JSON.stringify({deploy_commands_json:JSON.stringify(DEFAULT_DEPLOY_COMMANDS_V2)})});
  if(!state.overview) state.overview = {};
  if(!state.overview.settings) state.overview.settings = {};
  state.overview.settings.deploy_commands_json = JSON.stringify(DEFAULT_DEPLOY_COMMANDS_V2);
  deployEditModeV2 = false;
  renderDeployCommands(false);
  alert('Deploy commands reset.');
}



/* login-experience-v1 */
document.documentElement.classList.toggle('reduced-motion', window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);



/* display-only-gpu-command-text-fix-v1
   Safe frontend override only. Does not change login, client, server, DB, notifications.
*/
function isIntegratedGpuDisplayName(name){
  return /Intel|UHD|Iris|Radeon\(TM\) Graphics|Radeon Graphics|Vega|Integrated/i.test(String(name||''));
}
function displayGpuMemoryMb(m,g){
  const name = String(g?.name || g?.gpu_name || '');
  const shared = Number(g?.shared_memory_mb || 0);
  const dedicated = Number(g?.dedicated_memory_mb || g?.memory_total_mb || g?.adapter_ram_mb || 0);
  const totalRamGb = Number(m?.ram_total_gb || nested(payload(m),'hardware.memory.total_gb',0) || 0);
  if(shared > 0) return shared;
  if(isIntegratedGpuDisplayName(name) && totalRamGb > 0) return totalRamGb * 1024 / 2;
  return dedicated;
}
function fmtGpuMemDisplay(mb){
  const x = Number(mb);
  if(!Number.isFinite(x) || x <= 0) return 'N/A';
  return x >= 1024 ? `${(x/1024).toFixed(1).replace(/\.0$/,'')} GB` : `${Math.round(x)} MB`;
}
function displayGpuUsage(g){
  const src = String(g?.source || '').toLowerCase();
  const name = String(g?.name || g?.gpu_name || '');
  const u = g?.usage_percent ?? g?.utilization_gpu ?? g?.load_percent;
  if(src && src !== 'nvidia-smi') return 'N/A';
  if(isIntegratedGpuDisplayName(name) && !src.includes('nvidia')) return 'N/A';
  return fmt(u,'%');
}
function displayGpuTotalMemory(m){
  const p = payload(m);
  const gpus = arr(nested(p,'hardware.gpus',[])).filter(x=>typeof x==='object');
  const values = gpus.map(g=>displayGpuMemoryMb(m,g)).filter(v=>Number.isFinite(Number(v)) && Number(v)>0);
  if(values.length) return Math.max(...values);
  const s = Number(m?.gpu_total_memory_mb || 0);
  return s > 0 ? s : 0;
}
function displayGpuDetailsHtml(m){
  const p = payload(m);
  const gpus = arr(nested(p,'hardware.gpus',[])).filter(x=>typeof x==='object');
  if(!gpus.length) return '<p>No GPU data</p>';
  return gpus.map(g=>{
    const name = esc(String(g.name || g.gpu_name || 'GPU').replace(/^\s*\d{2}:\d{2}\.\d+\s+[^:]+:\s*/,'').trim());
    const memory = fmtGpuMemDisplay(displayGpuMemoryMb(m,g));
    const usage = displayGpuUsage(g);
    const temp = fmt(g.temperature_c ?? g.temp_c,' C');
    const src = esc(g.source || '');
    return `<div class="gpu-line"><strong>${name}</strong><small>Memory: ${memory} | Usage: ${usage} | Temp: ${temp}${src ? ' | Source: '+src : ''}</small></div>`;
  }).join('');
}
function roleLabel(){return `${state.username||'user'} - ${state.role||'viewer'}`;}
function machineLabel(m){return `${host(m)} - ${m.primary_ip||((m.all_ips||[])[0]||'No IP')}`;}
function renderCommandSystemSpotlight(m){
  const el=$('#commandSystemSpotlight'); if(!el) return;
  if(!m){ el.innerHTML='<div class="empty">No client data yet.</div>'; return; }
  el.innerHTML=`<div class="spot-head"><div><span class="eyebrow">Selected System Analytics</span><h2>${esc(host(m))}</h2><p>${esc(m.primary_ip||'No IP')} - ${esc(m.os||'')}</p></div>${statusPill(m)}</div><div class="ring-row">${ring('CPU',m.cpu_percent)}${ring('RAM',m.ram_percent)}${ring('Disk',m.disk_max_percent)}</div><div class="spot-kv"><div><span>Download now</span><strong>${fmt(m.wan_download_mbps,' Mbps',2)}</strong></div><div><span>Upload now</span><strong>${fmt(m.wan_upload_mbps,' Mbps',2)}</strong></div><div><span>Today data</span><strong>Down ${fmt(m.today_download_gb,' GB',2)} / Up ${fmt(m.today_upload_gb,' GB',2)}</strong></div><div><span>Inventory</span><strong>${esc(m.usb_count||0)} USB - ${esc(m.software_count||0)} apps</strong></div></div><div class="spot-actions"><button class="btn small" onclick="switchPage('machine360')">Open 360</button><button class="btn small download-only" onclick="downloadCurrentMachine()">Download selected CSV</button></div>`;
}
function renderMachine360(){
  const m=selectedMachine('machineSelect'); const el=$('#machineDetails'); if(!el)return;
  if(!m){el.innerHTML='<div class="empty">Select one machine.</div>';return;}
  const p=payload(m);
  const gpuTotalMb = displayGpuTotalMemory(m);
  el.innerHTML=[
    detail('Identity',[['Status',statusPill(m)],['Machine',esc(host(m))],['Machine ID',`<code>${esc(m.machine_id)}</code>`],['OS',esc(m.os||'')],['Last Seen',ago(m.updated_at)]]),
    detail('Live Usage',[['CPU',fmt(m.cpu_percent,'%')],['CPU Temp',fmt(m.cpu_temp_c,' C')],['RAM',`${fmt(m.ram_used_gb,' GB')} / ${fmt(m.ram_total_gb,' GB')} (${fmt(m.ram_percent,'%')})`],['Disk Max',fmt(m.disk_max_percent,'%')],['Network Now',`Down ${fmt(m.wan_download_mbps,' Mbps',2)} / Up ${fmt(m.wan_upload_mbps,' Mbps',2)}`]]),
    detail('Network',[['Primary IP',esc(m.primary_ip||'')],['Public IP',esc(m.public_ip||'')],['ISP',esc(m.isp_name||'')],['VPN',m.vpn_active?'Active':'Not detected'],['All IPs',esc((m.all_ips||[]).join(', '))]]),
    detail('Inventory',[['USB / Peripherals',esc(m.usb_count||0)],['Installed Apps',esc(m.software_count||0)],['GPU Count',esc(m.gpu_count||0)],['GPU Max Usage',fmt(m.gpu_max_usage,'%')],['GPU Temp',fmt(m.gpu_max_temp_c,' C')],['GPU Memory Total',fmtGpuMemDisplay(gpuTotalMb)],['Agent',esc(nested(p,'agent.version',''))]]),
    `<article class="detail-card machine-gpu-detail"><h3>GPU Details</h3>${displayGpuDetailsHtml(m)}</article>`
  ].join('');
}
function renderHardware(){
  const el=$('#hardwareCards'); if(!el)return;
  el.innerHTML=state.machines.map(m=>{
    const p=payload(m); const cpu=nested(p,'hardware.cpu',{}), mem=nested(p,'hardware.memory',{}), disks=arr(nested(p,'storage.disks',[]));
    return `<article class="hw-card"><h3>${esc(host(m))}</h3><div class="kv"><span>CPU</span><strong>${esc(cpu.name||'')}</strong></div><div class="kv"><span>Cores / Threads</span><strong>${esc(cpu.cores||'')} / ${esc(cpu.threads||'')}</strong></div><div class="kv"><span>RAM</span><strong>${fmt(mem.used_gb,' GB')} / ${fmt(mem.total_gb,' GB')}</strong></div><div class="kv"><span>CPU Temp</span><strong>${fmt(cpu.temperature_c,' C')}</strong></div><h4>Disks</h4>${disks.map(d=>`<p>${esc(d.mount||d.name)}: ${fmt(d.used_percent,'%')} of ${fmt(d.total_gb,' GB')}</p>`).join('')||'<p>No disk data</p>'}<h4>GPU</h4>${displayGpuDetailsHtml(m)}</article>`;
  }).join('') || '<div class="empty">No hardware data.</div>';
}



/* strict-actual-gpu-display-v1
   Frontend display override: no RAM/2 fake values. Use only payload fields collected from client.
*/
function strictGpuIsIntegrated(name){ return /Intel|UHD|Iris|Radeon\(TM\) Graphics|Radeon Graphics|Vega|Integrated/i.test(String(name||'')); }
function strictGpuMemMb(g){
  const name = String(g?.name || g?.gpu_name || '');
  const src = String(g?.source || '');
  const shared = Number(g?.shared_memory_mb || 0);
  const total = Number(g?.memory_total_mb || 0);
  const dedicated = Number(g?.dedicated_memory_mb || g?.adapter_ram_mb || 0);
  if(strictGpuIsIntegrated(name)){
    if(shared > 0) return shared;
    if(src.toLowerCase().includes('dxdiag') && total > 0) return total;
    return 0;
  }
  if(total > 0) return total;
  if(dedicated > 0) return dedicated;
  return 0;
}
function strictFmtMemMb(mb){
  const x = Number(mb);
  if(!Number.isFinite(x) || x <= 0) return 'N/A';
  return x >= 1024 ? `${(x/1024).toFixed(1).replace(/\.0$/,'')} GB` : `${Math.round(x)} MB`;
}
function strictGpuUsage(g){
  const src = String(g?.source || '').toLowerCase();
  const u = g?.usage_percent ?? g?.utilization_gpu ?? g?.load_percent;
  if(src === 'nvidia-smi') return fmt(u,'%');
  return 'N/A';
}
function strictGpuTotalMb(m){
  const gpus = arr(nested(payload(m),'hardware.gpus',[])).filter(x=>typeof x==='object');
  const vals = gpus.map(strictGpuMemMb).filter(v=>Number.isFinite(Number(v)) && Number(v)>0);
  return vals.length ? Math.max(...vals) : 0;
}
function strictGpuDetailsHtml(m){
  const gpus = arr(nested(payload(m),'hardware.gpus',[])).filter(x=>typeof x==='object');
  if(!gpus.length) return '<p>No GPU data</p>';
  return gpus.map(g=>{
    const name = esc(String(g.name || g.gpu_name || 'GPU').replace(/^\s*\d{2}:\d{2}\.\d+\s+[^:]+:\s*/,'').trim());
    const memory = strictFmtMemMb(strictGpuMemMb(g));
    const dedicated = strictFmtMemMb(g.dedicated_memory_mb || g.adapter_ram_mb || 0);
    const shared = strictFmtMemMb(g.shared_memory_mb || 0);
    const usage = strictGpuUsage(g);
    const temp = fmt(g.temperature_c ?? g.temp_c,' C');
    const src = esc(g.source || '');
    return `<div class="gpu-line"><strong>${name}</strong><small>Memory: ${memory} | Dedicated: ${dedicated} | Shared: ${shared} | Usage: ${usage} | Temp: ${temp}${src ? ' | Source: '+src : ''}</small></div>`;
  }).join('');
}
function roleLabel(){return `${state.username||'user'} - ${state.role||'viewer'}`;}
function machineLabel(m){return `${host(m)} - ${m.primary_ip||((m.all_ips||[])[0]||'No IP')}`;}
function renderCommandSystemSpotlight(m){
  const el=$('#commandSystemSpotlight'); if(!el) return;
  if(!m){ el.innerHTML='<div class="empty">No client data yet.</div>'; return; }
  el.innerHTML=`<div class="spot-head"><div><span class="eyebrow">Selected System Analytics</span><h2>${esc(host(m))}</h2><p>${esc(m.primary_ip||'No IP')} - ${esc(m.os||'')}</p></div>${statusPill(m)}</div><div class="ring-row">${ring('CPU',m.cpu_percent)}${ring('RAM',m.ram_percent)}${ring('Disk',m.disk_max_percent)}</div><div class="spot-kv"><div><span>Download now</span><strong>${fmt(m.wan_download_mbps,' Mbps',2)}</strong></div><div><span>Upload now</span><strong>${fmt(m.wan_upload_mbps,' Mbps',2)}</strong></div><div><span>Today data</span><strong>Down ${fmt(m.today_download_gb,' GB',2)} / Up ${fmt(m.today_upload_gb,' GB',2)}</strong></div><div><span>Inventory</span><strong>${esc(m.usb_count||0)} USB - ${esc(m.software_count||0)} apps</strong></div></div><div class="spot-actions"><button class="btn small" onclick="switchPage('machine360')">Open 360</button><button class="btn small download-only" onclick="downloadCurrentMachine()">Download selected CSV</button></div>`;
}
function renderMachine360(){
  const m=selectedMachine('machineSelect'); const el=$('#machineDetails'); if(!el)return;
  if(!m){el.innerHTML='<div class="empty">Select one machine.</div>';return;}
  const p=payload(m);
  const gpuTotalMb = strictGpuTotalMb(m);
  el.innerHTML=[
    detail('Identity',[['Status',statusPill(m)],['Machine',esc(host(m))],['Machine ID',`<code>${esc(m.machine_id)}</code>`],['OS',esc(m.os||'')],['Last Seen',ago(m.updated_at)]]),
    detail('Live Usage',[['CPU',fmt(m.cpu_percent,'%')],['CPU Temp',fmt(m.cpu_temp_c,' C')],['RAM',`${fmt(m.ram_used_gb,' GB')} / ${fmt(m.ram_total_gb,' GB')} (${fmt(m.ram_percent,'%')})`],['Disk Max',fmt(m.disk_max_percent,'%')],['Network Now',`Down ${fmt(m.wan_download_mbps,' Mbps',2)} / Up ${fmt(m.wan_upload_mbps,' Mbps',2)}`]]),
    detail('Network',[['Primary IP',esc(m.primary_ip||'')],['Public IP',esc(m.public_ip||'')],['ISP',esc(m.isp_name||'')],['VPN',m.vpn_active?'Active':'Not detected'],['All IPs',esc((m.all_ips||[]).join(', '))]]),
    detail('Inventory',[['USB / Peripherals',esc(m.usb_count||0)],['Installed Apps',esc(m.software_count||0)],['GPU Count',esc(m.gpu_count||0)],['GPU Max Usage',fmt(m.gpu_max_usage,'%')],['GPU Temp',fmt(m.gpu_max_temp_c,' C')],['GPU Memory Total',strictFmtMemMb(gpuTotalMb)],['Agent',esc(nested(p,'agent.version',''))]]),
    `<article class="detail-card machine-gpu-detail"><h3>GPU Details</h3>${strictGpuDetailsHtml(m)}</article>`
  ].join('');
}
function renderHardware(){
  const el=$('#hardwareCards'); if(!el)return;
  el.innerHTML=state.machines.map(m=>{
    const p=payload(m); const cpu=nested(p,'hardware.cpu',{}), mem=nested(p,'hardware.memory',{}), disks=arr(nested(p,'storage.disks',[]));
    return `<article class="hw-card"><h3>${esc(host(m))}</h3><div class="kv"><span>CPU</span><strong>${esc(cpu.name||'')}</strong></div><div class="kv"><span>Cores / Threads</span><strong>${esc(cpu.cores||'')} / ${esc(cpu.threads||'')}</strong></div><div class="kv"><span>RAM</span><strong>${fmt(mem.used_gb,' GB')} / ${fmt(mem.total_gb,' GB')}</strong></div><div class="kv"><span>CPU Temp</span><strong>${fmt(cpu.temperature_c,' C')}</strong></div><h4>Disks</h4>${disks.map(d=>`<p>${esc(d.mount||d.name)}: ${fmt(d.used_percent,'%')} of ${fmt(d.total_gb,' GB')}</p>`).join('')||'<p>No disk data</p>'}<h4>GPU</h4>${strictGpuDetailsHtml(m)}</article>`;
  }).join('') || '<div class="empty">No hardware data.</div>';
}

/* attention-click-navigation-fix: click Attention count -> Fleet filtered to Needs attention */
document.addEventListener('DOMContentLoaded', bindAttentionClick);
setInterval(bindAttentionClick, 1000);

/* MACHINE_360_FULL_PAGE_ONLY_START */
/*
  Machine 360 premium UI override.
  Scope: only #page-machine360 and renderMachine360().
  Other pages, server.py, dashboard, fleet, hardware, USB, software are untouched.
*/
function m360InstallScopedStyle(){
  const old=document.getElementById('m360ScopedStyle');
  if(old) old.remove();
  const css = `
    #page-machine360{
      --m360-blue:#2563eb;
      --m360-cyan:#06b6d4;
      --m360-indigo:#4f46e5;
      --m360-ink:#0f172a;
      --m360-muted:#64748b;
      --m360-line:rgba(148,163,184,.26);
      --m360-soft:#f8fbff;
      --m360-glass:rgba(255,255,255,.82);
      --m360-shadow:0 24px 80px rgba(30,64,175,.16);
      --m360-shadow2:0 14px 34px rgba(15,23,42,.10);
      font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
    }
    #page-machine360 .panel{overflow:visible}
    #page-machine360 #machineDetails,
    #page-machine360 .machine-details{
      display:block!important;
      width:100%!important;
      max-width:none!important;
      min-width:0!important;
    }
    #page-machine360 .m360-shell{
      position:relative;
      width:100%;
      color:var(--m360-ink);
      animation:m360FadeUp .45s ease both;
    }
    #page-machine360 .m360-hero{
      position:relative;
      overflow:hidden;
      border-radius:30px;
      padding:24px;
      background:
        radial-gradient(circle at 12% 15%, rgba(59,130,246,.34), transparent 30%),
        radial-gradient(circle at 88% 16%, rgba(6,182,212,.28), transparent 31%),
        linear-gradient(135deg, rgba(255,255,255,.96), rgba(239,246,255,.90));
      border:1px solid rgba(255,255,255,.85);
      box-shadow:var(--m360-shadow);
      isolation:isolate;
    }
    #page-machine360 .m360-hero:before{
      content:"";
      position:absolute;
      inset:-80px;
      background:conic-gradient(from 130deg, rgba(37,99,235,.12), rgba(6,182,212,.22), rgba(79,70,229,.12), rgba(37,99,235,.12));
      filter:blur(18px);
      animation:m360Aurora 9s linear infinite;
      z-index:-1;
    }
    #page-machine360 .m360-hero-top{
      display:flex;
      justify-content:space-between;
      align-items:flex-start;
      gap:18px;
      flex-wrap:wrap;
    }
    #page-machine360 .m360-eyebrow{
      letter-spacing:.24em;
      text-transform:uppercase;
      font-size:11px;
      font-weight:900;
      color:var(--m360-blue);
      margin:0 0 8px;
    }
    #page-machine360 .m360-hero h2{
      margin:0;
      font-size:clamp(26px,3vw,44px);
      line-height:1.03;
      letter-spacing:-.04em;
      color:#08111f;
    }
    #page-machine360 .m360-sub{
      margin:10px 0 0;
      color:var(--m360-muted);
      font-weight:650;
      font-size:14px;
    }
    #page-machine360 .m360-status{
      display:flex;
      gap:10px;
      align-items:center;
      flex-wrap:wrap;
    }
    #page-machine360 .m360-status .pill{
      transform:scale(1.05);
      box-shadow:0 10px 24px rgba(34,197,94,.18);
    }
    #page-machine360 .m360-chips{
      margin-top:22px;
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
      gap:12px;
    }
    #page-machine360 .m360-chip{
      position:relative;
      overflow:hidden;
      border-radius:20px;
      padding:14px 15px;
      background:rgba(255,255,255,.78);
      border:1px solid rgba(255,255,255,.86);
      box-shadow:0 12px 30px rgba(30,64,175,.10);
      backdrop-filter:blur(16px);
      transition:transform .22s ease, box-shadow .22s ease;
    }
    #page-machine360 .m360-chip:hover,
    #page-machine360 .m360-card:hover{
      transform:translateY(-3px);
      box-shadow:0 24px 55px rgba(30,64,175,.16);
    }
    #page-machine360 .m360-chip span{
      display:block;
      color:var(--m360-muted);
      font-size:11px;
      font-weight:850;
      text-transform:uppercase;
      letter-spacing:.08em;
    }
    #page-machine360 .m360-chip strong{
      display:block;
      margin-top:6px;
      font-size:20px;
      color:#0f172a;
      letter-spacing:-.02em;
    }
    #page-machine360 .m360-layout{
      margin-top:18px;
      display:grid;
      grid-template-columns:repeat(12,1fr);
      gap:16px;
      align-items:start;
    }
    #page-machine360 .m360-card{
      grid-column:span 4;
      border-radius:24px;
      background:var(--m360-glass);
      border:1px solid rgba(255,255,255,.82);
      box-shadow:var(--m360-shadow2);
      padding:18px;
      backdrop-filter:blur(18px);
      min-width:0;
      animation:m360FadeUp .45s ease both;
    }
    #page-machine360 .m360-card.m360-wide{grid-column:1/-1}
    #page-machine360 .m360-card.m360-half{grid-column:span 6}
    #page-machine360 .m360-card h3{
      margin:0 0 14px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:10px;
      font-size:17px;
      letter-spacing:-.02em;
      color:#0f172a;
    }
    #page-machine360 .m360-badge{
      display:inline-flex;
      align-items:center;
      border-radius:999px;
      padding:5px 10px;
      font-size:11px;
      font-weight:900;
      color:#1d4ed8;
      background:rgba(37,99,235,.10);
      border:1px solid rgba(37,99,235,.18);
    }
    #page-machine360 .m360-kv{
      display:grid;
      grid-template-columns:minmax(120px,170px) 1fr;
      gap:9px 12px;
      padding:9px 0;
      border-bottom:1px dashed var(--m360-line);
      align-items:start;
    }
    #page-machine360 .m360-kv:last-child{border-bottom:0}
    #page-machine360 .m360-kv span{
      color:var(--m360-muted);
      font-size:12px;
      font-weight:800;
    }
    #page-machine360 .m360-kv strong{
      color:#0f172a;
      font-size:13px;
      word-break:break-word;
      font-weight:850;
    }
    #page-machine360 code{
      color:#1e3a8a;
      background:rgba(37,99,235,.07);
      border:1px solid rgba(37,99,235,.13);
      border-radius:8px;
      padding:2px 5px;
      font-family:"Cascadia Code","Consolas",monospace;
      font-size:11px;
    }
    #page-machine360 .m360-scroll{
      width:100%;
      max-height:520px;
      overflow:auto;
      border-radius:18px;
      border:1px solid rgba(148,163,184,.24);
      background:rgba(255,255,255,.66);
    }
    #page-machine360 .m360-table{
      width:100%;
      border-collapse:separate;
      border-spacing:0;
      min-width:780px;
      font-size:13px;
    }
    #page-machine360 .m360-table th{
      position:sticky;
      top:0;
      z-index:2;
      text-align:left;
      padding:12px;
      color:#334155;
      background:linear-gradient(180deg,#f8fbff,#eef6ff);
      border-bottom:1px solid rgba(148,163,184,.28);
      font-size:12px;
      text-transform:uppercase;
      letter-spacing:.08em;
    }
    #page-machine360 .m360-table td{
      padding:12px;
      border-bottom:1px solid rgba(148,163,184,.16);
      color:#0f172a;
      vertical-align:top;
      font-weight:650;
    }
    #page-machine360 .m360-table tr:hover td{
      background:rgba(37,99,235,.045);
    }
    #page-machine360 .m360-table small{
      display:block;
      color:var(--m360-muted);
      margin-top:4px;
      font-weight:650;
    }
    #page-machine360 .m360-empty{
      border-radius:18px;
      padding:18px;
      background:rgba(248,250,252,.8);
      color:var(--m360-muted);
      border:1px dashed rgba(100,116,139,.30);
      font-weight:750;
    }
    #page-machine360 .m360-actions{
      display:flex;
      gap:8px;
      flex-wrap:wrap;
      align-items:center;
    }
    #page-machine360 .m360-soft-btn{
      border:1px solid rgba(37,99,235,.18);
      background:linear-gradient(180deg,#fff,#eff6ff);
      color:#1d4ed8;
      border-radius:999px;
      padding:7px 12px;
      font-size:12px;
      font-weight:900;
      cursor:pointer;
    }
    #page-machine360 details.m360-details summary{cursor:pointer;font-weight:900;color:#1d4ed8}
    #page-machine360 details.m360-details pre{
      white-space:pre-wrap;
      max-height:360px;
      overflow:auto;
      background:#0b1220;
      color:#dbeafe;
      border-radius:16px;
      padding:14px;
      font-size:12px;
      line-height:1.55;
    }
    #page-machine360 .m360-ring-row{
      display:grid;
      grid-template-columns:repeat(3,minmax(0,1fr));
      gap:12px;
    }
    #page-machine360 .m360-meter{
      border-radius:18px;
      padding:14px;
      background:linear-gradient(180deg,rgba(255,255,255,.86),rgba(239,246,255,.76));
      border:1px solid rgba(255,255,255,.9);
      box-shadow:0 12px 24px rgba(30,64,175,.08);
    }
    #page-machine360 .m360-meter span{
      display:flex;
      justify-content:space-between;
      color:#334155;
      font-weight:900;
      font-size:12px;
      margin-bottom:8px;
    }
    #page-machine360 .m360-bar{
      height:10px;
      background:#e2e8f0;
      border-radius:999px;
      overflow:hidden;
    }
    #page-machine360 .m360-fill{
      height:100%;
      border-radius:999px;
      background:linear-gradient(90deg,var(--m360-blue),var(--m360-cyan));
      width:0;
      animation:m360Grow .8s ease forwards;
    }
    @keyframes m360FadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
    @keyframes m360Aurora{to{transform:rotate(360deg)}}
    @keyframes m360Grow{from{width:0}to{width:var(--w)}}
    @media(max-width:1100px){
      #page-machine360 .m360-card,#page-machine360 .m360-card.m360-half{grid-column:1/-1}
    }
    @media(max-width:720px){
      #page-machine360 .m360-hero{padding:18px;border-radius:22px}
      #page-machine360 .m360-kv{grid-template-columns:1fr}
      #page-machine360 .m360-ring-row{grid-template-columns:1fr}
    }
  `;
  const style=document.createElement('style');
  style.id='m360ScopedStyle';
  style.textContent=css;
  document.head.appendChild(style);
}
function m360List(v){
  try{ if(typeof arr === 'function') return arr(v); }catch(e){}
  if(v===null||v===undefined||v==='') return [];
  if(Array.isArray(v)) return v.flatMap(m360List);
  if(typeof v === 'object'){
    const direct=['name','display_name','class','type','device_id','vid','pid','version','publisher','mount','total_gb'];
    if(direct.some(k=>Object.prototype.hasOwnProperty.call(v,k))) return [v];
    return Object.values(v).flatMap(m360List);
  }
  return [v];
}
function m360Obj(v){return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {};}
function m360Text(v){return esc(v===undefined||v===null||v==='' ? 'N/A' : v);}
function m360Number(v){const n=Number(v||0); return Number.isFinite(n)?n:0;}
function m360Pct(v){return Math.max(0,Math.min(100,m360Number(v)));}
function m360Json(v){try{return esc(JSON.stringify(v,null,2));}catch(e){return esc(String(v||''));}}
function m360Meter(label,value){
  const p=m360Pct(value);
  return `<div class="m360-meter"><span><b>${esc(label)}</b><b>${fmt(p,'%')}</b></span><div class="m360-bar"><div class="m360-fill" style="--w:${p}%"></div></div></div>`;
}
function m360Table(headers, rows, emptyText){
  if(!rows || !rows.length) return `<div class="m360-empty">${esc(emptyText||'No data available.')}</div>`;
  return `<div class="m360-scroll"><table class="m360-table"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}
function m360DeviceName(u){return u.display_name || u.friendly_name || u.name || u.device_name || u.description || 'Unknown device';}
function m360SoftwareName(a){return a.name || a.display_name || a.DisplayName || a.package || 'Unknown software';}
function m360DiskName(d){return d.mount || d.name || d.device || d.drive || d.DriveLetter || 'Disk';}
function m360FmtMem(mb){try{return typeof fmtMemMb==='function'?fmtMemMb(mb):fmt(Number(mb||0)/1024,' GB');}catch(e){return 'N/A';}}

function renderMachine360(){
  m360InstallScopedStyle();
  const m=selectedMachine('machineSelect');
  const el=$('#machineDetails');
  if(!el) return;
  if(!m){el.innerHTML='<div class="m360-empty">Select one machine.</div>';return;}

  const p=payload(m);
  const identity=m360Obj(nested(p,'identity',{}));
  const osObj=m360Obj(nested(p,'os',{}));
  const cpu=m360Obj(nested(p,'hardware.cpu',{}));
  const mem=m360Obj(nested(p,'hardware.memory',{}));
  const network=m360Obj(nested(p,'network',{}));
  const traffic=m360Obj(nested(p,'network.traffic',{}));
  const vpn=m360Obj(nested(p,'network.vpn',{}));

  const disks=m360List(nested(p,'storage.disks',[])).filter(x=>x && typeof x==='object');
  const gpus=m360List(nested(p,'hardware.gpus',[])).filter(x=>x && typeof x==='object');
  const adapters=m360List(nested(p,'network.adapters',[])).filter(x=>x && typeof x==='object');
  const usbRaw=nested(p,'usb.devices',nested(p,'usb',[]));
  const usbDevices=(typeof cleanUsbItems==='function' ? cleanUsbItems(usbRaw) : m360List(usbRaw)).filter(x=>x && typeof x==='object');
  const apps=m360List(nested(p,'software.installed',nested(p,'software',[]))).filter(x=>x && typeof x==='object');
  const changes=m360List(p.changes||[]).filter(x=>x && typeof x==='object');

  const diskRows=disks.map(d=>`<tr>
    <td><strong>${m360Text(m360DiskName(d))}</strong><small>${m360Text(d.type||d.media_type||d.filesystem||'')}</small></td>
    <td>${fmt(d.used_percent ?? d.usage_percent,'%')}</td>
    <td>${fmt(d.total_gb ?? d.size_gb,' GB')}</td>
    <td>${fmt(d.used_gb,' GB')}</td>
    <td>${fmt(d.free_gb,' GB')}</td>
    <td><code>${m360Text(d.serial||d.model||d.device||'')}</code></td>
  </tr>`);

  const gpuRows=gpus.map(g=>`<tr>
    <td><strong>${m360Text(g.name||g.gpu_name||'GPU')}</strong><small>${m360Text(g.source||'client')}</small></td>
    <td>${fmt(g.usage_percent ?? g.utilization_gpu ?? g.load_percent,'%')}</td>
    <td>${fmt(g.temperature_c ?? g.temp_c,' C')}</td>
    <td>${m360FmtMem(g.memory_total_mb || g.adapter_ram_mb || g.dedicated_memory_mb || 0)}</td>
    <td>${m360FmtMem(g.memory_used_mb || 0)}</td>
    <td>${m360Text(g.driver_version||g.driver||'')}</td>
  </tr>`);

  const adapterRows=adapters.map(a=>{
    const ips=Array.isArray(a.ips||a.ip_addresses) ? (a.ips||a.ip_addresses).join(', ') : (a.ips||a.ip_addresses||'');
    return `<tr>
      <td><strong>${m360Text(a.name||'Adapter')}</strong><small>${m360Text(a.description||'')}</small></td>
      <td>${m360Text(ips)}</td>
      <td><code>${m360Text(a.mac||a.mac_address||a.MACAddress||'')}</code></td>
      <td>${a.is_vpn||a.vpn?'VPN':(a.is_virtual?'Virtual':'Physical')}</td>
      <td>${m360Text(a.status||a.oper_status||'')}</td>
    </tr>`;
  });

  const usbRows=usbDevices.map(u=>`<tr>
    <td><strong>${m360Text(m360DeviceName(u))}</strong><small>${m360Text(u.manufacturer||u.class||'Peripheral')}</small></td>
    <td>${m360Text(u.type||u.class||'Peripheral')}</td>
    <td>${m360Text(u.status||'')}</td>
    <td>${m360Text(u.vid||'')}</td>
    <td>${m360Text(u.pid||'')}</td>
    <td><details><summary>View ID</summary><code>${m360Text(u.device_id||u.instance_id||u.id||'')}</code></details></td>
  </tr>`);

  const appRows=apps.map(a=>`<tr>
    <td><strong>${m360Text(m360SoftwareName(a))}</strong></td>
    <td>${m360Text(a.version||'')}</td>
    <td>${m360Text(a.publisher||a.vendor||'')}</td>
    <td>${m360Text(typeof fmtInstallDate==='function' ? fmtInstallDate(a.install_date||a.installDate||'') : (a.install_date||a.installDate||''))}</td>
  </tr>`);

  const changeRows=changes.slice(0,80).map(c=>`<tr>
    <td>${m360Text(c.type||'change')}</td>
    <td>${m360Text(c.title||c.message||'')}</td>
    <td>${m360Text(c.created_at||c.time||'')}</td>
  </tr>`);

  const gpuTotal = gpus.length || m.gpu_count || 0;
  const allIps = Array.isArray(m.all_ips) ? m.all_ips.join(', ') : (m.all_ips||'');

  el.innerHTML=`
    <div class="m360-shell">
      <section class="m360-hero">
        <div class="m360-hero-top">
          <div>
            <p class="m360-eyebrow">Machine 360 Universal Inventory</p>
            <h2>${esc(host(m))}</h2>
            <p class="m360-sub">${m360Text(m.primary_ip||'No LAN IP')} Â· ${m360Text(m.os||osObj.name||'Unknown OS')} Â· Last seen ${ago(m.updated_at)}</p>
          </div>
          <div class="m360-status">${statusPill(m)}<button class="m360-soft-btn download-only" onclick="downloadCurrentMachine()">Download CSV</button></div>
        </div>
        <div class="m360-chips">
          <div class="m360-chip"><span>CPU</span><strong>${fmt(m.cpu_percent,'%')}</strong></div>
          <div class="m360-chip"><span>RAM</span><strong>${fmt(m.ram_used_gb,' GB')} / ${fmt(m.ram_total_gb,' GB')}</strong></div>
          <div class="m360-chip"><span>Disk Max</span><strong>${fmt(m.disk_max_percent,'%')}</strong></div>
          <div class="m360-chip"><span>Network Now</span><strong>${fmt(m.wan_download_mbps,' Mbps',2)} â†“</strong></div>
          <div class="m360-chip"><span>USB</span><strong>${usbDevices.length}</strong></div>
          <div class="m360-chip"><span>Software</span><strong>${apps.length}</strong></div>
          <div class="m360-chip"><span>GPU</span><strong>${gpuTotal}</strong></div>
        </div>
      </section>

      <section class="m360-layout">
        <article class="m360-card m360-wide">
          <h3>Live Health <span class="m360-badge">Animated</span></h3>
          <div class="m360-ring-row">
            ${m360Meter('CPU Usage',cpu.usage_percent ?? m.cpu_percent)}
            ${m360Meter('RAM Usage',mem.used_percent ?? m.ram_percent)}
            ${m360Meter('Disk Usage',m.disk_max_percent)}
          </div>
        </article>

        <article class="m360-card">
          <h3>Identity + OS <span class="m360-badge">Core</span></h3>
          <div class="m360-kv"><span>Machine ID</span><strong><code>${m360Text(m.machine_id)}</code></strong></div>
          <div class="m360-kv"><span>ID Source</span><strong>${m360Text(m.id_source)}</strong></div>
          <div class="m360-kv"><span>ID Value</span><strong>${m360Text(m.id_value)}</strong></div>
          <div class="m360-kv"><span>Hostname</span><strong>${m360Text(identity.hostname||m.hostname||host(m))}</strong></div>
          <div class="m360-kv"><span>OS</span><strong>${m360Text(osObj.name||m.os)}</strong></div>
          <div class="m360-kv"><span>Version</span><strong>${m360Text(osObj.version||osObj.build||'')}</strong></div>
          <div class="m360-kv"><span>System UUID</span><strong><code>${m360Text(identity.system_uuid||'')}</code></strong></div>
          <div class="m360-kv"><span>BIOS Serial</span><strong><code>${m360Text(identity.bios_serial||'')}</code></strong></div>
          <div class="m360-kv"><span>Board Serial</span><strong><code>${m360Text(identity.motherboard_serial||identity.baseboard_serial||'')}</code></strong></div>
        </article>

        <article class="m360-card">
          <h3>CPU + Memory <span class="m360-badge">Live</span></h3>
          <div class="m360-kv"><span>CPU Name</span><strong>${m360Text(cpu.name||cpu.model||'')}</strong></div>
          <div class="m360-kv"><span>Cores / Threads</span><strong>${m360Text(cpu.cores||'')} / ${m360Text(cpu.threads||'')}</strong></div>
          <div class="m360-kv"><span>CPU Usage</span><strong>${fmt(cpu.usage_percent ?? m.cpu_percent,'%')}</strong></div>
          <div class="m360-kv"><span>CPU Temp</span><strong>${fmt(cpu.temperature_c ?? m.cpu_temp_c,' C')}</strong></div>
          <div class="m360-kv"><span>RAM Total</span><strong>${fmt(mem.total_gb ?? m.ram_total_gb,' GB')}</strong></div>
          <div class="m360-kv"><span>RAM Used</span><strong>${fmt(mem.used_gb ?? m.ram_used_gb,' GB')}</strong></div>
          <div class="m360-kv"><span>RAM Free</span><strong>${fmt(mem.free_gb ?? m.ram_free_gb,' GB')}</strong></div>
          <div class="m360-kv"><span>RAM Usage</span><strong>${fmt(mem.used_percent ?? m.ram_percent,'%')}</strong></div>
        </article>

        <article class="m360-card">
          <h3>Network + Traffic <span class="m360-badge">WAN/LAN</span></h3>
          <div class="m360-kv"><span>Primary IP</span><strong>${m360Text(m.primary_ip||network.primary_ip||'')}</strong></div>
          <div class="m360-kv"><span>All IPs</span><strong>${m360Text(allIps)}</strong></div>
          <div class="m360-kv"><span>Public IP</span><strong>${m360Text(m.public_ip||'')}</strong></div>
          <div class="m360-kv"><span>ISP</span><strong>${m360Text(m.isp_name||'')}</strong></div>
          <div class="m360-kv"><span>VPN</span><strong>${m.vpn_active || vpn.active || vpn.is_active ? 'Active' : 'Not detected'}</strong></div>
          <div class="m360-kv"><span>Download Now</span><strong>${fmt(traffic.current_download_mbps ?? m.wan_download_mbps,' Mbps',2)}</strong></div>
          <div class="m360-kv"><span>Upload Now</span><strong>${fmt(traffic.current_upload_mbps ?? m.wan_upload_mbps,' Mbps',2)}</strong></div>
          <div class="m360-kv"><span>Today Data</span><strong>Down ${fmt(traffic.today_download_gb ?? m.today_download_gb,' GB',2)} / Up ${fmt(traffic.today_upload_gb ?? m.today_upload_gb,' GB',2)}</strong></div>
        </article>

        <article class="m360-card m360-wide">
          <h3>Disk / Storage - All Drives <span class="m360-badge">${disks.length} found</span></h3>
          ${m360Table(['Drive','Used %','Total','Used','Free','Serial / Model'],diskRows,'No disk/storage data from this client.')}
        </article>

        <article class="m360-card m360-wide">
          <h3>GPU - All Graphics Hardware <span class="m360-badge">${gpus.length} found</span></h3>
          ${m360Table(['GPU','Usage','Temp','Total Memory','Used Memory','Driver'],gpuRows,'No GPU data from this client.')}
        </article>

        <article class="m360-card m360-wide">
          <h3>Network Adapters - All NIC / Wi-Fi / VPN <span class="m360-badge">${adapters.length} found</span></h3>
          ${m360Table(['Adapter','IP Addresses','MAC','Type','Status'],adapterRows,'No adapter data from this client.')}
        </article>

        <article class="m360-card m360-wide">
          <h3>USB + Peripherals - All Devices <span class="m360-badge">${usbDevices.length} found</span></h3>
          ${m360Table(['Device','Type','Status','VID','PID','Technical ID'],usbRows,'No USB/peripheral data from this client.')}
        </article>

        <article class="m360-card m360-wide">
          <h3>Installed Software - All Applications <span class="m360-badge">${apps.length} found</span></h3>
          ${m360Table(['Name','Version','Publisher','Install Date'],appRows,'No installed software data from this client.')}
        </article>

        <article class="m360-card m360-half">
          <h3>Recent Client Changes <span class="m360-badge">${changes.length} event</span></h3>
          ${m360Table(['Type','Change','Time'],changeRows,'No recent change event sent by this client.')}
        </article>

        <article class="m360-card m360-half">
          <h3>Raw Payload For Debug <span class="m360-badge">Advanced</span></h3>
          <details class="m360-details"><summary>Open full raw JSON received from selected client</summary><pre>${m360Json(p)}</pre></details>
        </article>
      </section>
    </div>
  `;
}
/* MACHINE_360_FULL_PAGE_ONLY_END */

/* NETWORK_VPN_MACHINE_WISE_ONLY_START */
/* Only Network + VPN page UI is changed. */
function n360Style(){
  const old=document.getElementById('n360Style'); if(old) old.remove();
  const s=document.createElement('style'); s.id='n360Style';
  s.textContent=`
  #page-network{--b:#2563eb;--c:#06b6d4;--i:#0f172a;--m:#64748b;--line:rgba(148,163,184,.25);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
  #page-network #networkCards{display:block!important;width:100%!important;max-width:none!important}
  #page-network .n360-shell{width:100%;animation:n360Up .45s ease both;color:var(--i)}
  #page-network .n360-hero{position:relative;overflow:hidden;border-radius:30px;padding:24px;background:radial-gradient(circle at 10% 10%,rgba(37,99,235,.34),transparent 30%),radial-gradient(circle at 90% 18%,rgba(6,182,212,.28),transparent 30%),linear-gradient(135deg,rgba(255,255,255,.96),rgba(239,246,255,.90));border:1px solid rgba(255,255,255,.88);box-shadow:0 24px 80px rgba(30,64,175,.16);isolation:isolate}
  #page-network .n360-hero:before{content:"";position:absolute;inset:-90px;background:conic-gradient(from 140deg,rgba(37,99,235,.12),rgba(6,182,212,.22),rgba(79,70,229,.12),rgba(37,99,235,.12));filter:blur(18px);animation:n360Aura 9s linear infinite;z-index:-1}
  #page-network .n360-top{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;flex-wrap:wrap}
  #page-network .n360-eye{letter-spacing:.24em;text-transform:uppercase;font-size:11px;font-weight:900;color:var(--b);margin:0 0 8px}
  #page-network .n360-hero h2{margin:0;font-size:clamp(26px,3vw,44px);line-height:1.03;letter-spacing:-.04em;color:#08111f}
  #page-network .n360-sub{margin:10px 0 0;color:var(--m);font-weight:650;font-size:14px}
  #page-network .n360-select{min-width:320px;max-width:560px;border:1px solid rgba(37,99,235,.18);background:rgba(255,255,255,.92);color:#0f172a;border-radius:16px;padding:11px 14px;font-weight:800;outline:none;box-shadow:0 12px 26px rgba(30,64,175,.10)}
  #page-network .n360-chips{margin-top:22px;display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px}
  #page-network .n360-chip{border-radius:20px;padding:14px 15px;background:rgba(255,255,255,.80);border:1px solid rgba(255,255,255,.90);box-shadow:0 12px 30px rgba(30,64,175,.10);backdrop-filter:blur(16px);transition:.22s}
  #page-network .n360-chip:hover,#page-network .n360-card:hover{transform:translateY(-3px);box-shadow:0 24px 55px rgba(30,64,175,.16)}
  #page-network .n360-chip span{display:block;color:var(--m);font-size:11px;font-weight:850;text-transform:uppercase;letter-spacing:.08em}
  #page-network .n360-chip strong{display:block;margin-top:6px;font-size:20px;color:#0f172a;letter-spacing:-.02em;word-break:break-word}
  #page-network .n360-layout{margin-top:18px;display:grid;grid-template-columns:repeat(12,1fr);gap:16px;align-items:start}
  #page-network .n360-card{grid-column:span 4;border-radius:24px;background:rgba(255,255,255,.84);border:1px solid rgba(255,255,255,.82);box-shadow:0 14px 34px rgba(15,23,42,.10);padding:18px;backdrop-filter:blur(18px);min-width:0;animation:n360Up .45s ease both}
  #page-network .n360-wide{grid-column:1/-1}.n360-half{grid-column:span 6}
  #page-network .n360-card h3{margin:0 0 14px;display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:17px;letter-spacing:-.02em;color:#0f172a}
  #page-network .n360-badge{display:inline-flex;border-radius:999px;padding:5px 10px;font-size:11px;font-weight:900;color:#1d4ed8;background:rgba(37,99,235,.10);border:1px solid rgba(37,99,235,.18)}
  #page-network .n360-vpn-on{color:#b45309;background:rgba(245,158,11,.13);border-color:rgba(245,158,11,.24)}
  #page-network .n360-vpn-off{color:#047857;background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.22)}
  #page-network .n360-kv{display:grid;grid-template-columns:minmax(120px,170px) 1fr;gap:9px 12px;padding:9px 0;border-bottom:1px dashed var(--line);align-items:start}
  #page-network .n360-kv span{color:var(--m);font-size:12px;font-weight:800}
  #page-network .n360-kv strong{color:#0f172a;font-size:13px;word-break:break-word;font-weight:850}
  #page-network code{color:#1e3a8a;background:rgba(37,99,235,.07);border:1px solid rgba(37,99,235,.13);border-radius:8px;padding:2px 5px;font-family:"Cascadia Code","Consolas",monospace;font-size:11px}
  #page-network .n360-scroll{width:100%;max-height:540px;overflow:auto;border-radius:18px;border:1px solid rgba(148,163,184,.24);background:rgba(255,255,255,.66)}
  #page-network .n360-table{width:100%;border-collapse:separate;border-spacing:0;min-width:900px;font-size:13px}
  #page-network .n360-table th{position:sticky;top:0;z-index:2;text-align:left;padding:12px;color:#334155;background:linear-gradient(180deg,#f8fbff,#eef6ff);border-bottom:1px solid rgba(148,163,184,.28);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
  #page-network .n360-table td{padding:12px;border-bottom:1px solid rgba(148,163,184,.16);color:#0f172a;vertical-align:top;font-weight:650}
  #page-network .n360-table tr:hover td{background:rgba(37,99,235,.045)}
  #page-network .n360-table small{display:block;color:var(--m);margin-top:4px;font-weight:650}
  #page-network .n360-empty{border-radius:18px;padding:18px;background:rgba(248,250,252,.8);color:var(--m);border:1px dashed rgba(100,116,139,.30);font-weight:750}
  #page-network .n360-meter{border-radius:18px;padding:14px;background:linear-gradient(180deg,rgba(255,255,255,.86),rgba(239,246,255,.76));border:1px solid rgba(255,255,255,.9);box-shadow:0 12px 24px rgba(30,64,175,.08)}
  #page-network .n360-meter span{display:flex;justify-content:space-between;color:#334155;font-weight:900;font-size:12px;margin-bottom:8px}
  #page-network .n360-bar{height:10px;background:#e2e8f0;border-radius:999px;overflow:hidden}
  #page-network .n360-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--b),var(--c));width:0;animation:n360Grow .8s ease forwards}
  #page-network details.n360-details summary{cursor:pointer;font-weight:900;color:#1d4ed8}
  #page-network details.n360-details pre{white-space:pre-wrap;max-height:360px;overflow:auto;background:#0b1220;color:#dbeafe;border-radius:16px;padding:14px;font-size:12px;line-height:1.55}
  @keyframes n360Up{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}@keyframes n360Aura{to{transform:rotate(360deg)}}@keyframes n360Grow{from{width:0}to{width:var(--w)}}
  @media(max-width:1100px){#page-network .n360-card,#page-network .n360-half{grid-column:1/-1}#page-network .n360-select{min-width:240px;width:100%}}@media(max-width:720px){#page-network .n360-hero{padding:18px;border-radius:22px}#page-network .n360-kv{grid-template-columns:1fr}}
  `;
  document.head.appendChild(s);
}
function n360List(v){try{if(typeof arr==='function')return arr(v)}catch(e){} if(v==null||v==='')return[]; if(Array.isArray(v))return v.flatMap(n360List); if(typeof v==='object'){const d=['name','description','mac','ips','ip_addresses','status','type']; if(d.some(k=>Object.prototype.hasOwnProperty.call(v,k)))return[v]; return Object.values(v).flatMap(n360List)} return[v]}
function n360Obj(v){return(v&&typeof v==='object'&&!Array.isArray(v))?v:{}}
function n360Text(v){return esc(v===undefined||v===null||v===''?'N/A':v)}
function n360Json(v){try{return esc(JSON.stringify(v,null,2))}catch(e){return esc(String(v||''))}}
function n360Num(v){const n=Number(v||0);return Number.isFinite(n)?n:0}
function n360Meter(label,value,max,unit){const p=Math.max(0,Math.min(100,(n360Num(value)/Math.max(1,max))*100));return`<div class="n360-meter"><span><b>${esc(label)}</b><b>${fmt(value,unit||'',2)}</b></span><div class="n360-bar"><div class="n360-fill" style="--w:${p}%"></div></div></div>`}
function n360Table(headers,rows,empty){if(!rows||!rows.length)return`<div class="n360-empty">${esc(empty||'No data available.')}</div>`;return`<div class="n360-scroll"><table class="n360-table"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`}
function n360Label(m){return`${host(m)} - ${m.primary_ip||((m.all_ips||[])[0]||'No IP')}`}
function n360Selected(){const stored=localStorage.getItem('sagar_network_machine')||state.selected||'';let m=state.machines.find(x=>x.machine_id===stored)||state.machines[0]||null;if(m){localStorage.setItem('sagar_network_machine',m.machine_id);state.selected=m.machine_id;localStorage.setItem('sagar_selected_machine',m.machine_id)}return m}
function n360SelectMachine(v){localStorage.setItem('sagar_network_machine',v||'');if(v){state.selected=v;localStorage.setItem('sagar_selected_machine',v)}renderNetwork()}
function n360Type(a){const t=`${a.name||''} ${a.description||''} ${a.type||''}`.toLowerCase();if(a.is_vpn||a.vpn||/vpn|wireguard|openvpn|tap|tun/.test(t))return'VPN';if(a.is_virtual||/virtual|hyper-v|vmware|virtualbox|docker|wsl|loopback/.test(t))return'Virtual';if(/wi-fi|wifi|wireless|802\.11/.test(t))return'Wi-Fi';if(/ethernet|lan|realtek|intel/.test(t))return'Ethernet';return'Physical'}
function renderNetwork(){
  n360Style();
  const el=$('#networkCards'); if(!el)return;
  if(!state.machines.length){el.innerHTML='<div class="n360-empty">No network data yet. Wait for client heartbeat.</div>';return}
  const m=n360Selected(); if(!m){el.innerHTML='<div class="n360-empty">Select one machine.</div>';return}
  const p=payload(m), network=n360Obj(nested(p,'network',{})), traffic=n360Obj(nested(p,'network.traffic',{})), vpn=n360Obj(nested(p,'network.vpn',{}));
  const pub=n360Obj(nested(p,'network.public_internet',nested(p,'public_internet',{}))), speed=n360Obj(nested(p,'network.internet_speed',nested(p,'internet_speed',{})));
  const adapters=n360List(nested(p,'network.adapters',nested(p,'adapters',[]))).filter(x=>x&&typeof x==='object');
  const allIps=Array.isArray(m.all_ips)?m.all_ips.join(', '):(m.all_ips||'');
  const vpnNames=[]; if(vpn.name)vpnNames.push(vpn.name); adapters.forEach(a=>{if(n360Type(a)==='VPN')vpnNames.push(a.name||a.description||'VPN Adapter')});
  const vpnActive=!!(vpn.active||vpn.is_active||vpnNames.length||m.vpn_active);
  const options=state.machines.map(x=>`<option value="${esc(x.machine_id)}" ${x.machine_id===m.machine_id?'selected':''}>${esc(n360Label(x))}</option>`).join('');
  const adapterRows=adapters.map(a=>{const ips=Array.isArray(a.ips||a.ip_addresses)?(a.ips||a.ip_addresses).join(', '):(a.ips||a.ip_addresses||a.ip||'');const gateways=Array.isArray(a.gateways)?a.gateways.join(', '):(a.gateway||a.gateways||'');const dns=Array.isArray(a.dns_servers)?a.dns_servers.join(', '):(a.dns||a.dns_servers||'');const type=n360Type(a);return`<tr><td><strong>${n360Text(a.name||'Adapter')}</strong><small>${n360Text(a.description||'')}</small></td><td><span class="n360-badge ${type==='VPN'?'n360-vpn-on':''}">${esc(type)}</span></td><td>${n360Text(ips)}</td><td><code>${n360Text(a.mac||a.mac_address||a.MACAddress||'')}</code></td><td>${n360Text(gateways)}</td><td>${n360Text(dns)}</td><td>${n360Text(a.status||a.oper_status||a.state||'')}</td></tr>`});
  const vpnRows=[...new Set(vpnNames.filter(Boolean))].map(name=>`<tr><td><strong>${n360Text(name)}</strong></td><td>Active / detected</td><td>${n360Text(vpn.public_ip||m.public_ip||'')}</td></tr>`);
  const maxSpeed=Math.max(5,n360Num(m.wan_download_mbps),n360Num(m.wan_upload_mbps),n360Num(speed.download_mbps),n360Num(speed.upload_mbps));
  el.innerHTML=`<div class="n360-shell">
    <section class="n360-hero"><div class="n360-top"><div><p class="n360-eye">Network + VPN Machine View</p><h2>${esc(host(m))}</h2><p class="n360-sub">${n360Text(m.primary_ip||'No LAN IP')} Â· ${n360Text(m.os||'Unknown OS')} Â· Last seen ${ago(m.updated_at)}</p></div><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end"><select class="n360-select" onchange="n360SelectMachine(this.value)">${options}</select>${statusPill(m)}</div></div><div class="n360-chips"><div class="n360-chip"><span>Primary IP</span><strong>${n360Text(m.primary_ip||network.primary_ip||'')}</strong></div><div class="n360-chip"><span>Public IP</span><strong>${n360Text(m.public_ip||pub.public_ip||pub.ip||'')}</strong></div><div class="n360-chip"><span>ISP</span><strong>${n360Text(m.isp_name||pub.isp||pub.org||'')}</strong></div><div class="n360-chip"><span>VPN Status</span><strong>${vpnActive?'Active':'Not detected'}</strong></div><div class="n360-chip"><span>Download Now</span><strong>${fmt(traffic.current_download_mbps??m.wan_download_mbps,' Mbps',2)}</strong></div><div class="n360-chip"><span>Upload Now</span><strong>${fmt(traffic.current_upload_mbps??m.wan_upload_mbps,' Mbps',2)}</strong></div><div class="n360-chip"><span>Adapters</span><strong>${adapters.length}</strong></div></div></section>
    <section class="n360-layout">
      <article class="n360-card n360-wide"><h3>Live Network Speed <span class="n360-badge">Animated</span></h3><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px">${n360Meter('Current Download',traffic.current_download_mbps??m.wan_download_mbps,maxSpeed,' Mbps')}${n360Meter('Current Upload',traffic.current_upload_mbps??m.wan_upload_mbps,maxSpeed,' Mbps')}${n360Meter('ISP Download Probe',speed.download_mbps??m.isp_download_mbps,Math.max(maxSpeed,n360Num(speed.download_mbps)),' Mbps')}${n360Meter('ISP Upload Probe',speed.upload_mbps??m.isp_upload_mbps,Math.max(maxSpeed,n360Num(speed.upload_mbps)),' Mbps')}</div></article>
      <article class="n360-card"><h3>IP Summary <span class="n360-badge">LAN/WAN</span></h3><div class="n360-kv"><span>Primary IP</span><strong>${n360Text(m.primary_ip||network.primary_ip||'')}</strong></div><div class="n360-kv"><span>All LAN IPs</span><strong>${n360Text(allIps)}</strong></div><div class="n360-kv"><span>Receiver Seen IP</span><strong>${n360Text(network.receiver_seen_ip||'')}</strong></div><div class="n360-kv"><span>Public IP</span><strong>${n360Text(m.public_ip||pub.public_ip||pub.ip||'')}</strong></div><div class="n360-kv"><span>Country / City</span><strong>${n360Text((pub.country||'')+(pub.city?' / '+pub.city:''))}</strong></div></article>
      <article class="n360-card"><h3>ISP + Internet <span class="n360-badge">Provider</span></h3><div class="n360-kv"><span>ISP</span><strong>${n360Text(m.isp_name||pub.isp||'')}</strong></div><div class="n360-kv"><span>Org / AS</span><strong>${n360Text(pub.org||pub.as||'')}</strong></div><div class="n360-kv"><span>Speed Source</span><strong>${n360Text(speed.source||m.isp_speed_source||'')}</strong></div><div class="n360-kv"><span>Day Download</span><strong>${fmt(traffic.today_download_gb??m.today_download_gb,' GB',2)}</strong></div><div class="n360-kv"><span>Day Upload</span><strong>${fmt(traffic.today_upload_gb??m.today_upload_gb,' GB',2)}</strong></div></article>
      <article class="n360-card"><h3>VPN Detection <span class="n360-badge ${vpnActive?'n360-vpn-on':'n360-vpn-off'}">${vpnActive?'VPN Active':'No VPN'}</span></h3><div class="n360-kv"><span>Status</span><strong>${vpnActive?'Active / detected':'Not detected'}</strong></div><div class="n360-kv"><span>Detected Names</span><strong>${n360Text([...new Set(vpnNames)].join(', '))}</strong></div><div class="n360-kv"><span>VPN Public IP</span><strong>${n360Text(vpn.public_ip||'')}</strong></div><div class="n360-kv"><span>VPN Detail</span><strong>${n360Text(vpn.detail||vpn.status||'')}</strong></div></article>
      <article class="n360-card n360-wide"><h3>All Network Adapters <span class="n360-badge">${adapters.length} found</span></h3>${n360Table(['Adapter','Type','IP Addresses','MAC','Gateway','DNS','Status'],adapterRows,'No adapter data from this client.')}</article>
      <article class="n360-card n360-half"><h3>VPN Adapters <span class="n360-badge">${vpnRows.length} found</span></h3>${n360Table(['VPN Adapter','Status','Public IP'],vpnRows,'No VPN adapter detected for this machine.')}</article>
      <article class="n360-card n360-half"><h3>Raw Network Payload <span class="n360-badge">Advanced</span></h3><details class="n360-details"><summary>Open raw network JSON</summary><pre>${n360Json(network)}</pre></details></article>
    </section></div>`;
}
/* NETWORK_VPN_MACHINE_WISE_ONLY_END */

/* NETWORK_TODAY_IP_CHANGE_RECORDS_START */
/*
  Adds Today IP Change Records under Network + VPN page only.
  Uses existing /api/changes API and current machine selection.
  Does not change theme, other pages, or backend.
*/
async function n360LoadTodayIpChanges(machineId){
  const box=document.getElementById('n360TodayIpChangesBox');
  if(!box) return;
  try{
    const d=await api('/api/changes');
    const rows=(d.changes||[]).filter(c=>{
      const typ=String(c.change_type||c.type||'').toLowerCase();
      const same=!machineId || c.machine_id===machineId;
      const day=new Date(c.created_at||c.time||Date.now()).toDateString()===new Date().toDateString();
      return same && day && (typ==='ip' || typ.includes('ip'));
    }).slice(0,80);

    if(!rows.length){
      box.innerHTML='<div class="n360-empty">No IP change record found today for selected machine.</div>';
      return;
    }

    box.innerHTML = n360Table(
      ['Time','Machine','Change','Added IP / Adapter','Removed IP / Adapter'],
      rows.map(c=>{
        const added=(c.added_items||[]).join('<br>') || c.added_text || '';
        const removed=(c.removed_items||[]).join('<br>') || c.removed_text || '';
        return `<tr>
          <td>${esc(new Date(c.created_at||c.time).toLocaleString())}</td>
          <td><strong>${esc(c.hostname||c.machine_id||'')}</strong></td>
          <td>${esc(c.human_message||c.message||c.title||'IP changed')}</td>
          <td>${added ? added : 'N/A'}</td>
          <td>${removed ? removed : 'N/A'}</td>
        </tr>`;
      }),
      'No IP change record found today.'
    );
  }catch(e){
    box.innerHTML='<div class="n360-empty">Unable to load today IP change record. Check server change log API.</div>';
  }
}

if(!window.__n360TodayIpHooked){
  window.__n360TodayIpHooked = true;
  window.__n360BaseRenderNetwork = renderNetwork;
  renderNetwork = function(){
    window.__n360BaseRenderNetwork();
    setTimeout(()=>{
      const layout=document.querySelector('#page-network .n360-layout');
      const m=(typeof n360Selected==='function') ? n360Selected() : null;
      if(!layout || document.getElementById('n360TodayIpChangesCard')) return;
      const card=document.createElement('article');
      card.className='n360-card n360-wide';
      card.id='n360TodayIpChangesCard';
      card.innerHTML=`<h3>Today IP Change Records - All LAN Adapters <span class="n360-badge">Today</span></h3><div id="n360TodayIpChangesBox"><div class="n360-empty">Loading today IP changes...</div></div>`;
      layout.appendChild(card);
      n360LoadTodayIpChanges(m ? m.machine_id : '');
    },120);
  };
}
/* NETWORK_TODAY_IP_CHANGE_RECORDS_END */

/* HARDWARE_PREMIUM_PAGE_ONLY_START */
/*
  Hardware page premium commercial UI override.
  Scope: only #page-hardware and renderHardware().
  Other pages, server.py, dashboard, fleet, Machine 360, Network, USB, Software are untouched.
*/
function h360Style(){
  const old=document.getElementById('h360Style'); if(old) old.remove();
  const s=document.createElement('style'); s.id='h360Style';
  s.textContent=`
  #page-hardware{--hb:#2563eb;--hc:#06b6d4;--hi:#0f172a;--hm:#64748b;--hl:rgba(148,163,184,.25);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
  #page-hardware #hardwareCards{display:block!important;width:100%!important;max-width:none!important}
  #page-hardware .h360-shell{width:100%;animation:h360Up .45s ease both;color:var(--hi)}
  #page-hardware .h360-hero{position:relative;overflow:hidden;border-radius:30px;padding:24px;background:radial-gradient(circle at 10% 10%,rgba(37,99,235,.34),transparent 30%),radial-gradient(circle at 90% 18%,rgba(6,182,212,.28),transparent 30%),linear-gradient(135deg,rgba(255,255,255,.96),rgba(239,246,255,.90));border:1px solid rgba(255,255,255,.88);box-shadow:0 24px 80px rgba(30,64,175,.16);isolation:isolate}
  #page-hardware .h360-hero:before{content:"";position:absolute;inset:-90px;background:conic-gradient(from 140deg,rgba(37,99,235,.12),rgba(6,182,212,.22),rgba(79,70,229,.12),rgba(37,99,235,.12));filter:blur(18px);animation:h360Aura 9s linear infinite;z-index:-1}
  #page-hardware .h360-top{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;flex-wrap:wrap}
  #page-hardware .h360-eye{letter-spacing:.24em;text-transform:uppercase;font-size:11px;font-weight:900;color:var(--hb);margin:0 0 8px}
  #page-hardware .h360-hero h2{margin:0;font-size:clamp(26px,3vw,44px);line-height:1.03;letter-spacing:-.04em;color:#08111f}
  #page-hardware .h360-sub{margin:10px 0 0;color:var(--hm);font-weight:650;font-size:14px}
  #page-hardware .h360-select{min-width:320px;max-width:560px;border:1px solid rgba(37,99,235,.18);background:rgba(255,255,255,.92);color:#0f172a;border-radius:16px;padding:11px 14px;font-weight:800;outline:none;box-shadow:0 12px 26px rgba(30,64,175,.10)}
  #page-hardware .h360-chips{margin-top:22px;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
  #page-hardware .h360-chip{border-radius:20px;padding:14px 15px;background:rgba(255,255,255,.80);border:1px solid rgba(255,255,255,.90);box-shadow:0 12px 30px rgba(30,64,175,.10);backdrop-filter:blur(16px);transition:.22s}
  #page-hardware .h360-chip:hover,#page-hardware .h360-card:hover{transform:translateY(-3px);box-shadow:0 24px 55px rgba(30,64,175,.16)}
  #page-hardware .h360-chip span{display:block;color:var(--hm);font-size:11px;font-weight:850;text-transform:uppercase;letter-spacing:.08em}
  #page-hardware .h360-chip strong{display:block;margin-top:6px;font-size:20px;color:#0f172a;letter-spacing:-.02em;word-break:break-word}
  #page-hardware .h360-layout{margin-top:18px;display:grid;grid-template-columns:repeat(12,1fr);gap:16px;align-items:start}
  #page-hardware .h360-card{grid-column:span 4;border-radius:24px;background:rgba(255,255,255,.84);border:1px solid rgba(255,255,255,.82);box-shadow:0 14px 34px rgba(15,23,42,.10);padding:18px;backdrop-filter:blur(18px);min-width:0;animation:h360Up .45s ease both}
  #page-hardware .h360-wide{grid-column:1/-1}.h360-half{grid-column:span 6}.h360-third{grid-column:span 4}
  #page-hardware .h360-card h3{margin:0 0 14px;display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:17px;letter-spacing:-.02em;color:#0f172a}
  #page-hardware .h360-badge{display:inline-flex;border-radius:999px;padding:5px 10px;font-size:11px;font-weight:900;color:#1d4ed8;background:rgba(37,99,235,.10);border:1px solid rgba(37,99,235,.18)}
  #page-hardware .h360-warn{color:#b45309;background:rgba(245,158,11,.13);border-color:rgba(245,158,11,.24)}
  #page-hardware .h360-ok{color:#047857;background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.22)}
  #page-hardware .h360-kv{display:grid;grid-template-columns:minmax(120px,165px) 1fr;gap:9px 12px;padding:8px 0;border-bottom:1px dashed var(--hl);align-items:start}
  #page-hardware .h360-kv span{color:var(--hm);font-size:12px;font-weight:800}
  #page-hardware .h360-kv strong{color:#0f172a;font-size:13px;word-break:break-word;font-weight:850}
  #page-hardware code{color:#1e3a8a;background:rgba(37,99,235,.07);border:1px solid rgba(37,99,235,.13);border-radius:8px;padding:2px 5px;font-family:"Cascadia Code","Consolas",monospace;font-size:11px}
  #page-hardware .h360-scroll{width:100%;max-height:310px;overflow:auto;border-radius:18px;border:1px solid rgba(148,163,184,.24);background:rgba(255,255,255,.66)}
  #page-hardware .h360-scroll.small{max-height:240px}
  #page-hardware .h360-table{width:100%;border-collapse:separate;border-spacing:0;min-width:780px;font-size:13px}
  #page-hardware .h360-table.compact{min-width:620px}
  #page-hardware .h360-table th{position:sticky;top:0;z-index:2;text-align:left;padding:11px;color:#334155;background:linear-gradient(180deg,#f8fbff,#eef6ff);border-bottom:1px solid rgba(148,163,184,.28);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
  #page-hardware .h360-table td{padding:11px;border-bottom:1px solid rgba(148,163,184,.16);color:#0f172a;vertical-align:top;font-weight:650}
  #page-hardware .h360-table tr:hover td{background:rgba(37,99,235,.045)}
  #page-hardware .h360-table small{display:block;color:var(--hm);margin-top:4px;font-weight:650}
  #page-hardware .h360-empty{border-radius:18px;padding:18px;background:rgba(248,250,252,.8);color:var(--hm);border:1px dashed rgba(100,116,139,.30);font-weight:750}
  #page-hardware .h360-meters{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
  #page-hardware .h360-meter{border-radius:18px;padding:14px;background:linear-gradient(180deg,rgba(255,255,255,.86),rgba(239,246,255,.76));border:1px solid rgba(255,255,255,.9);box-shadow:0 12px 24px rgba(30,64,175,.08)}
  #page-hardware .h360-meter span{display:flex;justify-content:space-between;color:#334155;font-weight:900;font-size:12px;margin-bottom:8px}
  #page-hardware .h360-bar{height:10px;background:#e2e8f0;border-radius:999px;overflow:hidden}
  #page-hardware .h360-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--hb),var(--hc));width:0;animation:h360Grow .8s ease forwards}
  #page-hardware .h360-fill.warn{background:linear-gradient(90deg,#f59e0b,#ef4444)}
  #page-hardware details.h360-details summary{cursor:pointer;font-weight:900;color:#1d4ed8}
  #page-hardware details.h360-details pre{white-space:pre-wrap;max-height:260px;overflow:auto;background:#0b1220;color:#dbeafe;border-radius:16px;padding:14px;font-size:12px;line-height:1.55}
  @keyframes h360Up{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}@keyframes h360Aura{to{transform:rotate(360deg)}}@keyframes h360Grow{from{width:0}to{width:var(--w)}}
  @media(max-width:1100px){#page-hardware .h360-card,#page-hardware .h360-half,#page-hardware .h360-third{grid-column:1/-1}#page-hardware .h360-select{min-width:240px;width:100%}}@media(max-width:720px){#page-hardware .h360-hero{padding:18px;border-radius:22px}#page-hardware .h360-kv{grid-template-columns:1fr}}
  `;
  document.head.appendChild(s);
}
function h360List(v){try{if(typeof arr==='function')return arr(v)}catch(e){} if(v==null||v==='')return[]; if(Array.isArray(v))return v.flatMap(h360List); if(typeof v==='object'){const d=['name','display_name','mount','device','used_percent','total_gb','memory_total_mb','temperature_c']; if(d.some(k=>Object.prototype.hasOwnProperty.call(v,k)))return[v]; return Object.values(v).flatMap(h360List)} return[v]}
function h360Obj(v){return(v&&typeof v==='object'&&!Array.isArray(v))?v:{}}
function h360Text(v){return esc(v===undefined||v===null||v===''?'N/A':v)}
function h360Json(v){try{return esc(JSON.stringify(v,null,2))}catch(e){return esc(String(v||''))}}
function h360Num(v){const n=Number(v||0);return Number.isFinite(n)?n:0}
function h360Pct(v){return Math.max(0,Math.min(100,h360Num(v)))}
function h360Mem(mb){try{return typeof fmtMemMb==='function'?fmtMemMb(mb):fmt(Number(mb||0)/1024,' GB')}catch(e){return 'N/A'}}
function h360MachineLabel(m){return`${host(m)} - ${m.primary_ip||((m.all_ips||[])[0]||'No IP')}`}
function h360Selected(){const stored=localStorage.getItem('sagar_hardware_machine')||state.selected||'';let m=state.machines.find(x=>x.machine_id===stored)||state.machines[0]||null;if(m){localStorage.setItem('sagar_hardware_machine',m.machine_id);state.selected=m.machine_id;localStorage.setItem('sagar_selected_machine',m.machine_id)}return m}
function h360SelectMachine(v){localStorage.setItem('sagar_hardware_machine',v||'');if(v){state.selected=v;localStorage.setItem('sagar_selected_machine',v)}renderHardware()}
function h360Meter(label,value,unit){const p=h360Pct(value);const warn=p>=90?'warn':'';return`<div class="h360-meter"><span><b>${esc(label)}</b><b>${fmt(value,unit||'%')}</b></span><div class="h360-bar"><div class="h360-fill ${warn}" style="--w:${p}%"></div></div></div>`}
function h360Table(headers,rows,empty,compact=false){if(!rows||!rows.length)return`<div class="h360-empty">${esc(empty||'No data available.')}</div>`;return`<div class="h360-scroll ${compact?'small':''}"><table class="h360-table ${compact?'compact':''}"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`}
function h360DiskName(d){return d.mount||d.name||d.device||d.drive||d.DriveLetter||'Disk'}
function h360GpuName(g){return String(g.name||g.gpu_name||'GPU').replace(/^\s*\d{2}:\d{2}\.\d+\s+[^:]+:\s*/,'').trim()}
function h360Health(m){const bad=[];if(h360Num(m.cpu_percent)>=90)bad.push('CPU');if(h360Num(m.ram_percent)>=90)bad.push('RAM');if(h360Num(m.disk_max_percent)>=90)bad.push('Disk');if(h360Num(m.gpu_max_temp_c)>=90)bad.push('GPU Temp');return bad}

function renderHardware(){
  h360Style();
  const el=$('#hardwareCards'); if(!el)return;
  if(!state.machines.length){el.innerHTML='<div class="h360-empty">No hardware data yet. Wait for client heartbeat.</div>';return}
  const m=h360Selected(); if(!m){el.innerHTML='<div class="h360-empty">Select one machine.</div>';return}

  const p=payload(m), hw=h360Obj(nested(p,'hardware',{})), cpu=h360Obj(nested(p,'hardware.cpu',{})), mem=h360Obj(nested(p,'hardware.memory',{})), identity=h360Obj(nested(p,'identity',{}));
  const disks=h360List(nested(p,'storage.disks',[])).filter(x=>x&&typeof x==='object');
  const gpus=h360List(nested(p,'hardware.gpus',[])).filter(x=>x&&typeof x==='object');
  const options=state.machines.map(x=>`<option value="${esc(x.machine_id)}" ${x.machine_id===m.machine_id?'selected':''}>${esc(h360MachineLabel(x))}</option>`).join('');
  const health=h360Health(m);

  const diskRows=disks.map(d=>`<tr><td><strong>${h360Text(h360DiskName(d))}</strong><small>${h360Text(d.type||d.media_type||d.filesystem||'')}</small></td><td>${fmt(d.used_percent??d.usage_percent,'%')}</td><td>${fmt(d.total_gb??d.size_gb,' GB')}</td><td>${fmt(d.used_gb,' GB')}</td><td>${fmt(d.free_gb,' GB')}</td><td><code>${h360Text(d.serial||d.model||d.device||'')}</code></td></tr>`);
  const gpuRows=gpus.map(g=>`<tr><td><strong>${h360Text(h360GpuName(g))}</strong><small>${h360Text(g.source||'client')}</small></td><td>${fmt(g.usage_percent??g.utilization_gpu??g.load_percent,'%')}</td><td>${fmt(g.temperature_c??g.temp_c,' C')}</td><td>${h360Mem(g.memory_total_mb||g.adapter_ram_mb||g.dedicated_memory_mb||0)}</td><td>${h360Mem(g.memory_used_mb||0)}</td><td>${h360Text(g.driver_version||g.driver||'')}</td></tr>`);
  const fleetRows=state.machines.map(x=>`<tr><td><strong>${esc(host(x))}</strong><small>${esc(x.primary_ip||'No IP')}</small></td><td>${statusPill(x)}</td><td>${fmt(x.cpu_percent,'%')}</td><td>${fmt(x.ram_percent,'%')}</td><td>${fmt(x.disk_max_percent,'%')}</td><td>${fmt(x.gpu_max_temp_c,' C')}</td><td><span class="h360-badge ${h360Health(x).length?'h360-warn':'h360-ok'}">${h360Health(x).length?h360Health(x).join(', '):'Healthy'}</span></td></tr>`);

  el.innerHTML=`<div class="h360-shell">
    <section class="h360-hero">
      <div class="h360-top">
        <div><p class="h360-eye">Global Hardware Command View</p><h2>${esc(host(m))}</h2><p class="h360-sub">${h360Text(m.primary_ip||'No LAN IP')} Â· ${h360Text(m.os||'Unknown OS')} Â· Last seen ${ago(m.updated_at)}</p></div>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end"><select class="h360-select" onchange="h360SelectMachine(this.value)">${options}</select>${statusPill(m)}</div>
      </div>
      <div class="h360-chips">
        <div class="h360-chip"><span>CPU</span><strong>${fmt(m.cpu_percent,'%')}</strong></div>
        <div class="h360-chip"><span>RAM</span><strong>${fmt(m.ram_used_gb,' GB')} / ${fmt(m.ram_total_gb,' GB')}</strong></div>
        <div class="h360-chip"><span>Disk Max</span><strong>${fmt(m.disk_max_percent,'%')}</strong></div>
        <div class="h360-chip"><span>CPU Temp</span><strong>${fmt(m.cpu_temp_c,' C')}</strong></div>
        <div class="h360-chip"><span>GPU</span><strong>${gpus.length||m.gpu_count||0}</strong></div>
        <div class="h360-chip"><span>GPU Temp</span><strong>${fmt(m.gpu_max_temp_c,' C')}</strong></div>
        <div class="h360-chip"><span>Health</span><strong>${health.length?health.join(', '):'Healthy'}</strong></div>
      </div>
    </section>

    <section class="h360-layout">
      <article class="h360-card h360-wide"><h3>Live Hardware Usage <span class="h360-badge">Animated</span></h3><div class="h360-meters">${h360Meter('CPU Usage',cpu.usage_percent??m.cpu_percent,'%')}${h360Meter('RAM Usage',mem.used_percent??m.ram_percent,'%')}${h360Meter('Disk Usage',m.disk_max_percent,'%')}${h360Meter('GPU Usage',m.gpu_max_usage,'%')}</div></article>

      <article class="h360-card h360-third"><h3>Processor <span class="h360-badge">CPU</span></h3><div class="h360-kv"><span>Name</span><strong>${h360Text(cpu.name||cpu.model||'')}</strong></div><div class="h360-kv"><span>Cores / Threads</span><strong>${h360Text(cpu.cores||'')} / ${h360Text(cpu.threads||'')}</strong></div><div class="h360-kv"><span>Usage</span><strong>${fmt(cpu.usage_percent??m.cpu_percent,'%')}</strong></div><div class="h360-kv"><span>Temperature</span><strong>${fmt(cpu.temperature_c??m.cpu_temp_c,' C')}</strong></div></article>

      <article class="h360-card h360-third"><h3>Memory <span class="h360-badge">RAM</span></h3><div class="h360-kv"><span>Total</span><strong>${fmt(mem.total_gb??m.ram_total_gb,' GB')}</strong></div><div class="h360-kv"><span>Used</span><strong>${fmt(mem.used_gb??m.ram_used_gb,' GB')}</strong></div><div class="h360-kv"><span>Free</span><strong>${fmt(mem.free_gb??m.ram_free_gb,' GB')}</strong></div><div class="h360-kv"><span>Usage</span><strong>${fmt(mem.used_percent??m.ram_percent,'%')}</strong></div></article>

      <article class="h360-card h360-third"><h3>Identity <span class="h360-badge">Asset</span></h3><div class="h360-kv"><span>Machine ID</span><strong><code>${h360Text(m.machine_id)}</code></strong></div><div class="h360-kv"><span>UUID</span><strong><code>${h360Text(identity.system_uuid||'')}</code></strong></div><div class="h360-kv"><span>BIOS Serial</span><strong><code>${h360Text(identity.bios_serial||'')}</code></strong></div><div class="h360-kv"><span>Board Serial</span><strong><code>${h360Text(identity.motherboard_serial||identity.baseboard_serial||'')}</code></strong></div></article>

      <article class="h360-card h360-half"><h3>Storage / Drives <span class="h360-badge">${disks.length} found</span></h3>${h360Table(['Drive','Used %','Total','Used','Free','Serial / Model'],diskRows,'No disk/storage data from this client.',true)}</article>
      <article class="h360-card h360-half"><h3>GPU / Graphics <span class="h360-badge">${gpus.length} found</span></h3>${h360Table(['GPU','Usage','Temp','Total Memory','Used Memory','Driver'],gpuRows,'No GPU data from this client.',true)}</article>

      <article class="h360-card h360-wide"><h3>Hardware Fleet Overview <span class="h360-badge">${state.machines.length} machines</span></h3>${h360Table(['Machine','Status','CPU','RAM','Disk','GPU Temp','Health'],fleetRows,'No fleet hardware data.',true)}</article>

      <article class="h360-card h360-wide"><h3>Raw Hardware Payload <span class="h360-badge">Collapsed</span></h3><details class="h360-details"><summary>Open advanced raw hardware JSON only when needed</summary><pre>${h360Json(hw)}</pre></details></article>
    </section>
  </div>`;
}
/* HARDWARE_PREMIUM_PAGE_ONLY_END */

/* SOFTWARE_KEEP_PUBLISHERS_PAGE_ONLY_START */
/*
  Software page only.
  Final:
  - Same machine selection for Software Application Center and Installed Software grid.
  - Download Software CSV.
  - Remove Software Map.
  - Keep Top Publishers.
  - Keep Recent Install Records.
  - Today Software Changes shows software add/remove from /api/changes.
*/
function swfStyle(){
  const old=document.getElementById('swfStyle'); if(old) old.remove();
  const s=document.createElement('style'); s.id='swfStyle';
  s.textContent=`
  #page-software{
    --x-ink:#07111f;--x-muted:#64748b;--x-blue:#2563eb;--x-cyan:#06b6d4;--x-violet:#7c3aed;--x-green:#10b981;--x-red:#ef4444;--x-line:rgba(148,163,184,.24);
    font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
  }
  #page-software #softwareCards,#page-software #softwareTable,#page-software .software-list{display:block!important;width:100%!important;max-width:none!important}
  #page-software .swf-shell{width:100%;color:var(--x-ink);animation:swfIn .45s ease both}
  #page-software .swf-hero{
    position:relative;overflow:hidden;border-radius:34px;padding:26px;
    background:linear-gradient(135deg,rgba(255,255,255,.96),rgba(240,247,255,.92)),
      radial-gradient(circle at 10% 20%,rgba(37,99,235,.26),transparent 30%),
      radial-gradient(circle at 90% 12%,rgba(124,58,237,.22),transparent 30%),
      radial-gradient(circle at 55% 100%,rgba(6,182,212,.18),transparent 35%);
    border:1px solid rgba(255,255,255,.92);box-shadow:0 28px 90px rgba(30,64,175,.17);isolation:isolate;perspective:1200px;
  }
  #page-software .swf-hero:before{
    content:"";position:absolute;inset:-150px;background:conic-gradient(from 90deg,rgba(37,99,235,.12),rgba(6,182,212,.20),rgba(124,58,237,.16),rgba(37,99,235,.12));
    filter:blur(26px);animation:swfAura 12s linear infinite;z-index:-2;
  }
  #page-software .swf-hero:after{
    content:"";position:absolute;right:26px;top:24px;width:300px;height:190px;
    background:linear-gradient(135deg,rgba(37,99,235,.14),rgba(6,182,212,.08)),
      repeating-linear-gradient(90deg,transparent 0 28px,rgba(37,99,235,.08) 29px 30px),
      repeating-linear-gradient(0deg,transparent 0 28px,rgba(37,99,235,.06) 29px 30px);
    border:1px solid rgba(37,99,235,.15);border-radius:30px;transform:rotateX(62deg) rotateZ(-17deg);
    box-shadow:0 38px 70px rgba(37,99,235,.18);animation:swfFloat 4.5s ease-in-out infinite;z-index:-1;opacity:.72;
  }
  #page-software .swf-top{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;flex-wrap:wrap;position:relative;z-index:2}
  #page-software .swf-eye{margin:0 0 10px;color:var(--x-blue);font-size:11px;font-weight:950;letter-spacing:.25em;text-transform:uppercase}
  #page-software .swf-title{margin:0;font-size:clamp(30px,3.5vw,54px);line-height:.98;letter-spacing:-.06em;color:#06111f}
  #page-software .swf-sub{margin:12px 0 0;color:var(--x-muted);font-size:14px;font-weight:750}
  #page-software .swf-control{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
  #page-software .swf-select,#page-software .swf-search{
    border:1px solid rgba(37,99,235,.18);background:rgba(255,255,255,.94);color:#0f172a;border-radius:18px;padding:12px 15px;font-weight:850;outline:none;box-shadow:0 12px 30px rgba(30,64,175,.10)
  }
  #page-software .swf-select{min-width:330px;max-width:580px}
  #page-software .swf-search{min-width:310px}
  #page-software .swf-btn{
    border:1px solid rgba(37,99,235,.20);background:linear-gradient(135deg,#2563eb,#06b6d4);color:white;border-radius:18px;padding:12px 15px;font-weight:950;cursor:pointer;box-shadow:0 14px 30px rgba(37,99,235,.22);transition:.22s;
  }
  #page-software .swf-btn:hover{transform:translateY(-3px);box-shadow:0 24px 52px rgba(37,99,235,.28)}
  #page-software .swf-stats{margin-top:24px;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;position:relative;z-index:2}
  #page-software .swf-stat{
    position:relative;overflow:hidden;border-radius:22px;padding:16px;background:rgba(255,255,255,.82);border:1px solid rgba(255,255,255,.92);
    box-shadow:0 16px 34px rgba(30,64,175,.12);transition:transform .25s ease,box-shadow .25s ease;transform-style:preserve-3d;
  }
  #page-software .swf-stat:hover{transform:translateY(-5px) rotateX(4deg);box-shadow:0 28px 68px rgba(30,64,175,.18)}
  #page-software .swf-stat:after{content:"";position:absolute;right:-20px;top:-22px;width:76px;height:76px;border-radius:24px;background:linear-gradient(135deg,rgba(37,99,235,.16),rgba(6,182,212,.10));transform:rotate(18deg)}
  #page-software .swf-stat span{display:block;color:var(--x-muted);font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:.08em}
  #page-software .swf-stat strong{display:block;margin-top:7px;font-size:23px;letter-spacing:-.03em;color:#0f172a;word-break:break-word}
  #page-software .swf-section{
    margin-top:18px;border-radius:28px;background:rgba(255,255,255,.88);border:1px solid rgba(255,255,255,.90);box-shadow:0 16px 38px rgba(15,23,42,.10);padding:18px;backdrop-filter:blur(18px);animation:swfIn .45s ease both;
  }
  #page-software .swf-section h3{margin:0 0 14px;display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:18px;letter-spacing:-.025em;color:#0f172a}
  #page-software .swf-badge{display:inline-flex;align-items:center;border-radius:999px;padding:6px 11px;font-size:11px;font-weight:950;color:#1d4ed8;background:rgba(37,99,235,.10);border:1px solid rgba(37,99,235,.18)}
  #page-software .swf-add{color:#047857;background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.22)}
  #page-software .swf-rem{color:#b91c1c;background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.22)}
  #page-software .swf-app-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;max-height:610px;overflow:auto;padding:4px}
  #page-software .swf-app{
    position:relative;overflow:hidden;min-height:150px;border-radius:24px;padding:15px;background:linear-gradient(180deg,rgba(255,255,255,.92),rgba(248,251,255,.84));
    border:1px solid rgba(148,163,184,.22);box-shadow:0 14px 30px rgba(15,23,42,.08);transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease;transform-style:preserve-3d;
  }
  #page-software .swf-app:hover{transform:translateY(-6px) scale(1.01) rotateX(2deg);box-shadow:0 26px 58px rgba(30,64,175,.16);border-color:rgba(37,99,235,.28)}
  #page-software .swf-app:before{content:"";position:absolute;right:-28px;bottom:-34px;width:112px;height:112px;border-radius:34px;background:linear-gradient(135deg,rgba(37,99,235,.12),rgba(6,182,212,.08));transform:rotate(18deg)}
  #page-software .swf-app-head{display:flex;gap:12px;align-items:flex-start;position:relative;z-index:2}
  #page-software .swf-logo{flex:0 0 46px;width:46px;height:46px;border-radius:16px;display:grid;place-items:center;color:white;font-weight:950;font-size:18px;background:linear-gradient(135deg,var(--x-blue),var(--x-cyan));box-shadow:0 14px 24px rgba(37,99,235,.22)}
  #page-software .swf-app-title{min-width:0}
  #page-software .swf-app-title strong{display:block;font-size:14px;line-height:1.25;color:#0f172a;word-break:break-word}
  #page-software .swf-app-title small{display:block;margin-top:4px;color:var(--x-muted);font-weight:750}
  #page-software .swf-meta{position:relative;z-index:2;margin-top:12px;display:flex;flex-wrap:wrap;gap:6px}
  #page-software .swf-tag{border-radius:999px;padding:5px 8px;background:rgba(37,99,235,.08);border:1px solid rgba(37,99,235,.12);color:#1d4ed8;font-size:11px;font-weight:850}
  #page-software .swf-two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  #page-software .swf-info-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
  #page-software .swf-info{border:1px solid rgba(148,163,184,.20);background:linear-gradient(180deg,rgba(255,255,255,.80),rgba(248,251,255,.82));border-radius:18px;padding:12px;transition:.2s}
  #page-software .swf-info:hover{transform:translateY(-3px);border-color:rgba(37,99,235,.26);box-shadow:0 16px 32px rgba(30,64,175,.10)}
  #page-software .swf-info span{display:block;color:var(--x-muted);font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:.06em}
  #page-software .swf-info strong{display:block;margin-top:4px;color:#0f172a;font-size:13px;word-break:break-word}
  #page-software .swf-change-list{display:grid;gap:10px;max-height:390px;overflow:auto}
  #page-software .swf-change{display:grid;grid-template-columns:110px 1fr 1fr;gap:12px;border:1px solid rgba(148,163,184,.22);background:rgba(255,255,255,.78);border-radius:20px;padding:13px;transition:.2s}
  #page-software .swf-change:hover{transform:translateY(-3px);box-shadow:0 18px 38px rgba(30,64,175,.12)}
  #page-software .swf-time{color:var(--x-muted);font-size:12px;font-weight:900}
  #page-software .swf-change strong{display:block;color:#0f172a;font-size:13px}
  #page-software .swf-change small{display:block;color:var(--x-muted);margin-top:5px;font-weight:750;line-height:1.45}
  #page-software .swf-empty{border-radius:20px;padding:18px;background:rgba(248,250,252,.82);color:var(--x-muted);border:1px dashed rgba(100,116,139,.30);font-weight:800}
  @keyframes swfIn{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}@keyframes swfAura{to{transform:rotate(360deg)}}@keyframes swfFloat{0%,100%{transform:rotateX(62deg) rotateZ(-17deg) translateY(0)}50%{transform:rotateX(62deg) rotateZ(-14deg) translateY(12px)}}
  @media(max-width:1050px){#page-software .swf-two{grid-template-columns:1fr}#page-software .swf-select,#page-software .swf-search{min-width:240px;width:100%}}
  @media(max-width:760px){#page-software .swf-hero{padding:18px;border-radius:24px}#page-software .swf-hero:after{display:none}#page-software .swf-change{grid-template-columns:1fr}}
  `;
  document.head.appendChild(s);
}
function swfList(v){try{if(typeof arr==='function')return arr(v)}catch(e){} if(v==null||v==='')return[]; if(Array.isArray(v))return v.flatMap(swfList); if(typeof v==='object'){const d=['name','display_name','DisplayName','version','publisher','vendor','install_date']; if(d.some(k=>Object.prototype.hasOwnProperty.call(v,k)))return[v]; return Object.values(v).flatMap(swfList)} return[v]}
function swfText(v){return esc(v===undefined||v===null||v===''?'N/A':v)}
function swfName(a){return a.name||a.display_name||a.DisplayName||a.package||'Unknown software'}
function swfVersion(a){return a.version||a.DisplayVersion||''}
function swfPublisher(a){return a.publisher||a.vendor||a.Publisher||''}
function swfDate(a){try{return typeof fmtInstallDate==='function'?fmtInstallDate(a.install_date||a.installDate||a.InstallDate||''):(a.install_date||a.installDate||a.InstallDate||'')}catch(e){return a.install_date||a.installDate||a.InstallDate||''}}
function swfInitial(name){return esc(String(name||'S').trim().charAt(0).toUpperCase()||'S')}
function swfMachineLabel(m){return`${host(m)} - ${m.primary_ip||((m.all_ips||[])[0]||'No IP')}`}
function swfSelected(){
  const stored=localStorage.getItem('sagar_selected_machine') || localStorage.getItem('sagar_software_machine') || state.selected || '';
  let m=state.machines.find(x=>x.machine_id===stored)||state.machines[0]||null;
  if(m){
    state.selected=m.machine_id;
    localStorage.setItem('sagar_selected_machine',m.machine_id);
    localStorage.setItem('sagar_software_machine',m.machine_id);
  }
  return m;
}
function swfSyncExternalSelects(machineId){
  ['machineSelect','softwareSelect','softwareMachine','softwareMachineSelect'].forEach(id=>{
    const e=document.getElementById(id);
    if(e && e.tagName==='SELECT'){
      try{e.value=machineId;}catch(_){}
    }
  });
}
function swfSelectMachine(v){
  if(v){
    state.selected=v;
    localStorage.setItem('sagar_selected_machine',v);
    localStorage.setItem('sagar_software_machine',v);
    swfSyncExternalSelects(v);
  }
  renderSoftware();
}
function swfSearch(v){localStorage.setItem('sagar_software_search',v||'');renderSoftware()}
function swfAppCard(a,i){
  const name=swfName(a), ver=swfVersion(a), pub=swfPublisher(a), dt=swfDate(a);
  return `<article class="swf-app">
    <div class="swf-app-head">
      <div class="swf-logo">${swfInitial(name)}</div>
      <div class="swf-app-title"><strong>${swfText(name)}</strong><small>${swfText(pub||'Unknown publisher')}</small></div>
    </div>
    <div class="swf-meta">
      <span class="swf-tag">#${i+1}</span>
      <span class="swf-tag">Version: ${swfText(ver||'N/A')}</span>
      <span class="swf-tag">Install: ${swfText(dt||'N/A')}</span>
    </div>
  </article>`;
}
function swfCsvCell(v){
  const s=String(v===undefined||v===null?'':v);
  return `"${s.replace(/"/g,'""')}"`;
}
function swfDownloadSoftware(){
  const m=swfSelected();
  if(!m) return;
  const p=payload(m);
  const apps=swfList(nested(p,'software.installed',nested(p,'software',[]))).filter(x=>x&&typeof x==='object');
  const search=(localStorage.getItem('sagar_software_search')||'').toLowerCase().trim();
  const filtered=search ? apps.filter(a=>`${swfName(a)} ${swfVersion(a)} ${swfPublisher(a)}`.toLowerCase().includes(search)) : apps;
  const header=['Machine','Primary IP','Software','Version','Publisher','Install Date','Install Location / Source'];
  const rows=filtered.map(a=>[host(m), m.primary_ip||'', swfName(a), swfVersion(a), swfPublisher(a), swfDate(a), a.install_location||a.InstallLocation||a.source||'']);
  const csv=[header,...rows].map(r=>r.map(swfCsvCell).join(',')).join('\r\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  const safeHost=String(host(m)||'machine').replace(/[^a-z0-9_-]+/gi,'_');
  a.href=url;
  a.download=`software_${safeHost}_${new Date().toISOString().slice(0,10)}.csv`;
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}
function swfIsToday(ts){
  const d=new Date(ts||Date.now());
  if(isNaN(d.getTime())) return false;
  return d.toDateString()===new Date().toDateString();
}
function swfChangeItems(v){
  if(!v) return [];
  if(Array.isArray(v)) return v.map(x=>String(x||'').trim()).filter(Boolean);
  if(typeof v==='string') return v.split(/\s*\|\|\s*|\n/).map(x=>x.trim()).filter(Boolean);
  return [String(v)].filter(Boolean);
}
async function swfLoadTodayChanges(machineId){
  const box=document.getElementById('swfTodayChangesBox');
  if(!box) return;
  try{
    const d=await api('/api/changes');
    const rows=(d.changes||[]).filter(c=>{
      const ctype=String(c.change_type||c.type||'').toLowerCase();
      const msg=String(c.human_message||c.message||c.title||'').toLowerCase();
      const same=c.machine_id===machineId;
      const today=swfIsToday(c.created_at||c.time);
      return same && today && (ctype==='software' || ctype.includes('software') || msg.includes('software list changed') || msg.includes('software'));
    }).slice(0,100);

    if(!rows.length){
      box.innerHTML='<div class="swf-empty">No software added or removed today for selected machine.</div>';
      return;
    }

    box.innerHTML=`<div class="swf-change-list">${rows.map(c=>{
      const added=swfChangeItems((c.added_items&&c.added_items.length)?c.added_items:(c.added_text||c.added||''));
      const removed=swfChangeItems((c.removed_items&&c.removed_items.length)?c.removed_items:(c.removed_text||c.removed||''));
      const msg=esc(c.human_message||c.message||c.title||'Software list changed');
      let action='Changed', cls='swf-badge';
      if(added.length && !removed.length){action='Added'; cls='swf-badge swf-add';}
      if(removed.length && !added.length){action='Removed'; cls='swf-badge swf-rem';}
      if(added.length && removed.length){action='Added + Removed';}
      const addedHtml=added.length?added.map(esc).join('<br>'):'N/A';
      const removedHtml=removed.length?removed.map(esc).join('<br>'):'N/A';
      return `<div class="swf-change">
        <div class="swf-time">${esc(new Date(c.created_at||c.time).toLocaleTimeString())}<br><span class="${cls}">${action}</span></div>
        <div><strong>${msg}</strong><small>Added / Installed / Updated:<br>${addedHtml}</small></div>
        <div><strong>Removed Software</strong><small>${removedHtml}</small></div>
      </div>`;
    }).join('')}</div>`;
  }catch(e){
    box.innerHTML='<div class="swf-empty">Unable to load today software changes from /api/changes.</div>';
  }
}
function renderSoftware(){
  swfStyle();
  let el=$('#softwareCards') || $('#softwareTable') || document.querySelector('#page-software .software-list') || document.querySelector('#page-software .grid') || document.querySelector('#page-software .panel');
  if(!el) return;
  if(!state.machines.length){el.innerHTML='<div class="swf-empty">No software data yet. Wait for client heartbeat.</div>';return;}
  const m=swfSelected(); if(!m){el.innerHTML='<div class="swf-empty">Select one machine.</div>';return;}
  swfSyncExternalSelects(m.machine_id);

  const p=payload(m);
  const apps=swfList(nested(p,'software.installed',nested(p,'software',[]))).filter(x=>x&&typeof x==='object');
  const search=(localStorage.getItem('sagar_software_search')||'').toLowerCase().trim();
  const filtered=search ? apps.filter(a=>`${swfName(a)} ${swfVersion(a)} ${swfPublisher(a)}`.toLowerCase().includes(search)) : apps;
  const publishers=[...new Set(apps.map(swfPublisher).filter(Boolean))];
  const withVersion=apps.filter(a=>swfVersion(a)).length;
  const recentInstalled=apps.filter(a=>String(swfDate(a)||'').trim()).slice(0,12);
  const topPublishers=publishers.slice(0,16);
  const options=state.machines.map(x=>`<option value="${esc(x.machine_id)}" ${x.machine_id===m.machine_id?'selected':''}>${esc(swfMachineLabel(x))}</option>`).join('');

  const publisherCards=topPublishers.map(x=>`<div class="swf-info"><span>Publisher</span><strong>${swfText(x)}</strong></div>`).join('');
  const recentCards=recentInstalled.map(a=>`<div class="swf-info"><span>${swfText(swfDate(a))}</span><strong>${swfText(swfName(a))}</strong></div>`).join('');

  el.innerHTML=`<div class="swf-shell">
    <section class="swf-hero">
      <div class="swf-top">
        <div>
          <p class="swf-eye">Software Application Center</p>
          <h2>${esc(host(m))}</h2>
          <p class="swf-sub">${swfText(m.primary_ip||'No LAN IP')} Â· ${swfText(m.os||'Unknown OS')} Â· Last seen ${ago(m.updated_at)}</p>
        </div>
        <div class="swf-control">
          <select class="swf-select" onchange="swfSelectMachine(this.value)">${options}</select>
          <button class="swf-btn download-only" onclick="swfDownloadSoftware()">Download Software CSV</button>
          ${statusPill(m)}
        </div>
      </div>
      <div class="swf-stats">
        <div class="swf-stat"><span>Total Software</span><strong>${apps.length}</strong></div>
        <div class="swf-stat"><span>Showing</span><strong>${filtered.length}</strong></div>
        <div class="swf-stat"><span>Publishers</span><strong>${publishers.length}</strong></div>
        <div class="swf-stat"><span>With Version</span><strong>${withVersion}</strong></div>
        <div class="swf-stat"><span>Selected Machine</span><strong>${esc(host(m))}</strong></div>
      </div>
    </section>

    <section class="swf-section">
      <h3>Installed Software / Application Grid <span class="swf-badge">Same selected machine: ${esc(host(m))}</span></h3>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">
        <input class="swf-search" value="${esc(localStorage.getItem('sagar_software_search')||'')}" placeholder="Search app / publisher / version" oninput="swfSearch(this.value)">
        <button class="swf-btn download-only" onclick="swfDownloadSoftware()">Download Current List</button>
      </div>
      <div class="swf-app-grid">${filtered.map(swfAppCard).join('') || '<div class="swf-empty">No installed software data from this client.</div>'}</div>
    </section>

    <section class="swf-two">
      <article class="swf-section">
        <h3>Top Publishers <span class="swf-badge">${topPublishers.length}</span></h3>
        <div class="swf-info-list">${publisherCards || '<div class="swf-empty">No publisher data available.</div>'}</div>
      </article>
      <article class="swf-section">
        <h3>Recent Install Records <span class="swf-badge">${recentInstalled.length}</span></h3>
        <div class="swf-info-list">${recentCards || '<div class="swf-empty">No install date data available.</div>'}</div>
      </article>
    </section>

    <section class="swf-section">
      <h3>Today Software Changes <span class="swf-badge">Added / Removed</span></h3>
      <div id="swfTodayChangesBox"><div class="swf-empty">Loading today software changes...</div></div>
    </section>
  </div>`;
  setTimeout(()=>swfLoadTodayChanges(m.machine_id),120);
}
/* SOFTWARE_KEEP_PUBLISHERS_PAGE_ONLY_END */

/* USB_SIMPLE_HUMAN_PAGE_ONLY_START */
/*
  USB page only.
  Simple human-readable USB page for 10 to 90 year users.
  Other pages and backend are untouched.
*/
function usbSimpleStyle(){
  const old=document.getElementById('usbSimpleStyle'); if(old) old.remove();
  const s=document.createElement('style'); s.id='usbSimpleStyle';
  s.textContent=`
  #page-usb{
    --u-ink:#07111f;--u-muted:#64748b;--u-blue:#2563eb;--u-cyan:#06b6d4;--u-green:#10b981;--u-red:#ef4444;--u-line:rgba(148,163,184,.24);
    font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
  }
  #page-usb #usbCards,#page-usb #usbTable,#page-usb .usb-list{display:block!important;width:100%!important;max-width:none!important}
  #page-usb .usb-simple-shell{width:100%;color:var(--u-ink);animation:usbSimpleIn .45s ease both}
  #page-usb .usb-simple-hero{
    position:relative;overflow:hidden;border-radius:34px;padding:26px;
    background:
      linear-gradient(135deg,rgba(255,255,255,.96),rgba(240,247,255,.92)),
      radial-gradient(circle at 10% 20%,rgba(37,99,235,.28),transparent 30%),
      radial-gradient(circle at 90% 12%,rgba(6,182,212,.24),transparent 30%);
    border:1px solid rgba(255,255,255,.92);box-shadow:0 28px 90px rgba(30,64,175,.17);isolation:isolate;
  }
  #page-usb .usb-simple-hero:before{
    content:"";position:absolute;inset:-150px;background:conic-gradient(from 90deg,rgba(37,99,235,.12),rgba(6,182,212,.20),rgba(124,58,237,.12),rgba(37,99,235,.12));
    filter:blur(26px);animation:usbSimpleAura 12s linear infinite;z-index:-2;
  }
  #page-usb .usb-simple-top{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;flex-wrap:wrap;position:relative;z-index:2}
  #page-usb .usb-simple-eye{margin:0 0 10px;color:var(--u-blue);font-size:11px;font-weight:950;letter-spacing:.25em;text-transform:uppercase}
  #page-usb .usb-simple-title{margin:0;font-size:clamp(30px,3.5vw,54px);line-height:.98;letter-spacing:-.06em;color:#06111f}
  #page-usb .usb-simple-sub{margin:12px 0 0;color:var(--u-muted);font-size:15px;font-weight:750;line-height:1.45}
  #page-usb .usb-simple-control{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
  #page-usb .usb-simple-select,#page-usb .usb-simple-search{
    border:1px solid rgba(37,99,235,.18);background:rgba(255,255,255,.94);color:#0f172a;border-radius:18px;padding:12px 15px;font-weight:850;outline:none;box-shadow:0 12px 30px rgba(30,64,175,.10)
  }
  #page-usb .usb-simple-select{min-width:330px;max-width:580px}
  #page-usb .usb-simple-search{min-width:310px}
  #page-usb .usb-simple-btn{
    border:1px solid rgba(37,99,235,.20);background:linear-gradient(135deg,#2563eb,#06b6d4);color:white;border-radius:18px;padding:12px 15px;font-weight:950;cursor:pointer;box-shadow:0 14px 30px rgba(37,99,235,.22);transition:.22s;
  }
  #page-usb .usb-simple-btn:hover{transform:translateY(-3px);box-shadow:0 24px 52px rgba(37,99,235,.28)}
  #page-usb .usb-simple-help{
    margin-top:20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;position:relative;z-index:2;
  }
  #page-usb .usb-simple-help-card{
    border-radius:22px;padding:16px;background:rgba(255,255,255,.82);border:1px solid rgba(255,255,255,.92);box-shadow:0 16px 34px rgba(30,64,175,.12);transition:.22s;
  }
  #page-usb .usb-simple-help-card:hover{transform:translateY(-4px);box-shadow:0 28px 68px rgba(30,64,175,.18)}
  #page-usb .usb-simple-help-card span{display:block;color:var(--u-muted);font-size:12px;font-weight:900;text-transform:uppercase;letter-spacing:.08em}
  #page-usb .usb-simple-help-card strong{display:block;margin-top:7px;font-size:22px;letter-spacing:-.03em;color:#0f172a}
  #page-usb .usb-simple-help-card p{margin:7px 0 0;color:var(--u-muted);font-size:13px;font-weight:700;line-height:1.45}
  #page-usb .usb-simple-section{
    margin-top:18px;border-radius:28px;background:rgba(255,255,255,.88);border:1px solid rgba(255,255,255,.90);box-shadow:0 16px 38px rgba(15,23,42,.10);padding:18px;backdrop-filter:blur(18px);animation:usbSimpleIn .45s ease both;
  }
  #page-usb .usb-simple-section h3{margin:0 0 14px;display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:19px;letter-spacing:-.025em;color:#0f172a}
  #page-usb .usb-simple-badge{display:inline-flex;align-items:center;border-radius:999px;padding:6px 11px;font-size:11px;font-weight:950;color:#1d4ed8;background:rgba(37,99,235,.10);border:1px solid rgba(37,99,235,.18)}
  #page-usb .usb-simple-add{color:#047857;background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.22)}
  #page-usb .usb-simple-rem{color:#b91c1c;background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.22)}
  #page-usb .usb-simple-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;max-height:610px;overflow:auto;padding:4px}
  #page-usb .usb-simple-device{
    position:relative;overflow:hidden;min-height:178px;border-radius:24px;padding:16px;background:linear-gradient(180deg,rgba(255,255,255,.94),rgba(248,251,255,.86));
    border:1px solid rgba(148,163,184,.22);box-shadow:0 14px 30px rgba(15,23,42,.08);transition:.22s;transform-style:preserve-3d;
  }
  #page-usb .usb-simple-device:hover{transform:translateY(-6px) scale(1.01) rotateX(2deg);box-shadow:0 26px 58px rgba(30,64,175,.16);border-color:rgba(37,99,235,.28)}
  #page-usb .usb-simple-device:before{content:"";position:absolute;right:-30px;bottom:-36px;width:116px;height:116px;border-radius:36px;background:linear-gradient(135deg,rgba(37,99,235,.12),rgba(6,182,212,.08));transform:rotate(18deg)}
  #page-usb .usb-simple-head{display:flex;gap:12px;align-items:flex-start;position:relative;z-index:2}
  #page-usb .usb-simple-icon{
    flex:0 0 54px;width:54px;height:54px;border-radius:18px;display:grid;place-items:center;color:white;font-weight:950;font-size:20px;background:linear-gradient(135deg,var(--u-blue),var(--u-cyan));box-shadow:0 14px 24px rgba(37,99,235,.22);
  }
  #page-usb .usb-simple-name{min-width:0}
  #page-usb .usb-simple-name strong{display:block;font-size:16px;line-height:1.25;color:#0f172a;word-break:break-word}
  #page-usb .usb-simple-name small{display:block;margin-top:5px;color:var(--u-muted);font-weight:750;line-height:1.4}
  #page-usb .usb-simple-meaning{position:relative;z-index:2;margin-top:12px;padding:10px;border-radius:14px;background:rgba(37,99,235,.06);color:#1e3a8a;font-size:13px;font-weight:800;line-height:1.45}
  #page-usb .usb-simple-tags{position:relative;z-index:2;margin-top:12px;display:flex;flex-wrap:wrap;gap:6px}
  #page-usb .usb-simple-tag{border-radius:999px;padding:6px 9px;background:rgba(37,99,235,.08);border:1px solid rgba(37,99,235,.12);color:#1d4ed8;font-size:11px;font-weight:850}
  #page-usb .usb-simple-table-wrap{width:100%;max-height:430px;overflow:auto;border-radius:20px;border:1px solid rgba(148,163,184,.22);background:rgba(255,255,255,.70)}
  #page-usb .usb-simple-table{width:100%;border-collapse:separate;border-spacing:0;min-width:900px;font-size:13px}
  #page-usb .usb-simple-table th{position:sticky;top:0;z-index:2;text-align:left;padding:12px;color:#334155;background:linear-gradient(180deg,#f8fbff,#eef6ff);border-bottom:1px solid rgba(148,163,184,.28);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
  #page-usb .usb-simple-table td{padding:12px;border-bottom:1px solid rgba(148,163,184,.16);color:#0f172a;vertical-align:top;font-weight:650}
  #page-usb .usb-simple-table tr:hover td{background:rgba(37,99,235,.045)}
  #page-usb code{color:#1e3a8a;background:rgba(37,99,235,.07);border:1px solid rgba(37,99,235,.13);border-radius:8px;padding:2px 5px;font-family:"Cascadia Code","Consolas",monospace;font-size:11px}
  #page-usb .usb-simple-change-list{display:grid;gap:10px;max-height:390px;overflow:auto}
  #page-usb .usb-simple-change{display:grid;grid-template-columns:120px 1fr 1fr;gap:12px;border:1px solid rgba(148,163,184,.22);background:rgba(255,255,255,.78);border-radius:20px;padding:13px;transition:.2s}
  #page-usb .usb-simple-change:hover{transform:translateY(-3px);box-shadow:0 18px 38px rgba(30,64,175,.12)}
  #page-usb .usb-simple-time{color:var(--u-muted);font-size:12px;font-weight:900}
  #page-usb .usb-simple-change strong{display:block;color:#0f172a;font-size:13px}
  #page-usb .usb-simple-change small{display:block;color:var(--u-muted);margin-top:5px;font-weight:750;line-height:1.45}
  #page-usb .usb-simple-empty{border-radius:20px;padding:18px;background:rgba(248,250,252,.82);color:var(--u-muted);border:1px dashed rgba(100,116,139,.30);font-weight:800}
  @keyframes usbSimpleIn{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}@keyframes usbSimpleAura{to{transform:rotate(360deg)}}
  @media(max-width:1050px){#page-usb .usb-simple-select,#page-usb .usb-simple-search{min-width:240px;width:100%}}
  @media(max-width:760px){#page-usb .usb-simple-hero{padding:18px;border-radius:24px}#page-usb .usb-simple-change{grid-template-columns:1fr}}
  `;
  document.head.appendChild(s);
}
function usbSimpleList(v){try{if(typeof arr==='function')return arr(v)}catch(e){} if(v==null||v==='')return[]; if(Array.isArray(v))return v.flatMap(usbSimpleList); if(typeof v==='object'){const d=['name','display_name','friendly_name','device_name','description','device_id','vid','pid','class','type']; if(d.some(k=>Object.prototype.hasOwnProperty.call(v,k)))return[v]; return Object.values(v).flatMap(usbSimpleList)} return[v]}
function usbSimpleText(v){return esc(v===undefined||v===null||v===''?'N/A':v)}
function usbSimpleName(u){return u.display_name||u.friendly_name||u.name||u.device_name||u.description||'Unknown USB device'}
function usbSimpleType(u){return u.type||u.class||u.device_class||u.category||'Peripheral'}
function usbSimpleStatus(u){return u.status||u.state||u.present||u.connected||''}
function usbSimpleId(u){return u.device_id||u.instance_id||u.id||u.pnp_device_id||''}
function usbSimpleMachineLabel(m){return`${host(m)} - ${m.primary_ip||((m.all_ips||[])[0]||'No IP')}`}
function usbSimpleSelected(){
  const stored=localStorage.getItem('sagar_selected_machine') || localStorage.getItem('sagar_usb_machine') || state.selected || '';
  let m=state.machines.find(x=>x.machine_id===stored)||state.machines[0]||null;
  if(m){
    state.selected=m.machine_id;
    localStorage.setItem('sagar_selected_machine',m.machine_id);
    localStorage.setItem('sagar_usb_machine',m.machine_id);
  }
  return m;
}
function usbSimpleSelectMachine(v){
  if(v){
    state.selected=v;
    localStorage.setItem('sagar_selected_machine',v);
    localStorage.setItem('sagar_usb_machine',v);
  }
  renderUsb();
}
function usbSimpleSearch(v){localStorage.setItem('sagar_usb_search',v||'');renderUsb()}
function usbSimpleCleanDevices(raw){
  let list=[];
  try{ if(typeof cleanUsbItems==='function') list=cleanUsbItems(raw); else list=usbSimpleList(raw); }catch(e){ list=usbSimpleList(raw); }
  return list.filter(x=>x&&typeof x==='object');
}
function usbSimpleCategory(u){
  const t=String(usbSimpleName(u)+' '+usbSimpleType(u)+' '+(u.manufacturer||'')).toLowerCase();
  if(t.includes('keyboard')) return {icon:'âŒ¨ï¸', simple:'Keyboard', meaning:'This is used for typing.'};
  if(t.includes('mouse')) return {icon:'ðŸ–±ï¸', simple:'Mouse', meaning:'This is used for clicking and moving the pointer.'};
  if(t.includes('audio')||t.includes('headphone')||t.includes('speaker')||t.includes('microphone')) return {icon:'ðŸŽ§', simple:'Audio device', meaning:'This is used for sound, headphone, speaker, or microphone.'};
  if(t.includes('camera')||t.includes('webcam')) return {icon:'ðŸ“·', simple:'Camera', meaning:'This is used for video class, meeting, or recording.'};
  if(t.includes('storage')||t.includes('disk')||t.includes('drive')||t.includes('mass')) return {icon:'ðŸ’¾', simple:'Storage / Pen Drive', meaning:'This can store or transfer files.'};
  if(t.includes('printer')) return {icon:'ðŸ–¨ï¸', simple:'Printer', meaning:'This is used for printing.'};
  if(t.includes('bluetooth')) return {icon:'ðŸ”µ', simple:'Bluetooth device', meaning:'This connects wireless accessories.'};
  if(t.includes('hub')) return {icon:'ðŸ”Œ', simple:'USB Hub', meaning:'This adds more USB ports.'};
  return {icon:'ðŸ”Œ', simple:'USB / Peripheral', meaning:'This is an external device connected to the computer.'};
}
function usbSimpleDeviceCard(u,i){
  const c=usbSimpleCategory(u);
  return `<article class="usb-simple-device">
    <div class="usb-simple-head">
      <div class="usb-simple-icon">${esc(c.icon)}</div>
      <div class="usb-simple-name"><strong>${usbSimpleText(c.simple)}</strong><small>${usbSimpleText(usbSimpleName(u))}</small></div>
    </div>
    <div class="usb-simple-meaning">${esc(c.meaning)}</div>
    <div class="usb-simple-tags">
      <span class="usb-simple-tag">#${i+1}</span>
      <span class="usb-simple-tag">Type: ${usbSimpleText(usbSimpleType(u))}</span>
      <span class="usb-simple-tag">Status: ${usbSimpleText(usbSimpleStatus(u)||'N/A')}</span>
      <span class="usb-simple-tag">VID: ${usbSimpleText(u.vid||'N/A')}</span>
      <span class="usb-simple-tag">PID: ${usbSimpleText(u.pid||'N/A')}</span>
    </div>
  </article>`;
}
function usbSimpleCsvCell(v){
  const s=String(v===undefined||v===null?'':v);
  return `"${s.replace(/"/g,'""')}"`;
}
function usbSimpleDownloadUsb(){
  const m=usbSimpleSelected(); if(!m) return;
  const p=payload(m);
  const devices=usbSimpleCleanDevices(nested(p,'usb.devices',nested(p,'usb',[])));
  const search=(localStorage.getItem('sagar_usb_search')||'').toLowerCase().trim();
  const filtered=search ? devices.filter(u=>`${usbSimpleName(u)} ${usbSimpleType(u)} ${u.manufacturer||''} ${usbSimpleId(u)}`.toLowerCase().includes(search)) : devices;
  const header=['Machine','Primary IP','Simple Type','Device Name','Type','Manufacturer','Status','VID','PID','Device ID'];
  const rows=filtered.map(u=>[host(m),m.primary_ip||'',usbSimpleCategory(u).simple,usbSimpleName(u),usbSimpleType(u),u.manufacturer||'',usbSimpleStatus(u),u.vid||'',u.pid||'',usbSimpleId(u)]);
  const csv=[header,...rows].map(r=>r.map(usbSimpleCsvCell).join(',')).join('\r\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  const safeHost=String(host(m)||'machine').replace(/[^a-z0-9_-]+/gi,'_');
  a.href=url;
  a.download=`usb_simple_${safeHost}_${new Date().toISOString().slice(0,10)}.csv`;
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}
function usbSimpleIsToday(ts){
  const d=new Date(ts||Date.now());
  if(isNaN(d.getTime())) return false;
  return d.toDateString()===new Date().toDateString();
}
function usbSimpleChangeItems(v){
  if(!v) return [];
  if(Array.isArray(v)) return v.map(x=>String(x||'').trim()).filter(Boolean);
  if(typeof v==='string') return v.split(/\s*\|\|\s*|\n/).map(x=>x.trim()).filter(Boolean);
  return [String(v)].filter(Boolean);
}
async function usbSimpleLoadTodayChanges(machineId){
  const box=document.getElementById('usbSimpleTodayChangesBox');
  if(!box) return;
  try{
    const d=await api('/api/changes');
    const rows=(d.changes||[]).filter(c=>{
      const ctype=String(c.change_type||c.type||'').toLowerCase();
      const msg=String(c.human_message||c.message||c.title||'').toLowerCase();
      return c.machine_id===machineId && usbSimpleIsToday(c.created_at||c.time) && (ctype==='usb' || ctype.includes('usb') || msg.includes('usb') || msg.includes('peripheral'));
    }).slice(0,100);

    if(!rows.length){
      box.innerHTML='<div class="usb-simple-empty">No USB connected or removed today for selected machine.</div>';
      return;
    }

    box.innerHTML=`<div class="usb-simple-change-list">${rows.map(c=>{
      const added=usbSimpleChangeItems((c.added_items&&c.added_items.length)?c.added_items:(c.added_text||c.added||''));
      const removed=usbSimpleChangeItems((c.removed_items&&c.removed_items.length)?c.removed_items:(c.removed_text||c.removed||''));
      const msg=esc(c.human_message||c.message||c.title||'USB/peripheral changed');
      let action='Changed', cls='usb-simple-badge';
      if(added.length && !removed.length){action='Connected'; cls='usb-simple-badge usb-simple-add';}
      if(removed.length && !added.length){action='Removed'; cls='usb-simple-badge usb-simple-rem';}
      if(added.length && removed.length){action='Connected + Removed';}
      const addedHtml=added.length?added.map(esc).join('<br>'):'N/A';
      const removedHtml=removed.length?removed.map(esc).join('<br>'):'N/A';
      return `<div class="usb-simple-change">
        <div class="usb-simple-time">${esc(new Date(c.created_at||c.time).toLocaleTimeString())}<br><span class="${cls}">${action}</span></div>
        <div><strong>${msg}</strong><small>Connected today:<br>${addedHtml}</small></div>
        <div><strong>Removed today</strong><small>${removedHtml}</small></div>
      </div>`;
    }).join('')}</div>`;
  }catch(e){
    box.innerHTML='<div class="usb-simple-empty">Unable to load today USB changes from /api/changes.</div>';
  }
}
function usbSimpleTable(devices){
  if(!devices.length) return '<div class="usb-simple-empty">No USB/peripheral data from this client.</div>';
  return `<div class="usb-simple-table-wrap"><table class="usb-simple-table"><thead><tr><th>Simple Name</th><th>Real Device Name</th><th>Type</th><th>Manufacturer</th><th>Status</th><th>VID/PID</th><th>Technical ID</th></tr></thead><tbody>${devices.map(u=>{
    const c=usbSimpleCategory(u);
    return `<tr>
      <td><strong>${usbSimpleText(c.simple)}</strong></td>
      <td>${usbSimpleText(usbSimpleName(u))}</td>
      <td>${usbSimpleText(usbSimpleType(u))}</td>
      <td>${usbSimpleText(u.manufacturer||'')}</td>
      <td>${usbSimpleText(usbSimpleStatus(u)||'')}</td>
      <td>${usbSimpleText((u.vid||'') + (u.pid ? ' / '+u.pid : ''))}</td>
      <td><code>${usbSimpleText(usbSimpleId(u))}</code></td>
    </tr>`;
  }).join('')}</tbody></table></div>`;
}
function renderUsb(){
  usbSimpleStyle();
  let el=$('#usbCards') || $('#usbTable') || document.querySelector('#page-usb .usb-list') || document.querySelector('#page-usb .grid') || document.querySelector('#page-usb .panel');
  if(!el) return;
  if(!state.machines.length){el.innerHTML='<div class="usb-simple-empty">No USB data yet. Wait for client heartbeat.</div>';return;}
  const m=usbSimpleSelected(); if(!m){el.innerHTML='<div class="usb-simple-empty">Select one machine.</div>';return;}

  const p=payload(m);
  const raw=nested(p,'usb.devices',nested(p,'usb',[]));
  const devices=usbSimpleCleanDevices(raw);
  const search=(localStorage.getItem('sagar_usb_search')||'').toLowerCase().trim();
  const filtered=search ? devices.filter(u=>`${usbSimpleName(u)} ${usbSimpleType(u)} ${u.manufacturer||''} ${usbSimpleId(u)} ${usbSimpleCategory(u).simple}`.toLowerCase().includes(search)) : devices;
  const categories=[...new Set(devices.map(u=>usbSimpleCategory(u).simple).filter(Boolean))];
  const options=state.machines.map(x=>`<option value="${esc(x.machine_id)}" ${x.machine_id===m.machine_id?'selected':''}>${esc(usbSimpleMachineLabel(x))}</option>`).join('');

  el.innerHTML=`<div class="usb-simple-shell">
    <section class="usb-simple-hero">
      <div class="usb-simple-top">
        <div>
          <p class="usb-simple-eye">USB + Peripheral Center</p>
          <h2>${esc(host(m))}</h2>
          <p class="usb-simple-sub">Simple view of keyboard, mouse, headphone, camera, pen drive, printer and other connected devices.<br>${usbSimpleText(m.primary_ip||'No LAN IP')} Â· ${usbSimpleText(m.os||'Unknown OS')} Â· Last seen ${ago(m.updated_at)}</p>
        </div>
        <div class="usb-simple-control">
          <select class="usb-simple-select" onchange="usbSimpleSelectMachine(this.value)">${options}</select>
          <button class="usb-simple-btn download-only" onclick="usbSimpleDownloadUsb()">Download USB CSV</button>
          ${statusPill(m)}
        </div>
      </div>
      <div class="usb-simple-help">
        <div class="usb-simple-help-card"><span>Total Devices</span><strong>${devices.length}</strong><p>All USB/peripheral items detected on this machine.</p></div>
        <div class="usb-simple-help-card"><span>Showing Now</span><strong>${filtered.length}</strong><p>Devices after search/filter.</p></div>
        <div class="usb-simple-help-card"><span>Simple Categories</span><strong>${categories.length}</strong><p>Keyboard, mouse, audio, camera, storage, printer, etc.</p></div>
        <div class="usb-simple-help-card"><span>Selected Machine</span><strong>${esc(host(m))}</strong><p>This page shows only this PC/device.</p></div>
      </div>
    </section>

    <section class="usb-simple-section">
      <h3>Easy USB Device List <span class="usb-simple-badge">${filtered.length} devices</span></h3>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">
        <input class="usb-simple-search" value="${esc(localStorage.getItem('sagar_usb_search')||'')}" placeholder="Search keyboard / mouse / headphone / pendrive / device ID" oninput="usbSimpleSearch(this.value)">
        <button class="usb-simple-btn download-only" onclick="usbSimpleDownloadUsb()">Download Current USB List</button>
      </div>
      <div class="usb-simple-grid">${filtered.map(usbSimpleDeviceCard).join('') || '<div class="usb-simple-empty">No USB/peripheral data from this client.</div>'}</div>
    </section>

    <section class="usb-simple-section">
      <h3>Technical Details <span class="usb-simple-badge">For IT Team</span></h3>
      ${usbSimpleTable(filtered)}
    </section>

    <section class="usb-simple-section">
      <h3>Today USB Connected / Removed <span class="usb-simple-badge">Today</span></h3>
      <div id="usbSimpleTodayChangesBox"><div class="usb-simple-empty">Loading today USB changes...</div></div>
    </section>
  </div>`;
  setTimeout(()=>usbSimpleLoadTodayChanges(m.machine_id),120);
}
function renderUSB(){ return renderUsb(); }
/* USB_SIMPLE_HUMAN_PAGE_ONLY_END */

/* USB_CSS_PICTURE_ICONS_ONLY_START */
/*
  USB page icon fix only.
  Removes emoji dependency and broken mojibake text like Ã¢Å’Â¨Ã¯Â¸Â.
  Uses CSS-drawn picture icons instead.
*/
function usbSimpleIconPatchStyle(){
  const old=document.getElementById('usbSimpleIconPatchStyle');
  if(old) old.remove();
  const s=document.createElement('style');
  s.id='usbSimpleIconPatchStyle';
  s.textContent=`
    #page-usb .usb-simple-icon.usb-icon-host{
      position:relative;
      overflow:hidden;
      background:linear-gradient(135deg,#2563eb,#06b6d4)!important;
      box-shadow:0 16px 30px rgba(37,99,235,.26), inset 0 1px 0 rgba(255,255,255,.35)!important;
    }
    #page-usb .usb-simple-picture{
      width:42px;
      height:42px;
      display:grid;
      place-items:center;
      position:relative;
      animation:usbPicFloat 2.6s ease-in-out infinite;
    }
    #page-usb .usb-simple-picture span,
    #page-usb .usb-simple-picture i,
    #page-usb .usb-simple-picture b{
      position:absolute;
      display:block;
      box-sizing:border-box;
    }

    #page-usb .usb-pic-keyboard span{
      width:36px;height:22px;border-radius:7px;
      border:2px solid rgba(255,255,255,.96);
      background:
        repeating-linear-gradient(90deg,rgba(255,255,255,.92) 0 2px,transparent 2px 7px),
        repeating-linear-gradient(0deg,rgba(255,255,255,.72) 0 2px,transparent 2px 8px);
      bottom:8px;
    }
    #page-usb .usb-pic-keyboard i{width:22px;height:3px;border-radius:99px;background:#fff;bottom:12px}

    #page-usb .usb-pic-mouse span{
      width:24px;height:36px;border-radius:18px;
      border:2px solid #fff;top:3px;
    }
    #page-usb .usb-pic-mouse i{width:2px;height:12px;background:#fff;top:6px}
    #page-usb .usb-pic-mouse b{width:11px;height:2px;background:#fff;top:15px}

    #page-usb .usb-pic-audio span{
      width:32px;height:28px;border:3px solid #fff;border-bottom:0;border-radius:22px 22px 0 0;top:5px;
    }
    #page-usb .usb-pic-audio i{width:8px;height:18px;background:#fff;border-radius:6px;left:4px;bottom:4px}
    #page-usb .usb-pic-audio b{width:8px;height:18px;background:#fff;border-radius:6px;right:4px;bottom:4px}

    #page-usb .usb-pic-camera span{
      width:34px;height:24px;border-radius:8px;border:2px solid #fff;bottom:8px;
    }
    #page-usb .usb-pic-camera i{width:12px;height:12px;border-radius:50%;border:2px solid #fff;bottom:14px}
    #page-usb .usb-pic-camera b{width:14px;height:6px;border-radius:5px 5px 0 0;background:#fff;top:7px;left:10px}

    #page-usb .usb-pic-storage span{
      width:24px;height:34px;border-radius:7px;border:2px solid #fff;bottom:4px;
    }
    #page-usb .usb-pic-storage i{width:14px;height:6px;border-radius:2px;background:#fff;top:9px}
    #page-usb .usb-pic-storage b{width:10px;height:10px;border-radius:50%;border:2px solid #fff;bottom:9px}

    #page-usb .usb-pic-printer span{
      width:34px;height:22px;border-radius:8px;border:2px solid #fff;bottom:8px;
    }
    #page-usb .usb-pic-printer i{width:26px;height:13px;border-radius:4px;border:2px solid #fff;top:2px}
    #page-usb .usb-pic-printer b{width:20px;height:3px;border-radius:99px;background:#fff;bottom:13px}

    #page-usb .usb-pic-bluetooth span{
      width:26px;height:32px;top:5px;
    }
    #page-usb .usb-pic-bluetooth span:before,
    #page-usb .usb-pic-bluetooth span:after{
      content:"";position:absolute;left:10px;width:16px;height:16px;border-right:3px solid #fff;border-top:3px solid #fff;transform:rotate(45deg);
    }
    #page-usb .usb-pic-bluetooth span:after{top:15px;transform:rotate(135deg)}
    #page-usb .usb-pic-bluetooth i{width:3px;height:34px;background:#fff;left:19px;top:4px;transform:rotate(0deg)}

    #page-usb .usb-pic-hub span{
      width:34px;height:8px;border-radius:99px;background:#fff;bottom:10px;
    }
    #page-usb .usb-pic-hub i{width:8px;height:8px;border-radius:50%;background:#fff;top:7px}
    #page-usb .usb-pic-hub b{width:3px;height:18px;background:#fff;top:14px}

    #page-usb .usb-pic-usb span{
      width:28px;height:14px;border-radius:5px;border:2px solid #fff;bottom:12px;
    }
    #page-usb .usb-pic-usb i{width:10px;height:8px;border-radius:2px;background:#fff;top:8px}
    #page-usb .usb-pic-usb b{width:4px;height:18px;border-radius:4px;background:#fff;top:15px}

    @keyframes usbPicFloat{
      0%,100%{transform:translateY(0) rotateX(0)}
      50%{transform:translateY(-3px) rotateX(8deg)}
    }
  `;
  document.head.appendChild(s);
}

function usbSimpleCategory(u){
  const t=String(usbSimpleName(u)+' '+usbSimpleType(u)+' '+(u.manufacturer||'')).toLowerCase();
  if(t.includes('keyboard')) return {iconKey:'keyboard', simple:'Keyboard', meaning:'This is used for typing.'};
  if(t.includes('mouse')) return {iconKey:'mouse', simple:'Mouse', meaning:'This is used for clicking and moving the pointer.'};
  if(t.includes('audio')||t.includes('headphone')||t.includes('speaker')||t.includes('microphone')) return {iconKey:'audio', simple:'Audio device', meaning:'This is used for sound, headphone, speaker, or microphone.'};
  if(t.includes('camera')||t.includes('webcam')) return {iconKey:'camera', simple:'Camera', meaning:'This is used for video class, meeting, or recording.'};
  if(t.includes('storage')||t.includes('disk')||t.includes('drive')||t.includes('mass')) return {iconKey:'storage', simple:'Storage / Pen Drive', meaning:'This can store or transfer files.'};
  if(t.includes('printer')) return {iconKey:'printer', simple:'Printer', meaning:'This is used for printing.'};
  if(t.includes('bluetooth')) return {iconKey:'bluetooth', simple:'Bluetooth device', meaning:'This connects wireless accessories.'};
  if(t.includes('hub')) return {iconKey:'hub', simple:'USB Hub', meaning:'This adds more USB ports.'};
  return {iconKey:'usb', simple:'USB / Peripheral', meaning:'This is an external device connected to the computer.'};
}

function usbSimplePictureIcon(key,label){
  const safe=['keyboard','mouse','audio','camera','storage','printer','bluetooth','hub','usb'].includes(key) ? key : 'usb';
  return `<div class="usb-simple-picture usb-pic-${safe}" title="${esc(label)}"><span></span><i></i><b></b></div>`;
}

function usbSimpleDeviceCard(u,i){
  usbSimpleIconPatchStyle();
  const c=usbSimpleCategory(u);
  return `<article class="usb-simple-device">
    <div class="usb-simple-head">
      <div class="usb-simple-icon usb-icon-host">${usbSimplePictureIcon(c.iconKey,c.simple)}</div>
      <div class="usb-simple-name"><strong>${usbSimpleText(c.simple)}</strong><small>${usbSimpleText(usbSimpleName(u))}</small></div>
    </div>
    <div class="usb-simple-meaning">${esc(c.meaning)}</div>
    <div class="usb-simple-tags">
      <span class="usb-simple-tag">#${i+1}</span>
      <span class="usb-simple-tag">Type: ${usbSimpleText(usbSimpleType(u))}</span>
      <span class="usb-simple-tag">Status: ${usbSimpleText(usbSimpleStatus(u)||'N/A')}</span>
      <span class="usb-simple-tag">VID: ${usbSimpleText(u.vid||'N/A')}</span>
      <span class="usb-simple-tag">PID: ${usbSimpleText(u.pid||'N/A')}</span>
    </div>
  </article>`;
}
/* USB_CSS_PICTURE_ICONS_ONLY_END */

/* USB_SOFTWARE_CLEAN_DOWNLOAD_AND_CHANGES_FIX_START */
/*
  Fixes only USB + Software pages:
  1) Hide old mismatched header/download controls outside the new page shell.
  2) Keep only one clean download button.
  3) Today USB/Software Changes reads real human change records from /api/changes.
  4) Falls back from "today" to "recent" if date format/timezone causes blank result.
*/

function skFixRowsFromApi(d){
  if(Array.isArray(d)) return d;
  const keys=['changes','events','items','rows','records','logs'];
  for(const k of keys){
    if(d && Array.isArray(d[k])) return d[k];
  }
  if(d && d.data){
    if(Array.isArray(d.data)) return d.data;
    for(const k of keys){
      if(Array.isArray(d.data[k])) return d.data[k];
    }
  }
  return [];
}
function skFixText(c){
  try{
    return [
      c.change_type,c.type,c.category,c.kind,
      c.human_message,c.message,c.title,c.summary,c.description,c.details,
      c.added_text,c.removed_text,c.added,c.removed
    ].filter(Boolean).map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' ');
  }catch(e){
    return String(c.human_message||c.message||c.title||'');
  }
}
function skFixEsc(v){ return (typeof esc==='function') ? esc(v) : String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }
function skFixItems(){
  const out=[];
  for(const v of arguments){
    if(!v) continue;
    if(Array.isArray(v)){
      v.forEach(x=>{ const s=String(x||'').trim(); if(s) out.push(s); });
    }else if(typeof v==='object'){
      const s=JSON.stringify(v); if(s && s!=='{}') out.push(s);
    }else{
      String(v).split(/\s*\|\|\s*|\r?\n/).map(x=>x.trim()).filter(Boolean).forEach(x=>out.push(x));
    }
  }
  return [...new Set(out)].slice(0,60);
}
function skFixTime(c){
  return c.created_at||c.time||c.timestamp||c.created||c.updated_at||c.date||'';
}
function skFixIsTodayOrRecent(ts){
  if(!ts) return true;
  const d=new Date(ts);
  if(isNaN(d.getTime())) return true;
  const now=new Date();
  if(d.toDateString()===now.toDateString()) return true;
  return (now.getTime()-d.getTime()) <= (30*60*60*1000) && (now.getTime()-d.getTime()) >= 0;
}
function skFixMachineMatch(c,machineId){
  const m=(state.machines||[]).find(x=>x.machine_id===machineId)||null;
  const names=[
    machineId,
    m&&m.machine_id,
    m&&host(m),
    m&&m.hostname,
    m&&m.primary_ip,
    c.machine_id,c.host_id,c.hostname,c.host,c.machine,c.device_name,c.computer_name,c.pc_name
  ].filter(Boolean).map(x=>String(x).toLowerCase());
  const cMachine=String(c.machine_id||c.host_id||c.hostname||c.host||c.machine||c.computer_name||c.pc_name||'').toLowerCase();
  if(!cMachine) return true;
  return names.includes(cMachine);
}
function skFixIsUsbChange(c){
  const t=skFixText(c).toLowerCase();
  const ctype=String(c.change_type||c.type||c.category||'').toLowerCase();
  return ctype.includes('usb') || t.includes('usb') || t.includes('peripheral') || t.includes('keyboard') || t.includes('mouse') || t.includes('headphone') || t.includes('camera') || t.includes('printer') || t.includes('bluetooth') || t.includes('pen drive') || t.includes('pendrive');
}
function skFixIsSoftwareChange(c){
  const t=skFixText(c).toLowerCase();
  const ctype=String(c.change_type||c.type||c.category||'').toLowerCase();
  return ctype.includes('software') || ctype.includes('app') || t.includes('software') || t.includes('installed software') || t.includes('software list changed') || t.includes('program') || t.includes('application installed') || t.includes('application removed');
}
function skFixHideOldPageChrome(pageSel,shellSel,downloadLabel){
  const page=document.querySelector(pageSel);
  if(!page) return;
  const shell=page.querySelector(shellSel);

  // Hide old page top chrome that contains duplicate titles / old download buttons.
  [...page.children].forEach(ch=>{
    if(shell && (ch.contains(shell) || ch===shell || ch.querySelector(shellSel))) return;
    const tx=(ch.textContent||'').toLowerCase();
    if(tx.includes('download selected') || tx.includes('download all') || tx.includes('usb + peripherals') || tx.includes('software') || tx.includes('application center')){
      ch.style.display='none';
    }
  });

  // Keep only one download button inside the new shell.
  if(shell){
    const btns=[...shell.querySelectorAll('button.download-only')];
    btns.forEach((b,i)=>{
      b.textContent=downloadLabel;
      if(i>0) b.style.display='none';
    });
  }

  // Hide any old download buttons outside the new shell.
  [...page.querySelectorAll('button,a')].forEach(b=>{
    if(shell && shell.contains(b)) return;
    const tx=(b.textContent||'').toLowerCase();
    if(tx.includes('download selected') || tx.includes('download all') || tx.includes('download usb') || tx.includes('download software')){
      b.style.display='none';
    }
  });
}

async function usbSimpleLoadTodayChanges(machineId){
  const box=document.getElementById('usbSimpleTodayChangesBox') || document.getElementById('usbxTodayChangesBox');
  if(!box) return;
  try{
    const d=await api('/api/changes');
    const all=skFixRowsFromApi(d).filter(c=>skFixMachineMatch(c,machineId) && skFixIsUsbChange(c));

    let rows=all.filter(c=>skFixIsTodayOrRecent(skFixTime(c))).slice(0,100);
    let titleNote='';
    if(!rows.length && all.length){
      rows=all.slice(0,50);
      titleNote='<div class="usb-simple-empty" style="margin-bottom:10px">No exact today timestamp matched. Showing recent USB human change records.</div>';
    }

    if(!rows.length){
      box.innerHTML='<div class="usb-simple-empty">No USB connected or removed record found for selected machine.</div>';
      return;
    }

    box.innerHTML=titleNote+`<div class="usb-simple-change-list">${rows.map(c=>{
      const added=skFixItems(c.added_items,c.added_text,c.added,c.connected_items,c.connected_text,c.new_items);
      const removed=skFixItems(c.removed_items,c.removed_text,c.removed,c.disconnected_items,c.disconnected_text, c.old_items);
      const msg=skFixEsc(c.human_message||c.message||c.title||'USB/peripheral changed');
      let action='Changed', cls='usb-simple-badge';
      if(added.length && !removed.length){action='Connected'; cls='usb-simple-badge usb-simple-add';}
      if(removed.length && !added.length){action='Removed'; cls='usb-simple-badge usb-simple-rem';}
      if(added.length && removed.length){action='Connected + Removed';}
      const when=skFixTime(c);
      const whenText=when ? new Date(when).toLocaleString() : 'Time N/A';
      const addedHtml=added.length?added.map(skFixEsc).join('<br>'):'See details';
      const removedHtml=removed.length?removed.map(skFixEsc).join('<br>'):'See details';
      return `<div class="usb-simple-change">
        <div class="usb-simple-time">${skFixEsc(whenText)}<br><span class="${cls}">${action}</span></div>
        <div><strong>${msg}</strong><small>Connected / Added:<br>${addedHtml}</small></div>
        <div><strong>Removed / Disconnected</strong><small>${removedHtml}</small></div>
      </div>`;
    }).join('')}</div>`;
  }catch(e){
    box.innerHTML='<div class="usb-simple-empty">Unable to load USB changes from /api/changes.</div>';
  }
}

async function swfLoadTodayChanges(machineId){
  const box=document.getElementById('swfTodayChangesBox') || document.getElementById('swxTodayChangesBox') || document.getElementById('swaTodayChangesBox') || document.getElementById('swuTodayChangesBox');
  if(!box) return;
  try{
    const d=await api('/api/changes');
    const all=skFixRowsFromApi(d).filter(c=>skFixMachineMatch(c,machineId) && skFixIsSoftwareChange(c));

    let rows=all.filter(c=>skFixIsTodayOrRecent(skFixTime(c))).slice(0,100);
    let titleNote='';
    if(!rows.length && all.length){
      rows=all.slice(0,50);
      titleNote='<div class="swf-empty" style="margin-bottom:10px">No exact today timestamp matched. Showing recent software human change records.</div>';
    }

    if(!rows.length){
      box.innerHTML='<div class="swf-empty">No software added or removed record found for selected machine.</div>';
      return;
    }

    box.innerHTML=titleNote+`<div class="swf-change-list">${rows.map(c=>{
      const added=skFixItems(c.added_items,c.added_text,c.added,c.installed_items,c.installed_text,c.new_items,c.software_added);
      const removed=skFixItems(c.removed_items,c.removed_text,c.removed,c.uninstalled_items,c.uninstalled_text,c.old_items,c.software_removed);
      const msg=skFixEsc(c.human_message||c.message||c.title||'Software list changed');
      let action='Changed', cls='swf-badge';
      if(added.length && !removed.length){action='Added'; cls='swf-badge swf-add';}
      if(removed.length && !added.length){action='Removed'; cls='swf-badge swf-rem';}
      if(added.length && removed.length){action='Added + Removed';}
      const when=skFixTime(c);
      const whenText=when ? new Date(when).toLocaleString() : 'Time N/A';
      const addedHtml=added.length?added.map(skFixEsc).join('<br>'):'See details';
      const removedHtml=removed.length?removed.map(skFixEsc).join('<br>'):'See details';
      return `<div class="swf-change">
        <div class="swf-time">${skFixEsc(whenText)}<br><span class="${cls}">${action}</span></div>
        <div><strong>${msg}</strong><small>Added / Installed:<br>${addedHtml}</small></div>
        <div><strong>Removed / Uninstalled</strong><small>${removedHtml}</small></div>
      </div>`;
    }).join('')}</div>`;
  }catch(e){
    box.innerHTML='<div class="swf-empty">Unable to load software changes from /api/changes.</div>';
  }
}

if(typeof renderUsb==='function' && !window.__skUsbCleanFixWrapped){
  window.__skUsbCleanFixWrapped=true;
  window.__skOldRenderUsbCleanFix=renderUsb;
  renderUsb=function(){
    window.__skOldRenderUsbCleanFix();
    setTimeout(()=>{
      skFixHideOldPageChrome('#page-usb','.usb-simple-shell','Download USB CSV');
      const m=(typeof usbSimpleSelected==='function') ? usbSimpleSelected() : null;
      if(m) usbSimpleLoadTodayChanges(m.machine_id);
    },120);
  };
  renderUSB=function(){return renderUsb();};
}

if(typeof renderSoftware==='function' && !window.__skSoftwareCleanFixWrapped){
  window.__skSoftwareCleanFixWrapped=true;
  window.__skOldRenderSoftwareCleanFix=renderSoftware;
  renderSoftware=function(){
    window.__skOldRenderSoftwareCleanFix();
    setTimeout(()=>{
      skFixHideOldPageChrome('#page-software','.swf-shell','Download Software CSV');
      const m=(typeof swfSelected==='function') ? swfSelected() : null;
      if(m) swfLoadTodayChanges(m.machine_id);
    },120);
  };
}
/* USB_SOFTWARE_CLEAN_DOWNLOAD_AND_CHANGES_FIX_END */

