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


/* USB_SOFTWARE_HIDE_DUPLICATE_TOP_ONLY_START */
/*
  ONLY USB + Software duplicate cleanup.
  Does not change render logic.
  Does not touch Human page.
  Does not touch server.py.
  It only hides the old duplicate top area/search before the working page shell.
*/
(function(){
  function addStyle(){
    if(document.getElementById('skHideDupUsbSwStyle')) return;
    const s=document.createElement('style');
    s.id='skHideDupUsbSwStyle';
    s.textContent=`
      #page-usb .sk-hide-duplicate-top-only,
      #page-software .sk-hide-duplicate-top-only{
        display:none!important;
        visibility:hidden!important;
        height:0!important;
        min-height:0!important;
        margin:0!important;
        padding:0!important;
        overflow:hidden!important;
      }
    `;
    document.head.appendChild(s);
  }

  function isVisible(el){
    if(!el) return false;
    const st=getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden' && el.offsetParent!==null;
  }

  function isSearchInput(el){
    if(!el || el.tagName!=='INPUT') return false;
    const text=[
      el.type || '',
      el.placeholder || '',
      el.id || '',
      el.name || '',
      el.className || '',
      el.getAttribute('aria-label') || ''
    ].join(' ').toLowerCase();

    return (el.type||'').toLowerCase()==='search' ||
           text.includes('search') ||
           text.includes('filter');
  }

  function isDownload(el){
    if(!el) return false;
    const text=[
      el.textContent || '',
      el.id || '',
      el.className || '',
      el.getAttribute('aria-label') || ''
    ].join(' ').toLowerCase();
    return (el.tagName==='BUTTON' || el.tagName==='A') && text.includes('download');
  }

  function hide(el){
    if(!el) return;
    el.classList.add('sk-hide-duplicate-top-only');
    el.style.display='none';
  }

  function findShell(page, selectors){
    for(const sel of selectors){
      const e=page.querySelector(sel);
      if(e) return e;
    }
    return null;
  }

  function hideBeforeShell(page, shell){
    // Hide old duplicated header/controls that are before the working shell.
    let child=shell;
    while(child.parentElement && child.parentElement!==page){
      child=child.parentElement;
    }

    if(child.parentElement===page){
      let prev=child.previousElementSibling;
      while(prev){
        const p=prev;
        prev=prev.previousElementSibling;
        if(p.tagName==='SCRIPT' || p.tagName==='STYLE') continue;
        hide(p);
      }
    }

    // Also hide direct previous siblings of actual shell, if shell is directly placed after old header.
    let prev=shell.previousElementSibling;
    while(prev){
      const p=prev;
      prev=prev.previousElementSibling;
      if(p.tagName==='SCRIPT' || p.tagName==='STYLE') continue;
      hide(p);
    }
  }

  function keepOneSearch(page, shell){
    const searches=[...page.querySelectorAll('input')].filter(isSearchInput).filter(isVisible);
    if(searches.length <= 1) return;

    const inside=searches.filter(x=>shell.contains(x));
    const keep=(inside.length ? inside[inside.length-1] : searches[searches.length-1]);

    searches.forEach(x=>{
      if(x!==keep) hide(x);
    });
  }

  function keepOneMachineSelect(page, shell){
    const selects=[...page.querySelectorAll('select')].filter(isVisible);
    if(selects.length <= 1) return;

    const inside=selects.filter(x=>shell.contains(x));
    if(!inside.length) return;

    // Hide only selects outside the working shell. Do not touch select boxes inside shell.
    selects.forEach(x=>{
      if(!shell.contains(x)) hide(x);
    });
  }

  function keepOneDownload(page, shell){
    const downloads=[...page.querySelectorAll('button,a')].filter(isDownload).filter(isVisible);
    if(downloads.length <= 1) return;

    const inside=downloads.filter(x=>shell.contains(x));
    if(!inside.length) return;

    // Hide only download buttons outside the working shell.
    downloads.forEach(x=>{
      if(!shell.contains(x)) hide(x);
    });
  }

  function fixBrokenDot(page){
    // Only text cleanup, no layout/design change.
    const walker=document.createTreeWalker(page, NodeFilter.SHOW_TEXT);
    const nodes=[];
    while(walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(n=>{
      const old=n.nodeValue;
      const now=old.replace(/Â·/g,' - ').replace(/Â/g,'');
      if(now!==old) n.nodeValue=now;
    });
  }

  function cleanOne(pageSel, shellSelectors){
    const page=document.querySelector(pageSel);
    if(!page) return;

    const shell=findShell(page, shellSelectors);
    if(!shell) return;

    hideBeforeShell(page, shell);
    keepOneSearch(page, shell);
    keepOneMachineSelect(page, shell);
    keepOneDownload(page, shell);
    fixBrokenDot(page);
  }

  function run(){
    addStyle();

    cleanOne('#page-usb', [
      '.usb-simple-shell',
      '.usbx-shell',
      '.usb-shell',
      '#usbCards',
      '#usbTable',
      '.usb-list'
    ]);

    cleanOne('#page-software', [
      '.swf-shell',
      '.swx-shell',
      '.swa-shell',
      '.swu-shell',
      '.software-shell',
      '#softwareCards',
      '#softwareTable',
      '.software-list'
    ]);
  }

  ['renderUsb','renderUSB','renderSoftware'].forEach(fn=>{
    if(typeof window[fn]==='function' && !window['__skHideDupUsbSwWrap_'+fn]){
      window['__skHideDupUsbSwWrap_'+fn]=true;
      const old=window[fn];
      window[fn]=function(){
        const out=old.apply(this,arguments);
        setTimeout(run,80);
        setTimeout(run,350);
        return out;
      };
    }
  });

  setTimeout(run,500);
  setTimeout(run,1200);
  setInterval(run,2000);
})();
 /* USB_SOFTWARE_HIDE_DUPLICATE_TOP_ONLY_END */


/* USB_SOFTWARE_MINIMAL_SEARCH_FONT_FIX_START */
/*
  Minimal fix only:
  - USB + Software pages keep original page design.
  - Hide duplicate search boxes only.
  - Normal readable font only.
  - Replace broken mojibake text like Â· with normal dash.
  - Does not touch Human Change Log.
*/
(function(){
  function addStyle(){
    const old=document.getElementById('skMinSearchFontStyle');
    if(old) old.remove();
    const s=document.createElement('style');
    s.id='skMinSearchFontStyle';
    s.textContent=`
      #page-usb, #page-software,
      #page-usb *, #page-software *{
        font-family:"Segoe UI", Arial, sans-serif !important;
        letter-spacing:normal !important;
      }
      #page-usb .sk-min-hidden-duplicate,
      #page-software .sk-min-hidden-duplicate{
        display:none !important;
        visibility:hidden !important;
      }
    `;
    document.head.appendChild(s);
  }

  function isVisible(el){
    if(!el) return false;
    const st=getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden' && el.offsetParent!==null;
  }

  function isSearchInput(el){
    if(!el || el.tagName!=='INPUT') return false;
    const text=[
      el.type || '',
      el.placeholder || '',
      el.id || '',
      el.name || '',
      el.className || '',
      el.getAttribute('aria-label') || ''
    ].join(' ').toLowerCase();

    return (el.type||'').toLowerCase()==='search' ||
           text.includes('search') ||
           text.includes('filter');
  }

  function cleanBrokenText(page){
    if(!page) return;
    const walker=document.createTreeWalker(page, NodeFilter.SHOW_TEXT, null);
    const nodes=[];
    while(walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(n=>{
      let t=n.nodeValue;
      const nt=t
        .replace(/Â·/g,' - ')
        .replace(/âŒ¨ï¸/g,'')
        .replace(/â€”/g,'-')
        .replace(/â€“/g,'-')
        .replace(/Â/g,'');
      if(nt!==t) n.nodeValue=nt;
    });
  }

  function keepOnlyOneSearch(pageSel){
    const page=document.querySelector(pageSel);
    if(!page) return;

    cleanBrokenText(page);

    const searches=[...page.querySelectorAll('input')].filter(isSearchInput);

    searches.forEach(x=>{
      x.classList.remove('sk-min-hidden-duplicate');
      x.style.display='';
      x.style.visibility='';
    });

    const visible=searches.filter(isVisible);
    if(visible.length <= 1) return;

    // User said one search is not working and second is working.
    // So keep the last visible search box and hide only earlier duplicate search boxes.
    const keep=visible[visible.length-1];

    visible.forEach(x=>{
      if(x!==keep){
        x.classList.add('sk-min-hidden-duplicate');
        x.style.display='none';
      }
    });
  }

  function run(){
    addStyle();
    keepOnlyOneSearch('#page-usb');
    keepOnlyOneSearch('#page-software');
  }

  ['renderUsb','renderUSB','renderSoftware'].forEach(fn=>{
    if(typeof window[fn]==='function' && !window['__skMinSearchFontWrap_'+fn]){
      window['__skMinSearchFontWrap_'+fn]=true;
      const old=window[fn];
      window[fn]=function(){
        const out=old.apply(this,arguments);
        setTimeout(run,100);
        setTimeout(run,400);
        return out;
      };
    }
  });

  setTimeout(run,500);
  setInterval(run,1500);
})();
 /* USB_SOFTWARE_MINIMAL_SEARCH_FONT_FIX_END */

/* HRCL_SAFE_HUMAN_ONLY_START */
(function(){
  function $(s,r){return (r||document).querySelector(s)}
  function $all(s,r){return Array.from((r||document).querySelectorAll(s))}
  function text(el){return (el && (el.innerText || el.textContent) || '').trim()}
  function escHtml(v){
    return String(v == null ? '' : v).replace(/[&<>"']/g,function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function getApi(url){
    if (typeof api === 'function') return api(url);
    return fetch(url,{cache:'no-store'}).then(function(r){ return r.json(); });
  }
  function fmtDate(v){
    if(!v) return 'N/A';
    try { return new Date(v).toLocaleString(); } catch(e) { return String(v); }
  }
  function arrText(v){
    if(!v) return '';
    if(Array.isArray(v)) return v.map(function(x){return String(x)}).join(' | ');
    return String(v);
  }
  function titleOf(r){ return r.human_title || r.title || r.change_type || r.type || 'Change'; }
  function msgOf(r){ return r.human_message || r.summary || r.message || r.title || 'Change recorded'; }
  function csvCell(v){ return '"' + String(v == null ? '' : v).replace(/"/g,'""') + '"'; }

  function findHumanPage(){
    var p = $('#page-changes') || $('#page-history') || $('#page-change-log') || $('#page-changelog');
    if(p) return p;
    return $all('.page,[id^="page-"],main,section').find(function(x){
      var t = text(x).toLowerCase();
      return t.indexOf('human readable change log') >= 0 || (t.indexOf('refresh log') >= 0 && t.indexOf('download all change csv') >= 0);
    }) || document;
  }

  function findRefreshButton(page){
    return $all('button,a',page).find(function(b){
      return text(b).toLowerCase().indexOf('refresh log') >= 0;
    });
  }

  function addDateControls(){
    var page = findHumanPage();
    var refresh = findRefreshButton(page);
    if(!refresh) return;

    $all('#hrclSafeDateBox').forEach(function(x,i){ if(i>0) x.remove(); });
    if($('#hrclSafeDateBox')) return;

    var box = document.createElement('span');
    box.id = 'hrclSafeDateBox';
    box.style.display = 'inline-flex';
    box.style.alignItems = 'center';
    box.style.gap = '8px';
    box.style.flexWrap = 'wrap';
    box.style.marginLeft = '8px';
    box.innerHTML =
      '<label style="font-size:12px;font-weight:800;color:#64748b">From <input id="hrclSafeFrom" type="date" style="padding:7px;border-radius:8px;border:1px solid #cbd5e1;font-weight:700"></label>' +
      '<label style="font-size:12px;font-weight:800;color:#64748b">To <input id="hrclSafeTo" type="date" style="padding:7px;border-radius:8px;border:1px solid #cbd5e1;font-weight:700"></label>' +
      '<select id="hrclSafeLimit" style="padding:7px;border-radius:8px;border:1px solid #cbd5e1;font-weight:700"><option>500</option><option>1000</option><option selected>5000</option><option>10000</option></select>';

    refresh.insertAdjacentElement('afterend', box);

    $('#hrclSafeFrom').addEventListener('change', function(){ renderChanges(true); });
    $('#hrclSafeTo').addEventListener('change', function(){ renderChanges(true); });
    $('#hrclSafeLimit').addEventListener('change', function(){ renderChanges(true); });
  }

  function selectedMachineId(){
    var el = $('#changeMachine');
    if(el) return el.value || '';
    var page = findHumanPage();
    var sel = $all('select',page).find(function(s){ return s.id !== 'hrclSafeLimit'; });
    return sel ? (sel.value || '') : '';
  }

  function buildUrl(){
    var p = new URLSearchParams();
    var mid = selectedMachineId();
    var f = ($('#hrclSafeFrom') || {}).value || '';
    var t = ($('#hrclSafeTo') || {}).value || '';
    var lim = ($('#hrclSafeLimit') || {}).value || '5000';
    p.set('limit', lim);
    if(mid) p.set('machine_id', mid);
    if(f) p.set('from', f);
    if(t) p.set('to', t);
    return '/api/changes-range?' + p.toString();
  }

  function downloadRows(selectedOnly){
    var rows = window.__hrclSafeRows || [];
    if(selectedOnly){
      var ids = $all('.hrclSafeCheck:checked').map(function(x){ return String(x.value); });
      rows = ids.length ? rows.filter(function(r){ return ids.indexOf(String(r.id)) >= 0; }) : [];
    }

    var lines = [['ID','Created At','Machine ID','Hostname','Type','Title','Message','Added','Removed']];
    rows.forEach(function(r){
      lines.push([
        r.id,
        r.created_at,
        r.machine_id,
        r.hostname,
        r.change_type || r.type,
        titleOf(r),
        msgOf(r),
        arrText(r.added_items || r.added),
        arrText(r.removed_items || r.removed)
      ]);
    });

    var csv = lines.map(function(row){ return row.map(csvCell).join(','); }).join('\r\n');
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));
    a.download = (selectedOnly ? 'selected_' : 'all_') + 'human_change_log.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function hookDownloads(){
    var page = findHumanPage();
    $all('button,a',page).forEach(function(btn){
      var t = text(btn).toLowerCase();
      if(t.indexOf('download selected change csv') < 0 && t.indexOf('download all change csv') < 0) return;
      if(btn.dataset.hrclSafeDownload === '1') return;
      btn.dataset.hrclSafeDownload = '1';
      btn.addEventListener('click', function(ev){
        ev.preventDefault();
        ev.stopPropagation();
        ev.stopImmediatePropagation();
        downloadRows(t.indexOf('selected') >= 0);
      }, true);
    });
  }

  function details(r){
    var a = arrText(r.added_items || r.added);
    var rm = arrText(r.removed_items || r.removed);
    var out = '';
    if(a) out += '<div><b>Added:</b> ' + escHtml(a) + '</div>';
    if(rm) out += '<div><b>Removed:</b> ' + escHtml(rm) + '</div>';
    return out || '<span style="color:#64748b;font-size:12px">No extra details</span>';
  }

  function renderTable(rows){
    if(!rows.length){
      return '<div style="padding:14px;border:1px dashed #94a3b8;border-radius:12px;color:#64748b;font-weight:800;background:#fff">No real DB records found for selected machine/date range.</div>';
    }

    var html = '';
    html += '<div style="max-height:650px;overflow:auto;border:1px solid rgba(148,163,184,.25);border-radius:14px;background:#fff">';
    html += '<table style="width:100%;border-collapse:separate;border-spacing:0;min-width:1050px;font-size:13px">';
    html += '<thead><tr>';
    html += '<th style="position:sticky;top:0;background:#f8fbff;padding:10px;text-align:left"><input type="checkbox" id="hrclSafeAll"></th>';
    html += '<th style="position:sticky;top:0;background:#f8fbff;padding:10px;text-align:left">Time</th>';
    html += '<th style="position:sticky;top:0;background:#f8fbff;padding:10px;text-align:left">Machine</th>';
    html += '<th style="position:sticky;top:0;background:#f8fbff;padding:10px;text-align:left">Type</th>';
    html += '<th style="position:sticky;top:0;background:#f8fbff;padding:10px;text-align:left">Human Message</th>';
    html += '<th style="position:sticky;top:0;background:#f8fbff;padding:10px;text-align:left">Details</th>';
    html += '</tr></thead><tbody>';

    rows.forEach(function(r){
      html += '<tr>';
      html += '<td style="padding:10px;border-top:1px solid #e2e8f0"><input class="hrclSafeCheck" type="checkbox" value="' + escHtml(r.id) + '"></td>';
      html += '<td style="padding:10px;border-top:1px solid #e2e8f0">' + escHtml(fmtDate(r.created_at)) + '<div style="color:#64748b;font-size:12px">' + escHtml(r.created_at || '') + '</div></td>';
      html += '<td style="padding:10px;border-top:1px solid #e2e8f0"><b>' + escHtml(r.hostname || '') + '</b><div style="color:#64748b;font-size:12px">' + escHtml(r.machine_id || '') + '</div></td>';
      html += '<td style="padding:10px;border-top:1px solid #e2e8f0">' + escHtml(r.change_type || r.type || '') + '</td>';
      html += '<td style="padding:10px;border-top:1px solid #e2e8f0"><b>' + escHtml(titleOf(r)) + '</b><div>' + escHtml(msgOf(r)) + '</div></td>';
      html += '<td style="padding:10px;border-top:1px solid #e2e8f0">' + details(r) + '</td>';
      html += '</tr>';
    });

    html += '</tbody></table></div>';
    return html;
  }

  window.renderChanges = async function(force){
    addDateControls();
    hookDownloads();

    var el = $('#changeHistory');
    if(!el) return;

    el.innerHTML = '<div style="padding:12px;color:#64748b;font-weight:800">Loading real Human Change Log from DB...</div>';

    try{
      var d = await getApi(buildUrl());
      if(!d || d.ok === false) throw new Error((d && d.error) || 'API error');
      var rows = d.changes || [];
      window.__hrclSafeRows = rows;
      try{ if(window.state) state.changes = rows; }catch(e){}

      var f = ($('#hrclSafeFrom') || {}).value || '';
      var t = ($('#hrclSafeTo') || {}).value || '';
      var note = (f || t) ? ('Date range: ' + (f || 'start') + ' to ' + (t || 'end')) : 'Latest records';

      el.innerHTML = '<div style="margin:8px 0 10px;color:#64748b;font-size:13px;font-weight:800">Showing ' + rows.length + ' real DB record(s). ' + escHtml(note) + '</div>' + renderTable(rows);

      var all = $('#hrclSafeAll');
      if(all){
        all.addEventListener('change', function(){
          $all('.hrclSafeCheck').forEach(function(x){ x.checked = all.checked; });
        });
      }
    }catch(err){
      el.innerHTML = '<div style="padding:14px;border:1px solid #fecaca;border-radius:12px;background:#fff1f2;color:#991b1b;font-weight:800">Human Change Log error: ' + escHtml(err.message || err) + '</div>';
    }
  };

  setTimeout(function(){ addDateControls(); hookDownloads(); }, 700);
})();
/* HRCL_SAFE_HUMAN_ONLY_END */

/* HISTORY_FAST_3D_ONLY_START */
(function(){
  function q(s,r){return (r||document).querySelector(s)}
  function qa(s,r){return Array.from((r||document).querySelectorAll(s))}
  function safe(v){
    return String(v == null ? '' : v).replace(/[&<>"']/g,function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function txt(el){return (el && (el.innerText || el.textContent) || '').trim()}
  function apiGet(url){
    if(typeof api === 'function') return api(url);
    return fetch(url,{cache:'no-store'}).then(function(r){return r.json()});
  }
  function fmtTime(v){
    if(!v) return 'N/A';
    try{return new Date(v).toLocaleString()}catch(e){return String(v)}
  }
  function typeLabel(t){
    t=String(t||'').toLowerCase();
    if(t.indexOf('usb')>=0 || t.indexOf('peripheral')>=0) return 'USB';
    if(t.indexOf('software')>=0 || t.indexOf('app')>=0 || t.indexOf('install')>=0) return 'S/W';
    if(t.indexOf('vpn')>=0) return 'VPN';
    if(t.indexOf('ip')>=0 || t.indexOf('network')>=0 || t.indexOf('wan')>=0 || t.indexOf('internet')>=0 || t.indexOf('latency')>=0 || t.indexOf('dns')>=0) return 'Network';
    if(t.indexOf('hardware')>=0 || t.indexOf('cpu')>=0 || t.indexOf('ram')>=0 || t.indexOf('disk')>=0 || t.indexOf('gpu')>=0) return 'H/W';
    return t ? t.toUpperCase() : 'Change';
  }
  function titleOf(r){return r.human_title || r.title || r.change_type || r.type || 'Change'}
  function msgOf(r){return r.human_message || r.summary || r.message || r.title || 'Change recorded'}
  function arrText(v){
    if(!v)return '';
    if(Array.isArray(v)) return v.map(function(x){return String(x)}).join(' | ');
    return String(v);
  }
  function machineOptions(){
    var ms=[];
    try{ms=state.machines||[]}catch(e){}
    var html='<option value="">All machines</option>';
    ms.forEach(function(m){
      var id=m.machine_id||'';
      var name='';
      try{name=host(m)}catch(e){name=m.hostname||m.host||id}
      var ip=m.primary_ip || ((m.all_ips||[])[0]) || '';
      html += '<option value="'+safe(id)+'">'+safe(name)+(ip?' - '+safe(ip):'')+'</option>';
    });
    return html;
  }
  function page(){
    return q('#page-history') || q('#page-day-history') || q('#historyPage');
  }
  function addCss(){
    if(q('#historyFast3dCss')) return;
    var s=document.createElement('style');
    s.id='historyFast3dCss';
    s.textContent = `
      #page-history.history-fast-3d{
        position:relative;
        overflow:hidden;
        min-height:calc(100vh - 120px);
        padding:18px!important;
        color:#e5f2ff;
        background:
          radial-gradient(circle at 15% 20%, rgba(34,211,238,.26), transparent 26%),
          radial-gradient(circle at 80% 10%, rgba(168,85,247,.28), transparent 28%),
          radial-gradient(circle at 55% 90%, rgba(59,130,246,.24), transparent 30%),
          linear-gradient(135deg,#020617 0%,#0f172a 48%,#111827 100%)!important;
      }
      #page-history.history-fast-3d:before{
        content:"";
        position:absolute;
        inset:-30%;
        background:
          linear-gradient(rgba(255,255,255,.055) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,.055) 1px, transparent 1px);
        background-size:42px 42px;
        transform:perspective(700px) rotateX(63deg);
        animation:histGridMove 12s linear infinite;
        opacity:.42;
        pointer-events:none;
      }
      @keyframes histGridMove{from{background-position:0 0,0 0}to{background-position:0 42px,42px 0}}
      @keyframes histFloat{0%,100%{transform:translateY(0) rotateX(0deg) rotateY(0deg)}50%{transform:translateY(-9px) rotateX(4deg) rotateY(-4deg)}}
      @keyframes histOrbit{to{transform:rotate(360deg)}}
      .hist3d-root{position:relative;z-index:1;font-family:"Segoe UI",Arial,sans-serif}
      .hist3d-hero{
        display:grid;
        grid-template-columns:130px 1fr;
        gap:18px;
        align-items:center;
        padding:18px;
        border:1px solid rgba(148,163,184,.28);
        border-radius:28px;
        background:rgba(15,23,42,.66);
        box-shadow:0 28px 90px rgba(0,0,0,.42), inset 0 1px 0 rgba(255,255,255,.12);
        backdrop-filter:blur(15px);
        animation:histFloat 7s ease-in-out infinite;
      }
      .hist3d-globe{
        width:110px;height:110px;border-radius:50%;
        position:relative;
        background:radial-gradient(circle at 35% 28%,#67e8f9,#2563eb 52%,#1e1b4b 78%);
        box-shadow:0 0 40px rgba(34,211,238,.45), inset -22px -16px 35px rgba(2,6,23,.48);
      }
      .hist3d-globe:before,.hist3d-globe:after{
        content:"";position:absolute;inset:-9px;border-radius:50%;
        border:2px solid rgba(125,211,252,.45);
        border-left-color:transparent;border-right-color:transparent;
        animation:histOrbit 4.8s linear infinite;
      }
      .hist3d-globe:after{inset:14px;animation-duration:3.2s;transform:rotate(70deg)}
      .hist3d-title h1{margin:0;font-size:32px;letter-spacing:-.8px;color:#fff}
      .hist3d-title p{margin:8px 0 0;color:#b6c7e8;font-weight:700}
      .hist3d-controls{
        margin:16px 0;
        display:flex;gap:10px;flex-wrap:wrap;align-items:center;
        padding:12px;
        border:1px solid rgba(148,163,184,.22);
        border-radius:18px;
        background:rgba(15,23,42,.58);
        backdrop-filter:blur(10px);
      }
      .hist3d-controls select,.hist3d-controls input{
        border:1px solid rgba(148,163,184,.38);
        border-radius:13px;
        padding:10px 12px;
        background:rgba(255,255,255,.94);
        color:#0f172a;
        font-weight:800;
      }
      .hist3d-controls button{
        border:0;border-radius:13px;
        padding:11px 14px;
        color:#031827;
        font-weight:900;
        background:linear-gradient(135deg,#67e8f9,#a7f3d0);
        box-shadow:0 10px 30px rgba(34,211,238,.24);
        cursor:pointer;
      }
      .hist3d-stats{display:grid;grid-template-columns:repeat(5,minmax(130px,1fr));gap:12px;margin:14px 0}
      .hist3d-stat{
        border:1px solid rgba(148,163,184,.24);
        border-radius:20px;
        padding:14px;
        background:rgba(15,23,42,.62);
        box-shadow:0 16px 40px rgba(0,0,0,.22);
      }
      .hist3d-stat b{display:block;color:#fff;font-size:23px}
      .hist3d-stat span{color:#93c5fd;font-weight:800;font-size:12px;text-transform:uppercase}
      .hist3d-grid{display:grid;grid-template-columns:minmax(280px,390px) 1fr;gap:16px}
      .hist3d-days,.hist3d-events{
        border:1px solid rgba(148,163,184,.24);
        border-radius:24px;
        background:rgba(15,23,42,.66);
        backdrop-filter:blur(12px);
        box-shadow:0 22px 70px rgba(0,0,0,.3);
        overflow:hidden;
      }
      .hist3d-panel-head{
        padding:14px 16px;
        border-bottom:1px solid rgba(148,163,184,.18);
        display:flex;justify-content:space-between;gap:10px;align-items:center;
      }
      .hist3d-panel-head h2{margin:0;color:#fff;font-size:18px}
      .hist3d-day-list{max-height:620px;overflow:auto;padding:12px}
      .hist3d-day{
        margin:0 0 10px;
        padding:13px;
        border-radius:18px;
        border:1px solid rgba(148,163,184,.18);
        background:linear-gradient(135deg,rgba(30,41,59,.9),rgba(15,23,42,.74));
        cursor:pointer;
        transition:transform .18s ease, border-color .18s ease, background .18s ease;
      }
      .hist3d-day:hover,.hist3d-day.active{
        transform:translateY(-2px) scale(1.01);
        border-color:rgba(103,232,249,.7);
        background:linear-gradient(135deg,rgba(14,116,144,.45),rgba(30,41,59,.82));
      }
      .hist3d-day-top{display:flex;justify-content:space-between;gap:10px;align-items:center}
      .hist3d-day-date{font-weight:950;color:#fff;font-size:16px}
      .hist3d-count{font-weight:950;color:#67e8f9}
      .hist3d-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
      .hist3d-badge{
        font-size:11px;
        font-weight:950;
        border-radius:999px;
        padding:5px 8px;
        background:rgba(59,130,246,.18);
        color:#bfdbfe;
        border:1px solid rgba(147,197,253,.2);
      }
      .hist3d-event-list{max-height:620px;overflow:auto;padding:12px}
      .hist3d-event{
        display:grid;
        grid-template-columns:110px 1fr;
        gap:12px;
        margin-bottom:10px;
        padding:13px;
        border-radius:18px;
        border:1px solid rgba(148,163,184,.18);
        background:rgba(2,6,23,.34);
      }
      .hist3d-type{
        align-self:start;
        text-align:center;
        padding:9px 8px;
        border-radius:15px;
        background:linear-gradient(135deg,rgba(34,211,238,.24),rgba(168,85,247,.2));
        color:#e0f2fe;
        font-weight:950;
      }
      .hist3d-msg b{color:#fff}
      .hist3d-msg p{margin:6px 0;color:#dbeafe;font-weight:650}
      .hist3d-small{color:#93a4c3;font-size:12px;font-weight:700}
      .hist3d-empty{padding:18px;color:#cbd5e1;font-weight:900}
      @media(max-width:950px){.hist3d-grid{grid-template-columns:1fr}.hist3d-stats{grid-template-columns:repeat(2,1fr)}.hist3d-hero{grid-template-columns:1fr}.hist3d-globe{display:none}}
    `;
    document.head.appendChild(s);
  }
  function getFilters(){
    return {
      machine_id:(q('#histFastMachine')||{}).value||'',
      from:(q('#histFastFrom')||{}).value||'',
      to:(q('#histFastTo')||{}).value||'',
      limit:(q('#histFastLimit')||{}).value||'1000'
    };
  }
  function daysUrl(){
    var f=getFilters(), p=new URLSearchParams();
    p.set('mode','days');
    p.set('limit_days','1200');
    if(f.machine_id) p.set('machine_id',f.machine_id);
    if(f.from) p.set('from',f.from);
    if(f.to) p.set('to',f.to);
    return '/api/history-fast?'+p.toString();
  }
  function eventsUrl(day){
    var f=getFilters(), p=new URLSearchParams();
    p.set('mode','events');
    p.set('date',day);
    p.set('limit',f.limit || '1000');
    if(f.machine_id) p.set('machine_id',f.machine_id);
    return '/api/history-fast?'+p.toString();
  }
  function statSum(days,key){
    return days.reduce(function(n,d){return n + Number(d[key]||0)},0);
  }
  function dayBadges(d){
    var parts=[
      ['H/W',d.hardware_count],
      ['USB',d.usb_count],
      ['S/W',d.software_count],
      ['Network',d.network_count],
      ['VPN',d.vpn_count]
    ];
    return parts.filter(function(x){return Number(x[1]||0)>0}).map(function(x){
      return '<span class="hist3d-badge">'+safe(x[0])+': '+safe(x[1])+'</span>';
    }).join('');
  }
  function renderShell(){
    var p=page();
    if(!p) return null;
    addCss();
    p.classList.add('history-fast-3d');
    p.innerHTML =
      '<div class="hist3d-root">'+
        '<div class="hist3d-hero">'+
          '<div class="hist3d-globe"></div>'+
          '<div class="hist3d-title"><h1>History</h1><p>Fast global 3D change history. Shows only days where real changes happened: H/W, USB, S/W, Network and VPN.</p></div>'+
        '</div>'+
        '<div class="hist3d-controls">'+
          '<select id="histFastMachine">'+machineOptions()+'</select>'+
          '<label>From <input id="histFastFrom" type="date"></label>'+
          '<label>To <input id="histFastTo" type="date"></label>'+
          '<select id="histFastLimit"><option>300</option><option selected>1000</option><option>2000</option><option>5000</option></select>'+
          '<button id="histFastRefresh">Refresh History</button>'+
          '<button id="histFastDownload">Download Selected Day CSV</button>'+
        '</div>'+
        '<div id="histFastStats" class="hist3d-stats"></div>'+
        '<div class="hist3d-grid">'+
          '<div class="hist3d-days"><div class="hist3d-panel-head"><h2>Change Days</h2><span id="histFastDayCount" class="hist3d-small">Loading...</span></div><div id="histFastDays" class="hist3d-day-list"></div></div>'+
          '<div class="hist3d-events"><div class="hist3d-panel-head"><h2 id="histFastEventTitle">Selected Day Changes</h2><span id="histFastEventCount" class="hist3d-small"></span></div><div id="histFastEvents" class="hist3d-event-list"></div></div>'+
        '</div>'+
      '</div>';
    q('#histFastRefresh').onclick=function(){window.renderHistory(true)};
    q('#histFastMachine').onchange=function(){window.renderHistory(true)};
    q('#histFastFrom').onchange=function(){window.renderHistory(true)};
    q('#histFastTo').onchange=function(){window.renderHistory(true)};
    q('#histFastLimit').onchange=function(){ if(window.__histFastSelectedDay) loadEvents(window.__histFastSelectedDay); };
    q('#histFastDownload').onclick=function(){downloadEvents()};
    return p;
  }
  function renderStats(days){
    var html = '';
    html += '<div class="hist3d-stat"><span>Total Changes</span><b>'+safe(statSum(days,'total_count'))+'</b></div>';
    html += '<div class="hist3d-stat"><span>H/W</span><b>'+safe(statSum(days,'hardware_count'))+'</b></div>';
    html += '<div class="hist3d-stat"><span>USB</span><b>'+safe(statSum(days,'usb_count'))+'</b></div>';
    html += '<div class="hist3d-stat"><span>S/W</span><b>'+safe(statSum(days,'software_count'))+'</b></div>';
    html += '<div class="hist3d-stat"><span>Network + VPN</span><b>'+safe(statSum(days,'network_count')+statSum(days,'vpn_count'))+'</b></div>';
    q('#histFastStats').innerHTML=html;
  }
  function renderDays(days){
    q('#histFastDayCount').textContent=days.length+' day(s)';
    if(!days.length){
      q('#histFastDays').innerHTML='<div class="hist3d-empty">No change days found in DB.</div>';
      q('#histFastEvents').innerHTML='<div class="hist3d-empty">Select another range or machine.</div>';
      q('#histFastEventCount').textContent='';
      return;
    }
    q('#histFastDays').innerHTML=days.map(function(d,i){
      return '<div class="hist3d-day '+(i===0?'active':'')+'" data-day="'+safe(d.day)+'">'+
        '<div class="hist3d-day-top"><span class="hist3d-day-date">'+safe(d.day)+'</span><span class="hist3d-count">'+safe(d.total_count)+' changes</span></div>'+
        '<div class="hist3d-badges">'+dayBadges(d)+'</div>'+
      '</div>';
    }).join('');
    qa('.hist3d-day').forEach(function(card){
      card.onclick=function(){
        qa('.hist3d-day').forEach(function(x){x.classList.remove('active')});
        card.classList.add('active');
        loadEvents(card.dataset.day);
      };
    });
    loadEvents(days[0].day);
  }
  function renderEvents(day, rows){
    window.__histFastSelectedDay=day;
    window.__histFastEvents=rows;
    q('#histFastEventTitle').textContent='Changes on '+day;
    q('#histFastEventCount').textContent=rows.length+' record(s)';
    if(!rows.length){
      q('#histFastEvents').innerHTML='<div class="hist3d-empty">No change records for this day.</div>';
      return;
    }
    q('#histFastEvents').innerHTML=rows.map(function(r){
      var add=arrText(r.added_items||r.added);
      var rem=arrText(r.removed_items||r.removed);
      var detail='';
      if(add) detail+='<div class="hist3d-small"><b>Added:</b> '+safe(add)+'</div>';
      if(rem) detail+='<div class="hist3d-small"><b>Removed:</b> '+safe(rem)+'</div>';
      return '<div class="hist3d-event">'+
        '<div class="hist3d-type">'+safe(typeLabel(r.change_type||r.type))+'</div>'+
        '<div class="hist3d-msg">'+
          '<b>'+safe(titleOf(r))+'</b>'+
          '<p>'+safe(msgOf(r))+'</p>'+
          '<div class="hist3d-small">'+safe(fmtTime(r.created_at))+' | '+safe(r.hostname||'')+' | '+safe(r.machine_id||'')+'</div>'+
          detail+
        '</div>'+
      '</div>';
    }).join('');
  }
  async function loadEvents(day){
    q('#histFastEvents').innerHTML='<div class="hist3d-empty">Loading selected day changes...</div>';
    try{
      var d=await apiGet(eventsUrl(day));
      if(!d || d.ok===false) throw new Error((d&&d.error)||'API error');
      renderEvents(day,d.events||[]);
    }catch(e){
      q('#histFastEvents').innerHTML='<div class="hist3d-empty">Error loading events: '+safe(e.message||e)+'</div>';
    }
  }
  function csvCell(v){return '"'+String(v==null?'':v).replace(/"/g,'""')+'"'}
  function downloadEvents(){
    var rows=window.__histFastEvents||[];
    var csv=[['ID','Created At','Machine','Hostname','Type','Title','Message','Added','Removed']].concat(rows.map(function(r){
      return [r.id,r.created_at,r.machine_id,r.hostname,r.change_type||r.type,titleOf(r),msgOf(r),arrText(r.added_items||r.added),arrText(r.removed_items||r.removed)];
    })).map(function(row){return row.map(csvCell).join(',')}).join('\r\n');
    var a=document.createElement('a');
    a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));
    a.download='history_'+(window.__histFastSelectedDay||'selected_day')+'.csv';
    document.body.appendChild(a);a.click();a.remove();
  }
  window.renderHistory = async function(force){
    renderShell();
    q('#histFastDays').innerHTML='<div class="hist3d-empty">Loading change days fast from DB...</div>';
    q('#histFastEvents').innerHTML='<div class="hist3d-empty">Waiting for day selection...</div>';
    try{
      var d=await apiGet(daysUrl());
      if(!d || d.ok===false) throw new Error((d&&d.error)||'API error');
      var days=d.days||[];
      window.__histFastDays=days;
      renderStats(days);
      renderDays(days);
    }catch(e){
      q('#histFastDays').innerHTML='<div class="hist3d-empty">Error loading history: '+safe(e.message||e)+'</div>';
      q('#histFastStats').innerHTML='';
    }
  };
})();
/* HISTORY_FAST_3D_ONLY_END */

/* HW_INVENTORY_ONLY_START */
(function(){
  var HW_FIELDS = [
    ['sr_no','Sr. N.'], ['tagname_hostname','Tagname / Hostname'], ['room_location','Room No / Location'], ['person_allocated_to','Person Name / Allocated To'], ['assets_type','Assets Type'], ['oem_name','OEM Name'], ['model_no','Model No'], ['serial_no','Sr. No'], ['configuration','Configuration'], ['vendor_name','Vendor Name'], ['po_invoice_bill_no','PO / Invoice / Bill No'], ['bill_path_google_drive_path','Bill Path / Google Drive Path'], ['purchase_date','Purchase Date'], ['warranty_start_date','Warranty Start Date'], ['warranty_end_date','Warranty End Date'], ['warranty_status','Warranty Status'], ['status','Status'], ['remark','Remark']
  ];
  var STATUS_VALUES = ['Working','Not Working','Standby','On Repair','Not Working'];
  var WARRANTY_VALUES = ['Active','Expired','Unknown','Not Applicable'];
  function qs(s,r){return (r||document).querySelector(s)}
  function qsa(s,r){return Array.from((r||document).querySelectorAll(s))}
  function esc(v){return String(v == null ? '' : v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function apiGet(url){ if(typeof api==='function') return api(url); return fetch(url,{cache:'no-store'}).then(function(r){return r.json()}); }
  function apiPost(url,obj){
    if(obj && Array.isArray(obj.rows)){
      var saved=0,total=0;
      var p=Promise.resolve();
      obj.rows.forEach(function(row){
        p=p.then(function(){ return apiPost(url,{row:row}); }).then(function(d){
          if(!d.ok) throw new Error(d.error||'Save failed');
          saved += Number(d.saved||0);
          total = Number(d.total||total||0);
        });
      });
      return p.then(function(){ return {ok:true,saved:saved,total:total}; });
    }
    var qs=new URLSearchParams();
    qs.set('payload', JSON.stringify(obj||{}));
    var full=url + (url.indexOf('?')>=0?'&':'?') + qs.toString();
    if(typeof api==='function') return api(full);
    return fetch(full,{cache:'no-store'}).then(function(r){return r.json()});
  }
  function addStyle(){
    if(qs('#hwInventoryStyle')) return;
    var s=document.createElement('style');
    s.id='hwInventoryStyle';
    s.textContent='\n#page-hardware .hw-inv-root{font-family:"Segoe UI",Arial,sans-serif;color:#0f172a}\n.hw-inv-hero{position:relative;overflow:hidden;border-radius:28px;padding:22px;background:radial-gradient(circle at 18% 20%,rgba(34,211,238,.30),transparent 26%),radial-gradient(circle at 86% 10%,rgba(99,102,241,.25),transparent 28%),linear-gradient(135deg,#020617,#0f172a 52%,#111827);color:#fff;box-shadow:0 28px 90px rgba(15,23,42,.34)}\n.hw-inv-hero h1{margin:0;font-size:30px;letter-spacing:-.7px}.hw-inv-hero p{margin:8px 0 0;color:#c7d2fe;font-weight:700}.hw-inv-actions{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0;padding:12px;border-radius:18px;background:#fff;border:1px solid #e2e8f0;box-shadow:0 12px 28px rgba(15,23,42,.08)}.hw-inv-actions input,.hw-inv-actions select{padding:10px 12px;border-radius:12px;border:1px solid #cbd5e1;font-weight:800;min-width:150px}.hw-inv-actions button,.hw-inv-file{padding:10px 13px;border-radius:12px;border:0;background:linear-gradient(135deg,#2563eb,#06b6d4);color:#fff;font-weight:900;cursor:pointer}.hw-inv-kpis{display:grid;grid-template-columns:repeat(5,minmax(130px,1fr));gap:12px;margin:14px 0}.hw-inv-kpi{background:#fff;border:1px solid #e2e8f0;border-radius:18px;padding:13px;box-shadow:0 10px 25px rgba(15,23,42,.07)}.hw-inv-kpi b{font-size:24px;display:block}.hw-inv-kpi span{font-size:12px;font-weight:900;color:#64748b;text-transform:uppercase}.hw-inv-table-wrap{overflow:auto;max-height:650px;background:#fff;border:1px solid #e2e8f0;border-radius:22px;box-shadow:0 18px 50px rgba(15,23,42,.09)}.hw-inv-table{border-collapse:separate;border-spacing:0;min-width:2450px;width:100%;font-size:12px}.hw-inv-table th{position:sticky;top:0;z-index:2;background:#f8fafc;color:#334155;text-align:left;padding:10px;border-bottom:1px solid #e2e8f0;text-transform:uppercase;font-size:11px}.hw-inv-table td{padding:8px;border-bottom:1px solid #edf2f7;vertical-align:top}.hw-inv-table td[contenteditable="true"]{background:#fff;border-left:1px solid #f1f5f9;min-width:90px}.hw-inv-table td[contenteditable="true"]:focus{outline:2px solid #38bdf8;background:#f0f9ff}.hw-inv-status{min-width:120px;padding:7px;border:1px solid #cbd5e1;border-radius:10px;font-weight:800}.hw-pill{display:inline-block;border-radius:999px;padding:5px 8px;font-size:11px;font-weight:900;margin:2px}.hw-pill.live{background:#dcfce7;color:#166534}.hw-pill.miss{background:#fee2e2;color:#991b1b}.hw-pill.dup{background:#fef3c7;color:#92400e}.hw-inv-small{font-size:11px;color:#64748b;font-weight:700}.hw-inv-report{margin:10px 0;color:#475569;font-weight:800}.hw-inv-hidden{display:none!important}@media(max-width:900px){.hw-inv-kpis{grid-template-columns:repeat(2,1fr)}.hw-inv-hero h1{font-size:24px}.hw-inv-actions input,.hw-inv-actions select{min-width:100%;box-sizing:border-box}.hw-inv-actions button,.hw-inv-file{width:100%;box-sizing:border-box;text-align:center}}';
    document.head.appendChild(s);
  }
  function target(){ return qs('#hardwareCards') || qs('#page-hardware') || qs('#hardwareTable') || qs('.hardware-list'); }
  function csvCell(v){ return '"'+String(v==null?'':v).replace(/"/g,'""')+'"'; }
  function parseCsv(text){
    var rows=[], row=[], cur='', quote=false;
    for(var i=0;i<text.length;i++){
      var c=text[i], n=text[i+1];
      if(c==='"' && quote && n==='"'){cur+='"';i++;continue;}
      if(c==='"'){quote=!quote;continue;}
      if(c===',' && !quote){row.push(cur);cur='';continue;}
      if((c==='\n'||c==='\r') && !quote){ if(c==='\r'&&n==='\n')i++; row.push(cur); if(row.some(function(x){return String(x).trim()})) rows.push(row); row=[]; cur=''; continue;}
      cur+=c;
    }
    row.push(cur); if(row.some(function(x){return String(x).trim()})) rows.push(row);
    return rows;
  }
  function headersToKeys(headers){
    function clean(x){return String(x||'').toLowerCase().replace(/[^a-z0-9]/g,'');}
    var map={};
    HW_FIELDS.forEach(function(f){map[clean(f[1])]=f[0]; map[clean(f[0])]=f[0];});
    map['tagnamehostname']='tagname_hostname'; map['roomnolocation']='room_location'; map['personnameallocatedto']='person_allocated_to'; map['assetstype']='assets_type'; map['oemname']='oem_name'; map['modelno']='model_no'; map['srno']='serial_no'; map['serialno']='serial_no'; map['configration']='configuration'; map['configuration']='configuration'; map['vendorname']='vendor_name'; map['poinvoicebillno']='po_invoice_bill_no'; map['billpathorgoogledrivepath']='bill_path_google_drive_path'; map['purchasedate']='purchase_date'; map['warrantystartdate']='warranty_start_date'; map['warrantyenddate']='warranty_end_date'; map['warrantystatus']='warranty_status';
    return headers.map(function(h){return map[clean(h)] || '';});
  }
  function shell(){
    var el=target(); if(!el) return null; addStyle();
    el.innerHTML='<div class="hw-inv-root"><div class="hw-inv-hero"><h1>Hardware Inventory</h1><p>Editable hardware asset inventory synced with live monitoring data. Source loaded from your Nexttoppers Assets Detail workbook; duplicates are highlighted.</p></div><div class="hw-inv-actions"><input id="hwInvSearch" placeholder="Search tag, serial, person, room"><select id="hwInvType"><option value="">All Asset Types</option></select><select id="hwInvStatus"><option value="">All Status</option><option>Working</option><option>Not Working</option><option>Standby</option><option>On Repair</option></select><button id="hwInvRefresh">Refresh</button><button id="hwInvAdd">Add Row</button><button id="hwInvSave">Save Changes</button><button id="hwInvCsv">Download CSV</button><button id="hwInvSample">Sample CSV</button><label class="hw-inv-file">Upload CSV<input id="hwInvUpload" type="file" accept=".csv" class="hw-inv-hidden"></label></div><div id="hwInvReport" class="hw-inv-report">Loading inventory...</div><div id="hwInvKpis" class="hw-inv-kpis"></div><div class="hw-inv-table-wrap"><table class="hw-inv-table"><thead id="hwInvHead"></thead><tbody id="hwInvBody"></tbody></table></div></div>';
    qs('#hwInvRefresh').onclick=function(){loadInventory()};
    qs('#hwInvSearch').oninput=function(){clearTimeout(window.__hwInvTimer);window.__hwInvTimer=setTimeout(loadInventory,300)};
    qs('#hwInvType').onchange=loadInventory; qs('#hwInvStatus').onchange=loadInventory;
    qs('#hwInvAdd').onclick=addRow; qs('#hwInvSave').onclick=saveRows; qs('#hwInvCsv').onclick=downloadCsv; qs('#hwInvSample').onclick=downloadSample;
    qs('#hwInvUpload').onchange=uploadCsv;
    return el;
  }
  function renderHead(){
    qs('#hwInvHead').innerHTML='<tr><th>ID</th>'+HW_FIELDS.map(function(f){return '<th>'+esc(f[1])+'</th>';}).join('')+'<th>Live Sync</th><th>Duplicate</th></tr>';
  }
  function statusSelect(v){ return '<select class="hw-inv-status" data-key="status">'+STATUS_VALUES.map(function(x){return '<option '+(String(v||'').toLowerCase()===x.toLowerCase()?'selected':'')+'>'+esc(x)+'</option>';}).join('')+'</select>'; }
  function warrantySelect(v){ return '<select class="hw-inv-status" data-key="warranty_status">'+WARRANTY_VALUES.map(function(x){return '<option '+(String(v||'').toLowerCase()===x.toLowerCase()?'selected':'')+'>'+esc(x)+'</option>';}).join('')+'</select>'; }
  function renderRows(rows){
    renderHead();
    qs('#hwInvBody').innerHTML=rows.map(function(r){return rowHtml(r)}).join('');
    renderKpis(rows);
    updateTypeOptions(rows);
  }
  function rowHtml(r){
    var dup=[]; if(r.duplicate_tag) dup.push('Tag'); if(r.duplicate_serial) dup.push('Serial');
    var live = r.live_sync_status==='Live matched';
    var html='<tr data-id="'+esc(r.id||'')+'"><td class="hw-inv-small">'+esc(r.id||'new')+'</td>';
    HW_FIELDS.forEach(function(f){
      var k=f[0], v=r[k]||'';
      if(k==='status') html+='<td>'+statusSelect(v)+'</td>';
      else if(k==='warranty_status') html+='<td>'+warrantySelect(v)+'</td>';
      else html+='<td contenteditable="true" data-key="'+esc(k)+'">'+esc(v)+'</td>';
    });
    html+='<td><span class="hw-pill '+(live?'live':'miss')+'">'+esc(r.live_sync_status||'Not matched')+'</span><div class="hw-inv-small">'+esc(r.live_machine||'')+' '+esc(r.live_ip||'')+'</div></td>';
    html+='<td>'+(dup.length?'<span class="hw-pill dup">Duplicate '+esc(dup.join(' + '))+'</span>':'<span class="hw-inv-small">OK</span>')+'</td></tr>';
    return html;
  }
  function renderKpis(rows){
    var dup=rows.filter(function(r){return r.duplicate_tag||r.duplicate_serial}).length;
    var live=rows.filter(function(r){return r.live_sync_status==='Live matched'}).length;
    var working=rows.filter(function(r){return String(r.status||'').toLowerCase().indexOf('working')>=0 && String(r.status||'').toLowerCase().indexOf('not')<0}).length;
    var types={}; rows.forEach(function(r){if(r.assets_type) types[r.assets_type]=1;});
    qs('#hwInvKpis').innerHTML='<div class="hw-inv-kpi"><span>Shown</span><b>'+rows.length+'</b></div><div class="hw-inv-kpi"><span>Working</span><b>'+working+'</b></div><div class="hw-inv-kpi"><span>Live Matched</span><b>'+live+'</b></div><div class="hw-inv-kpi"><span>Duplicate Rows</span><b>'+dup+'</b></div><div class="hw-inv-kpi"><span>Asset Types</span><b>'+Object.keys(types).length+'</b></div>';
  }
  function updateTypeOptions(rows){
    var sel=qs('#hwInvType'), cur=sel.value, types={}; rows.forEach(function(r){if(r.assets_type)types[r.assets_type]=1;});
    var list=Object.keys(types).sort();
    sel.innerHTML='<option value="">All Asset Types</option>'+list.map(function(x){return '<option '+(x===cur?'selected':'')+'>'+esc(x)+'</option>';}).join('');
    if(cur) sel.value=cur;
  }
  async function loadInventory(){
    if(!qs('#hwInvBody')) shell();
    var p=new URLSearchParams();
    var q=qs('#hwInvSearch')?qs('#hwInvSearch').value:''; var t=qs('#hwInvType')?qs('#hwInvType').value:''; var s=qs('#hwInvStatus')?qs('#hwInvStatus').value:'';
    if(q)p.set('q',q); if(t)p.set('asset_type',t); if(s)p.set('status',s); p.set('limit','5000');
    qs('#hwInvReport').textContent='Loading hardware inventory from DB...';
    try{ var d=await apiGet('/api/hardware-inventory?'+p.toString()); if(!d.ok) throw new Error(d.error||'API error'); window.__hwInvRows=d.rows||[]; renderRows(window.__hwInvRows); qs('#hwInvReport').textContent='Loaded '+d.count+' row(s), total DB '+d.total+'. You can edit cells and click Save Changes.'; }
    catch(e){ qs('#hwInvReport').textContent='Hardware inventory error: '+(e.message||e); }
  }
  function collectRows(){ return qsa('#hwInvBody tr').map(function(tr){ var r={id:tr.dataset.id||''}; HW_FIELDS.forEach(function(f){ var k=f[0]; var el=qs('[data-key="'+k+'"]',tr); r[k]=el?('value' in el?el.value:el.innerText.trim()):''; }); return r; }); }
  async function saveRows(){
    var rows=collectRows(); qs('#hwInvReport').textContent='Saving '+rows.length+' inventory row(s)...';
    try{ var d=await apiPost('/api/hardware-inventory-save',{rows:rows}); if(!d.ok) throw new Error(d.error||'Save failed'); qs('#hwInvReport').textContent='Saved '+d.saved+' row(s). Refreshing...'; await loadInventory(); }
    catch(e){ qs('#hwInvReport').textContent='Save error: '+(e.message||e); }
  }
  function addRow(){
    var r={id:''}; HW_FIELDS.forEach(function(f){r[f[0]]=''}); r.sr_no=(qsa('#hwInvBody tr').length+1); r.status='Working'; r.warranty_status='Unknown'; r.live_sync_status='Not matched';
    qs('#hwInvBody').insertAdjacentHTML('beforeend',rowHtml(r));
  }
  function rowsToCsv(rows){ return [HW_FIELDS.map(function(f){return f[1];})].concat(rows.map(function(r){return HW_FIELDS.map(function(f){return r[f[0]]||'';});})).map(function(row){return row.map(csvCell).join(',');}).join('\r\n'); }
  function downloadCsv(){ var rows=collectRows(); var a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([rowsToCsv(rows)],{type:'text/csv;charset=utf-8;'})); a.download='hardware_inventory.csv'; document.body.appendChild(a); a.click(); a.remove(); }
  function downloadSample(){ var sample={}; HW_FIELDS.forEach(function(f){sample[f[0]]=''}); sample.sr_no='1'; sample.tagname_hostname='STU1_PC'; sample.room_location='Studio 1'; sample.person_allocated_to='Sagar'; sample.assets_type='CPU'; sample.oem_name='Dell'; sample.model_no='Optiplex'; sample.serial_no='SERIAL123'; sample.configuration='i5 / 16GB RAM / 512GB SSD'; sample.vendor_name='Vendor Name'; sample.po_invoice_bill_no='INV-001'; sample.bill_path_google_drive_path='https://drive.google.com/...'; sample.purchase_date='2026-01-01'; sample.warranty_start_date='2026-01-01'; sample.warranty_end_date='2029-01-01'; sample.warranty_status='Active'; sample.status='Working'; sample.remark='Sample row'; var a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([rowsToCsv([sample])],{type:'text/csv;charset=utf-8;'})); a.download='hardware_inventory_sample.csv'; document.body.appendChild(a); a.click(); a.remove(); }
  async function uploadCsv(ev){
    var file=ev.target.files[0]; if(!file)return; var text=await file.text(); var data=parseCsv(text); if(data.length<2){qs('#hwInvReport').textContent='CSV has no rows.';return;}
    var keys=headersToKeys(data[0]); var rows=[];
    data.slice(1).forEach(function(line){ var r={}; keys.forEach(function(k,i){ if(k) r[k]=line[i]||''; }); if(Object.keys(r).length) rows.push(r); });
    if(!rows.length){qs('#hwInvReport').textContent='CSV headers not matched. Download sample CSV and use same headers.';return;}
    qs('#hwInvReport').textContent='Uploading '+rows.length+' CSV row(s)...';
    try{ var d=await apiPost('/api/hardware-inventory-save',{rows:rows}); if(!d.ok) throw new Error(d.error||'Upload failed'); qs('#hwInvReport').textContent='Uploaded '+d.saved+' row(s). Refreshing...'; await loadInventory(); }
    catch(e){ qs('#hwInvReport').textContent='CSV upload error: '+(e.message||e); }
    ev.target.value='';
  }
  window.renderHardware = function(){ shell(); loadInventory(); };
})();
/* HW_INVENTORY_ONLY_END */

/* ASSETS_INVENTORY_V9_FAST_TABLE_ONLY_START */
(function(){
  function q(s,r){return (r||document).querySelector(s)}
  function qa(s,r){return Array.from((r||document).querySelectorAll(s))}
  function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function txt(el){return (el && (el.innerText || el.textContent) || '').trim()}
  function apiGet(url){ if(typeof api==='function') return api(url); return fetch(url,{cache:'no-store'}).then(r=>r.json()) }
  function csvCell(v){return '"' + String(v==null?'':v).replace(/"/g,'""') + '"'}
  function getPage(){ return q('#page-hardware') || q('#hardwareCards')?.closest('.page') || q('#hardwareTable')?.closest('.page') }

  const FIELDS=[
    ['tagname_hostname','Tagname / Hostname'],
    ['room_location','Room No / Location'],
    ['person_allocated_to','Allocated To'],
    ['assets_type','Assets Type'],
    ['oem_name','OEM Name'],
    ['model_no','Model No'],
    ['serial_no','Serial No'],
    ['configuration','Configuration'],
    ['vendor_name','Vendor Name'],
    ['po_invoice_bill_no','PO / Invoice / Bill No'],
    ['bill_path_google_drive_path','Bill / Drive Path'],
    ['purchase_date','Purchase Date'],
    ['warranty_start_date','Warranty Start Date'],
    ['warranty_end_date','Warranty End Date'],
    ['warranty_status','Warranty Status'],
    ['status','Status'],
    ['remark','Remark']
  ];
  const STATUS=['Working','Not Working','Standby','On Repair','Scrap','Missing','Unknown'];
  const PAGE_SIZE_OPTIONS=[25,50,100,200];

  function st(){
    window.__assetInvV9 = window.__assetInvV9 || {rows:[],loaded:false,search:'',status:'',type:'',sync:'',page:1,pageSize:50};
    return window.__assetInvV9;
  }

  function renameNav(){
    qa('[data-page="hardware"],.nav').forEach(function(el){
      if((el.dataset && el.dataset.page==='hardware') || txt(el)==='Hardware'){
        if(el.textContent.indexOf('Hardware')>=0 && el.textContent.indexOf('Assets Inventory')<0){
          el.innerHTML = el.innerHTML.replace(/Hardware/g,'Assets Inventory');
        }
      }
    });
  }

  function addCss(){
    if(q('#assetsInvV9Css')) return;
    const s=document.createElement('style');
    s.id='assetsInvV9Css';
    s.textContent=`
      #page-hardware.assets-inv-v9{
        position:relative; overflow:hidden; min-height:calc(100vh - 120px); padding:18px!important;
        background:
          radial-gradient(circle at 8% 4%, rgba(14,165,233,.14), transparent 28%),
          radial-gradient(circle at 92% 8%, rgba(99,102,241,.12), transparent 26%),
          linear-gradient(180deg,#f6f9ff 0%,#edf3fb 100%)!important;
        color:#10233f; font-family:"Inter","Segoe UI",Arial,sans-serif;
      }
      #page-hardware.assets-inv-v9:before{
        content:""; position:absolute; inset:0; pointer-events:none; opacity:.50;
        background:
          linear-gradient(135deg, rgba(255,255,255,.72), transparent 26%),
          linear-gradient(315deg, rgba(255,255,255,.32), transparent 28%);
      }
      @keyframes ai9Float{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
      @keyframes ai9Shine{0%{background-position:-220px 0}100%{background-position:calc(100% + 220px) 0}}
      .ai9-root{position:relative;z-index:1}
      .ai9-hero{
        display:grid; grid-template-columns:76px 1fr auto; gap:16px; align-items:center;
        padding:18px 22px; border-radius:28px;
        background:linear-gradient(135deg,#0b1220 0%,#172554 56%,#0f766e 138%);
        color:#fff; box-shadow:0 20px 60px rgba(15,23,42,.18); animation:ai9Float 7s ease-in-out infinite;
      }
      .ai9-cube{
        width:72px;height:72px;border-radius:22px;position:relative;
        background:linear-gradient(135deg,#67e8f9 0%,#3b82f6 52%,#8b5cf6 100%);
        box-shadow:0 16px 34px rgba(59,130,246,.34), inset -14px -14px 28px rgba(15,23,42,.25);
        transform:rotate(-8deg);
      }
      .ai9-cube:before{content:"";position:absolute;inset:12px;border-radius:17px;border:1.5px solid rgba(255,255,255,.45)}
      .ai9-hero h1{margin:0;font-size:32px;letter-spacing:-.9px}
      .ai9-hero p{margin:7px 0 0;color:#dbeafe;font-weight:650;font-size:14px}
      .ai9-hero-actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}
      .ai9-btn{
        border:0;border-radius:14px;padding:11px 15px;font-weight:850;font-size:13px;cursor:pointer;
        background:linear-gradient(135deg,#06b6d4,#22c55e);color:#062033;box-shadow:0 10px 30px rgba(34,197,94,.18);
      }
      .ai9-btn.secondary{background:#fff;color:#0f172a;border:1px solid #dbe6f4;box-shadow:0 8px 24px rgba(15,23,42,.06)}
      .ai9-btn.danger{background:linear-gradient(135deg,#fb7185,#f97316);color:#fff}
      .ai9-card,.ai9-toolbar,.ai9-stat,.ai9-section,.ai9-modal-card{
        background:rgba(255,255,255,.88); backdrop-filter:blur(14px); border:1px solid rgba(215,227,245,.95);
        box-shadow:0 10px 30px rgba(15,23,42,.06);
      }
      .ai9-toolbar{
        margin-top:16px; padding:14px; border-radius:22px;
        display:grid; grid-template-columns:minmax(260px,1fr) 165px 165px 155px auto; gap:10px; align-items:center;
      }
      .ai9-toolbar input,.ai9-toolbar select{
        border:1px solid #d7e3f5;background:#fff;color:#0f172a;border-radius:13px;padding:10px 12px;font-weight:750;outline:none;
      }
      .ai9-actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}
      .ai9-stats{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:14px;margin-top:16px}
      .ai9-stat{padding:16px;border-radius:22px;position:relative;overflow:hidden}
      .ai9-stat:before{content:"";position:absolute;inset:0;opacity:.7;background:linear-gradient(110deg,transparent 0%,rgba(255,255,255,.5) 40%,transparent 80%);background-size:220px 100%;animation:ai9Shine 5.5s linear infinite}
      .ai9-stat span{position:relative;display:block;color:#5b708d;font-size:12px;font-weight:850;text-transform:uppercase;letter-spacing:.55px}
      .ai9-stat b{position:relative;display:block;margin-top:5px;font-size:28px;color:#10233f}
      .ai9-section{border-radius:24px;overflow:hidden;margin-top:16px}
      .ai9-head{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:16px 18px;border-bottom:1px solid #e8eef8}
      .ai9-head h2{margin:0;font-size:20px;color:#10233f}
      .ai9-sub{color:#5b708d;font-size:12px;font-weight:750}
      .ai9-pill{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:#f1f7ff;border:1px solid #dbe6f4;color:#0f4c81;font-size:12px;font-weight:850}
      .ai9-sync-board{display:grid;grid-template-columns:repeat(4,minmax(170px,1fr));gap:14px;padding:16px}
      .ai9-sync-tile{border-radius:20px;padding:14px;background:#f8fbff;border:1px solid #e4edf9}
      .ai9-sync-tile span{display:block;color:#5b708d;font-size:12px;font-weight:850;text-transform:uppercase}
      .ai9-sync-tile b{display:block;color:#10233f;font-size:24px;margin-top:5px}
      .ai9-live{display:inline-flex;align-items:center;gap:7px;color:#15803d;font-weight:900}
      .ai9-dot{width:9px;height:9px;border-radius:50%;background:#22c55e;box-shadow:0 0 0 6px rgba(34,197,94,.13)}
      .ai9-quality{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;padding:16px}
      .ai9-issues{display:flex;gap:8px;flex-wrap:wrap}
      .ai9-issue{border-radius:999px;background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;padding:7px 10px;font-size:12px;font-weight:850}
      .ai9-issue.ok{background:#ecfdf5;color:#15803d;border-color:#bbf7d0}
      .ai9-table-wrap{overflow:auto;max-height:650px}
      .ai9-table{width:100%;border-collapse:separate;border-spacing:0;min-width:1180px;font-size:14px}
      .ai9-table th{
        position:sticky;top:0;z-index:2;padding:13px 11px;background:#f8fbff;color:#43617f;text-align:left;
        border-bottom:1px solid #dbe6f4;font-weight:900;white-space:nowrap;
      }
      .ai9-table td{padding:13px 11px;border-bottom:1px solid #edf2fa;color:#122033;vertical-align:middle}
      .ai9-table tr:hover td{background:#f9fcff}
      .ai9-main b{display:block;font-size:15px;color:#0f172a}
      .ai9-main small{display:block;color:#64748b;margin-top:3px;font-weight:750}
      .ai9-muted{color:#64748b;font-weight:700}
      .ai9-link{color:#0ea5e9;font-weight:850;text-decoration:none}
      .ai9-status,.ai9-sync{
        display:inline-flex;align-items:center;gap:7px;padding:6px 10px;border-radius:999px;font-size:12px;font-weight:900;border:1px solid transparent;white-space:nowrap;
      }
      .ai9-status .dot,.ai9-sync .dot{width:8px;height:8px;border-radius:50%}
      .ai9-sync.online{background:#ecfdf5;color:#15803d;border-color:#bbf7d0}
      .ai9-sync.matched{background:#eff6ff;color:#1d4ed8;border-color:#bfdbfe}
      .ai9-sync.nomatch{background:#f8fafc;color:#64748b;border-color:#e2e8f0}
      .ai9-pager{display:flex;gap:10px;justify-content:space-between;align-items:center;padding:14px 16px;border-top:1px solid #e8eef8;flex-wrap:wrap}
      .ai9-pager-left,.ai9-pager-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
      .ai9-dup-wrap{padding:16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px;max-height:520px;overflow:auto}
      .ai9-dup-card{border-radius:20px;background:#fff;border:1px solid #dfe9f7;border-left:5px solid var(--dup);overflow:hidden}
      .ai9-dup-top{padding:12px 14px;background:linear-gradient(90deg,var(--dup-soft),#fff);font-weight:900;color:#0f172a}
      .ai9-dup-top small{display:block;color:#64748b;font-weight:750;font-size:12px;margin-top:3px}
      .ai9-dup-row{display:flex;justify-content:space-between;gap:10px;padding:12px 14px;border-top:1px solid #eef3fb}
      .ai9-dup-row b{display:block;color:#0f172a}.ai9-dup-row small{display:block;color:#64748b;margin-top:3px;font-weight:700}
      .ai9-mini-btn{border:1px solid #d7e3f5;background:#fff;border-radius:11px;padding:8px 10px;font-size:12px;font-weight:850;cursor:pointer;color:#0f172a}
      .ai9-mini-btn.red{background:#fff1f2;color:#be123c;border-color:#fecdd3}
      .ai9-analytics{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;padding:16px}
      .ai9-analytic{border-radius:20px;padding:14px;background:#f8fbff;border:1px solid #e4edf9}
      .ai9-analytic span{display:block;color:#64748b;font-size:12px;font-weight:850;text-transform:uppercase}
      .ai9-analytic b{display:block;color:#10233f;font-size:21px;margin-top:5px}
      .ai9-modal{position:fixed;inset:0;z-index:9999;background:rgba(15,23,42,.38);backdrop-filter:blur(7px);display:flex;justify-content:center;align-items:center;padding:18px}
      .ai9-modal-card{width:min(1120px,96vw);max-height:92vh;overflow:auto;border-radius:28px}
      .ai9-modal-head{display:flex;justify-content:space-between;align-items:center;padding:18px 20px;border-bottom:1px solid #e8eef8}
      .ai9-modal-head h3{margin:0;font-size:22px;color:#10233f}
      .ai9-form{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:14px;padding:18px}
      .ai9-form label{font-size:12px;font-weight:850;color:#60758f}
      .ai9-form input,.ai9-form select,.ai9-form textarea{width:100%;box-sizing:border-box;margin-top:6px;padding:10px 12px;border-radius:13px;border:1px solid #d7e3f5;background:#fff;color:#0f172a;font-weight:700}
      .ai9-form textarea{min-height:80px;resize:vertical}
      .ai9-modal-foot{display:flex;justify-content:flex-end;gap:10px;padding:18px;border-top:1px solid #e8eef8}
      .ai9-empty{padding:18px;color:#5d728f;font-weight:850}
      .ai9-loading{padding:24px;color:#5d728f;font-weight:850}
      .ai9-skeleton{height:14px;border-radius:999px;background:linear-gradient(90deg,#eef4fb,#ffffff,#eef4fb);background-size:220px 100%;animation:ai9Shine 1.2s linear infinite;margin:10px 0}
      @media(max-width:1200px){
        .ai9-toolbar{grid-template-columns:1fr 1fr}.ai9-actions{grid-column:1/-1;justify-content:flex-start}
        .ai9-stats,.ai9-sync-board{grid-template-columns:repeat(3,1fr)}
      }
      @media(max-width:800px){
        .ai9-hero{grid-template-columns:1fr}.ai9-cube{display:none}.ai9-toolbar{grid-template-columns:1fr}
        .ai9-stats,.ai9-sync-board{grid-template-columns:repeat(2,1fr)}.ai9-quality{grid-template-columns:1fr}.ai9-form{grid-template-columns:1fr}
      }
      @media(max-width:560px){
        #page-hardware.assets-inv-v9{padding:10px!important}.ai9-stats,.ai9-sync-board{grid-template-columns:1fr}.ai9-hero h1{font-size:26px}
      }
    `;
    document.head.appendChild(s);
  }

  function normal(s){return String(s||'').trim().toLowerCase()}
  function liveMachines(){try{return state.machines||[]}catch(e){return[]}}
  function hostName(m){try{return (typeof host==='function')?host(m):(m.hostname||m.host||m.machine_id||'')}catch(e){return m.hostname||m.host||m.machine_id||''}}
  function isOnline(m){try{return String(m.status||'').toLowerCase()==='online'||!!m.online||(Date.now()-new Date(m.last_seen||m.updated_at||0).getTime()<90000)}catch(e){return false}}
  function liveIndex(){
    const idx=new Map();
    liveMachines().forEach(function(m){
      [hostName(m),m.hostname,m.host,m.machine_id,m.serial,m.serial_no,m.asset_tag,m.tagname_hostname].filter(Boolean).forEach(function(v){
        const k=normal(v); if(k) idx.set(k,m);
      });
    });
    return idx;
  }
  function syncFor(row,idx){
    idx=idx||liveIndex();
    const keys=[row.tagname_hostname,row.serial_no].filter(Boolean).map(normal);
    let m=null;
    for(const k of keys){ if(idx.has(k)){m=idx.get(k);break;} }
    if(!m){
      const tag=normal(row.tagname_hostname);
      if(tag && tag.length>3){
        for(const [k,v] of idx.entries()){ if(k.length>3 && (k.includes(tag)||tag.includes(k))){m=v;break;} }
      }
    }
    if(!m) return {state:'nomatch',label:'No Live Match',machine:null};
    return {state:isOnline(m)?'online':'matched',label:isOnline(m)?'Live Online':'Live Matched',machine:m};
  }

  function statusBadge(v){
    const s=String(v||'Unknown'), low=s.toLowerCase();
    let bg='#eff6ff',bd='#bfdbfe',fg='#1d4ed8',dot='#3b82f6';
    if(low.includes('work')&&!low.includes('not')){bg='#ecfdf5';bd='#bbf7d0';fg='#15803d';dot='#22c55e'}
    else if(low.includes('repair')){bg='#fffbeb';bd='#fde68a';fg='#a16207';dot='#f59e0b'}
    else if(low.includes('not')){bg='#fff1f2';bd='#fecdd3';fg='#be123c';dot='#fb7185'}
    else if(low.includes('stand')){bg='#f5f3ff';bd='#ddd6fe';fg='#6d28d9';dot='#8b5cf6'}
    return `<span class="ai9-status" style="background:${bg};border-color:${bd};color:${fg}"><span class="dot" style="background:${dot}"></span>${esc(s)}</span>`;
  }
  function syncBadge(s){return `<span class="ai9-sync ${esc(s.state)}"><span class="dot"></span>${esc(s.label)}</span>`}

  async function loadRows(force){
    const x=st();
    if(x.loaded && !force) return x.rows;
    const d=await apiGet('/api/hardware-inventory?limit=20000');
    if(!d || d.ok===false) throw new Error((d&&d.error)||'Inventory API error');
    x.rows=d.rows || d.inventory || [];
    x.loaded=true;
    return x.rows;
  }

  async function savePayload(obj){
    const p=new URLSearchParams(); p.set('payload', JSON.stringify(obj||{}));
    const d=await apiGet('/api/hardware-inventory-save?'+p.toString());
    if(!d || d.ok===false) throw new Error((d&&d.error)||'Save failed');
    st().loaded=false;
    return d;
  }
  async function deleteIds(ids){
    if(!ids.length) return;
    if(!confirm('Delete selected asset(s)?')) return;
    const d=await apiGet('/api/hardware-inventory-delete?ids='+encodeURIComponent(ids.join(',')));
    if(!d || d.ok===false) throw new Error((d&&d.error)||'Delete failed');
    st().loaded=false;
    return d;
  }

  function assetTypes(rows){return Array.from(new Set(rows.map(r=>String(r.assets_type||'Unknown').trim()||'Unknown'))).sort();}
  function filterRows(){
    const x=st(), s=normal(x.search), idx=liveIndex();
    return (x.rows||[]).filter(r=>{
      if(x.status && normal(r.status)!==normal(x.status)) return false;
      if(x.type && normal(r.assets_type)!==normal(x.type)) return false;
      if(x.sync && syncFor(r,idx).state!==x.sync) return false;
      if(s){
        const blob=[r.id,r.tagname_hostname,r.room_location,r.person_allocated_to,r.assets_type,r.oem_name,r.model_no,r.serial_no,r.configuration,r.vendor_name,r.status,r.remark].join(' ').toLowerCase();
        if(!blob.includes(s)) return false;
      }
      return true;
    });
  }
  function pageRows(rows){
    const x=st();
    const totalPages=Math.max(1,Math.ceil(rows.length/x.pageSize));
    if(x.page>totalPages) x.page=totalPages;
    if(x.page<1) x.page=1;
    const start=(x.page-1)*x.pageSize;
    return rows.slice(start,start+x.pageSize);
  }

  function duplicateGroups(rows){
    const map={};
    function push(kind,key,row){key=normal(key);if(!key||['na','n/a','none','unknown','nil','-'].includes(key))return;const id=kind+':'+key;map[id]=map[id]||{kind:kind,key:key,rows:[]};map[id].rows.push(row)}
    rows.forEach(r=>{push('Tag / Hostname',r.tagname_hostname,r);push('Serial No',r.serial_no,r)});
    return Object.values(map).filter(g=>g.rows.length>1).sort((a,b)=>b.rows.length-a.rows.length);
  }
  function quality(rows){
    const dups=duplicateGroups(rows);
    const missingTag=rows.filter(r=>!String(r.tagname_hostname||'').trim()).length;
    const missingSerial=rows.filter(r=>!String(r.serial_no||'').trim()).length;
    const unknownStatus=rows.filter(r=>!String(r.status||'').trim()||normal(r.status)==='unknown').length;
    let fixable=0; rows.forEach(r=>{const n=normalizeRow(r); if(JSON.stringify(n)!==JSON.stringify(pickFields(r))) fixable++});
    return {dups,missingTag,missingSerial,unknownStatus,fixable};
  }
  function pickFields(r){const o={id:r.id};FIELDS.forEach(f=>o[f[0]]=r[f[0]]||'');return o}
  function capWords(s){return String(s||'').toLowerCase().replace(/\b\w/g,m=>m.toUpperCase())}
  function normStatus(s){
    const x=normal(s); if(!x) return 'Unknown';
    if(x.includes('stand'))return'Standby'; if(x.includes('repair'))return'On Repair'; if(x.includes('not')||x.includes('dead')||x.includes('fault'))return'Not Working'; if(x.includes('work')||x==='ok'||x==='active')return'Working'; if(x.includes('scrap'))return'Scrap'; if(x.includes('miss'))return'Missing';
    return capWords(s);
  }
  function normalizeRow(r){
    const o=pickFields(r);
    Object.keys(o).forEach(k=>{if(k!=='id')o[k]=String(o[k]||'').trim().replace(/\s+/g,' ')});
    o.status=normStatus(o.status);
    if(o.tagname_hostname && /^[a-z0-9_-]+$/i.test(o.tagname_hostname)) o.tagname_hostname=o.tagname_hostname.toUpperCase();
    if(o.serial_no && /^[a-z0-9_-]+$/i.test(o.serial_no)) o.serial_no=o.serial_no.toUpperCase();
    if(o.warranty_end_date){const d=new Date(o.warranty_end_date);if(!isNaN(d))o.warranty_status=d.getTime()>=new Date().setHours(0,0,0,0)?'In Warranty':'Expired'}
    if(!o.warranty_status)o.warranty_status='Unknown';
    return o;
  }
  async function autoCorrect(){
    const rows=filterRows();
    const changed=rows.map(r=>normalizeRow(r)).filter((n,i)=>JSON.stringify(n)!==JSON.stringify(pickFields(rows[i])));
    if(!changed.length){alert('No auto-correctable data found.');return}
    if(!confirm('Auto-correct '+changed.length+' rows? It fixes spacing, status spelling, warranty status, tag/serial case. It will not delete duplicates.'))return;
    for(const row of changed){await savePayload({row})}
    alert('Auto-correct completed: '+changed.length+' rows updated.');
    await window.renderHardware(true);
  }

  function toolbar(){
    const x=st(), types=assetTypes(x.rows||[]);
    return `<div class="ai9-toolbar">
      <input id="ai9Search" placeholder="Search asset, serial, room, person, configuration..." value="${esc(x.search)}">
      <select id="ai9Status"><option value="">All Status</option>${STATUS.map(s=>`<option ${x.status===s?'selected':''}>${esc(s)}</option>`).join('')}</select>
      <select id="ai9Type"><option value="">All Asset Types</option>${types.map(t=>`<option ${x.type===t?'selected':''}>${esc(t)}</option>`).join('')}</select>
      <select id="ai9Sync"><option value="">All Live Sync</option><option value="online" ${x.sync==='online'?'selected':''}>Live Online</option><option value="matched" ${x.sync==='matched'?'selected':''}>Live Matched</option><option value="nomatch" ${x.sync==='nomatch'?'selected':''}>No Live Match</option></select>
      <div class="ai9-actions">
        <button class="ai9-btn secondary" id="ai9Refresh">Refresh</button>
        <button class="ai9-btn" id="ai9Add">Add Asset</button>
        <button class="ai9-btn secondary" id="ai9AutoFix">Auto Correct</button>
        <button class="ai9-btn secondary" id="ai9Sample">Sample CSV</button>
        <label class="ai9-btn secondary" style="cursor:pointer">Upload CSV<input id="ai9Upload" type="file" accept=".csv" style="display:none"></label>
        <button class="ai9-btn secondary" id="ai9Download">Download CSV</button>
      </div>
    </div>`;
  }

  function stats(rows){
    const idx=liveIndex(), syncs=rows.map(r=>syncFor(r,idx)), q=quality(rows);
    const working=rows.filter(r=>normal(r.status).includes('work')&&!normal(r.status).includes('not')).length;
    return `<div class="ai9-stats">
      ${[['Total Assets',rows.length],['Working',working],['Live Online',syncs.filter(s=>s.state==='online').length],['Live Matched',syncs.filter(s=>s.state==='matched').length],['No Live Match',syncs.filter(s=>s.state==='nomatch').length],['Duplicate Groups',q.dups.length]].map(m=>`<div class="ai9-stat"><span>${esc(m[0])}</span><b>${esc(m[1])}</b></div>`).join('')}
    </div>`;
  }

  function liveSyncSummary(rows){
    const syncs=rows.map(r=>syncFor(r,liveIndex()));
    return `<div class="ai9-section"><div class="ai9-head"><div><h2>Asset-wise Live Sync</h2><div class="ai9-sub">Each row below shows live sync status. Matching is by tag / hostname or serial number.</div></div><span class="ai9-live"><span class="ai9-dot"></span>Live Sync Active</span></div>
      <div class="ai9-sync-board">
        <div class="ai9-sync-tile"><span>Live Machines</span><b>${esc(liveMachines().length)}</b></div>
        <div class="ai9-sync-tile"><span>Live Online Assets</span><b>${esc(syncs.filter(s=>s.state==='online').length)}</b></div>
        <div class="ai9-sync-tile"><span>Live Matched Assets</span><b>${esc(syncs.filter(s=>s.state==='matched').length)}</b></div>
        <div class="ai9-sync-tile"><span>No Live Match</span><b>${esc(syncs.filter(s=>s.state==='nomatch').length)}</b></div>
      </div>
    </div>`;
  }

  function qualitySection(rows){
    const x=quality(rows);
    return `<div class="ai9-section"><div class="ai9-head"><div><h2>Data Quality & Auto Correct</h2><div class="ai9-sub">Simple checks for wrong/missing data. Auto Correct does not delete duplicates.</div></div><button class="ai9-btn" id="ai9AutoFix2">Auto Correct Data</button></div>
      <div class="ai9-quality"><div class="ai9-issues">
        <span class="ai9-issue ${x.missingTag?'':'ok'}">Missing Tag: ${esc(x.missingTag)}</span>
        <span class="ai9-issue ${x.missingSerial?'':'ok'}">Missing Serial: ${esc(x.missingSerial)}</span>
        <span class="ai9-issue ${x.unknownStatus?'':'ok'}">Unknown Status: ${esc(x.unknownStatus)}</span>
        <span class="ai9-issue ${x.dups.length?'':'ok'}">Duplicate Groups: ${esc(x.dups.length)}</span>
        <span class="ai9-issue ${x.fixable?'':'ok'}">Auto-fixable Rows: ${esc(x.fixable)}</span>
      </div><div class="ai9-sub">For duplicates, review below and delete only the wrong rows.</div></div>
    </div>`;
  }

  function tableSection(rows){
    const idx=liveIndex(), x=st(), visible=pageRows(rows), totalPages=Math.max(1,Math.ceil(rows.length/x.pageSize)), start=rows.length?((x.page-1)*x.pageSize+1):0, end=Math.min(rows.length,x.page*x.pageSize);
    const body=visible.map(r=>{
      const s=syncFor(r,idx);
      return `<tr>
        <td><b>${esc(r.id||'')}</b></td>
        <td><div class="ai9-main"><b>${esc(r.tagname_hostname||'No Tag')}</b><small>${esc(r.assets_type||'Unknown Type')} · ${esc(r.oem_name||'')}</small></div></td>
        <td>${esc(r.room_location||'—')}</td>
        <td>${esc(r.person_allocated_to||'—')}</td>
        <td>${esc(r.serial_no||'—')}</td>
        <td>${syncBadge(s)}${s.machine?`<div class="ai9-muted" style="font-size:12px;margin-top:4px">${esc(hostName(s.machine))}</div>`:''}</td>
        <td>${statusBadge(r.status)}</td>
        <td>${esc(r.warranty_status||'Unknown')}</td>
        <td>${esc(r.configuration||'—')}</td>
        <td><div style="display:flex;gap:8px;flex-wrap:wrap"><button class="ai9-mini-btn" onclick="assetInvV9Edit('${esc(r.id)}')">Edit</button><button class="ai9-mini-btn" onclick="assetInvV9Details('${esc(r.id)}')">Details</button><button class="ai9-mini-btn red" onclick="assetInvV9Delete('${esc(r.id)}')">Delete</button></div></td>
      </tr>`;
    }).join('');
    return `<div class="ai9-section"><div class="ai9-head"><div><h2>Assets Inventory Table</h2><div class="ai9-sub">Fast tabular view. Only ${esc(x.pageSize)} rows render at a time for speed.</div></div><span class="ai9-pill">${esc(rows.length)} filtered rows</span></div>
      <div class="ai9-table-wrap"><table class="ai9-table"><thead><tr>
        <th>ID</th><th>Asset / Type</th><th>Location</th><th>Allocated To</th><th>Serial No</th><th>Live Sync</th><th>Status</th><th>Warranty</th><th>Configuration</th><th>Action</th>
      </tr></thead><tbody>${body || '<tr><td colspan="10"><div class="ai9-empty">No assets found for this filter.</div></td></tr>'}</tbody></table></div>
      <div class="ai9-pager"><div class="ai9-pager-left"><span class="ai9-sub">Showing ${esc(start)}-${esc(end)} of ${esc(rows.length)}</span><select id="ai9PageSize">${PAGE_SIZE_OPTIONS.map(n=>`<option ${x.pageSize===n?'selected':''}>${n}</option>`).join('')}</select></div><div class="ai9-pager-right"><button class="ai9-mini-btn" id="ai9Prev">Previous</button><span class="ai9-pill">Page ${esc(x.page)} / ${esc(totalPages)}</span><button class="ai9-mini-btn" id="ai9Next">Next</button></div></div>
    </div>`;
  }

  function duplicateSection(rows){
    const groups=duplicateGroups(rows).slice(0,60);
    if(!groups.length)return `<div class="ai9-section"><div class="ai9-head"><div><h2>Duplicate Review</h2><div class="ai9-sub">Below table. Same-color groups appear here.</div></div><span class="ai9-pill">0 group</span></div><div class="ai9-empty">No duplicate groups found.</div></div>`;
    return `<div class="ai9-section"><div class="ai9-head"><div><h2>Duplicate Review</h2><div class="ai9-sub">Below table. Review same-color groups, then delete wrong rows only.</div></div><span class="ai9-pill">${esc(groups.length)} shown</span></div>
      <div class="ai9-dup-wrap">${groups.map((g,i)=>`<div class="ai9-dup-card" style="--dup:${['#0ea5e9','#8b5cf6','#10b981','#f59e0b','#ec4899','#2563eb','#14b8a6','#ef4444'][i%8]};--dup-soft:${['#e0f2fe','#f3e8ff','#dcfce7','#fef3c7','#fce7f3','#dbeafe','#ccfbf1','#fee2e2'][i%8]}"><div class="ai9-dup-top">${esc(g.kind)} duplicate: ${esc(g.key)} <small>${g.rows.length} rows found</small></div>${g.rows.slice(0,5).map(r=>`<div class="ai9-dup-row"><div><b>${esc(r.tagname_hostname||'No Tag')}</b><small>ID ${esc(r.id||'')} · ${esc(r.assets_type||'')} · ${esc(r.room_location||'')}</small><small>Serial: ${esc(r.serial_no||'')} · Allocated: ${esc(r.person_allocated_to||'')}</small></div><div style="display:flex;gap:8px;flex-wrap:wrap"><button class="ai9-mini-btn" onclick="assetInvV9Edit('${esc(r.id)}')">Review</button><button class="ai9-mini-btn red" onclick="assetInvV9Delete('${esc(r.id)}')">Delete</button></div></div>`).join('')}${g.rows.length>5?`<div class="ai9-empty">+ ${esc(g.rows.length-5)} more rows in this duplicate group.</div>`:''}</div>`).join('')}</div>
    </div>`;
  }

  function analyticsSection(rows){
    const typeMap={}, locMap={};
    rows.forEach(r=>{const t=String(r.assets_type||'Unknown').trim()||'Unknown';const l=String(r.room_location||'Unknown').trim()||'Unknown';typeMap[t]=(typeMap[t]||0)+1;locMap[l]=(locMap[l]||0)+1});
    const items=Object.entries(typeMap).sort((a,b)=>b[1]-a[1]).slice(0,6).map(x=>['Type: '+x[0],x[1]]).concat(Object.entries(locMap).sort((a,b)=>b[1]-a[1]).slice(0,6).map(x=>['Location: '+x[0],x[1]]));
    return `<div class="ai9-section"><div class="ai9-head"><div><h2>Inventory Analytics</h2><div class="ai9-sub">Future Hardware Analytics is now Inventory Analytics.</div></div><span class="ai9-pill">Analytics</span></div><div class="ai9-analytics">${items.map(x=>`<div class="ai9-analytic"><span>${esc(x[0])}</span><b>${esc(x[1])}</b></div>`).join('')}</div></div>`;
  }

  function shell(rows){
    const filtered=filterRows();
    return `<div class="ai9-root"><div class="ai9-hero"><div class="ai9-cube"></div><div><h1>Assets Inventory</h1><p>International tabular inventory view designed for simple reading, fast loading, asset-wise live sync, duplicate review and data correction.</p></div><div class="ai9-hero-actions"><button class="ai9-btn" id="ai9HeroAdd">+ Add Asset</button><button class="ai9-btn secondary" id="ai9HeroRefresh">Refresh</button></div></div>
      ${toolbar()}${stats(filtered)}${liveSyncSummary(filtered)}${qualitySection(filtered)}${tableSection(filtered)}${duplicateSection(filtered)}${analyticsSection(filtered)}
    </div>`;
  }

  function bind(){
    q('#ai9Search')?.addEventListener('input',function(){st().search=this.value;st().page=1;clearTimeout(window.__ai9search);window.__ai9search=setTimeout(()=>window.renderHardware(false),200)});
    q('#ai9Status')?.addEventListener('change',function(){st().status=this.value;st().page=1;window.renderHardware(false)});
    q('#ai9Type')?.addEventListener('change',function(){st().type=this.value;st().page=1;window.renderHardware(false)});
    q('#ai9Sync')?.addEventListener('change',function(){st().sync=this.value;st().page=1;window.renderHardware(false)});
    q('#ai9Refresh')?.addEventListener('click',()=>window.renderHardware(true));
    q('#ai9HeroRefresh')?.addEventListener('click',()=>window.renderHardware(true));
    q('#ai9Add')?.addEventListener('click',()=>openModal({}));
    q('#ai9HeroAdd')?.addEventListener('click',()=>openModal({}));
    q('#ai9AutoFix')?.addEventListener('click',()=>autoCorrect().catch(e=>alert('Auto correct failed: '+(e.message||e))));
    q('#ai9AutoFix2')?.addEventListener('click',()=>autoCorrect().catch(e=>alert('Auto correct failed: '+(e.message||e))));
    q('#ai9Download')?.addEventListener('click',downloadCurrent);
    q('#ai9Sample')?.addEventListener('click',downloadSample);
    q('#ai9Upload')?.addEventListener('change',uploadCsv);
    q('#ai9PageSize')?.addEventListener('change',function(){st().pageSize=parseInt(this.value,10)||50;st().page=1;window.renderHardware(false)});
    q('#ai9Prev')?.addEventListener('click',function(){st().page=Math.max(1,st().page-1);window.renderHardware(false)});
    q('#ai9Next')?.addEventListener('click',function(){const total=Math.max(1,Math.ceil(filterRows().length/st().pageSize));st().page=Math.min(total,st().page+1);window.renderHardware(false)});
  }

  function fieldInput(k,label,row){
    const val=row[k]||'';
    if(k==='status')return `<label>${esc(label)}<select name="${esc(k)}">${STATUS.map(s=>`<option ${normal(val)===normal(s)?'selected':''}>${esc(s)}</option>`).join('')}</select></label>`;
    if(k==='remark'||k==='configuration')return `<label>${esc(label)}<textarea name="${esc(k)}">${esc(val)}</textarea></label>`;
    const type=(k.includes('date')?'date':'text');
    return `<label>${esc(label)}<input type="${type}" name="${esc(k)}" value="${esc(val)}"></label>`;
  }
  function openModal(row){
    row=row||{};
    const modal=document.createElement('div');
    modal.className='ai9-modal';
    modal.innerHTML=`<div class="ai9-modal-card"><div class="ai9-modal-head"><h3>${row.id?'Asset Details / Edit':'Add New Asset'}</h3><button class="ai9-mini-btn" id="ai9Close">Close</button></div><form id="ai9Form"><input type="hidden" name="id" value="${esc(row.id||'')}"><div class="ai9-form">${FIELDS.map(f=>fieldInput(f[0],f[1],row)).join('')}</div><div class="ai9-modal-foot"><button type="button" class="ai9-btn secondary" id="ai9Cancel">Cancel</button><button class="ai9-btn" type="submit">Save Asset</button></div></form></div>`;
    document.body.appendChild(modal);
    function close(){modal.remove()}
    q('#ai9Close',modal).onclick=close;q('#ai9Cancel',modal).onclick=close;
    q('#ai9Form',modal).onsubmit=async function(ev){ev.preventDefault();const data={};new FormData(ev.target).forEach((v,k)=>data[k]=v);try{await savePayload({row:data});close();await window.renderHardware(true)}catch(e){alert('Save failed: '+(e.message||e))}};
  }
  window.assetInvV9Edit=function(id){const r=(st().rows||[]).find(x=>String(x.id)===String(id));if(r)openModal(r)};
  window.assetInvV9Details=function(id){const r=(st().rows||[]).find(x=>String(x.id)===String(id));if(r)openModal(r)};
  window.assetInvV9Delete=function(id){deleteIds([id]).then(()=>window.renderHardware(true)).catch(e=>alert('Delete failed: '+(e.message||e)))};

  function downloadCurrent(){
    const rows=filterRows(), headers=['ID'].concat(FIELDS.map(f=>f[1])), keys=['id'].concat(FIELDS.map(f=>f[0]));
    const csv=[headers].concat(rows.map(r=>keys.map(k=>r[k]||''))).map(r=>r.map(csvCell).join(',')).join('\r\n');
    const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));a.download='assets_inventory_current.csv';document.body.appendChild(a);a.click();a.remove();
  }
  function downloadSample(){
    const headers=FIELDS.map(f=>f[1]);
    const sample=['NXT-PC-001','Studio 1','Sagar','Desktop','Dell','OptiPlex','ABC12345','i5 / 16GB / 512 SSD','Vendor Name','INV-001','https://drive.google.com/...','2026-01-01','2026-01-01','2027-01-01','In Warranty','Working','Sample remark'];
    const csv=[headers,sample].map(r=>r.map(csvCell).join(',')).join('\r\n');
    const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));a.download='assets_inventory_sample_upload.csv';document.body.appendChild(a);a.click();a.remove();
  }
  function parseCsv(text){
    const rows=[];let row=[],cur='',inQ=false;
    for(let i=0;i<text.length;i++){const ch=text[i],nx=text[i+1];if(ch==='"'&&inQ&&nx==='"'){cur+='"';i++;continue}if(ch==='"'){inQ=!inQ;continue}if(ch===','&&!inQ){row.push(cur);cur='';continue}if((ch==='\n'||ch==='\r')&&!inQ){if(ch==='\r'&&nx==='\n')i++;row.push(cur);if(row.some(x=>String(x).trim()))rows.push(row);row=[];cur='';continue}cur+=ch}
    row.push(cur);if(row.some(x=>String(x).trim()))rows.push(row);return rows;
  }
  function normHeader(h){return String(h||'').toLowerCase().replace(/[^a-z0-9]/g,'')}
  const MAP={tagnamehostname:'tagname_hostname',taghostname:'tagname_hostname',hostname:'tagname_hostname',tagname:'tagname_hostname',roomnolocation:'room_location',roomlocation:'room_location',roomno:'room_location',location:'room_location',room:'room_location',allocatedto:'person_allocated_to',personallocatedto:'person_allocated_to',personnameallocatedto:'person_allocated_to',personname:'person_allocated_to',assetstype:'assets_type',assettype:'assets_type',oemname:'oem_name',oem:'oem_name',modelno:'model_no',modleno:'model_no',model:'model_no',serialno:'serial_no',serialnumber:'serial_no',srno:'serial_no',configuration:'configuration',configration:'configuration',vendorname:'vendor_name',vendor:'vendor_name',poinvoicebillno:'po_invoice_bill_no',poinvicebillno:'po_invoice_bill_no',billno:'po_invoice_bill_no',invoice:'po_invoice_bill_no',billpathgoogledrivepath:'bill_path_google_drive_path',billpathorgoogledrivepath:'bill_path_google_drive_path',billpath:'bill_path_google_drive_path',purchasedate:'purchase_date',purchessdate:'purchase_date',warrantystartdate:'warranty_start_date',warntystartdate:'warranty_start_date',warrantyenddate:'warranty_end_date',warrentyenddate:'warranty_end_date',warrantystatus:'warranty_status',warrentystaus:'warranty_status',status:'status',remark:'remark'};
  async function uploadCsv(ev){
    const file=ev.target.files&&ev.target.files[0];if(!file)return;
    const grid=parseCsv(await file.text());if(grid.length<2){alert('CSV has no data');return}
    const headers=grid[0].map(h=>MAP[normHeader(h)]||'');
    const rows=grid.slice(1).map(r=>{const o={};headers.forEach((k,i)=>{if(k)o[k]=r[i]||''});return o}).filter(o=>Object.values(o).some(v=>String(v||'').trim()));
    if(!rows.length){alert('No valid rows found in CSV');return}
    if(!confirm('Upload '+rows.length+' asset rows?'))return;
    for(const row of rows){await savePayload({row})}
    alert('CSV upload complete: '+rows.length+' row(s)');await window.renderHardware(true);
  }

  window.renderHardware=async function(force){
    renameNav();
    const page=getPage(); if(!page)return;
    addCss(); page.classList.add('assets-inv-v9');
    if(!st().loaded || force) page.innerHTML='<div class="ai9-root"><div class="ai9-hero"><div class="ai9-cube"></div><div><h1>Assets Inventory</h1><p>Loading fast tabular inventory...</p><div class="ai9-skeleton"></div><div class="ai9-skeleton" style="width:70%"></div></div></div></div>';
    try{await loadRows(force);page.innerHTML=shell(st().rows);bind();renameNav();}
    catch(e){page.innerHTML='<div class="ai9-root"><div class="ai9-empty">Assets Inventory error: '+esc(e.message||e)+'</div></div>'}
  };
  setTimeout(renameNav,500);setInterval(renameNav,2500);
})();
/* ASSETS_INVENTORY_V9_FAST_TABLE_ONLY_END */

/* SW_INVENTORY_NEW_TAB_ONLY_START */
(function(){
  function q(s,r){return (r||document).querySelector(s)}
  function qa(s,r){return Array.from((r||document).querySelectorAll(s))}
  function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function text(el){return (el && (el.innerText || el.textContent) || '').trim()}
  function apiGet(url){ if(typeof api==='function') return api(url); return fetch(url,{cache:'no-store'}).then(r=>r.json()) }
  function csvCell(v){return '"' + String(v==null?'':v).replace(/"/g,'""') + '"'}
  const FIELDS=[
    ['software_name','Software Name'],
    ['category','Category'],
    ['login_url','Login / Website URL'],
    ['username','User ID / Email'],
    ['password_value','Password'],
    ['license_key','License Key'],
    ['mfa_recovery','MFA / Recovery Info'],
    ['machine_asset','Machine / Asset Tag'],
    ['allocated_to','Allocated To'],
    ['vendor_name','Vendor Name'],
    ['po_invoice_bill_no','PO / Invoice / Bill No'],
    ['bill_path_google_drive_path','Bill / Google Drive Path'],
    ['purchase_date','Purchase Date'],
    ['renewal_expiry_date','Renewal / Expiry Date'],
    ['status','Status'],
    ['notes','Notes']
  ];
  const STATUS=['Active','Expired','Trial','Free','Disabled','Shared','Unknown'];
  const CATS=['OS','Productivity','Design','Development','Security','Education','Cloud','Communication','Utility','Other'];
  function st(){
    window.__swInv = window.__swInv || {rows:[],loaded:false,search:'',status:'',category:'',page:1,pageSize:50,showPasswords:{}};
    return window.__swInv;
  }
  function ensureTab(){
    let page=q('#page-sw-inventory');
    if(!page){
      const ref=q('#page-software') || q('.page:last-of-type');
      page=document.createElement('section');
      page.id='page-sw-inventory';
      page.className='page';
      if(ref && ref.parentElement) ref.insertAdjacentElement('afterend',page); else document.body.appendChild(page);
    }
    let nav=q('[data-page="sw-inventory"]');
    if(!nav){
      const ref=q('[data-page="software"]') || qa('.nav').find(n=>text(n).toLowerCase().includes('software'));
      if(ref){
        nav=ref.cloneNode(true);
        nav.dataset.page='sw-inventory';
        nav.textContent='S/W Inventory';
        nav.classList.remove('active');
        ref.insertAdjacentElement('afterend',nav);
      }else{
        nav=document.createElement('button');
        nav.className='nav';
        nav.dataset.page='sw-inventory';
        nav.textContent='S/W Inventory';
        const side=q('aside')||q('.sidebar')||document.body;
        side.appendChild(nav);
      }
    }
    if(!nav.dataset.swInvBound){
      nav.dataset.swInvBound='1';
      nav.addEventListener('click',function(ev){ev.preventDefault(); goSwInventory();});
    }
  }
  function goSwInventory(){
    ensureTab();
    try{ if(window.state) state.page='sw-inventory'; }catch(e){}
    qa('.page').forEach(p=>p.classList.remove('active'));
    q('#page-sw-inventory')?.classList.add('active');
    qa('.nav,[data-page]').forEach(n=>{ if(n.dataset && n.dataset.page) n.classList.toggle('active',n.dataset.page==='sw-inventory'); });
    renderSoftwareInventory(true);
  }
  function addCss(){
    if(q('#swInvCss')) return;
    const s=document.createElement('style');
    s.id='swInvCss';
    s.textContent=`
      #page-sw-inventory.sw-inv-page{position:relative;min-height:calc(100vh - 120px);padding:18px!important;background:radial-gradient(circle at 10% 5%,rgba(14,165,233,.13),transparent 28%),radial-gradient(circle at 90% 8%,rgba(16,185,129,.12),transparent 28%),linear-gradient(180deg,#f7fbff,#eef4fb)!important;color:#10233f;font-family:"Inter","Segoe UI",Arial,sans-serif}
      #page-sw-inventory.sw-inv-page:before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.45;background:linear-gradient(135deg,rgba(255,255,255,.7),transparent 28%)}
      @keyframes swFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}} @keyframes swShine{0%{background-position:-220px 0}100%{background-position:calc(100% + 220px) 0}}
      .sw-root{position:relative;z-index:1}.sw-hero{display:grid;grid-template-columns:72px 1fr auto;gap:16px;align-items:center;padding:18px 22px;border-radius:28px;background:linear-gradient(135deg,#0b1220,#172554 56%,#065f46 135%);color:#fff;box-shadow:0 20px 60px rgba(15,23,42,.18);animation:swFloat 7s ease-in-out infinite}
      .sw-cube{width:70px;height:70px;border-radius:22px;background:linear-gradient(135deg,#34d399,#3b82f6,#8b5cf6);box-shadow:0 16px 34px rgba(59,130,246,.32),inset -14px -14px 28px rgba(15,23,42,.25);transform:rotate(-8deg)}
      .sw-hero h1{margin:0;font-size:32px;letter-spacing:-.9px}.sw-hero p{margin:7px 0 0;color:#dbeafe;font-weight:650;font-size:14px}.sw-hero-actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}
      .sw-btn{border:0;border-radius:14px;padding:11px 15px;font-weight:850;font-size:13px;cursor:pointer;background:linear-gradient(135deg,#06b6d4,#22c55e);color:#062033;box-shadow:0 10px 30px rgba(34,197,94,.18)}
      .sw-btn.secondary{background:#fff;color:#0f172a;border:1px solid #dbe6f4;box-shadow:0 8px 24px rgba(15,23,42,.06)}.sw-btn.danger{background:linear-gradient(135deg,#fb7185,#f97316);color:#fff}
      .sw-toolbar,.sw-stat,.sw-section,.sw-modal-card{background:rgba(255,255,255,.88);backdrop-filter:blur(14px);border:1px solid rgba(215,227,245,.95);box-shadow:0 10px 30px rgba(15,23,42,.06)}
      .sw-toolbar{margin-top:16px;padding:14px;border-radius:22px;display:grid;grid-template-columns:minmax(260px,1fr) 160px 160px auto;gap:10px;align-items:center}.sw-toolbar input,.sw-toolbar select{border:1px solid #d7e3f5;background:#fff;color:#0f172a;border-radius:13px;padding:10px 12px;font-weight:750;outline:none}.sw-actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}
      .sw-stats{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:14px;margin-top:16px}.sw-stat{padding:16px;border-radius:22px;position:relative;overflow:hidden}.sw-stat:before{content:"";position:absolute;inset:0;opacity:.7;background:linear-gradient(110deg,transparent 0%,rgba(255,255,255,.5) 40%,transparent 80%);background-size:220px 100%;animation:swShine 5.5s linear infinite}.sw-stat span{position:relative;display:block;color:#5b708d;font-size:12px;font-weight:850;text-transform:uppercase}.sw-stat b{position:relative;display:block;margin-top:5px;font-size:28px;color:#10233f}
      .sw-section{border-radius:24px;overflow:hidden;margin-top:16px}.sw-head{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:16px 18px;border-bottom:1px solid #e8eef8}.sw-head h2{margin:0;font-size:20px;color:#10233f}.sw-sub{color:#5b708d;font-size:12px;font-weight:750}.sw-pill{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:#f1f7ff;border:1px solid #dbe6f4;color:#0f4c81;font-size:12px;font-weight:850}
      .sw-table-wrap{overflow:auto;max-height:650px}.sw-table{width:100%;border-collapse:separate;border-spacing:0;min-width:1260px;font-size:14px}.sw-table th{position:sticky;top:0;z-index:2;padding:13px 11px;background:#f8fbff;color:#43617f;text-align:left;border-bottom:1px solid #dbe6f4;font-weight:900;white-space:nowrap}.sw-table td{padding:13px 11px;border-bottom:1px solid #edf2fa;color:#122033;vertical-align:middle}.sw-table tr:hover td{background:#f9fcff}
      .sw-main b{display:block;font-size:15px;color:#0f172a}.sw-main small{display:block;color:#64748b;margin-top:3px;font-weight:750}.sw-status{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;border-radius:999px;font-size:12px;font-weight:900;border:1px solid transparent;white-space:nowrap}.sw-status .dot{width:8px;height:8px;border-radius:50%}
      .sw-live.installed{background:#ecfdf5;color:#15803d;border-color:#bbf7d0}.sw-live.notfound{background:#f8fafc;color:#64748b;border-color:#e2e8f0}.sw-password{font-family:ui-monospace,Consolas,monospace;font-weight:850}.sw-mini-btn{border:1px solid #d7e3f5;background:#fff;border-radius:11px;padding:8px 10px;font-size:12px;font-weight:850;cursor:pointer;color:#0f172a}.sw-mini-btn.red{background:#fff1f2;color:#be123c;border-color:#fecdd3}
      .sw-pager{display:flex;gap:10px;justify-content:space-between;align-items:center;padding:14px 16px;border-top:1px solid #e8eef8;flex-wrap:wrap}.sw-pager-left,.sw-pager-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
      .sw-dup-wrap,.sw-analytics{padding:16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.sw-card{border-radius:20px;background:#fff;border:1px solid #dfe9f7;border-left:5px solid #0ea5e9;overflow:hidden;padding:14px}.sw-card b{display:block;color:#0f172a}.sw-card small{display:block;color:#64748b;margin-top:4px;font-weight:700}
      .sw-modal{position:fixed;inset:0;z-index:9999;background:rgba(15,23,42,.38);backdrop-filter:blur(7px);display:flex;justify-content:center;align-items:center;padding:18px}.sw-modal-card{width:min(1120px,96vw);max-height:92vh;overflow:auto;border-radius:28px}.sw-modal-head{display:flex;justify-content:space-between;align-items:center;padding:18px 20px;border-bottom:1px solid #e8eef8}.sw-modal-head h3{margin:0;font-size:22px;color:#10233f}.sw-form{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:14px;padding:18px}.sw-form label{font-size:12px;font-weight:850;color:#60758f}.sw-form input,.sw-form select,.sw-form textarea{width:100%;box-sizing:border-box;margin-top:6px;padding:10px 12px;border-radius:13px;border:1px solid #d7e3f5;background:#fff;color:#0f172a;font-weight:700}.sw-form textarea{min-height:80px;resize:vertical}.sw-modal-foot{display:flex;justify-content:flex-end;gap:10px;padding:18px;border-top:1px solid #e8eef8}.sw-empty{padding:18px;color:#5d728f;font-weight:850}
      @media(max-width:1100px){.sw-toolbar{grid-template-columns:1fr 1fr}.sw-actions{grid-column:1/-1;justify-content:flex-start}.sw-stats{grid-template-columns:repeat(2,1fr)}.sw-hero{grid-template-columns:1fr}.sw-cube{display:none}.sw-form{grid-template-columns:1fr}}`;
    document.head.appendChild(s);
  }
  function installedSoftwareNames(){
    const out=new Set();
    function add(v){v=String(v||'').trim(); if(v && v.length<120) out.add(v.toLowerCase())}
    function scan(x,depth){
      if(!x || depth>4 || out.size>5000) return;
      if(Array.isArray(x)){x.slice(0,1000).forEach(v=>scan(v,depth+1));return}
      if(typeof x==='object'){
        const name=x.name||x.display_name||x.displayName||x.app_name||x.Software||x.software_name||x.title;
        if(name) add(name);
        Object.keys(x).forEach(k=>{ if(/software|installed|apps|applications|programs/i.test(k)) scan(x[k],depth+1); });
      }else if(typeof x==='string' && depth>1){ add(x); }
    }
    try{(state.machines||[]).forEach(m=>scan(m,0));}catch(e){}
    return out;
  }
  function isInstalled(row,set){
    const name=String(row.software_name||'').trim().toLowerCase();
    if(!name) return false;
    if(set.has(name)) return true;
    for(const x of set){ if(x.includes(name)||name.includes(x)) return true; }
    return false;
  }
  function statusBadge(v){
    const s=String(v||'Unknown'), low=s.toLowerCase();
    let bg='#eff6ff',bd='#bfdbfe',fg='#1d4ed8',dot='#3b82f6';
    if(low.includes('active')||low.includes('free')){bg='#ecfdf5';bd='#bbf7d0';fg='#15803d';dot='#22c55e'}
    else if(low.includes('expire')||low.includes('disable')){bg='#fff1f2';bd='#fecdd3';fg='#be123c';dot='#fb7185'}
    else if(low.includes('trial')){bg='#fffbeb';bd='#fde68a';fg='#a16207';dot='#f59e0b'}
    return `<span class="sw-status" style="background:${bg};border-color:${bd};color:${fg}"><span class="dot" style="background:${dot}"></span>${esc(s)}</span>`;
  }
  function loadRows(force){
    const x=st();
    if(x.loaded && !force) return Promise.resolve(x.rows);
    return apiGet('/api/software-inventory?limit=20000').then(d=>{ if(!d||d.ok===false) throw new Error((d&&d.error)||'Software Inventory API error'); x.rows=d.rows||[]; x.loaded=true; return x.rows; });
  }
  function savePayload(obj){const p=new URLSearchParams();p.set('payload',JSON.stringify(obj||{}));return apiGet('/api/software-inventory-save?'+p.toString()).then(d=>{if(!d||d.ok===false)throw new Error((d&&d.error)||'Save failed');st().loaded=false;return d})}
  function deleteIds(ids){if(!ids.length)return Promise.resolve(); if(!confirm('Delete selected software entry?'))return Promise.resolve(); return apiGet('/api/software-inventory-delete?ids='+encodeURIComponent(ids.join(','))).then(d=>{if(!d||d.ok===false)throw new Error((d&&d.error)||'Delete failed');st().loaded=false;return d})}
  function categories(){return Array.from(new Set((st().rows||[]).map(r=>String(r.category||'Other').trim()||'Other').concat(CATS))).sort()}
  function filterRows(){
    const x=st(), s=String(x.search||'').toLowerCase();
    return (x.rows||[]).filter(r=>{
      if(x.status && r.status!==x.status) return false;
      if(x.category && r.category!==x.category) return false;
      if(s){
        const blob=[r.software_name,r.category,r.login_url,r.username,r.license_key,r.machine_asset,r.allocated_to,r.vendor_name,r.notes].join(' ').toLowerCase();
        if(!blob.includes(s)) return false;
      }
      return true;
    });
  }
  function duplicateGroups(rows){
    const map={};
    rows.forEach(r=>{
      const key=[String(r.software_name||'').trim().toLowerCase(),String(r.username||'').trim().toLowerCase(),String(r.login_url||'').trim().toLowerCase()].join('|');
      if(key.replace(/\|/g,'')){
        map[key]=map[key]||[];
        map[key].push(r);
      }
    });
    return Object.entries(map).filter(x=>x[1].length>1).map(x=>({key:x[0],rows:x[1]}));
  }
  function pageRows(rows){
    const x=st(), total=Math.max(1,Math.ceil(rows.length/x.pageSize));
    if(x.page>total)x.page=total;if(x.page<1)x.page=1;
    return rows.slice((x.page-1)*x.pageSize,x.page*x.pageSize);
  }
  function toolbar(){
    const x=st();
    return `<div class="sw-toolbar"><input id="swSearch" placeholder="Search software, user, URL, license, machine..." value="${esc(x.search)}"><select id="swStatus"><option value="">All Status</option>${STATUS.map(s=>`<option ${x.status===s?'selected':''}>${esc(s)}</option>`).join('')}</select><select id="swCategory"><option value="">All Category</option>${categories().map(c=>`<option ${x.category===c?'selected':''}>${esc(c)}</option>`).join('')}</select><div class="sw-actions"><button class="sw-btn secondary" id="swRefresh">Refresh</button><button class="sw-btn" id="swAdd">Add Software</button><button class="sw-btn secondary" id="swSample">Sample CSV</button><label class="sw-btn secondary" style="cursor:pointer">Upload CSV<input id="swUpload" type="file" accept=".csv" style="display:none"></label><button class="sw-btn secondary" id="swDownload">Download CSV</button></div></div>`;
  }
  function stats(rows){
    const installed=installedSoftwareNames(), match=rows.filter(r=>isInstalled(r,installed)).length, dups=duplicateGroups(rows).length, active=rows.filter(r=>String(r.status||'').toLowerCase().includes('active')).length, expired=rows.filter(r=>String(r.status||'').toLowerCase().includes('expire')).length;
    return `<div class="sw-stats">${[['Total Software',rows.length],['Active',active],['Expired',expired],['Live Installed Match',match],['Duplicate Groups',dups]].map(m=>`<div class="sw-stat"><span>${esc(m[0])}</span><b>${esc(m[1])}</b></div>`).join('')}</div>`;
  }
  function table(rows){
    const x=st(), visible=pageRows(rows), totalPages=Math.max(1,Math.ceil(rows.length/x.pageSize)), installed=installedSoftwareNames();
    return `<div class="sw-section"><div class="sw-head"><div><h2>S/W Inventory Table</h2><div class="sw-sub">Fast tabular software inventory with password show/hide and live installed match.</div></div><span class="sw-pill">${esc(rows.length)} rows</span></div><div class="sw-table-wrap"><table class="sw-table"><thead><tr><th>ID</th><th>Software</th><th>Login / URL</th><th>User ID</th><th>Password</th><th>License</th><th>Machine / Asset</th><th>Allocated To</th><th>Live Match</th><th>Status</th><th>Expiry</th><th>Action</th></tr></thead><tbody>${visible.map(r=>{
      const show=!!st().showPasswords[r.id], live=isInstalled(r,installed);
      return `<tr><td><b>${esc(r.id||'')}</b></td><td><div class="sw-main"><b>${esc(r.software_name||'No Name')}</b><small>${esc(r.category||'Other')} · ${esc(r.vendor_name||'')}</small></div></td><td>${r.login_url?`<a class="sw-link" target="_blank" href="${esc(r.login_url)}">${esc(r.login_url)}</a>`:'—'}</td><td>${esc(r.username||'—')}</td><td><span class="sw-password">${esc(show?(r.password_value||r.password||''):'••••••••')}</span> <button class="sw-mini-btn" onclick="swInvTogglePass('${esc(r.id)}')">${show?'Hide':'Show'}</button></td><td>${esc(r.license_key||'—')}</td><td>${esc(r.machine_asset||'—')}</td><td>${esc(r.allocated_to||'—')}</td><td><span class="sw-status sw-live ${live?'installed':'notfound'}"><span class="dot"></span>${live?'Installed':'Not Found'}</span></td><td>${statusBadge(r.status)}</td><td>${esc(r.renewal_expiry_date||'—')}</td><td><div style="display:flex;gap:8px;flex-wrap:wrap"><button class="sw-mini-btn" onclick="swInvEdit('${esc(r.id)}')">Edit</button><button class="sw-mini-btn red" onclick="swInvDelete('${esc(r.id)}')">Delete</button></div></td></tr>`;
    }).join('') || '<tr><td colspan="12"><div class="sw-empty">No software inventory rows found.</div></td></tr>'}</tbody></table></div><div class="sw-pager"><div class="sw-pager-left"><span class="sw-sub">Page ${esc(x.page)} / ${esc(totalPages)}</span><select id="swPageSize">${[25,50,100,200].map(n=>`<option ${x.pageSize===n?'selected':''}>${n}</option>`).join('')}</select></div><div class="sw-pager-right"><button class="sw-mini-btn" id="swPrev">Previous</button><button class="sw-mini-btn" id="swNext">Next</button></div></div></div>`;
  }
  function duplicateSection(rows){
    const d=duplicateGroups(rows);
    return `<div class="sw-section"><div class="sw-head"><div><h2>Duplicate Review</h2><div class="sw-sub">Same software + same user + same URL duplicates.</div></div><span class="sw-pill">${esc(d.length)} groups</span></div><div class="sw-dup-wrap">${d.length?d.slice(0,80).map(g=>`<div class="sw-card"><b>${esc(g.rows[0].software_name||'Software')}</b><small>${esc(g.rows.length)} duplicate rows · User: ${esc(g.rows[0].username||'')}</small>${g.rows.map(r=>`<small>ID ${esc(r.id)} · ${esc(r.machine_asset||'')} <button class="sw-mini-btn" onclick="swInvEdit('${esc(r.id)}')">Review</button> <button class="sw-mini-btn red" onclick="swInvDelete('${esc(r.id)}')">Delete</button></small>`).join('')}</div>`).join(''):'<div class="sw-empty">No duplicate software entries found.</div>'}</div></div>`;
  }
  function analytics(rows){
    const byCat={}; rows.forEach(r=>{const k=r.category||'Other';byCat[k]=(byCat[k]||0)+1});
    return `<div class="sw-section"><div class="sw-head"><div><h2>S/W Inventory Analytics</h2><div class="sw-sub">Category-wise software inventory summary.</div></div><span class="sw-pill">Analytics</span></div><div class="sw-analytics">${Object.entries(byCat).sort((a,b)=>b[1]-a[1]).slice(0,12).map(x=>`<div class="sw-card"><span>${esc(x[0])}</span><b style="font-size:22px">${esc(x[1])}</b></div>`).join('') || '<div class="sw-empty">No analytics data.</div>'}</div></div>`;
  }
  function shell(rows){
    const filtered=filterRows();
    return `<div class="sw-root"><div class="sw-hero"><div class="sw-cube"></div><div><h1>S/W Inventory</h1><p>Software credentials, license, renewal, password and live installed-software match in one secure inventory tab.</p></div><div class="sw-hero-actions"><button class="sw-btn" id="swHeroAdd">+ Add Software</button><button class="sw-btn secondary" id="swHeroRefresh">Refresh</button></div></div>${toolbar()}${stats(filtered)}${table(filtered)}${duplicateSection(filtered)}${analytics(filtered)}</div>`;
  }
  function bind(){
    q('#swSearch')?.addEventListener('input',function(){st().search=this.value;st().page=1;clearTimeout(window.__swSearch);window.__swSearch=setTimeout(()=>renderSoftwareInventory(false),200)});
    q('#swStatus')?.addEventListener('change',function(){st().status=this.value;st().page=1;renderSoftwareInventory(false)});
    q('#swCategory')?.addEventListener('change',function(){st().category=this.value;st().page=1;renderSoftwareInventory(false)});
    q('#swRefresh')?.addEventListener('click',()=>renderSoftwareInventory(true)); q('#swHeroRefresh')?.addEventListener('click',()=>renderSoftwareInventory(true));
    q('#swAdd')?.addEventListener('click',()=>openModal({})); q('#swHeroAdd')?.addEventListener('click',()=>openModal({}));
    q('#swDownload')?.addEventListener('click',downloadCsv); q('#swSample')?.addEventListener('click',downloadSample); q('#swUpload')?.addEventListener('change',uploadCsv);
    q('#swPageSize')?.addEventListener('change',function(){st().pageSize=parseInt(this.value,10)||50;st().page=1;renderSoftwareInventory(false)});
    q('#swPrev')?.addEventListener('click',function(){st().page=Math.max(1,st().page-1);renderSoftwareInventory(false)});
    q('#swNext')?.addEventListener('click',function(){const total=Math.max(1,Math.ceil(filterRows().length/st().pageSize));st().page=Math.min(total,st().page+1);renderSoftwareInventory(false)});
  }
  function fieldInput(k,label,row){
    const val=row[k]||'';
    if(k==='status') return `<label>${esc(label)}<select name="${esc(k)}">${STATUS.map(s=>`<option ${String(val).toLowerCase()===s.toLowerCase()?'selected':''}>${esc(s)}</option>`).join('')}</select></label>`;
    if(k==='category') return `<label>${esc(label)}<select name="${esc(k)}">${CATS.map(s=>`<option ${String(val).toLowerCase()===s.toLowerCase()?'selected':''}>${esc(s)}</option>`).join('')}</select></label>`;
    if(k==='notes'||k==='mfa_recovery') return `<label>${esc(label)}<textarea name="${esc(k)}">${esc(val)}</textarea></label>`;
    const type=(k==='password_value'?'password':(k.includes('date')?'date':'text'));
    return `<label>${esc(label)}<input type="${type}" name="${esc(k)}" value="${esc(val)}"></label>`;
  }
  function openModal(row){
    row=row||{};
    const modal=document.createElement('div');
    modal.className='sw-modal';
    modal.innerHTML=`<div class="sw-modal-card"><div class="sw-modal-head"><h3>${row.id?'Edit Software':'Add Software'}</h3><button class="sw-mini-btn" id="swClose">Close</button></div><form id="swForm"><input type="hidden" name="id" value="${esc(row.id||'')}"><div class="sw-form">${FIELDS.map(f=>fieldInput(f[0],f[1],row)).join('')}</div><div class="sw-modal-foot"><button type="button" class="sw-btn secondary" id="swCancel">Cancel</button><button class="sw-btn" type="submit">Save Software</button></div></form></div>`;
    document.body.appendChild(modal);
    function close(){modal.remove()}
    q('#swClose',modal).onclick=close; q('#swCancel',modal).onclick=close;
    q('#swForm',modal).onsubmit=function(ev){ev.preventDefault();const data={};new FormData(ev.target).forEach((v,k)=>data[k]=v);savePayload({row:data}).then(()=>{close();return renderSoftwareInventory(true)}).catch(e=>alert('Save failed: '+(e.message||e)))};
  }
  window.swInvEdit=function(id){const r=(st().rows||[]).find(x=>String(x.id)===String(id));if(r)openModal(r)};
  window.swInvDelete=function(id){deleteIds([id]).then(()=>renderSoftwareInventory(true)).catch(e=>alert('Delete failed: '+(e.message||e)))};
  window.swInvTogglePass=function(id){st().showPasswords[id]=!st().showPasswords[id];renderSoftwareInventory(false)};
  function downloadCsv(){
    const headers=['ID'].concat(FIELDS.map(f=>f[1])), keys=['id'].concat(FIELDS.map(f=>f[0])), rows=filterRows();
    const csv=[headers].concat(rows.map(r=>keys.map(k=>r[k]||''))).map(r=>r.map(csvCell).join(',')).join('\r\n');
    const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));a.download='software_inventory_with_passwords.csv';document.body.appendChild(a);a.click();a.remove();
  }
  function downloadSample(){
    const headers=FIELDS.map(f=>f[1]);
    const sample=['Adobe Photoshop','Design','https://account.adobe.com','user@example.com','Password123','LIC-KEY-001','Recovery code here','STU5_PC','Sagar','Adobe','INV-001','https://drive.google.com/...','2026-01-01','2027-01-01','Active','Sample only'];
    const csv=[headers,sample].map(r=>r.map(csvCell).join(',')).join('\r\n');
    const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));a.download='software_inventory_sample.csv';document.body.appendChild(a);a.click();a.remove();
  }
  function parseCsv(text){
    const rows=[];let row=[],cur='',inQ=false;
    for(let i=0;i<text.length;i++){const ch=text[i],nx=text[i+1];if(ch==='"'&&inQ&&nx==='"'){cur+='"';i++;continue}if(ch==='"'){inQ=!inQ;continue}if(ch===','&&!inQ){row.push(cur);cur='';continue}if((ch==='\n'||ch==='\r')&&!inQ){if(ch==='\r'&&nx==='\n')i++;row.push(cur);if(row.some(x=>String(x).trim()))rows.push(row);row=[];cur='';continue}cur+=ch}
    row.push(cur);if(row.some(x=>String(x).trim()))rows.push(row);return rows;
  }
  function norm(h){return String(h||'').toLowerCase().replace(/[^a-z0-9]/g,'')}
  const MAP={softwarename:'software_name',software:'software_name',appname:'software_name',category:'category',loginwebsiteurl:'login_url',loginurl:'login_url',website:'login_url',url:'login_url',useridemail:'username',userid:'username',username:'username',email:'username',password:'password_value',licensekey:'license_key',license:'license_key',mfarecoveryinfo:'mfa_recovery',mfa:'mfa_recovery',machineassettag:'machine_asset',machineasset:'machine_asset',asset:'machine_asset',allocatedto:'allocated_to',person:'allocated_to',vendorname:'vendor_name',vendor:'vendor_name',poinvoicebillno:'po_invoice_bill_no',billno:'po_invoice_bill_no',billgoogledrivepath:'bill_path_google_drive_path',billpath:'bill_path_google_drive_path',purchasedate:'purchase_date',renewalexpirydate:'renewal_expiry_date',expirydate:'renewal_expiry_date',status:'status',notes:'notes',remark:'notes'};
  async function uploadCsv(ev){
    const file=ev.target.files&&ev.target.files[0];if(!file)return;
    const grid=parseCsv(await file.text()); if(grid.length<2){alert('CSV has no data');return}
    const headers=grid[0].map(h=>MAP[norm(h)]||'');
    const rows=grid.slice(1).map(r=>{const o={};headers.forEach((k,i)=>{if(k)o[k]=r[i]||''});return o}).filter(o=>Object.values(o).some(v=>String(v||'').trim()));
    if(!rows.length){alert('No valid rows found');return}
    if(!confirm('Upload '+rows.length+' software rows?'))return;
    for(const row of rows){await savePayload({row})}
    alert('CSV upload complete: '+rows.length+' row(s)'); await renderSoftwareInventory(true);
  }
  window.renderSoftwareInventory=function(force){
    ensureTab(); addCss();
    const page=q('#page-sw-inventory'); if(!page)return;
    page.classList.add('sw-inv-page');
    if(!st().loaded || force) page.innerHTML='<div class="sw-root"><div class="sw-hero"><div class="sw-cube"></div><div><h1>S/W Inventory</h1><p>Loading software inventory...</p></div></div></div>';
    return loadRows(force).then(rows=>{page.innerHTML=shell(rows);bind();}).catch(e=>{page.innerHTML='<div class="sw-root"><div class="sw-empty">S/W Inventory error: '+esc(e.message||e)+'</div></div>'});
  };
  if(typeof window.switchPage==='function' && !window.__swInvSwitchWrap){
    window.__swInvSwitchWrap=true;
    const old=window.switchPage;
    window.switchPage=function(page){ if(page==='sw-inventory'){goSwInventory();return;} return old.apply(this,arguments); };
  }
  setTimeout(ensureTab,600);
  setInterval(ensureTab,2500);
})();
/* SW_INVENTORY_NEW_TAB_ONLY_END */

/* FULL_NAME_LABELS_ONLY_START */
(function(){
  function replaceText(root){
    if(!root) return;
    const map = {
      'Command Center': 'System Health Monitoring Command Center',
      'S/W Inventory': 'Software Inventory',
      'S/W Inventory Table': 'Software Inventory Table',
      'S/W Inventory Analytics': 'Software Inventory Analytics'
    };
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while(walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(n=>{
      const raw = n.nodeValue || '';
      const t = raw.trim();
      if(map[t]) n.nodeValue = raw.replace(t, map[t]);
    });
    document.querySelectorAll('[placeholder],[title],[aria-label]').forEach(el=>{
      ['placeholder','title','aria-label'].forEach(a=>{
        const v = el.getAttribute(a);
        if(v && v.includes('S/W')) el.setAttribute(a, v.replace(/S\/W/g, 'Software'));
        if(v === 'Command Center') el.setAttribute(a, 'System Health Monitoring Command Center');
      });
    });
  }
  function run(){ replaceText(document.body); }
  setTimeout(run,200);
  setTimeout(run,900);
  setTimeout(run,1800);
  setInterval(run,2500);
})();
/* FULL_NAME_LABELS_ONLY_END */

/* CLIENT_MESSAGES_UI_V2_ONLY_START */
(function(){
  function q(s,r){return (r||document).querySelector(s)}
  function qa(s,r){return Array.from((r||document).querySelectorAll(s))}
  function txt(el){return (el && (el.innerText || el.textContent) || '').trim()}

  function findClientMessagesPage(){
    const ids=['#page-client-messages','#page-clientmessages','#page-messages','#page-clientMessages','#page-client_messages'];
    for(const id of ids){const el=q(id);if(el)return el;}
    return qa('.page,[id^="page-"],main section').find(p=>{
      const t=txt(p).toLowerCase();
      return t.includes('client messages') || t.includes('client message') || (t.includes('send') && t.includes('message') && t.includes('client'));
    }) || null;
  }

  function addCss(){
    if(q('#clientMessagesUiV2Css')) return;
    const s=document.createElement('style');
    s.id='clientMessagesUiV2Css';
    s.textContent=`
      .client-msg-v2{
        position:relative;
        overflow:hidden;
        min-height:calc(100vh - 120px);
        padding:18px!important;
        background:
          radial-gradient(circle at 8% 5%, rgba(14,165,233,.14), transparent 28%),
          radial-gradient(circle at 90% 8%, rgba(16,185,129,.12), transparent 28%),
          linear-gradient(180deg,#f6f9ff 0%,#edf3fb 100%)!important;
        color:#10233f;
        font-family:"Inter","Segoe UI",Arial,sans-serif;
      }
      .client-msg-v2:before{
        content:"";
        position:absolute;
        inset:0;
        pointer-events:none;
        opacity:.50;
        background:linear-gradient(135deg,rgba(255,255,255,.72),transparent 26%),linear-gradient(315deg,rgba(255,255,255,.32),transparent 28%);
      }
      .client-msg-v2 > *{position:relative;z-index:1}
      @keyframes cm2Float{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
      @keyframes cm2Shine{0%{background-position:-220px 0}100%{background-position:calc(100% + 220px) 0}}

      .cm2-hero{
        display:grid;
        grid-template-columns:72px 1fr auto;
        gap:16px;
        align-items:center;
        padding:18px 22px;
        border-radius:28px;
        margin-bottom:16px;
        background:linear-gradient(135deg,#0b1220 0%,#172554 56%,#0f766e 138%);
        color:#fff;
        box-shadow:0 20px 60px rgba(15,23,42,.18);
        animation:cm2Float 7s ease-in-out infinite;
      }
      .cm2-icon{
        width:70px;height:70px;border-radius:22px;
        background:linear-gradient(135deg,#67e8f9 0%,#3b82f6 52%,#8b5cf6 100%);
        box-shadow:0 16px 34px rgba(59,130,246,.34),inset -14px -14px 28px rgba(15,23,42,.25);
        transform:rotate(-8deg);
        position:relative;
      }
      .cm2-icon:before{
        content:"";
        position:absolute;
        inset:13px;
        border-radius:17px;
        border:1.5px solid rgba(255,255,255,.45);
      }
      .cm2-hero h1{margin:0;font-size:32px;letter-spacing:-.9px;color:#fff}
      .cm2-hero p{margin:7px 0 0;color:#dbeafe;font-weight:650;font-size:14px}
      .cm2-ready{
        display:inline-flex;align-items:center;gap:8px;
        padding:9px 13px;border-radius:999px;
        background:rgba(255,255,255,.14);
        border:1px solid rgba(255,255,255,.22);
        color:#d1fae5;font-weight:900;white-space:nowrap;
      }
      .cm2-ready-dot{width:9px;height:9px;border-radius:50%;background:#22c55e;box-shadow:0 0 0 6px rgba(34,197,94,.15)}

      .cm2-section{
        background:rgba(255,255,255,.90)!important;
        border:1px solid rgba(215,227,245,.95)!important;
        border-radius:24px!important;
        box-shadow:0 10px 30px rgba(15,23,42,.06)!important;
        backdrop-filter:blur(14px);
        margin-bottom:16px!important;
        overflow:hidden;
      }
      .cm2-section-head{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:10px;
        padding:16px 18px;
        border-bottom:1px solid #e8eef8;
        background:linear-gradient(180deg,#fff,#f8fbff);
      }
      .cm2-section-head h2{
        margin:0;
        font-size:20px;
        color:#10233f;
        letter-spacing:-.35px;
      }
      .cm2-section-head p{
        margin:4px 0 0;
        color:#5b708d;
        font-size:12px;
        font-weight:750;
      }
      .cm2-pill{
        display:inline-flex;
        align-items:center;
        gap:6px;
        padding:6px 10px;
        border-radius:999px;
        background:#f1f7ff;
        border:1px solid #dbe6f4;
        color:#0f4c81;
        font-size:12px;
        font-weight:850;
        white-space:nowrap;
      }
      .cm2-section-body{padding:16px}

      .client-msg-v2 h1,
      .client-msg-v2 h2,
      .client-msg-v2 h3{
        color:#10233f;
        letter-spacing:-.3px;
      }
      .client-msg-v2 input,
      .client-msg-v2 select,
      .client-msg-v2 textarea{
        border:1px solid #d7e3f5!important;
        background:#fff!important;
        color:#0f172a!important;
        border-radius:14px!important;
        padding:11px 13px!important;
        font-weight:750!important;
        outline:none!important;
        box-shadow:0 6px 18px rgba(15,23,42,.04)!important;
        font-family:"Inter","Segoe UI",Arial,sans-serif!important;
      }
      .client-msg-v2 textarea{
        min-height:118px;
        resize:vertical;
        line-height:1.45;
      }
      .client-msg-v2 button,
      .client-msg-v2 .btn,
      .client-msg-v2 a.button{
        border-radius:14px!important;
        padding:10px 14px!important;
        font-weight:850!important;
        border:1px solid #dbe6f4!important;
        box-shadow:0 8px 24px rgba(15,23,42,.06)!important;
        transition:transform .15s ease, box-shadow .15s ease, opacity .15s ease;
        font-family:"Inter","Segoe UI",Arial,sans-serif!important;
      }
      .client-msg-v2 button:hover,
      .client-msg-v2 .btn:hover{transform:translateY(-1px);box-shadow:0 12px 30px rgba(15,23,42,.10)!important}
      .client-msg-v2 button:not(.danger):not(.red):not(.delete),
      .client-msg-v2 .btn:not(.danger):not(.red):not(.delete){
        background:linear-gradient(135deg,#06b6d4,#22c55e)!important;
        color:#062033!important;
      }

      .client-msg-v2 table{
        width:100%;
        border-collapse:separate!important;
        border-spacing:0!important;
        background:#fff!important;
        border:1px solid #dbe6f4!important;
        border-radius:18px!important;
        overflow:hidden!important;
        box-shadow:none!important;
      }
      .client-msg-v2 th{
        position:sticky;
        top:0;
        z-index:2;
        padding:13px 11px!important;
        background:#f8fbff!important;
        color:#43617f!important;
        text-align:left!important;
        border-bottom:1px solid #dbe6f4!important;
        font-weight:900!important;
        white-space:nowrap;
      }
      .client-msg-v2 td{
        padding:13px 11px!important;
        border-bottom:1px solid #edf2fa!important;
        color:#122033!important;
        vertical-align:middle!important;
      }
      .client-msg-v2 tr:hover td{background:#f9fcff!important}

      .cm2-message-item{
        border:1px solid #dbe6f4!important;
        border-radius:18px!important;
        background:#fff!important;
        box-shadow:0 6px 18px rgba(15,23,42,.04)!important;
        padding:13px!important;
        margin-bottom:10px!important;
      }
      .cm2-hide{display:none!important}

      .cm2-pager{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:10px;
        padding:14px 16px;
        border-top:1px solid #e8eef8;
        background:#fbfdff;
        flex-wrap:wrap;
      }
      .cm2-pager button{
        background:#fff!important;
        color:#0f172a!important;
      }
      .cm2-page-info{
        color:#5b708d;
        font-size:12px;
        font-weight:850;
      }
      @media(max-width:900px){
        .cm2-hero{grid-template-columns:1fr}
        .cm2-icon{display:none}
      }
    `;
    document.head.appendChild(s);
  }

  function removeOldStats(page){
    qa('.cm-pro-quickbar', page).forEach(x=>x.remove());
    qa('.cm-pro-stat', page).forEach(x=>x.remove());
    const badTexts=['Visible Messages','Page Scope','UI Mode','Premium'];
    qa('div,section,article', page).forEach(el=>{
      const t=txt(el);
      if(t && badTexts.some(b=>t===b || t.includes('Visible Messages') || t.includes('Page Scope') || t.includes('UI Mode')) && el.className && String(el.className).includes('cm-pro')){
        el.remove();
      }
    });
  }

  function ensureHero(page){
    qa('.cm-pro-hero', page).forEach(x=>x.remove());
    if(q('.cm2-hero', page)) return;
    const hero=document.createElement('div');
    hero.className='cm2-hero';
    hero.innerHTML=`
      <div class="cm2-icon"></div>
      <div>
        <h1>Client Message Center</h1>
        <p>Send messages to selected clients and review delivery status in a clean, simple command view.</p>
      </div>
      <div class="cm2-ready"><span class="cm2-ready-dot"></span>Ready</div>
    `;
    page.insertBefore(hero, page.firstChild);
  }

  function findComposer(page){
    const candidates=qa('section,.card,.panel,.box,form,div', page).filter(el=>{
      if(el.closest('.cm2-hero') || el.closest('.cm2-section') || el.classList.contains('cm2-hero')) return false;
      const t=txt(el).toLowerCase();
      const hasTextArea=!!q('textarea',el);
      const hasSend=qa('button,input[type="submit"]',el).some(b=>txt(b).toLowerCase().includes('send') || String(b.value||'').toLowerCase().includes('send'));
      return t.includes('send message to client') || t.includes('send message') || (hasTextArea && hasSend);
    });
    return candidates.sort((a,b)=>a.querySelectorAll('*').length-b.querySelectorAll('*').length)[0] || null;
  }

  function findDelivery(page, composer){
    const candidates=qa('section,.card,.panel,.box,div', page).filter(el=>{
      if(el===composer || el.contains(composer) || el.closest('.cm2-hero') || el.closest('.cm2-section') || el.classList.contains('cm2-hero')) return false;
      const t=txt(el).toLowerCase();
      const hasRows=qa('tbody tr',el).length>0;
      const hasMessageItems=qa('.message,.msg,[class*="message"],[class*="Message"]',el).length>0;
      return t.includes('message delivery') || t.includes('delivery') || t.includes('delivered') || t.includes('pending') || hasRows || hasMessageItems;
    });
    return candidates.sort((a,b)=>a.querySelectorAll('*').length-b.querySelectorAll('*').length)[0] || null;
  }

  function sectionWrap(page, id, title, subtitle, badge, content){
    let wrap=q('#'+id,page);
    if(!wrap){
      wrap=document.createElement('div');
      wrap.id=id;
      wrap.className='cm2-section';
      wrap.innerHTML=`
        <div class="cm2-section-head">
          <div><h2>${title}</h2><p>${subtitle}</p></div>
          <span class="cm2-pill">${badge}</span>
        </div>
        <div class="cm2-section-body"></div>
      `;
      page.appendChild(wrap);
    }
    const body=q('.cm2-section-body',wrap);
    if(content && content.parentElement!==body) body.appendChild(content);
    return wrap;
  }

  function deliveryItems(delivery){
    if(!delivery) return [];
    const rows=qa('tbody tr',delivery);
    if(rows.length) return rows;
    let cards=qa('.message,.msg,[class*="message"],[class*="Message"]',delivery)
      .filter(x=>txt(x).length>0 && !x.closest('.cm2-hero') && !x.closest('.cm2-pager'));
    if(cards.length) return cards;
    return qa(':scope > *',delivery).filter(x=>txt(x).length>0 && !x.classList.contains('cm2-pager'));
  }

  function applyDeliveryPagination(section){
    if(!section) return;
    const body=q('.cm2-section-body',section);
    if(!body) return;
    const deliveryContent=qa(':scope > *',body).find(x=>!x.classList.contains('cm2-pager'));
    if(!deliveryContent) return;
    const items=deliveryItems(deliveryContent);
    const total=items.length;
    const pageSize=10;
    section.__cm2Page = section.__cm2Page || 1;
    const pages=Math.max(1,Math.ceil(total/pageSize));
    if(section.__cm2Page>pages) section.__cm2Page=pages;
    if(section.__cm2Page<1) section.__cm2Page=1;
    const start=(section.__cm2Page-1)*pageSize;
    const end=start+pageSize;

    items.forEach((it,i)=>{
      it.classList.toggle('cm2-hide', !(i>=start && i<end));
      if(!it.matches('tr')) it.classList.add('cm2-message-item');
    });

    let pager=q('.cm2-pager',section);
    if(!pager){
      pager=document.createElement('div');
      pager.className='cm2-pager';
      section.appendChild(pager);
    }
    pager.innerHTML=`
      <span class="cm2-page-info">Showing ${total?start+1:0}-${Math.min(end,total)} of ${total} messages</span>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <button type="button" class="cm2-prev">Previous</button>
        <span class="cm2-pill">Page ${section.__cm2Page} / ${pages}</span>
        <button type="button" class="cm2-next">Next</button>
      </div>
    `;
    q('.cm2-prev',pager).onclick=function(){section.__cm2Page=Math.max(1,section.__cm2Page-1);applyDeliveryPagination(section)};
    q('.cm2-next',pager).onclick=function(){section.__cm2Page=Math.min(pages,section.__cm2Page+1);applyDeliveryPagination(section)};
  }

  function renameComposerTitle(composer){
    if(!composer) return;
    const heads=qa('h1,h2,h3,h4,strong,b',composer);
    const found=heads.find(h=>txt(h).toLowerCase().includes('send') && txt(h).toLowerCase().includes('message'));
    if(found) found.textContent='Send Message to Client';
  }

  function run(){
    addCss();
    const page=findClientMessagesPage();
    if(!page) return;
    page.classList.add('client-msg-v2');
    page.classList.remove('client-msg-pro');

    removeOldStats(page);
    ensureHero(page);

    const composer=findComposer(page);
    if(composer){
      renameComposerTitle(composer);
      const composerSection=sectionWrap(page,'cm2-send-section','Send Message to Client','Choose client, write message, and send using existing working logic.','Composer',composer);
      const hero=q('.cm2-hero',page);
      if(hero && composerSection.previousElementSibling!==hero) hero.insertAdjacentElement('afterend',composerSection);
    }

    const delivery=findDelivery(page, composer);
    if(delivery){
      const deliverySection=sectionWrap(page,'cm2-delivery-section','Message Delivery','Recent 10 messages show first. Use Next for remaining delivery history.','Recent 10',delivery);
      const composerSection=q('#cm2-send-section',page);
      if(composerSection && deliverySection.previousElementSibling!==composerSection) composerSection.insertAdjacentElement('afterend',deliverySection);
      applyDeliveryPagination(deliverySection);
    }
  }

  setTimeout(run,300);
  setTimeout(run,1000);
  setTimeout(run,2200);
  setInterval(run,2500);
})();
/* CLIENT_MESSAGES_UI_V2_ONLY_END */

/* NOTIFICATION_SIMPLE_PAGED_HISTORY_UI_ONLY_START */
(function(){
  function q(s,r){return (r||document).querySelector(s)}
  function qa(s,r){return Array.from((r||document).querySelectorAll(s))}
  function txt(el){return (el && (el.innerText || el.textContent) || '').trim()}

  function findNotificationPage(){
    const ids=['#page-notifications','#page-notification','#page-alerts','#page-rules'];
    for(const id of ids){const el=q(id);if(el)return el;}
    return qa('.page,[id^="page-"],main section').find(p=>{
      const t=txt(p).toLowerCase();
      return t.includes('notification') || (t.includes('alert history') && t.includes('rule'));
    }) || null;
  }

  function addCss(){
    if(q('#notificationSimplePagedCss')) return;
    const s=document.createElement('style');
    s.id='notificationSimplePagedCss';
    s.textContent=`
      .notif-simple-page{
        padding:18px!important;
        background:
          radial-gradient(circle at 8% 5%, rgba(14,165,233,.08), transparent 28%),
          linear-gradient(180deg,#f7fbff 0%,#eef4fb 100%)!important;
        color:#111827!important;
        font-family:"Segoe UI",Arial,sans-serif!important;
      }

      .notif-simple-page *,
      .notif-simple-page table,
      .notif-simple-page td,
      .notif-simple-page th,
      .notif-simple-page input,
      .notif-simple-page select,
      .notif-simple-page textarea,
      .notif-simple-page button{
        font-family:"Segoe UI",Arial,sans-serif!important;
      }

      .notif-simple-page .nt-hero,
      .notif-simple-page #ntExtraAlertsSection,
      .notif-simple-page .nt-alert-grid,
      .notif-simple-page .nt-alert-card,
      .notif-simple-page .ns-compact-head,
      .notif-simple-page #ncfTopbar,
      .notif-simple-page #ncfGrid,
      .notif-simple-page .ncf-topbar,
      .notif-simple-page .ncf-grid{
        display:none!important;
      }

      .notif-simple-title{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:12px;
        margin:0 0 14px;
        padding:14px 16px;
        border-radius:18px;
        background:#ffffff;
        border:1px solid #dbe6f4;
        box-shadow:0 8px 22px rgba(15,23,42,.05);
      }
      .notif-simple-title h1{
        margin:0;
        color:#0f172a!important;
        font-size:24px;
        font-weight:800;
        letter-spacing:-.3px;
      }
      .notif-simple-title p{
        margin:3px 0 0;
        color:#475569!important;
        font-size:13px;
        font-weight:600;
      }
      .notif-simple-badge{
        padding:7px 11px;
        border-radius:999px;
        background:#ecfdf5;
        border:1px solid #bbf7d0;
        color:#15803d;
        font-size:12px;
        font-weight:800;
        white-space:nowrap;
      }

      .notif-simple-page .card,
      .notif-simple-page .panel,
      .notif-simple-page .box,
      .notif-simple-page .section,
      .notif-simple-page form{
        background:#ffffff!important;
        border:1px solid #dbe6f4!important;
        border-radius:16px!important;
        box-shadow:0 6px 18px rgba(15,23,42,.04)!important;
        color:#111827!important;
      }

      .notif-simple-page h1,
      .notif-simple-page h2,
      .notif-simple-page h3,
      .notif-simple-page label,
      .notif-simple-page strong,
      .notif-simple-page b{
        color:#0f172a!important;
      }

      .notif-simple-page p,
      .notif-simple-page span,
      .notif-simple-page small,
      .notif-simple-page div{
        color:inherit;
      }

      .notif-simple-page input,
      .notif-simple-page select,
      .notif-simple-page textarea{
        border:1px solid #cbd5e1!important;
        background:#ffffff!important;
        color:#0f172a!important;
        border-radius:10px!important;
        padding:9px 10px!important;
        font-size:14px!important;
        font-weight:600!important;
        outline:none!important;
      }

      .notif-simple-page button,
      .notif-simple-page .btn{
        border-radius:10px!important;
        padding:9px 12px!important;
        font-size:13px!important;
        font-weight:750!important;
        border:1px solid #cbd5e1!important;
        background:#ffffff!important;
        color:#0f172a!important;
        box-shadow:none!important;
      }
      .notif-simple-page button:hover,
      .notif-simple-page .btn:hover{
        background:#f8fafc!important;
      }

      .notif-simple-page table{
        width:100%;
        border-collapse:separate!important;
        border-spacing:0!important;
        background:#ffffff!important;
        border:1px solid #dbe6f4!important;
        border-radius:14px!important;
        overflow:hidden!important;
        box-shadow:none!important;
        font-size:14px!important;
      }
      .notif-simple-page th{
        position:sticky;
        top:0;
        z-index:2;
        padding:10px!important;
        background:#f1f5f9!important;
        color:#0f172a!important;
        text-align:left!important;
        border-bottom:1px solid #cbd5e1!important;
        font-size:13px!important;
        font-weight:850!important;
        white-space:nowrap;
      }
      .notif-simple-page td{
        padding:10px!important;
        border-bottom:1px solid #e2e8f0!important;
        color:#111827!important;
        vertical-align:middle!important;
        font-size:13px!important;
      }
      .notif-simple-page tr:hover td{
        background:#f8fafc!important;
      }

      .notif-history-simple{
        background:#ffffff!important;
        border:1px solid #dbe6f4!important;
        border-radius:16px!important;
        box-shadow:0 6px 18px rgba(15,23,42,.04)!important;
        margin-top:14px!important;
        overflow:hidden!important;
      }
      .notif-history-simple-head{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:10px;
        padding:13px 15px;
        background:#ffffff;
        border-bottom:1px solid #e2e8f0;
      }
      .notif-history-simple-head h2{
        margin:0;
        color:#0f172a!important;
        font-size:19px;
        font-weight:800;
      }
      .notif-history-simple-head p{
        margin:3px 0 0;
        color:#475569!important;
        font-size:12px;
        font-weight:600;
      }
      .notif-history-body{
        padding:12px;
        max-height:420px;
        overflow:auto;
        background:#ffffff;
      }
      .notif-history-hide{
        display:none!important;
      }
      .notif-history-pager{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:10px;
        padding:11px 12px;
        border-top:1px solid #e2e8f0;
        background:#f8fafc;
        flex-wrap:wrap;
      }
      .notif-history-pager span{
        color:#334155!important;
        font-size:12px;
        font-weight:750;
      }
      .notif-history-pager button{
        background:#ffffff!important;
        color:#0f172a!important;
      }

      @media(max-width:700px){
        .notif-simple-title,
        .notif-history-simple-head,
        .notif-history-pager{
          align-items:flex-start;
          flex-direction:column;
        }
      }
    `;
    document.head.appendChild(s);
  }

  function removeBadAddedUi(page){
    // Remove old bulky blocks and confusing two-panel UI created earlier.
    qa('.nt-hero,.ns-compact-head,#ntExtraAlertsSection,.nt-alert-grid,.nt-alert-card,#ncfTopbar,#ncfGrid,.ncf-topbar,.ncf-grid',page).forEach(x=>{
      // If previous two-panel moved real content inside, move it back before removing.
      if(x.id==='ncfGrid'){
        const rules=q('#ncfRulesBody',x);
        const history=q('#ncfHistoryBody',x);
        const parent=x.parentElement;
        if(parent){
          if(rules){ while(rules.firstChild) parent.insertBefore(rules.firstChild,x); }
          if(history){ while(history.firstChild) parent.insertBefore(history.firstChild,x); }
        }
      }
      x.remove();
    });

    // Remove text-only bulky block if it survived.
    qa('div,section,article',page).forEach(el=>{
      const t=txt(el);
      if(!t) return;
      if(
        t.includes('New Advanced Alert Rules') ||
        t.includes('Add / Refresh Rules') ||
        t.includes('Metric: max_disk_used_percent') ||
        t.includes('Metric: cpu_ram_combined_percent') ||
        t.includes('Metric: cpu_gpu_temp_max_c') ||
        t.includes('Metric: thread_core_usage_percent')
      ){
        if(t.length < 2500 || el.id==='ntExtraAlertsSection' || String(el.className).includes('nt-')){
          el.remove();
        }
      }
    });
  }

  function ensureSimpleHeader(page){
    if(q('#notifSimpleTitle',page)) return;
    const title=document.createElement('div');
    title.id='notifSimpleTitle';
    title.className='notif-simple-title';
    title.innerHTML=`
      <div>
        <h1>Notification Center</h1>
        <p>Simple view for alert rules and alert history.</p>
      </div>
      <span class="notif-simple-badge">Readable Mode</span>
    `;
    page.insertBefore(title,page.firstChild);
  }

  function findHistory(page){
    return qa('section,.card,.panel,.box,div,table',page).find(el=>{
      if(el.closest('#notifSimpleTitle') || el.closest('.notif-history-simple')) return false;
      const t=txt(el).toLowerCase();
      return t.includes('alert history') || (t.includes('history') && t.includes('alert'));
    }) || null;
  }

  function wrapHistory(page){
    let section=q('#notifHistorySimple',page);
    if(section) return section;

    const old=findHistory(page);
    if(!old) return null;

    section=document.createElement('div');
    section.id='notifHistorySimple';
    section.className='notif-history-simple';
    section.innerHTML=`
      <div class="notif-history-simple-head">
        <div>
          <h2>Alert History</h2>
          <p>Recent 10 alerts first. Click Next for older alerts.</p>
        </div>
        <span class="notif-simple-badge" style="background:#eff6ff;border-color:#bfdbfe;color:#1d4ed8">Page Wise</span>
      </div>
      <div class="notif-history-body"></div>
    `;
    old.insertAdjacentElement('beforebegin',section);
    q('.notif-history-body',section).appendChild(old);
    return section;
  }

  function historyItems(section){
    const body=q('.notif-history-body',section);
    if(!body) return [];
    const rows=qa('tbody tr',body);
    if(rows.length) return rows;

    let items=qa('.alert,.event,.log,.message,.card,.panel,.box,li',body).filter(x=>txt(x).length>0 && !x.closest('.notif-history-pager'));
    if(items.length) return items;

    return qa(':scope > *',body).filter(x=>txt(x).length>0 && !x.classList.contains('notif-history-pager'));
  }

  function paginateHistory(section){
    if(!section) return;
    const items=historyItems(section);
    const total=items.length;
    const size=10;

    section.__notifSimplePage = section.__notifSimplePage || 1;
    const pages=Math.max(1,Math.ceil(total/size));
    if(section.__notifSimplePage>pages) section.__notifSimplePage=pages;
    if(section.__notifSimplePage<1) section.__notifSimplePage=1;

    const start=(section.__notifSimplePage-1)*size;
    const end=start+size;

    items.forEach((it,i)=>it.classList.toggle('notif-history-hide', !(i>=start && i<end)));

    let pager=q('.notif-history-pager',section);
    if(!pager){
      pager=document.createElement('div');
      pager.className='notif-history-pager';
      section.appendChild(pager);
    }

    pager.innerHTML=`
      <span>Showing ${total?start+1:0}-${Math.min(end,total)} of ${total} alerts</span>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <button type="button" class="notif-prev">Previous</button>
        <span>Page ${section.__notifSimplePage} / ${pages}</span>
        <button type="button" class="notif-next">Next</button>
      </div>
    `;

    q('.notif-prev',pager).onclick=function(){
      section.__notifSimplePage=Math.max(1,section.__notifSimplePage-1);
      paginateHistory(section);
    };
    q('.notif-next',pager).onclick=function(){
      section.__notifSimplePage=Math.min(pages,section.__notifSimplePage+1);
      paginateHistory(section);
    };
  }

  function run(){
    addCss();
    const page=findNotificationPage();
    if(!page) return;

    page.classList.add('notif-simple-page');
    page.classList.remove('notif-pro','notif-smooth','noti-compact-page');

    removeBadAddedUi(page);
    ensureSimpleHeader(page);
    const history=wrapHistory(page);
    paginateHistory(history);
  }

  setTimeout(run,250);
  setTimeout(run,900);
  setTimeout(run,1800);
  setInterval(run,3000);
})();
/* NOTIFICATION_SIMPLE_PAGED_HISTORY_UI_ONLY_END */

/* BRANDING_SETTINGS_FOUNDATION_ONLY_START */
(function(){
  const BRAND_KEY = 'sk_company_branding_foundation_v1';
  const DEFAULT_BRAND = {
    companyName: 'Next Toppers',
    companyWebsite: 'https://www.nexttoppers.com',
    companyLogoUrl: '/branding/nexttoppers-logo.png',
    loginBackgroundUrl: '/branding/nexttoppers-team-bg.png',
    loginTagline: 'Live system health monitoring for labs, classrooms, offices and mixed Windows + Ubuntu fleets.',
    taglineFontPercent: 50
  };

  function q(s,r){return (r||document).querySelector(s)}
  function qa(s,r){return Array.from((r||document).querySelectorAll(s))}
  function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function text(el){return (el && (el.innerText || el.textContent) || '').trim()}

  window.getCompanyBranding = function(){
    try{
      return Object.assign({}, DEFAULT_BRAND, JSON.parse(localStorage.getItem(BRAND_KEY) || '{}') || {});
    }catch(e){
      return Object.assign({}, DEFAULT_BRAND);
    }
  };

  window.saveCompanyBranding = function(next){
    const clean = Object.assign({}, DEFAULT_BRAND, next || {});
    localStorage.setItem(BRAND_KEY, JSON.stringify(clean));
    return clean;
  };

  function addCss(){
    if(q('#brandingFoundationCss')) return;
    const s=document.createElement('style');
    s.id='brandingFoundationCss';
    s.textContent = `
      .brand-found-card{
        margin-top:16px;
        padding:18px;
        border-radius:18px;
        background:#fff;
        border:1px solid #dbe6f4;
        box-shadow:0 8px 24px rgba(15,23,42,.05);
      }
      .brand-found-card h3{
        margin:0 0 5px;
        color:#0f172a;
        font-size:22px;
        font-weight:850;
      }
      .brand-found-card p{
        margin:0 0 14px;
        color:#64748b;
        font-size:13px;
        font-weight:650;
      }
      .brand-found-grid{
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
        gap:14px;
      }
      .brand-found-field label{
        display:block;
        font-size:12px;
        font-weight:850;
        color:#0f172a;
        margin-bottom:6px;
      }
      .brand-found-field input{
        width:100%;
        box-sizing:border-box;
        padding:10px 12px;
        border-radius:12px;
        border:1px solid #cbd5e1;
        background:#fff;
        color:#0f172a;
        font-size:14px;
        font-weight:650;
      }
      .brand-found-preview-row{
        display:flex;
        gap:10px;
        align-items:center;
        flex-wrap:wrap;
        margin-top:8px;
      }
      .brand-found-logo-preview{
        width:100px;
        height:66px;
        background:#000;
        border-radius:14px;
        border:1px solid #dbe6f4;
        overflow:hidden;
        display:flex;
        align-items:center;
        justify-content:center;
      }
      .brand-found-logo-preview img{
        width:90%;
        height:90%;
        object-fit:contain;
        display:block;
      }
      .brand-found-bg-preview{
        width:150px;
        height:90px;
        background:#000;
        border-radius:14px;
        border:1px solid #dbe6f4;
        overflow:hidden;
      }
      .brand-found-bg-preview img{
        width:100%;
        height:100%;
        object-fit:cover;
        display:block;
      }
      .brand-found-actions{
        margin-top:14px;
        display:flex;
        gap:10px;
        align-items:center;
        flex-wrap:wrap;
      }
      .brand-found-btn{
        padding:10px 14px;
        border-radius:12px;
        border:1px solid #dbe6f4;
        background:#fff;
        color:#0f172a;
        font-weight:850;
        cursor:pointer;
      }
      .brand-found-btn.primary{
        background:linear-gradient(135deg,#06b6d4,#22c55e);
        border-color:transparent;
        color:#062033;
      }
      .brand-found-status{
        color:#15803d;
        font-size:12px;
        font-weight:850;
      }
    `;
    document.head.appendChild(s);
  }

  function findSettingsPage(){
    return q('#page-settings') || qa('.page,[id^="page-"],section,div').find(el=>{
      const t=text(el);
      return t.includes('Settings') && (t.includes('Users') || t.includes('password') || t.includes('refresh'));
    }) || null;
  }

  function readFileAsDataUrl(input, cb){
    const f = input && input.files && input.files[0];
    if(!f) return cb('');
    const r = new FileReader();
    r.onload = function(){ cb(String(r.result || '')); };
    r.readAsDataURL(f);
  }

  function ensureBrandingSettings(){
    addCss();
    const page = findSettingsPage();
    if(!page) return;
    if(q('#brandFoundationCard', page)) return;

    const b = window.getCompanyBranding();
    const card = document.createElement('div');
    card.id = 'brandFoundationCard';
    card.className = 'brand-found-card';
    card.innerHTML = `
      <h3>Company Branding Settings</h3>
      <p>Safe foundation only. Save company name, website, logo, login background and tagline here.</p>
      <div class="brand-found-grid">
        <div class="brand-found-field">
          <label>Company Name</label>
          <input id="brandFoundCompanyName" type="text" value="${esc(b.companyName)}">
        </div>
        <div class="brand-found-field">
          <label>Company Website</label>
          <input id="brandFoundWebsite" type="url" value="${esc(b.companyWebsite)}">
        </div>
        <div class="brand-found-field">
          <label>Login Tagline</label>
          <input id="brandFoundTagline" type="text" value="${esc(b.loginTagline)}">
        </div>
        <div class="brand-found-field">
          <label>Tagline Font Size Percent</label>
          <input id="brandFoundTaglineSize" type="number" min="20" max="100" value="${esc(b.taglineFontPercent)}">
        </div>
        <div class="brand-found-field">
          <label>Company Logo</label>
          <input id="brandFoundLogoFile" type="file" accept="image/*">
          <div class="brand-found-preview-row">
            <div class="brand-found-logo-preview"><img id="brandFoundLogoPreview" src="${esc(b.companyLogoUrl)}" alt="logo"></div>
          </div>
        </div>
        <div class="brand-found-field">
          <label>Login Background Image</label>
          <input id="brandFoundBgFile" type="file" accept="image/*">
          <div class="brand-found-preview-row">
            <div class="brand-found-bg-preview"><img id="brandFoundBgPreview" src="${esc(b.loginBackgroundUrl)}" alt="login background"></div>
          </div>
        </div>
      </div>
      <div class="brand-found-actions">
        <button type="button" class="brand-found-btn primary" id="brandFoundSave">Save Branding</button>
        <button type="button" class="brand-found-btn" id="brandFoundReset">Reset Default</button>
        <span class="brand-found-status" id="brandFoundStatus">Ready</span>
      </div>
    `;

    page.appendChild(card);

    q('#brandFoundLogoFile',card).addEventListener('change', function(){
      readFileAsDataUrl(this, function(url){
        if(url) q('#brandFoundLogoPreview',card).src = url;
      });
    });
    q('#brandFoundBgFile',card).addEventListener('change', function(){
      readFileAsDataUrl(this, function(url){
        if(url) q('#brandFoundBgPreview',card).src = url;
      });
    });

    q('#brandFoundSave',card).onclick = function(){
      const status = q('#brandFoundStatus',card);
      status.textContent = 'Saving...';
      const old = window.getCompanyBranding();
      const next = Object.assign({}, old, {
        companyName: q('#brandFoundCompanyName',card).value || DEFAULT_BRAND.companyName,
        companyWebsite: q('#brandFoundWebsite',card).value || DEFAULT_BRAND.companyWebsite,
        loginTagline: q('#brandFoundTagline',card).value || DEFAULT_BRAND.loginTagline,
        taglineFontPercent: Number(q('#brandFoundTaglineSize',card).value || DEFAULT_BRAND.taglineFontPercent)
      });

      readFileAsDataUrl(q('#brandFoundLogoFile',card), function(logoUrl){
        if(logoUrl) next.companyLogoUrl = logoUrl;
        readFileAsDataUrl(q('#brandFoundBgFile',card), function(bgUrl){
          if(bgUrl) next.loginBackgroundUrl = bgUrl;
          window.saveCompanyBranding(next);
          status.textContent = 'Saved';
          setTimeout(function(){status.textContent='Ready';},1500);
        });
      });
    };

    q('#brandFoundReset',card).onclick = function(){
      window.saveCompanyBranding(DEFAULT_BRAND);
      q('#brandFoundCompanyName',card).value = DEFAULT_BRAND.companyName;
      q('#brandFoundWebsite',card).value = DEFAULT_BRAND.companyWebsite;
      q('#brandFoundTagline',card).value = DEFAULT_BRAND.loginTagline;
      q('#brandFoundTaglineSize',card).value = DEFAULT_BRAND.taglineFontPercent;
      q('#brandFoundLogoPreview',card).src = DEFAULT_BRAND.companyLogoUrl;
      q('#brandFoundBgPreview',card).src = DEFAULT_BRAND.loginBackgroundUrl;
      q('#brandFoundStatus',card).textContent='Default restored';
      setTimeout(function(){q('#brandFoundStatus',card).textContent='Ready';},1500);
    };
  }

  // Wrap switchPage safely so Settings card appears when Settings tab opens.
  if(typeof window.switchPage === 'function' && !window.__brandFoundationSwitchWrapped){
    window.__brandFoundationSwitchWrapped = true;
    const oldSwitch = window.switchPage;
    window.switchPage = function(page){
      const out = oldSwitch.apply(this, arguments);
      if(page === 'settings') setTimeout(ensureBrandingSettings, 120);
      return out;
    };
  }

  setTimeout(ensureBrandingSettings, 500);
  setInterval(function(){
    try{
      if((window.state && state.page === 'settings') || q('#page-settings.active')) ensureBrandingSettings();
    }catch(e){}
  }, 2500);
})();
/* BRANDING_SETTINGS_FOUNDATION_ONLY_END */

/* BRANDING_EXACT_STATIC_APPLY_ONLY_START */
(function(){
  const BRAND_KEY = 'sk_company_branding_foundation_v1';
  const DEFAULT_BRAND = {
    companyName: 'Next Toppers',
    companyWebsite: 'https://www.nexttoppers.com',
    companyLogoUrl: '/branding/nexttoppers-logo.png',
    loginBackgroundUrl: '/branding/nexttoppers-team-bg.png',
    loginTagline: 'Live system health monitoring for labs, classrooms, offices and mixed Windows + Ubuntu fleets.',
    taglineFontPercent: 50
  };

  function q(s,r){return (r||document).querySelector(s)}
  function qa(s,r){return Array.from((r||document).querySelectorAll(s))}
  function cleanUrlForCss(url){return String(url||'').replace(/"/g,'%22').replace(/\n/g,'');}
  function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}

  function getBrand(){
    try{
      if(typeof window.getCompanyBranding === 'function'){
        return Object.assign({}, DEFAULT_BRAND, window.getCompanyBranding() || {});
      }
      return Object.assign({}, DEFAULT_BRAND, JSON.parse(localStorage.getItem(BRAND_KEY) || '{}') || {});
    }catch(e){
      return Object.assign({}, DEFAULT_BRAND);
    }
  }

  function setLogoInto(el, logoUrl){
    if(!el) return;
    el.classList.add('brand-exact-logo-box');
    el.innerHTML = '<img alt="Company logo" src="'+esc(logoUrl || DEFAULT_BRAND.companyLogoUrl)+'">';
  }

  function applyExactBranding(){
    try{
      const b = getBrand();
      const logo = b.companyLogoUrl || DEFAULT_BRAND.companyLogoUrl;

      document.title = (b.companyName || DEFAULT_BRAND.companyName) + ' System Monitor Tool';

      setLogoInto(q('#brandPulseLogo'), logo);
      setLogoInto(q('#brandLoginLogo'), logo);
      setLogoInto(q('#brandSidebarLogo'), logo);

      const sidebarName = q('#brandSidebarName');
      if(sidebarName) sidebarName.textContent = b.companyName || DEFAULT_BRAND.companyName;

      const title = q('#brandLoginTagline');
      if(title){
        title.textContent = b.loginTagline || DEFAULT_BRAND.loginTagline;
        if(!title.dataset.brandBaseFontPx){
          const fs = parseFloat(getComputedStyle(title).fontSize || '0');
          if(fs > 0) title.dataset.brandBaseFontPx = String(fs);
        }
        const base = parseFloat(title.dataset.brandBaseFontPx || getComputedStyle(title).fontSize || '0');
        const pct = Math.max(20, Math.min(100, Number(b.taglineFontPercent || 50)));
        if(base > 0) title.style.fontSize = (base * pct / 100) + 'px';
        title.style.lineHeight = '1.08';
      }

      const loginScreen = q('#loginScreen');
      const appShell = q('#appShell');
      if(loginScreen){
        loginScreen.style.setProperty('--company-login-bg', 'url("'+cleanUrlForCss(b.loginBackgroundUrl || DEFAULT_BRAND.loginBackgroundUrl)+'")');
        if(!loginScreen.classList.contains('hidden') && (!appShell || appShell.classList.contains('locked'))){
          loginScreen.classList.add('brand-login-bg-exact');
        }else{
          loginScreen.classList.remove('brand-login-bg-exact');
        }
      }

      const topLogo = q('#brandTopPillLogo');
      if(topLogo) setLogoInto(topLogo, logo);
      const topName = q('#brandTopPillName');
      if(topName) topName.textContent = b.companyName || DEFAULT_BRAND.companyName;

      const website = q('#companyWebsiteBtn');
      if(website){
        let url = b.companyWebsite || DEFAULT_BRAND.companyWebsite;
        if(!/^https?:\/\//i.test(url)) url = 'https://' + url;
        website.textContent = 'Company Website';
        website.href = url;
      }

      const search = q('#globalSearch');
      if(search) search.classList.add('brand-hidden-search');

      // Keep only one company pill if an older dynamic patch made duplicates.
      const pills = qa('#brandCompanyPill,#ntfixCompanyPill,#ubCompanyPill,#sgbrandCompanyPill,#loginRealCompanyPill,#brandApplyCompanyPill');
      pills.forEach(p=>p.remove());

    }catch(e){
      console.warn('Exact branding apply failed', e);
    }
  }

  function bindSettingsButtons(){
    const save = q('#brandFoundSave');
    if(save && !save.dataset.exactBrandBound){
      save.dataset.exactBrandBound = '1';
      save.addEventListener('click', function(){
        setTimeout(applyExactBranding, 350);
        setTimeout(applyExactBranding, 1200);
        setTimeout(applyExactBranding, 2500);
      });
    }
    const reset = q('#brandFoundReset');
    if(reset && !reset.dataset.exactBrandBound){
      reset.dataset.exactBrandBound = '1';
      reset.addEventListener('click', function(){
        setTimeout(applyExactBranding, 350);
        setTimeout(applyExactBranding, 1200);
      });
    }
  }

  function run(){
    applyExactBranding();
    bindSettingsButtons();
  }

  window.applyExactCompanyBranding = run;

  setTimeout(run, 100);
  setTimeout(run, 500);
  setTimeout(run, 1300);
  setInterval(run, 3000);

  // Also hook login/logout if those functions exist later.
  const oldShow = window.showLogin;
  if(typeof oldShow === 'function' && !window.__exactBrandShowLoginWrapped){
    window.__exactBrandShowLoginWrapped = true;
    window.showLogin = function(){
      const out = oldShow.apply(this, arguments);
      setTimeout(run, 80);
      return out;
    };
  }
  const oldHide = window.hideLogin;
  if(typeof oldHide === 'function' && !window.__exactBrandHideLoginWrapped){
    window.__exactBrandHideLoginWrapped = true;
    window.hideLogin = function(){
      const out = oldHide.apply(this, arguments);
      setTimeout(run, 80);
      return out;
    };
  }
})();
/* BRANDING_EXACT_STATIC_APPLY_ONLY_END */


/* LOGIN_APPROVED_LAYOUT_ANIMATED_ONLY_START */
(function(){
  const BRAND_KEY = 'sk_company_branding_foundation_v1';
  const DEFAULT_BRAND = {
    companyName: 'Next Toppers',
    companyWebsite: 'https://www.nexttoppers.com',
    companyLogoUrl: '/branding/nexttoppers-logo.png',
    loginBackgroundUrl: '/branding/nexttoppers-team-bg.png',
    loginTagline: 'Live system health monitoring for labs, classrooms, offices and mixed Windows + Ubuntu fleets.'
  };

  function q(sel, root){ return (root || document).querySelector(sel); }
  function qa(sel, root){ return Array.from((root || document).querySelectorAll(sel)); }
  function getBrand(){
    try{
      if(typeof window.getCompanyBranding === 'function'){
        return Object.assign({}, DEFAULT_BRAND, window.getCompanyBranding() || {});
      }
      return Object.assign({}, DEFAULT_BRAND, JSON.parse(localStorage.getItem(BRAND_KEY) || '{}') || {});
    }catch(e){ return Object.assign({}, DEFAULT_BRAND); }
  }
  function loginVisible(){
    const login = q('#loginScreen');
    const shell = q('#appShell');
    return !!(login && !login.classList.contains('hidden') && (!shell || shell.classList.contains('locked')));
  }
  function findUsername(root){
    return q('#username', root) || q('input[name="username"]', root) || q('input[type="text"]', root) || q('input[type="email"]', root);
  }
  function findPassword(root){
    return q('#password', root) || q('input[name="password"]', root) || q('input[type="password"]', root);
  }
  function findButton(root){
    return q('#loginBtn', root) || q('button[type="submit"]', root) || q('.btn.wide', root) || qa('button', root).find(Boolean);
  }

  function build(){
    const login = q('#loginScreen');
    if(!login) return;
    const brand = getBrand();
    login.classList.add('login-approved-animated-layout');
    login.style.setProperty('--company-login-bg', 'url("' + String(brand.loginBackgroundUrl || DEFAULT_BRAND.loginBackgroundUrl).replace(/"/g,'%22') + '")');

    let shell = q('#approvedLoginShell', login);
    if(!shell){
      const username = findUsername(login);
      const password = findPassword(login);
      const button = findButton(login);
      const msg = q('#loginMsg', login) || document.createElement('div');
      if(msg && !msg.id) msg.id = 'loginMsg';

      const oldNodes = qa(':scope > *', login);
      oldNodes.forEach(n => { if(n) n.remove(); });

      shell = document.createElement('div');
      shell.id = 'approvedLoginShell';
      shell.innerHTML = `
        <div class="approved-login-card">
          <div class="approved-login-head">
            <div class="approved-login-logo"><img alt="Company logo" src="${brand.companyLogoUrl || DEFAULT_BRAND.companyLogoUrl}"></div>
            <div class="approved-login-kicker">SECURE ADMIN PORTAL</div>
            <h2>System Health<br>Monitor Tool</h2>
            <p class="approved-login-copy">Fast access to fleet status, alerts, software inventory, hardware health and deploy operations.</p>
          </div>
          <div class="approved-login-chips">
            <span>Windows</span><span>Ubuntu</span><span>Real-time alerts</span>
          </div>
          <label class="approved-field-label">Username</label>
          <div class="approved-field-slot approved-slot-user"></div>
          <label class="approved-field-label">Password</label>
          <div class="approved-field-slot approved-slot-pass"></div>
          <div class="approved-button-slot"></div>
          <div class="approved-login-foot">Viewer accounts can see live data only. Admin accounts can download reports, change settings and manage deploy commands.</div>
          <div class="approved-msg-slot"></div>
        </div>
        <div class="approved-monitor-panel">
          <div class="approved-monitor-kicker">INDUSTRIAL FLEET OBSERVABILITY</div>
          <h1 class="approved-monitor-title">Live system health monitoring for labs, classrooms, offices and mixed Windows + Ubuntu fleets.</h1>
          <p class="approved-monitor-copy">Monitor CPU, RAM, storage, GPU, internet, USB, software inventory, notifications and daily history from one operations console.</p>
          <div class="approved-feature-grid">
            <div class="approved-feature-card cpu"><div class="meta">CPU</div><div class="title">Live load</div><div class="sub">Usage + temperature</div><div class="icon chart"><span></span><span></span><span></span><span></span><span></span></div></div>
            <div class="approved-feature-card network"><div class="meta">NETWORK</div><div class="title">ISP and latency</div><div class="sub">Current traffic + reachability</div><div class="icon globe"></div></div>
            <div class="approved-feature-card hardware"><div class="meta">HARDWARE</div><div class="title">GPU / disk / RAM</div><div class="sub">Capacity + health view</div><div class="icon chip"></div></div>
            <div class="approved-feature-card usb"><div class="meta">USB</div><div class="title">Peripheral watch</div><div class="sub">Human readable change tracking</div><div class="icon usb"></div></div>
          </div>
          <div class="approved-ops-panel">
            <div class="approved-ops-head"><div><div class="meta">OPERATIONS OVERVIEW</div><div class="title">Real-time system pulse</div></div><div class="live-pill"><span class="dot"></span>Live heartbeat 5 sec</div></div>
            <div class="approved-ops-body">
              <div class="pulse-logo-wrap">
                <div class="pulse-rings"></div>
                <div class="pulse-logo"><img alt="Company logo" src="${brand.companyLogoUrl || DEFAULT_BRAND.companyLogoUrl}"></div>
              </div>
              <div class="bars-wrap">
                <div class="bar b1"></div>
                <div class="bar b2"></div>
                <div class="bar b3"></div>
                <div class="bar b4"></div>
                <div class="bar b5"></div>
                <div class="bar b6"></div>
              </div>
            </div>
            <div class="approved-stats-grid">
              <div class="stat-card"><div class="big">99.98%</div><div class="small">Visibility target</div></div>
              <div class="stat-card"><div class="big">5 sec</div><div class="small">Dashboard poll</div></div>
              <div class="stat-card"><div class="big">5-10 sec</div><div class="small">Client heartbeat</div></div>
            </div>
          </div>
        </div>`;
      login.appendChild(shell);

      if(username){
        username.classList.add('approved-login-input');
        username.placeholder = username.placeholder || 'admin';
        q('.approved-slot-user', shell)?.appendChild(username);
      }
      if(password){
        password.classList.add('approved-login-input');
        password.placeholder = password.placeholder || 'Enter password';
        q('.approved-slot-pass', shell)?.appendChild(password);
      }
      if(button){
        button.classList.add('approved-login-button');
        if('textContent' in button) button.textContent = 'Enter Operations Dashboard';
        q('.approved-button-slot', shell)?.appendChild(button);
      }
      q('.approved-msg-slot', shell)?.appendChild(msg);
    } else {
      const logo1 = q('.approved-login-logo img', shell);
      const logo2 = q('.pulse-logo img', shell);
      if(logo1) logo1.src = brand.companyLogoUrl || DEFAULT_BRAND.companyLogoUrl;
      if(logo2) logo2.src = brand.companyLogoUrl || DEFAULT_BRAND.companyLogoUrl;
      login.style.setProperty('--company-login-bg', 'url("' + String(brand.loginBackgroundUrl || DEFAULT_BRAND.loginBackgroundUrl).replace(/"/g,'%22') + '")');
    }
  }

  function apply(){
    const login = q('#loginScreen');
    if(!login) return;
    if(loginVisible()) build();
  }

  window.applyApprovedAnimatedLoginLayout = apply;
  setTimeout(apply,100);
  setTimeout(apply,500);
  setTimeout(apply,1200);
  setInterval(apply,2000);
})();
/* LOGIN_APPROVED_LAYOUT_ANIMATED_ONLY_END */


/* MACHINE_FLEET_IDENTITY_RESPONSIVE_V4_START */
(function(){
  const REAL_LAN_PREFIX = ['156.156.'];

  function esc(v){
    return String(v == null ? '' : v).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function norm(v){ return String(v || '').trim().toLowerCase().replace(/[^a-z0-9]+/g,''); }
  function validIp(ip){
    const p = String(ip || '').trim().split('.').map(Number);
    return p.length === 4 && p.every(n => Number.isInteger(n) && n >= 0 && n <= 255);
  }
  function badIp(ip){
    if(!validIp(ip)) return 'invalid';
    const p = ip.split('.').map(Number);
    if(ip === '0.0.0.0' || ip === '255.255.255.255') return 'invalid';
    if(p[0] === 127) return 'loopback';
    if(p[0] === 169 && p[1] === 254) return 'auto-ip';
    if(ip.startsWith('192.168.56.')) return 'VirtualBox';
    if(ip.startsWith('192.168.99.')) return 'Docker/VM';
    if(ip.startsWith('172.17.') || ip.startsWith('172.18.') || ip.startsWith('172.19.')) return 'Docker/VM';
    if(ip === '172.28.176.1') return 'virtual/VPN';
    return '';
  }
  function isPrivate(ip){
    const p = ip.split('.').map(Number);
    return p[0] === 10 || (p[0] === 192 && p[1] === 168) || (p[0] === 172 && p[1] >= 16 && p[1] <= 31);
  }
  function ipScore(ip, currentText){
    if(!validIp(ip)) return -9999;
    let s = 0;
    if(REAL_LAN_PREFIX.some(x => ip.startsWith(x))) s += 10000;
    if(isPrivate(ip)) s += 1000;
    if(ip.startsWith('192.168.') && !badIp(ip)) s += 700;
    if(ip.startsWith('10.')) s += 500;
    if(ip.startsWith('172.') && !badIp(ip)) s += 250;
    if(currentText && String(currentText).includes(ip)) s += 20;
    if(badIp(ip)) s -= 5000;
    return s;
  }
  function collectIps(obj){
    const out = new Set();
    const seen = new Set();
    const ipRe = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g;
    function walk(x, depth){
      if(depth > 8 || x == null) return;
      if(typeof x === 'string'){
        const m = x.match(ipRe);
        if(m) m.forEach(ip => { if(validIp(ip)) out.add(ip); });
        return;
      }
      if(typeof x === 'number' || typeof x === 'boolean') return;
      if(seen.has(x)) return;
      seen.add(x);
      if(Array.isArray(x)) x.forEach(v => walk(v, depth + 1));
      else if(typeof x === 'object') Object.keys(x).forEach(k => walk(x[k], depth + 1));
    }
    walk(obj,0);
    return Array.from(out);
  }
  function payloadSafe(m){
    try{
      if(typeof payload === 'function') return payload(m) || {};
    }catch(e){}
    return (m && (m.payload || m.data || m.raw)) || m || {};
  }
  function machineList(){
    try{
      if(typeof state !== 'undefined' && Array.isArray(state.machines)) return state.machines;
    }catch(e){}
    if(window.state && Array.isArray(window.state.machines)) return window.state.machines;
    return [];
  }
  function hostName(m){
    try{
      if(typeof host === 'function') return host(m);
    }catch(e){}
    const p = payloadSafe(m);
    return p.hostname || p.computer_name || p.machine_name || p.host || m.hostname || m.name || m.machine || m.machine_id || '';
  }
  function identity(m){
    const p = payloadSafe(m);
    return {
      hostname: hostName(m),
      machineId: p.machine_id || p.client_id || p.device_id || m.machine_id || m.id || '',
      asset: p.asset_id || p.asset_tag || p.asset || p.serial || p.serial_number || p.bios_serial || p.motherboard_serial || p.uuid || ''
    };
  }
  function bestIp(m, currentText){
    let ips = m ? collectIps(payloadSafe(m)) : [];
    const inRow = String(currentText || '').match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || [];
    ips.push(...inRow);
    ips = Array.from(new Set(ips)).filter(validIp);
    ips.sort((a,b) => ipScore(b,currentText) - ipScore(a,currentText));
    return {primary: ips[0] || '', all: ips};
  }
  function fleetTables(){
    return Array.from(document.querySelectorAll('table')).filter(t => {
      const h = Array.from(t.querySelectorAll('thead th')).map(x => x.textContent.trim().toUpperCase());
      return h.includes('MACHINE') && h.includes('IP') && h.includes('OS');
    });
  }
  function rowName(row){
    const c = row.children;
    if(c.length < 2) return '';
    return (c[1].textContent || '').split(/\n|ASSET:|CLIENT:|ID:/i)[0].trim();
  }
  function match(row){
    const list = machineList();
    const rn = norm(rowName(row));
    if(!rn || !list.length) return null;
    let m = list.find(x => norm(hostName(x)) === rn);
    if(m) return m;
    m = list.find(x => {
      const h = norm(hostName(x));
      return h && (h.includes(rn) || rn.includes(h));
    });
    if(m) return m;
    const rowIps = (row.textContent || '').match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || [];
    if(rowIps.length){
      return list.find(x => {
        const ips = collectIps(payloadSafe(x));
        return rowIps.some(ip => ips.includes(ip));
      }) || null;
    }
    return null;
  }
  function labels(table){
    const hs = Array.from(table.querySelectorAll('thead th')).map(x => x.textContent.trim());
    table.querySelectorAll('tbody tr').forEach(tr => {
      Array.from(tr.children).forEach((td,i) => {
        if(hs[i]) td.setAttribute('data-label', hs[i]);
      });
    });
    return hs.map(x => x.toUpperCase());
  }
  function machineCell(td, m){
    if(!td || td.dataset.mfv4Done === '1') return;
    const old = td.textContent || '';
    const id = m ? identity(m) : {};
    const name = id.hostname || old.split(/\n|ASSET:|CLIENT:|ID:/i)[0].trim() || 'Unknown machine';
    const meta = [];
    if(id.asset) meta.push('<span>Asset: ' + esc(id.asset) + '</span>');
    if(id.machineId && norm(id.machineId) !== norm(id.asset)) meta.push('<span>Client: ' + esc(id.machineId) + '</span>');
    if(!meta.length){
      const asset = (old.match(/ASSET:\s*([^\n]+)/i) || [])[1] || '';
      if(asset) meta.push('<span>Asset: ' + esc(asset.trim()) + '</span>');
    }
    td.innerHTML = '<div class="mfv4-name">' + esc(name) + '</div><div class="mfv4-meta">' + meta.join('') + '</div>';
    td.dataset.mfv4Done = '1';
  }
  function ipCell(td, m){
    if(!td) return 0;
    const old = td.textContent || '';
    const current = (old.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || [])[0] || '';
    const info = bestIp(m, old);
    const primary = info.primary || current;
    if(!primary) return 0;
    const badCurrent = badIp(current);
    const badPrimary = badIp(primary);
    const others = info.all.filter(x => x !== primary).slice(0,4);
    td.innerHTML = '<div class="mfv4-ip ' + (badPrimary ? 'warn' : '') + '">' + esc(primary) + '</div>' +
      '<div class="mfv4-ip-meta">' +
      ((current && primary !== current) ? '<span class="good">main IP fixed</span>' : '') +
      (badPrimary ? '<span class="warn">' + esc(badPrimary) + '</span>' : '') +
      (others.length ? '<span title="' + esc(others.join(', ')) + '">+' + others.length + ' other IP</span>' : '') +
      '</div>';
    return (badCurrent || badPrimary || (current && primary !== current)) ? 1 : 0;
  }
  function banner(table, warnings){
    const holder = table.closest('.table-wrap,.table-shell,.panel,.card') || table.parentElement;
    if(!holder || holder.parentElement.querySelector('.mfv4-banner')) return;
    const div = document.createElement('div');
    div.className = 'mfv4-banner';
    div.innerHTML = '<b>Machine Fleet identity/IP optimizer active</b><span>Real LAN IP is preferred over Docker/VM/VirtualBox IP when available.</span><em>' + warnings + ' review row(s)</em>';
    holder.parentElement.insertBefore(div, holder);
  }
  function enhance(){
    fleetTables().forEach(table => {
      table.classList.add('mfv4-table');
      const wrap = table.closest('.table-wrap,.table-shell') || table.parentElement;
      if(wrap) wrap.classList.add('mfv4-wrap');
      const hs = labels(table);
      const im = hs.indexOf('MACHINE');
      const ii = hs.indexOf('IP');
      let warnings = 0;
      table.querySelectorAll('tbody tr').forEach(row => {
        row.classList.add('mfv4-row');
        const cells = Array.from(row.children);
        const m = match(row);
        if(im >= 0) machineCell(cells[im], m);
        if(ii >= 0) warnings += ipCell(cells[ii], m);
      });
      banner(table, warnings);
    });
  }

  window.fixMachineFleetIdentityResponsiveV4 = enhance;
  setTimeout(enhance,200);
  setTimeout(enhance,1000);
  setInterval(enhance,3000);
  new MutationObserver(function(){
    clearTimeout(window.__mfv4Timer);
    window.__mfv4Timer = setTimeout(enhance,250);
  }).observe(document.documentElement,{childList:true,subtree:true});
})();
/* MACHINE_FLEET_IDENTITY_RESPONSIVE_V4_END */

