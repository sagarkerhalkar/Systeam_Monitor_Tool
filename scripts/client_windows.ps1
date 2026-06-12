param(
  [string]$ServerUrl = "http://127.0.0.1:2278",
  [int]$IntervalSeconds = 5,
  [switch]$Once
)
$ErrorActionPreference = "SilentlyContinue"
$Root = "C:\ProgramData\SagarSystemMonitor"
$StatePath = Join-Path $Root "client_state.json"
$StatusPath = Join-Path $Root "client_status.json"
$LogPath = Join-Path $Root "client_error.log"
$InventoryStatePath = Join-Path $Root "inventory_state.json"
$IspStatePath = Join-Path $Root "isp_state.json"
$LastPayloadPath = Join-Path $Root "last_payload.json"
$ServerMessageLogPath = Join-Path $Root "server_messages.log"
New-Item -ItemType Directory -Force -Path $Root | Out-Null

function Write-Status($ok, $message, $extra) {
  try {
    $obj = [ordered]@{
      ok=$ok
      message=$message
      server_url=$ServerUrl
      computer=$env:COMPUTERNAME
      time=(Get-Date).ToUniversalTime().ToString('o')
      extra=$extra
    }
    $obj | ConvertTo-Json -Depth 20 | Set-Content -Path $StatusPath -Encoding UTF8
  } catch {}
}
function Write-ClientLog($message) {
  try { "$(Get-Date -Format s) $message" | Add-Content -Path $LogPath } catch {}
}

