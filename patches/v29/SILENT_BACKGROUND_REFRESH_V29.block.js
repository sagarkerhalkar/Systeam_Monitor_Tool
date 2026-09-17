/* SILENT_BACKGROUND_REFRESH_SAFE_FIX_V29_START
   Scope: frontend refresh presentation only.
   - Keeps the existing 5-second background polling.
   - Hides the old "new data" banner during automatic refresh.
   - Suppresses page/card animations and transitions only while an automatic refresh is painting.
   - Keeps manual Refresh available as a fallback.
   - Does not change server.py, DB, API, clients, heartbeat, inventory data or notification logic.
*/
(function(){
  'use strict';
  if(window.__silentBackgroundRefreshV29) return;
  window.__silentBackgroundRefreshV29=true;

  function installCss(){
    if(document.getElementById('silent-background-refresh-v29-css')) return;
    var st=document.createElement('style');
    st.id='silent-background-refresh-v29-css';
    st.textContent=`
      #newDataBanner{display:none!important}
      html.v29-silent-refresh .page.active,
      html.v29-silent-refresh .page.active *,
      html.v29-silent-refresh .page.active *:before,
      html.v29-silent-refresh .page.active *:after{
        animation:none!important;
        transition:none!important;
        scroll-behavior:auto!important;
      }
      html.v29-silent-refresh .panel:hover,
      html.v29-silent-refresh .kpi:hover,
      html.v29-silent-refresh .summary-tile:hover,
      html.v29-silent-refresh .net-card:hover,
      html.v29-silent-refresh .hw-card:hover,
      html.v29-silent-refresh .detail-card:hover,
      html.v29-silent-refresh .usb-group:hover,
      html.v29-silent-refresh .device-card:hover,
      html.v29-silent-refresh .timeline-card:hover,
      html.v29-silent-refresh .btn:hover{
        transform:none!important;
      }
    `;
    document.head.appendChild(st);
  }

  function hideBanner(){
    try{
      var b=document.getElementById('newDataBanner');
      if(b){b.classList.add('hidden');b.style.display='none';b.setAttribute('aria-hidden','true');}
      if(typeof state!=='undefined') state.pendingUpdate=false;
    }catch(e){}
  }

  function updateRefreshCopy(){
    try{
      var settings=document.getElementById('page-settings');
      if(!settings) return;
      var heads=settings.querySelectorAll('.panel-head h2');
      for(var i=0;i<heads.length;i++){
        if((heads[i].textContent||'').trim()==='Refresh Control'){
          var panel=heads[i].closest('.panel');
          var p=panel&&panel.querySelector('p.muted');
          if(p) p.textContent='Live data refreshes silently in the background. Only the latest values and status are shown; no refresh banner or page redraw notice is displayed.';
          break;
        }
      }
    }catch(e){}
  }

  installCss();
  hideBanner();
  updateRefreshCopy();

  var silentShowBanner=function(){hideBanner();};
  try{window.showBanner=silentShowBanner;showBanner=silentShowBanner;}catch(e){window.showBanner=silentShowBanner;}

  var priorRefresh=null;
  try{priorRefresh=window.refresh || refresh;}catch(e){}
  if(typeof priorRefresh==='function' && !window.__v29RefreshWrapped){
    window.__v29RefreshWrapped=true;
    var silentRefresh=async function(manual){
      if(manual) return priorRefresh.apply(this,arguments);
      var root=document.documentElement;
      root.classList.add('v29-silent-refresh');
      try{
        return await priorRefresh.apply(this,arguments);
      }finally{
        hideBanner();
        requestAnimationFrame(function(){
          requestAnimationFrame(function(){root.classList.remove('v29-silent-refresh');});
        });
      }
    };
    try{window.refresh=silentRefresh;refresh=silentRefresh;}catch(e){window.refresh=silentRefresh;}
  }

  var priorSwitch=null;
  try{priorSwitch=window.switchPage || switchPage;}catch(e){}
  if(typeof priorSwitch==='function' && !window.__v29SwitchWrapped){
    window.__v29SwitchWrapped=true;
    var sw=function(page){
      var out=priorSwitch.apply(this,arguments);
      hideBanner();
      if(page==='settings') setTimeout(updateRefreshCopy,0);
      return out;
    };
    try{window.switchPage=sw;switchPage=sw;}catch(e){window.switchPage=sw;}
  }

  console.info('[V29 silent refresh] automatic refresh is background-only; visible refresh banner disabled.');
})();
/* SILENT_BACKGROUND_REFRESH_SAFE_FIX_V29_END */
