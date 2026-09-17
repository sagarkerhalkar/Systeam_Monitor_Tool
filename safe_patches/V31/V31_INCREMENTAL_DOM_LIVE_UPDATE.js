/* V31_INCREMENTAL_DOM_LIVE_UPDATE_START
   Frontend-only architecture correction.
   Automatic 5-second polling:
   - fetches /api/overview directly in the background;
   - updates state without renderAll()/page innerHTML replacement;
   - patches only stable visible values already in the DOM;
   - preserves search inputs, focus, caret, scroll, open details and reading position.
   Manual refresh and user-triggered page/machine renders remain unchanged.
   No server/API/database/client/inventory-data behavior change.
*/
(function(){
  'use strict';
  if(window.__v31IncrementalDomLiveUpdateInstalled) return;
  window.__v31IncrementalDomLiveUpdateInstalled=true;

  function q(s,r){return (r||document).querySelector(s)}
  function qa(s,r){return Array.from((r||document).querySelectorAll(s))}
  function txt(el,v){if(el && el.textContent!==String(v==null?'':v)) el.textContent=String(v==null?'':v)}
  function num(v){var n=Number(v);return Number.isFinite(n)?n:0}
  function f(v,s,d){
    if(v===null||v===undefined||v==='')return'N/A';
    var n=Number(v); if(!Number.isFinite(n))return String(v);
    var x=n.toFixed(d==null?1:d).replace(/\.0$/,''); return x+(s||'');
  }
  function hostName(m){try{return typeof host==='function'?host(m):(m.hostname||m.machine_id||'UNKNOWN')}catch(e){return m&& (m.hostname||m.machine_id)||'UNKNOWN'}}
  function selectedId(page){
    page=page||((window.state&&state.page)||'');
    try{
      if(page==='machine360') return String(localStorage.getItem('sagar_machine360_selected')||localStorage.getItem('sagar_machine360_lock_v6')||localStorage.getItem('sagar_machineSelect')||state.selected||'');
      if(page==='network') return String(localStorage.getItem('sagar_network_machine')||state.selected||'');
      if(page==='software') return String(localStorage.getItem('sagar_software_machine')||state.selected||'');
      if(page==='usb') return String(localStorage.getItem('sagar_usb_machine')||state.selected||'');
      return String(state.selected||localStorage.getItem('sagar_selected_machine')||'');
    }catch(e){return ''}
  }
  function byId(id){
    id=String(id||'');
    try{return (state.machines||[]).find(function(m){return String(m.machine_id||'')===id})||null}catch(e){return null}
  }
  function setStrongByLabel(root,label,value){
    if(!root)return;
    var wanted=String(label).trim().toLowerCase();
    qa('.kv,.detail-card div,.n360-kv,.n360-chip',root).forEach(function(row){
      var lab=q('span',row); var val=q('strong',row); if(!lab||!val)return;
      if(String(lab.textContent||'').trim().toLowerCase()===wanted) txt(val,value);
    });
  }
  function setDetailByLabel(root,label,value){
    if(!root)return;
    var wanted=String(label).trim().toLowerCase();
    qa('.detail-card div',root).forEach(function(row){
      var lab=q('span',row); var val=q('strong',row); if(!lab||!val)return;
      if(String(lab.textContent||'').trim().toLowerCase()===wanted) txt(val,value);
    });
  }
  function statusText(m){return m&&m.online?'Online':'Offline'}

  function patchChrome(nowDate){
    var apiStatus=q('#apiStatus'); if(apiStatus)apiStatus.classList.add('ok');
    txt(q('#statusText'),'Live');
    txt(q('#lastRefreshText'),'Updated '+nowDate.toLocaleTimeString());
    var b=q('#newDataBanner'); if(b){b.classList.add('hidden');b.style.display='none';b.setAttribute('aria-hidden','true')}
    try{state.pendingUpdate=false}catch(e){}
  }
  function patchDashboard(){
    if(!window.state||state.page!=='dashboard')return;
    var o=state.overview||{}, ms=state.machines||[];
    txt(q('#kTotal'),o.total||0); txt(q('#kOnline'),o.online||0); txt(q('#kOffline'),o.offline||0); txt(q('#kCritical'),o.critical||0);
    txt(q('#kDownToday'),f(o.today_download_gb,' GB',2)); txt(q('#kUpToday'),f(o.today_upload_gb,' GB',2));
    txt(q('#kDownNow'),f(o.current_download_mbps,' Mbps',2)); txt(q('#kUpNow'),f(o.current_upload_mbps,' Mbps',2));
    txt(q('#kUsbTotal'),ms.reduce(function(a,m){return a+num(m.usb_count)},0));
    txt(q('#kSoftwareTotal'),ms.reduce(function(a,m){return a+num(m.software_count)},0));
    var ih=o.internet_health||{};
    if(q('#kLatency')) txt(q('#kLatency'),ih.avg_latency_ms!=null?f(ih.avg_latency_ms,' ms',0):(ih.latency_ms!=null?f(ih.latency_ms,' ms',0):'Probe blocked'));
    if(q('#kJitter')) txt(q('#kJitter'),f(ih.jitter_ms,' ms',0));
    if(q('#kLoss')) txt(q('#kLoss'),ih.loss_percent!=null?f(ih.loss_percent,'%',0):(ih.packet_loss_percent!=null?f(ih.packet_loss_percent,'%',0):'Probe blocked'));
  }
  function patchMachine360(){
    if(!window.state||state.page!=='machine360')return;
    var m=byId(selectedId('machine360')); if(!m)return;
    var root=q('#machineDetails'); if(!root)return;
    setDetailByLabel(root,'Status',statusText(m)); setDetailByLabel(root,'Machine',hostName(m));
    setDetailByLabel(root,'OS',m.os||''); setDetailByLabel(root,'Last Seen',typeof ago==='function'?ago(m.updated_at):String(m.updated_at||''));
    setDetailByLabel(root,'CPU',f(m.cpu_percent,'%',1)); setDetailByLabel(root,'CPU Temp',f(m.cpu_temp_c,' C',1));
    setDetailByLabel(root,'RAM Usage',f(m.ram_percent,'%',1)); setDetailByLabel(root,'RAM Capacity',f(m.ram_total_gb,' GB',1));
    setDetailByLabel(root,'RAM Used',f(m.ram_used_gb,' GB',1)); setDetailByLabel(root,'Disk Max',f(m.disk_max_percent,'%',1));
    setDetailByLabel(root,'Network Now','Down '+f(m.wan_download_mbps,' Mbps',2)+' / Up '+f(m.wan_upload_mbps,' Mbps',2));
    setDetailByLabel(root,'Primary IP',m.primary_ip||''); setDetailByLabel(root,'Public IP',m.public_ip||'');
    setDetailByLabel(root,'ISP',m.isp_name||''); setDetailByLabel(root,'VPN',m.vpn_active?'Active':'Not detected');
    setDetailByLabel(root,'USB / Peripherals',m.usb_count||0); setDetailByLabel(root,'Installed Apps',m.software_count||0);
    setDetailByLabel(root,'GPU Count',m.gpu_count||0); setDetailByLabel(root,'GPU Max Usage',f(m.gpu_max_usage,'%',1)); setDetailByLabel(root,'GPU Temp',f(m.gpu_max_temp_c,' C',1));
  }
  function patchNetwork(){
    if(!window.state||state.page!=='network')return;
    var m=byId(selectedId('network')); if(!m)return;
    var root=q('#networkCards'); if(!root)return;
    var hero=q('.n360-hero',root); if(hero){
      var h=q('h2',hero); if(h)txt(h,hostName(m));
      var sub=q('.n360-sub',hero); if(sub)txt(sub,(m.primary_ip||'No LAN IP')+' · '+(m.os||'Unknown OS')+' · Last seen '+(typeof ago==='function'?ago(m.updated_at):String(m.updated_at||'')));
    }
    setStrongByLabel(root,'Primary IP',m.primary_ip||''); setStrongByLabel(root,'Public IP',m.public_ip||'');
    setStrongByLabel(root,'ISP',m.isp_name||''); setStrongByLabel(root,'VPN Status',m.vpn_active?'Active':'Not detected');
    setStrongByLabel(root,'Download Now',f(m.wan_download_mbps,' Mbps',2)); setStrongByLabel(root,'Upload Now',f(m.wan_upload_mbps,' Mbps',2));
    setStrongByLabel(root,'Day Download',f(m.today_download_gb,' GB',2)); setStrongByLabel(root,'Day Upload',f(m.today_upload_gb,' GB',2));
  }
  function patchFleetStatusOnly(){
    if(!window.state||state.page!=='fleet')return;
    var root=q('#fleetTable'); if(!root)return;
    qa('tbody tr',root).forEach(function(tr){
      var rowText=String(tr.textContent||'');
      var m=(state.machines||[]).find(function(x){return rowText.indexOf(String(x.machine_id||''))>=0 || rowText.indexOf(hostName(x))>=0});
      if(!m)return;
      qa('.pill.online,.pill.offline',tr).forEach(function(p){p.classList.toggle('online',!!m.online);p.classList.toggle('offline',!m.online);txt(p,statusText(m))});
    });
  }
  function patchVisible(){patchDashboard();patchMachine360();patchNetwork();patchFleetStatusOnly()}

  async function fetchOverviewDirect(){
    var r=await fetch('/api/overview',{credentials:'same-origin',cache:'no-store',headers:{'Accept':'application/json'}});
    if(!r.ok) throw new Error((await r.text())||r.statusText);
    return r.json();
  }

  var priorRefresh=null;
  try{priorRefresh=window.refresh||refresh}catch(e){}
  if(typeof priorRefresh!=='function') return;

  var silentRefresh=async function(manual){
    if(manual) return priorRefresh.apply(this,arguments);
    try{
      var oldScrollX=window.scrollX, oldScrollY=window.scrollY;
      var active=document.activeElement;
      var activeValue=(active&&('value' in active))?active.value:null;
      var selStart=null,selEnd=null;
      try{selStart=active&&active.selectionStart;selEnd=active&&active.selectionEnd}catch(_e){}

      var data=await fetchOverviewDirect();
      var rows=Array.isArray(data.machines)?data.machines:[];
      try{
        var c=window.v206SelectedClientDetails&&window.v206SelectedClientDetails.cache;
        if(c&&typeof c.get==='function') rows=rows.map(function(x){var full=c.get(String(x.machine_id||''));return full?Object.assign({},full,x,{payload:full.payload||x.payload}):x});
      }catch(e){}
      state.overview=data; state.machines=rows; state.lastRefresh=new Date(); state.pendingUpdate=false;
      patchChrome(state.lastRefresh); patchVisible();

      if(active&&document.contains(active)){
        try{if(activeValue!==null&&active.value!==activeValue)active.value=activeValue}catch(e){}
        try{if(document.activeElement!==active)active.focus({preventScroll:true})}catch(e){}
        try{if(selStart!=null&&active.setSelectionRange)active.setSelectionRange(selStart,selEnd==null?selStart:selEnd)}catch(e){}
      }
      if(window.scrollX!==oldScrollX||window.scrollY!==oldScrollY) window.scrollTo(oldScrollX,oldScrollY);
      return data;
    }catch(e){
      try{q('#apiStatus')&&q('#apiStatus').classList.remove('ok');txt(q('#statusText'),'Offline')}catch(_e){}
      console.error('[V31 incremental refresh] background overview failed',e);
      return null;
    }
  };
  silentRefresh.__v31Incremental=true; silentRefresh.__v31Prior=priorRefresh;
  try{window.refresh=silentRefresh;refresh=silentRefresh}catch(e){window.refresh=silentRefresh}

  try{showBanner=function(){var b=q('#newDataBanner');if(b){b.classList.add('hidden');b.style.display='none'};try{state.pendingUpdate=false}catch(e){}};window.showBanner=showBanner}catch(e){}
  var style=document.createElement('style');style.id='v31IncrementalStyle';style.textContent='#newDataBanner{display:none!important}';document.head.appendChild(style);

  window.v31IncrementalDomLiveUpdate={patchVisible:patchVisible,fetchOverview:fetchOverviewDirect};
  console.info('[V31] automatic polling is now state-first + incremental DOM; full page renders are user/manual only.');
})();
/* V31_INCREMENTAL_DOM_LIVE_UPDATE_END */