function GoodText($v) { if ($null -eq $v) { return "" }; return ([string]$v).Trim() }
function Round2($v) { try { return [math]::Round([double]$v, 2) } catch { return $null } }
function New-ClientState {
  return [ordered]@{
    traffic_day=(Get-Date -Format yyyy-MM-dd)
    rx=0.0
    tx=0.0
    today_rx=0.0
    today_tx=0.0
    last_ts=(Get-Date).ToUniversalTime().ToString('o')
  }
}
function Get-Prop($obj, $name, $default) {
  try {
    if($null -ne $obj -and $obj.PSObject.Properties.Name -contains $name -and $null -ne $obj.$name -and [string]$obj.$name -ne '') { return $obj.$name }
  } catch {}
  return $default
}
function Get-State {
  $base = New-ClientState
  if(Test-Path $StatePath){
    try {
      $raw = Get-Content $StatePath -Raw | ConvertFrom-Json
      # V7.4: do not depend on the old property name 'date'. Some Windows clients hit a date property crash.
      $day = Get-Prop $raw 'traffic_day' (Get-Prop $raw 'date' $base.traffic_day)
      return [ordered]@{
        traffic_day=[string]$day
        rx=[double](Get-Prop $raw 'rx' 0)
        tx=[double](Get-Prop $raw 'tx' 0)
        today_rx=[double](Get-Prop $raw 'today_rx' 0)
        today_tx=[double](Get-Prop $raw 'today_tx' 0)
        last_ts=[string](Get-Prop $raw 'last_ts' $base.last_ts)
      }
    } catch { Write-ClientLog "State file invalid, recreating: $($_.Exception.Message)" }
  }
  return $base
}
function Save-State($s) {
  try {
    [ordered]@{
      traffic_day=[string]$s['traffic_day']
      rx=[double]$s['rx']
      tx=[double]$s['tx']
      today_rx=[double]$s['today_rx']
      today_tx=[double]$s['today_tx']
      last_ts=[string]$s['last_ts']
    } | ConvertTo-Json -Depth 8 | Set-Content -Path $StatePath -Encoding UTF8
  } catch { Write-ClientLog "Save-State failed: $($_.Exception.Message)" }
}
function Get-CpuUsage { try { return Round2((Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average) } catch { return $null } }
function Get-CpuTempC {
  try {
    $temps = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature | ForEach-Object { Round2(($_.CurrentTemperature / 10) - 273.15) } | Where-Object { $_ -gt 0 -and $_ -lt 130 }
    if($temps){ return Round2(($temps | Measure-Object -Average).Average) }
  } catch {}
  return $null
}
function Get-ProcessorInfo {
  $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
  return [ordered]@{ name=GoodText $cpu.Name; manufacturer=GoodText $cpu.Manufacturer; cores=$cpu.NumberOfCores; threads=$cpu.NumberOfLogicalProcessors; max_mhz=$cpu.MaxClockSpeed; current_mhz=$cpu.CurrentClockSpeed; socket=GoodText $cpu.SocketDesignation; processor_id=GoodText $cpu.ProcessorId; usage_percent=Get-CpuUsage; temperature_c=Get-CpuTempC }
}
function Get-MemoryInfo {
  $os = Get-CimInstance Win32_OperatingSystem
  $total = [double]$os.TotalVisibleMemorySize * 1024
  $free = [double]$os.FreePhysicalMemory * 1024
  $used = $total - $free
  return [ordered]@{ total_gb=Round2($total/1GB); used_gb=Round2($used/1GB); free_gb=Round2($free/1GB); used_percent=Round2(($used/$total)*100) }
}
function Get-Disks {
  $out = @()
  Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
    $total=[double]$_.Size; $free=[double]$_.FreeSpace; if($total -le 0){ return }
    $out += [ordered]@{ name=$_.DeviceID; mount=$_.DeviceID; type="Fixed"; file_system=$_.FileSystem; total_gb=Round2($total/1GB); free_gb=Round2($free/1GB); used_gb=Round2(($total-$free)/1GB); used_percent=Round2((($total-$free)/$total)*100) }
  }
  return $out
}
function Get-TotalRamMb {
  try {
    $cs = Get-CimInstance Win32_ComputerSystem
    return Round2(([double]$cs.TotalPhysicalMemory / 1MB))
  } catch { return $null }
}
function Get-GpuOverallUsagePercent {
  try {
    $samples = (Get-Counter '\GPU Engine(*)\Utilization Percentage' -ErrorAction Stop).CounterSamples
    $vals = @()
    foreach($s in $samples){
      $p = $s.Path.ToLower()
      if($p -match 'engtype_3d|engtype_compute|engtype_copy|engtype_video'){
        $vals += [double]$s.CookedValue
      }
    }
    if($vals.Count -gt 0){
      $m = ($vals | Measure-Object -Maximum).Maximum
      if($m -lt 0){ $m = 0 }
      if($m -gt 100){ $m = 100 }
      return Round2($m)
    }
  } catch {}
  return $null
}
function Get-TotalRamMb {
  try {
    $cs = Get-CimInstance Win32_ComputerSystem
    return Round2(([double]$cs.TotalPhysicalMemory / 1MB))
  } catch { return $null }
}
function Get-DxdiagGpuInfo {
  $cache = Join-Path $Root "dxdiag_gpu_cache.json"
  $txt = Join-Path $Root "dxdiag_gpu.txt"
  try {
    if((Test-Path $cache) -and ((Get-Date) - (Get-Item $cache).LastWriteTime).TotalHours -lt 12){
      $cached = Get-Content $cache -Raw | ConvertFrom-Json
      return @($cached)
    }
  } catch {}
  $out = @()
  try {
    $dx = Join-Path $env:windir "System32\dxdiag.exe"
    if(Test-Path $dx){
      Remove-Item $txt -Force -ErrorAction SilentlyContinue
      $p = Start-Process -FilePath $dx -ArgumentList "/whql:off /t `"$txt`"" -WindowStyle Hidden -PassThru
      try { Wait-Process -Id $p.Id -Timeout 25 -ErrorAction Stop } catch { try { Stop-Process -Id $p.Id -Force } catch {} }
    }
    if(Test-Path $txt){
      $cur = $null
      foreach($line in (Get-Content $txt -ErrorAction SilentlyContinue)){
        if($line -match '^\s*Card name:\s*(.+)$'){
          if($cur -and $cur.name){ $out += $cur }
          $cur = [ordered]@{ name=GoodText $matches[1]; display_memory_mb=$null; dedicated_memory_mb=$null; shared_memory_mb=$null }
        } elseif($cur -and $line -match '^\s*Display Memory:\s*([0-9]+)\s*MB'){
          $cur.display_memory_mb = Round2($matches[1])
        } elseif($cur -and $line -match '^\s*Dedicated Memory:\s*([0-9]+)\s*MB'){
          $cur.dedicated_memory_mb = Round2($matches[1])
        } elseif($cur -and $line -match '^\s*Shared Memory:\s*([0-9]+)\s*MB'){
          $cur.shared_memory_mb = Round2($matches[1])
        }
      }
      if($cur -and $cur.name){ $out += $cur }
    }
    if($out.Count -gt 0){ $out | ConvertTo-Json -Depth 6 | Set-Content $cache -Encoding UTF8 }
  } catch {}
  return @($out)
}
function Find-DxGpu($name, $dxList){
  if(-not $name -or -not $dxList){ return $null }
  $n = ($name -replace '[^A-Za-z0-9]','').ToLower()
  foreach($d in $dxList){
    $dn = ((GoodText $d.name) -replace '[^A-Za-z0-9]','').ToLower()
    if($dn -and ($dn.Contains($n) -or $n.Contains($dn))){ return $d }
    if($name -match 'Intel' -and (GoodText $d.name) -match 'Intel'){ return $d }
    if($name -match 'UHD' -and (GoodText $d.name) -match 'UHD'){ return $d }
    if($name -match 'NVIDIA' -and (GoodText $d.name) -match 'NVIDIA'){ return $d }
    if($name -match 'AMD|Radeon' -and (GoodText $d.name) -match 'AMD|Radeon'){ return $d }
  }
  return $null
}
function Get-Gpus {
  $out = @()
  $nvidiaDone = $false
  $dxList = @(Get-DxdiagGpuInfo)

  $nvsmi = (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue).Source
  if(-not $nvsmi){ $nvsmi = "C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe" }
  if(Test-Path $nvsmi){
    try{
      $lines = & $nvsmi --query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu --format=csv,noheader,nounits
      foreach($line in $lines){
        $p = $line.Split(',') | ForEach-Object { $_.Trim() }
        if($p.Count -ge 5){
          $name = GoodText $p[0]
          $dx = Find-DxGpu $name $dxList
          $shared = $null; try { if($dx -and $dx.shared_memory_mb){ $shared = Round2($dx.shared_memory_mb) } } catch {}
          $memTotal = Round2($p[1])
          $out += [ordered]@{
            name=$name
            memory_total_mb=$memTotal
            dedicated_memory_mb=$memTotal
            shared_memory_mb=$shared
            memory_used_mb=Round2($p[2])
            usage_percent=Round2($p[3])
            temperature_c=Round2($p[4])
            source="nvidia-smi"
          }
          $nvidiaDone=$true
        }
      }
    } catch {}
  }

  Get-CimInstance Win32_VideoController | ForEach-Object {
    $name=GoodText $_.Name
    if(-not $name){ return }
    if($nvidiaDone -and $name -match "NVIDIA"){ return }

    $dx = Find-DxGpu $name $dxList
    $adapterMb = $null
    try {
      $raw = [double]$_.AdapterRAM
      if($raw -gt 0){ $adapterMb = Round2($raw / 1MB) }
    } catch {}

    $isIntegrated = $false
    if($name -match "Intel|UHD|Iris|Radeon\(TM\) Graphics|Radeon Graphics|Vega|Integrated"){ $isIntegrated = $true }

    $dedicatedMb = $adapterMb
    $sharedMb = $null
    $displayMb = $null
    try { if($dx -and $dx.dedicated_memory_mb){ $dedicatedMb = Round2($dx.dedicated_memory_mb) } } catch {}
    try { if($dx -and $dx.shared_memory_mb){ $sharedMb = Round2($dx.shared_memory_mb) } } catch {}
    try { if($dx -and $dx.display_memory_mb){ $displayMb = Round2($dx.display_memory_mb) } } catch {}

    # Strict actual-data rule:
    # Do NOT calculate shared GPU memory from RAM.
    # Use dxdiag shared memory when available; otherwise leave memory_total null for integrated GPUs.
    $memoryTotal = $dedicatedMb
    $source = "wmi"
    if($dx){ $source = "dxdiag+wmi" }
    if($isIntegrated){
      if($sharedMb){ $memoryTotal = $sharedMb } else { $memoryTotal = $null }
    }

    $out += [ordered]@{
      name=$name
      memory_total_mb=$memoryTotal
      dedicated_memory_mb=$dedicatedMb
      shared_memory_mb=$sharedMb
      display_memory_mb=$displayMb
      memory_used_mb=$null
      usage_percent=$null
      temperature_c=$null
      driver_version=GoodText $_.DriverVersion
      source=$source
    }
  }
  return $out
}



function Get-Software {
  $paths = @("HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*")
  $apps = @{}
  foreach($p in $paths){
    Get-ItemProperty $p | Where-Object { $_.DisplayName } | ForEach-Object {
      $key = "$($_.DisplayName)|$($_.DisplayVersion)"
      if(-not $apps.ContainsKey($key)){ $apps[$key] = [ordered]@{ name=GoodText $_.DisplayName; version=GoodText $_.DisplayVersion; publisher=GoodText $_.Publisher; install_date=GoodText $_.InstallDate } }
    }
  }
  return @($apps.Values | Sort-Object name)
}
function Clean-DeviceName($name) {
  $n = GoodText $name
  if(-not $n){ return "" }
  # Windows registry DeviceDesc sometimes looks like: @input.inf,%hid_device_system_keyboard%;HID Keyboard Device
  if($n -match ";([^;]+)$"){ $n = $Matches[1] }
  $n = $n -replace '^@[^;]+;',''
  $n = $n -replace '\s+',' '
  $n = $n.Trim()
  return $n
}
function Classify-Usb($name, $class) {
  $s = ("$name $class").ToLower()
  if($s -match "keyboard") { return "Keyboard" }
  if($s -match "mouse|pointing") { return "Mouse" }
  if($s -match "headset|headphone|audio|speaker|microphone|sound") { return "Audio" }
  if($s -match "camera|webcam|image") { return "Camera" }
  if($s -match "storage|disk|flash|mass") { return "Storage" }
  if($s -match "bluetooth") { return "Bluetooth" }
  if($s -match "network|ethernet|wi-fi|wifi|802\.11|wireless") { return "USB Network" }
  if($s -match "hub") { return "Hub" }
  return "Peripheral"
}
function Is-NoisyWindowsUsb($name, $class, $id, $source) {
  $n = (GoodText $name).ToLower()
  $c = (GoodText $class).ToLower()
  $did = (GoodText $id).ToLower()
  $src = (GoodText $source).ToLower()

  # Keep useful real peripherals even if they are HID-based.
  if($n -match "keyboard|mouse|headset|headphone|speaker|microphone|audio|camera|webcam|printer|storage|flash|disk|bluetooth|ethernet|wi-fi|wifi|802\.11|wireless|razer|logitech|realtek|tp-link|hp|canon|epson") { return $false }
  if($c -match "keyboard|mouse|audioendpoint|media|camera|image|bluetooth|diskdrive|printer|net") { return $false }

  # Windows exposes many internal laptop/control drivers as HID/USB. They are not user peripherals.
  if($n -match "hid button|hid-compliant system controller|hid-compliant consumer control|hid-compliant vendor-defined|hid-compliant device|hid sensor|i2c hid|gpio buttons|system control|surface hid|intel.*hid|acpi.*button") { return $true }
  if($n -match "usb composite device|usb input device|generic usb hub|usb root hub|root hub|composite parent") { return $true }
  if($did -match "^acpi\|^root\|^swc\|^swd\|^display\|^hid\.*col[0-9a-f]{2}") { return $true }

  # If it came only from the broad fallback and it is a plain HIDClass entry, hide it.
  if($src -match "pnp" -and $c -match "hidclass|hid" -and $n -notmatch "keyboard|mouse|audio|headset|camera") { return $true }
  return $false
}
function Get-UsbDevices {
  # Human-readable peripheral inventory. Keep it useful; do not dump hundreds of raw HID/registry entries.
  $devices = @{}
  function Add-UsbItem($name,$class,$id,$manufacturer,$status,$source){
    $n=Clean-DeviceName $name; $c=GoodText $class; $did=GoodText $id
    if(-not $n -and -not $did){ return }
    if(Is-NoisyWindowsUsb $n $c $did $source){ return }
    $vid=""; $usbPid=""
    if($did -match "VID_([0-9A-Fa-f]{4})"){ $vid=$Matches[1].ToUpper() }
    if($did -match "PID_([0-9A-Fa-f]{4})"){ $usbPid=$Matches[1].ToUpper() }
    if(-not $n -or $n -match "^(USB Input Device|HID Keyboard Device|HID-compliant mouse)$"){
      if($c -match "Keyboard") { $n="Keyboard" }
      elseif($c -match "Mouse|Pointing") { $n="Mouse / Touchpad" }
      elseif($c -match "Audio|Media|AudioEndpoint") { $n="Audio device" }
      elseif($c -match "Camera|Image") { $n="Camera" }
      elseif($c -match "Net") { $n="Network adapter" }
      elseif($did -match 'VID_'){ $n = "USB Peripheral VID " + $vid + $(if($usbPid){" PID $usbPid"}else{""}) }
      elseif($did) { return }
    }
    $type = Classify-Usb $n $c
    # Do not show root hubs/composite/interface rows in the normal admin view.
    if($type -eq "Hub" -and $n -match "root hub|generic usb hub|composite"){ return }
    $key = "$type|$n|$vid|$usbPid"
    if(-not $devices.ContainsKey($key)){
      $connection = if($did -match "^USB") { "USB" } elseif($did -match "^HID") { "HID" } elseif($did -match "^BTH") { "Bluetooth" } else { "System / Peripheral" }
      $devices[$key] = [ordered]@{ name=$n; display_name=$n; class=$c; type=$type; vid=$vid; pid=$usbPid; device_id=$did; manufacturer=Clean-DeviceName $manufacturer; status=GoodText $status; source=$source; connection=$connection; is_usb=($did -match "USB|HID|BTH") }
    }
  }
  # Keyboards / mice / audio / cameras / USB disks: these are what admins and normal users understand.
  try { Get-CimInstance Win32_Keyboard | ForEach-Object { Add-UsbItem $_.Name "Keyboard" $_.DeviceID $_.Manufacturer $_.Status "Win32_Keyboard" } } catch {}
  try { Get-CimInstance Win32_PointingDevice | ForEach-Object { Add-UsbItem $_.Name "Mouse" $_.DeviceID $_.Manufacturer $_.Status "Win32_PointingDevice" } } catch {}
  try { Get-CimInstance Win32_SoundDevice | ForEach-Object { Add-UsbItem $_.Name "Audio" $_.PNPDeviceID $_.Manufacturer $_.Status "Win32_SoundDevice" } } catch {}
  try { Get-CimInstance Win32_DiskDrive | Where-Object { $_.InterfaceType -match "USB" } | ForEach-Object { Add-UsbItem $_.Model "Storage" $_.PNPDeviceID $_.Manufacturer $_.Status "Win32_DiskDrive" } } catch {}
  try {
    Get-CimInstance Win32_PnPEntity | Where-Object {
      ($_.PNPClass -match "Camera|Image|Bluetooth|Printer|Net") -or ($_.Name -match "camera|webcam|bluetooth|printer|usb.*network|usb.*ethernet|wi-fi|wifi")
    } | ForEach-Object { Add-UsbItem $_.Name $_.PNPClass $_.PNPDeviceID $_.Manufacturer $_.Status "Win32_PnPEntity" }
  } catch {}
  # Selective PnP fallback: adds missing user-visible peripherals without dumping hundreds of raw HID/root IDs.
  try {
    Get-PnpDevice -PresentOnly | Where-Object {
      ($_.Class -match "Keyboard|Mouse|AudioEndpoint|Media|Camera|Image|Bluetooth|DiskDrive|Printer|Net") -or
      ($_.FriendlyName -match "keyboard|mouse|headset|headphone|speaker|microphone|camera|webcam|bluetooth|printer|usb.*storage|usb.*network|usb.*ethernet|wi-fi|wifi|802\.11|razer|logitech")
    } | Select-Object -First 80 | ForEach-Object { Add-UsbItem $_.FriendlyName $_.Class $_.InstanceId $_.Manufacturer $_.Status "Get-PnpDevice" }
  } catch {}
  $arr = @($devices.Values | Sort-Object type,name)
  # If strict filters found nothing, send a minimal human-readable fallback instead of blank screen.
  if($arr.Count -eq 0){
    try {
      Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -match "keyboard|mouse|headset|headphone|speaker|microphone|camera|webcam|bluetooth|printer|razer|logitech|realtek|wi-fi|wifi|ethernet" } | Select-Object -First 20 | ForEach-Object {
        $fn = Clean-DeviceName $_.FriendlyName
        if($fn){
          $arr += [ordered]@{ name=$fn; display_name=$fn; class=GoodText $_.Class; type=Classify-Usb $fn $_.Class; vid=''; pid=''; device_id=GoodText $_.InstanceId; manufacturer=GoodText $_.Manufacturer; status=GoodText $_.Status; source='Get-PnpDeviceFallback'; connection='Peripheral'; is_usb=$true }
        }
      }
    } catch {}
  }
  return ,@($arr)
}
function Get-Network {
  $adapters=@(); $primary=""; $vpnActive=$false; $rxTotal=0.0; $txTotal=0.0
  try { $stats = @{}; Get-NetAdapterStatistics | ForEach-Object { $stats[$_.Name] = $_; $rxTotal += [double]$_.ReceivedBytes; $txTotal += [double]$_.SentBytes } } catch { $stats=@{} }
  try {
    Get-NetAdapter | ForEach-Object {
      $a=$_; $ips = @()
      try { $ips = @(Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch "^(127|169\.254)\." } | Select-Object -ExpandProperty IPAddress) } catch {}
      if(-not $primary -and $ips.Count -gt 0 -and $a.Status -eq "Up") { $primary=$ips[0] }
      $desc = "$($a.Name) $($a.InterfaceDescription)"; $isVpn = $desc -match "vpn|tap|tun|wireguard|openvpn|anyconnect|fortinet|globalprotect|zerotier|tailscale|ppp"
      if($isVpn -and $a.Status -eq "Up") { $vpnActive=$true }
      $adapters += [ordered]@{ name=GoodText $a.Name; description=GoodText $a.InterfaceDescription; status=GoodText $a.Status; mac=GoodText $a.MacAddress; link_speed=GoodText $a.LinkSpeed; ips=$ips; is_virtual=($desc -match "virtual|hyper-v|vmware|virtualbox|docker|wsl"); is_vpn=$isVpn; rx_bytes=if($stats[$a.Name]){[int64]$stats[$a.Name].ReceivedBytes}else{0}; tx_bytes=if($stats[$a.Name]){[int64]$stats[$a.Name].SentBytes}else{0} }
    }
  } catch {}
  $state=Get-State; $today=Get-Date -Format yyyy-MM-dd; $nowUtc=(Get-Date).ToUniversalTime()
  $elapsed = 0.0
  try { $elapsed = ($nowUtc - ([datetime]$state['last_ts'])).TotalSeconds } catch { $elapsed = 0.0 }
  if([string]$state['traffic_day'] -ne [string]$today){
    $state = [ordered]@{ traffic_day=$today; rx=[double]$rxTotal; tx=[double]$txTotal; today_rx=0.0; today_tx=0.0; last_ts=$nowUtc.ToString('o') }
  }
  # Safe Int64/Double delta. Do NOT use [math]::Max(0, bigCounter) because PowerShell can choose Int32 overload and crash on high traffic counters.
  $prevRx = 0.0; try { $prevRx = [double]$state['rx'] } catch { $prevRx = 0.0 }
  $prevTx = 0.0; try { $prevTx = [double]$state['tx'] } catch { $prevTx = 0.0 }
  $drx = ([double]$rxTotal) - $prevRx
  $dtx = ([double]$txTotal) - $prevTx
  if($drx -lt 0){ $drx = 0.0 }
  if($dtx -lt 0){ $dtx = 0.0 }
  # Better current speed: average traffic since last heartbeat. This works even if Windows performance counters return zero.
  if($elapsed -lt 1){ $elapsed = [math]::Max(1, $IntervalSeconds) }
  $curDown = Round2((($drx * 8) / 1MB) / $elapsed)
  $curUp = Round2((($dtx * 8) / 1MB) / $elapsed)
  $state['today_rx']=[double]$state['today_rx']+$drx; $state['today_tx']=[double]$state['today_tx']+$dtx; $state['rx']=[double]$rxTotal; $state['tx']=[double]$txTotal; $state['last_ts']=$nowUtc.ToString('o'); Save-State $state
  $traffic=[ordered]@{ date=$today; current_download_mbps=$curDown; current_upload_mbps=$curUp; today_download_gb=Round2([double]$state['today_rx']/1GB); today_upload_gb=Round2([double]$state['today_tx']/1GB); rx_total_bytes=[int64]$rxTotal; tx_total_bytes=[int64]$txTotal; sample_seconds=Round2($elapsed); note="Current speed is average traffic since previous heartbeat; day totals reset at local midnight." }
  return [ordered]@{ primary_ip=$primary; receiver_seen_ip=""; adapters=$adapters; vpn=[ordered]@{ active=$vpnActive; detected_adapters=@($adapters | Where-Object {$_.is_vpn} | Select-Object -ExpandProperty name) }; public_internet=Get-PublicInternetInfo; internet_speed=[ordered]@{ download_mbps=$curDown; upload_mbps=$curUp; source="live_adapter_delta"; note="Current traffic usage, not forced bandwidth speed test" }; traffic=$traffic; current_download_mbps=$curDown; current_upload_mbps=$curUp; today_download_gb=$traffic.today_download_gb; today_upload_gb=$traffic.today_upload_gb; traffic_date=$today }
}
function Get-Identity {
  $base=Get-CimInstance Win32_BaseBoard | Select-Object -First 1
  $prod=Get-CimInstance Win32_ComputerSystemProduct | Select-Object -First 1
  $bios=Get-CimInstance Win32_BIOS | Select-Object -First 1
  return [ordered]@{ hostname=$env:COMPUTERNAME; motherboard_serial=GoodText $base.SerialNumber; system_uuid=GoodText $prod.UUID; bios_serial=GoodText $bios.SerialNumber; manufacturer=GoodText $prod.Vendor; model=GoodText $prod.Name }
}

function Read-JsonFile($path) {
  if(Test-Path $path){ try { return Get-Content $path -Raw | ConvertFrom-Json } catch {} }
  return $null
}
function Write-JsonFile($path, $obj) {
  try { $obj | ConvertTo-Json -Depth 20 | Set-Content -Path $path -Encoding UTF8 } catch {}
}
function Get-PublicInternetInfo {
  $cache = Read-JsonFile $IspStatePath
  try {
    if($cache -and $cache.checked_at){
      $age = (Get-Date) - ([datetime]$cache.checked_at)
      if($age.TotalMinutes -lt 30 -and (($cache.public_ip) -or ($cache.isp))){ return $cache }
    }
  } catch {}
  try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
  $errors = @()
  $targets = @(
    @{ name='ipinfo'; url='https://ipinfo.io/json' },
    @{ name='ip-api'; url='http://ip-api.com/json/?fields=status,query,isp,org,as,country,city' },
    @{ name='ipify'; url='https://api.ipify.org?format=json' }
  )
  foreach($t in $targets){
    try {
      $r = Invoke-RestMethod -Uri $t.url -TimeoutSec 8 -Headers @{ 'User-Agent'='SagarSystemMonitor-Windows/5.1' }
      if($t.name -eq 'ipinfo'){
        $obj = [ordered]@{ public_ip=GoodText $r.ip; isp=GoodText $r.org; org=GoodText $r.org; as=GoodText $r.org; country=GoodText $r.country; city=GoodText $r.city; checked_at=(Get-Date).ToUniversalTime().ToString('o'); source='ipinfo' }
      } elseif($t.name -eq 'ip-api'){
        $obj = [ordered]@{ public_ip=GoodText $r.query; isp=GoodText $r.isp; org=GoodText $r.org; as=GoodText $r.as; country=GoodText $r.country; city=GoodText $r.city; checked_at=(Get-Date).ToUniversalTime().ToString('o'); source='ip-api' }
      } else {
        $obj = [ordered]@{ public_ip=GoodText $r.ip; isp=''; org=''; as=''; country=''; city=''; checked_at=(Get-Date).ToUniversalTime().ToString('o'); source='ipify' }
      }
      if($obj.public_ip -or $obj.isp){ Write-JsonFile $IspStatePath $obj; return $obj }
    } catch { $errors += "$($t.name): $($_.Exception.Message)" }
  }
  if($cache){ return $cache }
  $obj = [ordered]@{ public_ip=''; isp=''; org=''; as=''; country=''; city=''; checked_at=(Get-Date).ToUniversalTime().ToString('o'); source='unavailable'; errors=$errors }
  Write-JsonFile $IspStatePath $obj
  return $obj
}

function To-StringSet($items) {
  $arr = @()
  if($null -ne $items){ foreach($i in $items){ if($null -ne $i -and [string]$i -ne ""){ $arr += [string]$i } } }
  return @($arr | Sort-Object -Unique)
}
function Diff-Added($old, $new) { return @($new | Where-Object { $old -notcontains $_ }) }
function Make-InventorySnapshot($payload) {
  $software = @()
  foreach($a in @($payload.software.installed)){ $software += "$(GoodText $a.name)|$(GoodText $a.version)" }
  $usb = @()
  foreach($u in @($payload.usb.devices)){ $usb += "$(GoodText $u.type)|$(GoodText $u.name)|$(GoodText $u.vid):$(GoodText $u.pid)" }
  $gpus = @(); foreach($g in @($payload.hardware.gpus)){ $gpus += "$(GoodText $g.name)|$(GoodText $g.memory_total_mb)" }
  $disks = @(); foreach($d in @($payload.storage.disks)){ $disks += "$(GoodText $d.name)$(GoodText $d.mount)|$(GoodText $d.total_gb)|$(GoodText $d.type)" }
  $ips = @(); foreach($a in @($payload.network.adapters)){ foreach($ip in @($a.ips)){ $ips += [string]$ip } }
  $hardware = @(
    "cpu=$(GoodText $payload.hardware.cpu.name)",
    "cores=$(GoodText $payload.hardware.cpu.cores)",
    "threads=$(GoodText $payload.hardware.cpu.threads)",
    "ram_gb=$(GoodText $payload.hardware.memory.total_gb)"
  ) + $gpus + $disks
  return [ordered]@{
    software = To-StringSet $software
    usb = To-StringSet $usb
    hardware = To-StringSet $hardware
    ips = To-StringSet $ips
    vpn_active = [bool]$payload.network.vpn.active
  }
}
function New-Change($type, $title, $message, $added, $removed) {
  return [ordered]@{ type=$type; title=$title; message=$message; added=@($added | Select-Object -First 20); removed=@($removed | Select-Object -First 20); created_at=(Get-Date).ToUniversalTime().ToString("o") }
}
function Get-ChangeEvents($payload) {
  $old = Read-JsonFile $InventoryStatePath
  $snap = Make-InventorySnapshot $payload
  if($null -eq $old){ Write-JsonFile $InventoryStatePath $snap; return @() }
  $changes = @()
  $newUsb = @($snap.usb); $oldUsb = @($old.usb); $add = Diff-Added $oldUsb $newUsb; $rem = Diff-Added $newUsb $oldUsb
  if($add.Count -or $rem.Count){ $changes += New-Change "usb" "USB/peripheral changed" "USB/peripheral changed: +$($add.Count) / -$($rem.Count)" $add $rem }
  $newHw = @($snap.hardware); $oldHw = @($old.hardware); $add = Diff-Added $oldHw $newHw; $rem = Diff-Added $newHw $oldHw
  if($add.Count -or $rem.Count){ $changes += New-Change "hardware" "Hardware changed" "Hardware inventory changed: +$($add.Count) / -$($rem.Count)" $add $rem }
  $newSw = @($snap.software); $oldSw = @($old.software); $add = Diff-Added $oldSw $newSw; $rem = Diff-Added $newSw $oldSw
  if($add.Count -or $rem.Count){ $changes += New-Change "software" "Software changed" "Software/app list changed: +$($add.Count) installed/updated, -$($rem.Count) removed" $add $rem }
  $newIp = @($snap.ips); $oldIp = @($old.ips); $add = Diff-Added $oldIp $newIp; $rem = Diff-Added $newIp $oldIp
  if($add.Count -or $rem.Count){ $changes += New-Change "ip" "IP address changed" "IP address list changed: +$($add.Count) / -$($rem.Count)" $add $rem }
  try { if([bool]$snap.vpn_active -ne [bool]$old.vpn_active){ $changes += New-Change "vpn" "VPN status changed" "VPN is now $($snap.vpn_active)" @($snap.vpn_active) @($old.vpn_active) } } catch {}
  Write-JsonFile $InventoryStatePath $snap
  return @($changes)
}



function Show-WtsPopup($title, $message, $seconds) {
  # Shows a real closeable popup in the logged-in user's session even when the agent runs as SYSTEM.
  try {
    $code = @"
using System;
using System.Runtime.InteropServices;
public class WtsPopup {
  [DllImport("wtsapi32.dll", SetLastError=true)] public static extern bool WTSSendMessage(IntPtr hServer, int SessionId, string pTitle, int TitleLength, string pMessage, int MessageLength, int Style, int Timeout, out int pResponse, bool bWait);
  [DllImport("kernel32.dll")] public static extern int WTSGetActiveConsoleSessionId();
}
"@
    Add-Type -TypeDefinition $code -ErrorAction SilentlyContinue | Out-Null
    $sid = [WtsPopup]::WTSGetActiveConsoleSessionId()
    if($sid -lt 0){ return $false }
    $resp = 0
    $ok = [WtsPopup]::WTSSendMessage([IntPtr]::Zero, [int]$sid, [string]$title, ([string]$title).Length, [string]$message, ([string]$message).Length, 0x40, [int]$seconds, [ref]$resp, $false)
    return [bool]$ok
  } catch { return $false }
}

function Show-InteractiveUserPopup($title, $message, $seconds) {
  # Fallback for non-technical users: creates a closeable WScript popup in the active user's desktop session.
  try {
    $user = (Get-CimInstance Win32_ComputerSystem).UserName
    if([string]::IsNullOrWhiteSpace($user)){ return $false }
    $safeTitle = ([string]$title).Replace('"', "'")
    $safeMsg = ([string]$message).Replace('"', "'")
    if($safeMsg.Length -gt 900){ $safeMsg = $safeMsg.Substring(0,900) + '...' }
    $vbs = Join-Path $Root 'show_admin_message.vbs'
    $vbsText = 'CreateObject("WScript.Shell").Popup "' + $safeMsg + '", ' + [int]$seconds + ', "' + $safeTitle + '", 64'
    Set-Content -Path $vbs -Value $vbsText -Encoding ASCII
    $task = 'SagarMonitorAdminPopup_' + ([int][double]::Parse((Get-Date -UFormat %s)))
    $time = (Get-Date).AddMinutes(1).ToString('HH:mm')
    schtasks.exe /Create /TN $task /SC ONCE /ST $time /TR "wscript.exe `"$vbs`"" /RU $user /IT /F | Out-Null
    schtasks.exe /Run /TN $task | Out-Null
    Start-Sleep -Milliseconds 500
    schtasks.exe /Delete /TN $task /F | Out-Null
    return $true
  } catch { Write-ClientLog "Interactive popup fallback failed: $($_.Exception.Message)"; return $false }
}
function Show-ServerMessages($resp) {
  $shown = 0
  try {
    $msgs = @($resp.pending_messages)
    if($msgs.Count -eq 0){ return 0 }
    $publicDesktop = "C:\Users\Public\Desktop"
    $desktopFile = Join-Path $publicDesktop "Sagar Monitor Messages.txt"
    foreach($m in $msgs){
      $title = GoodText $m.title; if(-not $title){ $title = "Admin Message" }
      $msg = GoodText $m.message
      $priority = GoodText $m.priority; if(-not $priority){ $priority = "normal" }
      $popupMsg = $msg
      if($popupMsg.Length -gt 950){ $popupMsg = $popupMsg.Substring(0,950) + "..." }
      $line = "$(Get-Date -Format s) [$priority] $title - $msg"
      try { $line | Add-Content -Path $ServerMessageLogPath -Encoding UTF8 } catch {}
      try { if(Test-Path $publicDesktop){ "`r`n==== Sagar Kerhalkar System Monitor Tool ==== `r`n$line`r`n" | Add-Content -Path $desktopFile -Encoding UTF8 } } catch {}
      $sentVisible = Show-WtsPopup "Sagar Monitor - $title" $popupMsg 120
      if(-not $sentVisible){ $sentVisible = Show-InteractiveUserPopup ("Sagar Monitor - " + $title) $popupMsg 120 }
      if(-not $sentVisible){ try { & msg.exe * /TIME:120 ("Sagar Monitor - " + $title + "`n`n" + $popupMsg) 2>$null | Out-Null; $sentVisible=$true } catch {} }
      $shown += 1
    }
  } catch { Write-ClientLog "Message display error: $($_.Exception.Message)" }
  return $shown
}

function Get-UsbDebugSummary($items) {
  try {
    $arr=@($items)
    $byType=@{}
    foreach($x in $arr){ $t=GoodText $x.type; if(-not $t){$t='Unknown'}; if($byType.ContainsKey($t)){ $byType[$t] = [int]$byType[$t] + 1 } else { $byType[$t] = 1 } }
    return [ordered]@{ count=$arr.Count; types=$byType }
  } catch { return [ordered]@{ count=0; types=@{} } }
}

function Build-Payload {
  $os=Get-CimInstance Win32_OperatingSystem
  $usbDevices = @(Get-UsbDevices)
  $payload = [ordered]@{
    schema_version="pro-v2"; timestamp=(Get-Date).ToUniversalTime().ToString("o"); agent=[ordered]@{ name="SagarSystemMonitor-Windows"; version="4.1-sagar-v8.3-realtime"; interval_seconds=$IntervalSeconds; mode="realtime_inventory_changes" }
    identity=Get-Identity
    hostname=$env:COMPUTERNAME
    os=[ordered]@{ name=$os.Caption; version=$os.Version; build=$os.BuildNumber; architecture=$os.OSArchitecture }
    hardware=[ordered]@{ cpu=Get-ProcessorInfo; memory=Get-MemoryInfo; gpus=Get-Gpus }
    storage=[ordered]@{ disks=Get-Disks }
    network=Get-Network
    software=[ordered]@{ installed=Get-Software }
    usb=[ordered]@{ devices=@($usbDevices); count=@($usbDevices).Count }
  }
  $payload["changes"] = Get-ChangeEvents $payload
  return $payload
}

while($true){
  try{
    Write-ClientLog "Building payload..."
    $payload=Build-Payload
    $json=$payload | ConvertTo-Json -Depth 20 -Compress
    try { $payload | ConvertTo-Json -Depth 20 | Set-Content -Path $LastPayloadPath -Encoding UTF8 } catch {}
    $uri = ($ServerUrl.TrimEnd('/') + '/api/heartbeat')
    Write-ClientLog "Posting heartbeat to $uri"
    $resp = Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $json -TimeoutSec 30
    $msgCount = Show-ServerMessages $resp
    Write-Status $true "Heartbeat sent successfully" ([ordered]@{ response=$resp; payload_bytes=$json.Length; hostname=$env:COMPUTERNAME; usb=Get-UsbDebugSummary $payload.usb.devices; messages_received=$msgCount; message_log=$ServerMessageLogPath })
    Write-ClientLog "SUCCESS heartbeat posted. Machine=$($resp.machine_id)"
  }catch{
    $msg = $_.Exception.Message
    Write-Status $false $msg ([ordered]@{ error_type=$_.Exception.GetType().FullName })
    Write-ClientLog "ERROR $msg"
  }
  if($Once){ break }
  Start-Sleep -Seconds $IntervalSeconds
}
