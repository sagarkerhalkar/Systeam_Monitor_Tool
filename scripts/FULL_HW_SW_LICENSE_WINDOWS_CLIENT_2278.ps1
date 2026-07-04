param(
  [string]$ServerUrl = "http://156.156.40.51:2278",
  [int]$Samples = 5,
  [int]$IntervalSeconds = 5
)

$ErrorActionPreference = "Continue"
$OutDir = "C:\ProgramData\SagarSystemMonitor"
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$PayloadPath = Join-Path $OutDir "full_hw_sw_license_payload_latest.json"
$StatusPath = Join-Path $OutDir "full_hw_sw_license_client_status.json"
$LogPath = Join-Path $OutDir "full_hw_sw_license_client_error.log"
$MsgLog = Join-Path $OutDir "server_messages.log"

function Clean($v) { if ($null -eq $v) { return "" }; return ([string]$v).Trim() }
function ToGB($bytes) { try { return [math]::Round(([double]$bytes / 1GB), 2) } catch { return $null } }
function ToMB($bytes) { try { return [math]::Round(([double]$bytes / 1MB), 2) } catch { return $null } }
function Percent($used,$total) { try { if([double]$total -le 0){return $null}; return [math]::Round(([double]$used*100.0/[double]$total),2) } catch { return $null } }
function Add-Log($m) { try { Add-Content -Path $LogPath -Value ("{0} {1}" -f (Get-Date -Format s), $m) -Encoding UTF8 } catch {} }
function Write-Status($obj) { try { $obj | ConvertTo-Json -Depth 16 | Set-Content -Path $StatusPath -Encoding UTF8 } catch {} }

function Get-SensorTemperature($nameRegex) {
  $out = @()
  foreach($ns in @("root\OpenHardwareMonitor", "root\LibreHardwareMonitor")) {
    try {
      $items = Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction Stop | Where-Object { $_.SensorType -eq "Temperature" -and $_.Name -match $nameRegex }
      foreach($i in $items) { if($null -ne $i.Value -and [double]$i.Value -gt 0 -and [double]$i.Value -lt 125) { $out += [double]$i.Value } }
    } catch {}
  }
  if($out.Count -gt 0) { return [math]::Round(($out | Measure-Object -Average).Average,2) }
  return $null
}

function Get-CpuUsage {
  try {
    $c = Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples 1 -ErrorAction Stop
    return [math]::Round($c.CounterSamples[0].CookedValue,2)
  } catch {
    try { return [double]((Get-CimInstance Win32_Processor | Select-Object -First 1).LoadPercentage) } catch { return $null }
  }
}
function Get-CpuTemp {
  $sensor = Get-SensorTemperature '(CPU|Package|Core)'
  if($null -ne $sensor) { return [pscustomobject]@{ value=$sensor; source="OpenHardwareMonitor/LibreHardwareMonitor WMI"; reason="" } }
  try {
    $temps = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop |
      ForEach-Object { [math]::Round((($_.CurrentTemperature / 10) - 273.15), 2) } |
      Where-Object { $_ -gt 0 -and $_ -lt 125 }
    if ($temps) { return [pscustomobject]@{ value=[math]::Round(($temps | Measure-Object -Average).Average,2); source="MSAcpi_ThermalZoneTemperature"; reason="" } }
  } catch {}
  return [pscustomobject]@{ value=$null; source="not_available"; reason="CPU temperature sensor not exposed by Windows/WMI on this PC" }
}
function Get-MemoryInfo {
  try {
    $os = Get-CimInstance Win32_OperatingSystem
    $totalKB = [double]$os.TotalVisibleMemorySize
    $freeKB = [double]$os.FreePhysicalMemory
    $usedKB = $totalKB - $freeKB
    $mods = @()
    try {
      $mods = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object {
        [pscustomobject]@{
          bank = Clean $_.BankLabel; capacity_gb = ToGB $_.Capacity; speed_mhz = $_.Speed;
          manufacturer = Clean $_.Manufacturer; part_number = Clean $_.PartNumber; serial_number = Clean $_.SerialNumber
        }
      })
    } catch {}
    $ramTemp = Get-SensorTemperature '(Memory|RAM|DIMM|DRAM)'
    return [pscustomobject]@{
      total_gb = [math]::Round(($totalKB*1KB)/1GB,2)
      used_gb = [math]::Round(($usedKB*1KB)/1GB,2)
      free_gb = [math]::Round(($freeKB*1KB)/1GB,2)
      used_percent = Percent $usedKB $totalKB
      modules = $mods
      temperature_c = $ramTemp
      temperature_source = if($null -ne $ramTemp){"OpenHardwareMonitor/LibreHardwareMonitor WMI"}else{"not_available"}
      temperature_reason = if($null -ne $ramTemp){""}else{"RAM temperature is normally not exposed by Windows unless sensor software/hardware supports it"}
      source = "Win32_OperatingSystem+Win32_PhysicalMemory"
    }
  } catch { return [pscustomobject]@{} }
}

function Get-DiskSmartTemp($deviceId, $friendlyName) {
  $r = [ordered]@{ temperature_c=$null; health="N/A"; wear_percent=$null; source="not_available"; reason="No SMART/NVMe temperature source available" }
  try {
    $physical = Get-PhysicalDisk -ErrorAction Stop | Where-Object { ($_.FriendlyName -eq $friendlyName) -or ($_.DeviceId -eq $deviceId) } | Select-Object -First 1
    if($physical) {
      $r.health = Clean $physical.HealthStatus
      $r.media_type = Clean $physical.MediaType
      $rel = $null
      try { $rel = Get-StorageReliabilityCounter -PhysicalDisk $physical -ErrorAction Stop } catch {}
      if($rel) {
        if($null -ne $rel.Temperature) { $r.temperature_c = [double]$rel.Temperature }
        if($null -ne $rel.Wear) { $r.wear_percent = [double]$rel.Wear }
        $r.source = "Get-StorageReliabilityCounter"
        $r.reason = if($null -ne $r.temperature_c){""}else{"Drive did not expose temperature to Windows Storage Reliability Counter"}
      } else { $r.source = "Get-PhysicalDisk"; $r.reason = "Health is available, temperature is not exposed by Windows for this disk" }
    }
  } catch {}
  return [pscustomobject]$r
}

function Get-DiskInfo {
  $logical = @()
  try {
    $logical = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
      $total=[double]$_.Size; $free=[double]$_.FreeSpace; $used=$total-$free
      [pscustomobject]@{
        name = Clean $_.DeviceID; mount = Clean $_.DeviceID; label = Clean $_.VolumeName; filesystem = Clean $_.FileSystem
        total_gb = ToGB $total; free_gb = ToGB $free; used_gb = ToGB $used; used_percent = Percent $used $total
        is_root = ((Clean $_.DeviceID).ToUpper() -eq "C:")
        type = "LogicalDisk"; source = "Win32_LogicalDisk"
      }
    })
  } catch {}
  $physical = @()
  try {
    $physical = @(Get-CimInstance Win32_DiskDrive | ForEach-Object {
      $smart = Get-DiskSmartTemp $_.Index $_.Model
      [pscustomobject]@{
        index = $_.Index; model = Clean $_.Model; serial_number = Clean $_.SerialNumber; interface_type = Clean $_.InterfaceType
        media_type = Clean $_.MediaType; size_gb = ToGB $_.Size; firmware = Clean $_.FirmwareRevision
        temperature_c = $smart.temperature_c; health = $smart.health; wear_percent = $smart.wear_percent
        sensor_source = $smart.source; sensor_reason = $smart.reason; source = "Win32_DiskDrive+StorageReliability"
      }
    })
  } catch {}
  try {
    $pd = @(Get-PhysicalDisk -ErrorAction Stop | ForEach-Object {
      $rel=$null; try{$rel=Get-StorageReliabilityCounter -PhysicalDisk $_ -ErrorAction Stop}catch{}
      [pscustomobject]@{ friendly_name = Clean $_.FriendlyName; serial_number = Clean $_.SerialNumber; media_type = Clean $_.MediaType; bus_type = Clean $_.BusType; health = Clean $_.HealthStatus; operational_status = Clean ($_.OperationalStatus -join ','); size_gb = ToGB $_.Size; temperature_c = if($rel){$rel.Temperature}else{$null}; wear_percent = if($rel){$rel.Wear}else{$null}; sensor_source=if($rel){"Get-StorageReliabilityCounter"}else{"Get-PhysicalDisk"}; sensor_reason=if($rel -and $rel.Temperature){""}else{"Temperature not exposed by this disk/driver"}; source = "Get-PhysicalDisk" }
    })
    if ($pd.Count -gt 0) { $physical += $pd }
  } catch {}
  return [pscustomobject]@{ disks = $logical; physical_disks = $physical; source="Win32_LogicalDisk+Win32_DiskDrive+Get-PhysicalDisk" }
}

function Get-GpuInfo {
  $gpus = @()
  try {
    $nvsmi = (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue).Source
    if (-not $nvsmi) { $try = "C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"; if (Test-Path $try) { $nvsmi = $try } }
    if ($nvsmi) {
      $lines = & $nvsmi --query-gpu=name,utilization.gpu,memory.total,memory.used,memory.free,temperature.gpu,power.draw,driver_version --format=csv,noheader,nounits 2>$null
      foreach($line in $lines) {
        $p = $line -split ',' | ForEach-Object { $_.Trim() }
        if($p.Count -ge 6) {
          $gpus += [pscustomobject]@{ name=$p[0]; usage_percent=[double]$p[1]; memory_total_mb=[double]$p[2]; memory_used_mb=[double]$p[3]; memory_free_mb=[double]$p[4]; temperature_c=[double]$p[5]; power_watts=if($p.Count -ge 7 -and $p[6] -ne '[Not Supported]'){[double]$p[6]}else{$null}; driver_version= if($p.Count -ge 8){$p[7]}else{""}; source="nvidia-smi"; confidence="exact_vendor_tool" }
        }
      }
    }
  } catch { Add-Log "nvidia-smi GPU read failed: $_" }
  try {
    $wmi = @(Get-CimInstance Win32_VideoController | ForEach-Object {
      $ram = $null; try { if ($_.AdapterRAM -gt 0) { $ram = ToMB $_.AdapterRAM } } catch {}
      $exists = $false
      foreach($g in $gpus){ if((Clean $g.name) -and (Clean $_.Name) -and ((Clean $_.Name).Contains((Clean $g.name)) -or (Clean $g.name).Contains((Clean $_.Name)))){ $exists=$true } }
      if(-not $exists){ [pscustomobject]@{ name=Clean $_.Name; memory_total_mb=$ram; dedicated_memory_mb=$ram; shared_memory_mb=$null; usage_percent=$null; temperature_c=$null; driver_version=Clean $_.DriverVersion; source="Win32_VideoController"; confidence="reported_by_os"; missing_reason="Usage/temp not exposed by standard Win32_VideoController" } }
    }) | Where-Object { $_ }
    $gpus += $wmi
  } catch {}
  return @($gpus)
}

function Get-UsbInfo {
  $items = @()
  try {
    $items = @(Get-PnpDevice -PresentOnly -ErrorAction Stop | Where-Object {
      ($_.InstanceId -match '^(USB|HID|BTH)\\') -or ($_.Class -match 'Keyboard|Mouse|USB|HIDClass|AudioEndpoint|Media|Camera|Image|Bluetooth|DiskDrive|Printer|Net')
    } | ForEach-Object {
      [pscustomobject]@{ name=Clean $_.FriendlyName; display_name=Clean $_.FriendlyName; class=Clean $_.Class; type=Clean $_.Class; status=Clean $_.Status; device_id=Clean $_.InstanceId; source="Get-PnpDevice" }
    })
  } catch {
    try {
      $items = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPDeviceID -match '^(USB|HID|BTH)\\' } | ForEach-Object {
        [pscustomobject]@{ name=Clean $_.Name; display_name=Clean $_.Name; class=Clean $_.PNPClass; type=Clean $_.PNPClass; status=Clean $_.Status; device_id=Clean $_.PNPDeviceID; source="Win32_PnPEntity" }
      })
    } catch {}
  }
  return [pscustomobject]@{ count=@($items).Count; devices=@($items) }
}

function Get-InstalledSoftware {
  $paths = @('HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*')
  $apps = @()
  foreach($p in $paths) {
    try { $apps += @(Get-ItemProperty $p -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName } | ForEach-Object { [pscustomobject]@{ name=Clean $_.DisplayName; version=Clean $_.DisplayVersion; publisher=Clean $_.Publisher; install_date=Clean $_.InstallDate; uninstall_string=Clean $_.UninstallString; source=$p } }) } catch {}
  }
  $seen = @{}; $unique = @()
  foreach($a in $apps) { $k = ($a.name + '|' + $a.version + '|' + $a.publisher).ToLower(); if(-not $seen.ContainsKey($k)) { $seen[$k]=1; $unique += $a } }
  return [pscustomobject]@{ installed=@($unique); count=@($unique).Count; source="registry_uninstall" }
}

function Get-WindowsLicense {
  $out = [ordered]@{ product_name=""; product_id=""; edition=""; activation_status="Unknown"; license_channel="Unknown"; partial_product_key=""; source="SoftwareLicensingProduct+registry" }
  try { $cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction SilentlyContinue; $out.product_name = Clean $cv.ProductName; $out.product_id = Clean $cv.ProductId; $out.edition = Clean $cv.EditionID } catch {}
  try {
    $lic = Get-CimInstance SoftwareLicensingProduct | Where-Object { $_.PartialProductKey -and $_.Name -match 'Windows' } | Select-Object -First 1
    if($lic) { $out.partial_product_key = Clean $lic.PartialProductKey; $out.license_description = Clean $lic.Description; switch([int]$lic.LicenseStatus) { 0 {$out.activation_status='Unlicensed'} 1 {$out.activation_status='Licensed'} 2 {$out.activation_status='OOBGrace'} 3 {$out.activation_status='OOTGrace'} 4 {$out.activation_status='NonGenuineGrace'} 5 {$out.activation_status='Notification'} 6 {$out.activation_status='ExtendedGrace'} default {$out.activation_status='Unknown'} }; $d = (Clean $lic.Description).ToUpper(); if($d -match 'OEM'){$out.license_channel='OEM'} elseif($d -match 'RETAIL'){$out.license_channel='Retail'} elseif($d -match 'VOLUME|KMS|GVLK'){$out.license_channel='Volume/KMS'} }
  } catch {}
  return [pscustomobject]$out
}
function Get-OfficeLicense {
  $results=@()
  $paths = @("$env:ProgramFiles\Microsoft Office\Office16\OSPP.VBS", "$env:ProgramFiles(x86)\Microsoft Office\Office16\OSPP.VBS", "$env:ProgramFiles\Microsoft Office\Office15\OSPP.VBS", "$env:ProgramFiles(x86)\Microsoft Office\Office15\OSPP.VBS", "$env:ProgramFiles\Microsoft Office\Office14\OSPP.VBS", "$env:ProgramFiles(x86)\Microsoft Office\Office14\OSPP.VBS") | Where-Object { $_ -and (Test-Path $_) }
  foreach($ospp in $paths | Select-Object -Unique) {
    try { $txt = cscript.exe //nologo $ospp /dstatus 2>$null | Out-String; $last = ([regex]::Match($txt, 'Last 5 characters of installed product key:\s*([A-Z0-9]+)', 'IgnoreCase')).Groups[1].Value; $status = ([regex]::Match($txt, 'LICENSE STATUS:\s*---([^\r\n]+)---', 'IgnoreCase')).Groups[1].Value.Trim(); $name = ([regex]::Match($txt, 'LICENSE NAME:\s*([^\r\n]+)', 'IgnoreCase')).Groups[1].Value.Trim(); $results += [pscustomobject]@{ name=$name; license_status=$status; partial_product_key=$last; ospp_path=$ospp; source="ospp.vbs" } } catch { Add-Log "Office ospp failed: $_" }
  }
  return @($results)
}
function Get-Antivirus { try { return @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop | ForEach-Object { [pscustomobject]@{ name=Clean $_.displayName; product_state=$_.productState; path=Clean $_.pathToSignedProductExe; source="SecurityCenter2" } }) } catch { return @() } }

function Get-NetworkTrafficSample($seconds) {
  try {
    $a = @(Get-NetAdapterStatistics | Select-Object Name,ReceivedBytes,SentBytes)
    Start-Sleep -Seconds ([math]::Max(1,[math]::Min(3,$seconds)))
    $b = @(Get-NetAdapterStatistics | Select-Object Name,ReceivedBytes,SentBytes)
    $rx=0; $tx=0
    foreach($x in $b){ $old=$a | Where-Object { $_.Name -eq $x.Name } | Select-Object -First 1; if($old){ $rx += ([double]$x.ReceivedBytes - [double]$old.ReceivedBytes); $tx += ([double]$x.SentBytes - [double]$old.SentBytes) } }
    $dur=[math]::Max(1,[math]::Min(3,$seconds))
    return [pscustomobject]@{ current_download_mbps=[math]::Round(($rx*8/1000000)/$dur,2); current_upload_mbps=[math]::Round(($tx*8/1000000)/$dur,2); today_download_gb=0; today_upload_gb=0; source="Get-NetAdapterStatistics sample" }
  } catch { return [pscustomobject]@{ current_download_mbps=0; current_upload_mbps=0; today_download_gb=0; today_upload_gb=0; source="traffic_sample_failed" } }
}
function Get-NetworkInfo {
  $adapters=@(); $primary=""
  try {
    $cfgs = @(Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled })
    foreach($c in $cfgs) { $ips=@($c.IPAddress | Where-Object { $_ -and ($_ -notmatch ':') }); if(-not $primary -and $ips.Count -gt 0){$primary=$ips[0]}; $adapters += [pscustomobject]@{ name=Clean $c.Description; description=Clean $c.Description; mac=Clean $c.MACAddress; ips=$ips; gateway=@($c.DefaultIPGateway); dns=@($c.DNSServerSearchOrder); dhcp_enabled=$c.DHCPEnabled; is_virtual=([bool]((Clean $c.Description) -match 'Virtual|Hyper-V|VMware|VirtualBox|Docker|TAP|VPN|Loopback')) } }
  } catch {}
  $pub=[ordered]@{ public_ip=""; isp=""; org=""; country=""; city=""; source="not_checked" }
  try { $info = Invoke-RestMethod -Uri 'https://ipinfo.io/json' -TimeoutSec 5; $pub.public_ip = Clean $info.ip; $pub.isp = Clean $info.org; $pub.org = Clean $info.org; $pub.country = Clean $info.country; $pub.city = Clean $info.city; $pub.source = "ipinfo" } catch { try { $ip = (Invoke-RestMethod -Uri 'https://api.ipify.org?format=json' -TimeoutSec 4).ip; $pub.public_ip = Clean $ip; $pub.source = "api.ipify" } catch {} }
  $vpnInstalled = @(); try { $vpnInstalled = @(Get-InstalledSoftware).installed | Where-Object { $_.name -match 'VPN|AnyConnect|FortiClient|OpenVPN|WireGuard|Tailscale|ZeroTier|GlobalProtect|Pulse|NordVPN|ExpressVPN' } | Select-Object -First 20 } catch {}
  $vpnActive=$false; try { $vpnActive = [bool](Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and ($_.InterfaceDescription -match 'VPN|TAP|TUN|WireGuard|Tailscale|ZeroTier|AnyConnect|Forti|GlobalProtect|Pulse') }) } catch {}
  return [pscustomobject]@{ primary_ip=$primary; adapters=$adapters; public_internet=[pscustomobject]$pub; vpn=[pscustomobject]@{ active=$vpnActive; installed_count=@($vpnInstalled).Count; installed=$vpnInstalled }; traffic=(Get-NetworkTrafficSample 1) }
}
function Get-Identity { $bios=$null;$board=$null;$cs=$null; try{$bios=Get-CimInstance Win32_BIOS}catch{}; try{$board=Get-CimInstance Win32_BaseBoard}catch{}; try{$cs=Get-CimInstance Win32_ComputerSystemProduct}catch{}; [pscustomobject]@{ hostname=$env:COMPUTERNAME; bios_serial=Clean $bios.SerialNumber; motherboard_serial=Clean $board.SerialNumber; system_uuid=Clean $cs.UUID; vendor=Clean $cs.Vendor; model=Clean $cs.Name } }

function Build-Payload {
  $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
  $os = Get-CimInstance Win32_OperatingSystem
  $sw = Get-InstalledSoftware
  $ct = Get-CpuTemp
  $commercial = @($sw.installed | Where-Object { $_.name -match 'Microsoft Office|Microsoft 365|Adobe|AutoCAD|Autodesk|Corel|Tally|Quick Heal|Kaspersky|McAfee|Norton|AnyDesk|TeamViewer|Zoom|Windows' } | Select-Object -First 200)
  return [pscustomobject]@{
    hostname=$env:COMPUTERNAME
    identity=Get-Identity
    os=[pscustomobject]@{ name=(Clean $os.Caption); version=(Clean $os.Version); build=(Clean $os.BuildNumber); architecture=(Clean $os.OSArchitecture) }
    hardware=[pscustomobject]@{
      cpu=[pscustomobject]@{ name=Clean $cpu.Name; manufacturer=Clean $cpu.Manufacturer; cores=$cpu.NumberOfCores; threads=$cpu.NumberOfLogicalProcessors; usage_percent=Get-CpuUsage; temperature_c=$ct.value; temperature_source=$ct.source; temperature_reason=$ct.reason; source="Win32_Processor+Get-Counter+Sensors" }
      memory=Get-MemoryInfo
      gpus=@(Get-GpuInfo)
    }
    storage=Get-DiskInfo
    network=Get-NetworkInfo
    usb=Get-UsbInfo
    software=$sw
    windows_license=Get-WindowsLicense
    office_license=@(Get-OfficeLicense)
    antivirus_products=@(Get-Antivirus)
    software_license_register=[pscustomobject]@{ commercial_software_review=$commercial; fields_supported=@("software_name","version","publisher","assigned_user","license_type","seats","renewal_expiry","bill_invoice_po_no","proof_link","password_vault_reference","partial_key_or_reference","compliance_status"); note="No plaintext full product keys or passwords are exported." }
    changes=@()
    collector=[pscustomobject]@{ name="Sagar Y8 Real Sensor Full HW SW License Collector"; version="20260627-y8-real-sensors"; generated_at=(Get-Date).ToUniversalTime().ToString("o") }
  }
}

try {
  Write-Status @{ ok=$false; stage="starting"; server_url=$ServerUrl; time=(Get-Date).ToString("o") }
  for($i=1; $i -le [math]::Max(1,$Samples); $i++) {
    $payload = Build-Payload
    $json = $payload | ConvertTo-Json -Depth 40 -Compress
    $json | Set-Content -Path $PayloadPath -Encoding UTF8
    $uri = ($ServerUrl.TrimEnd('/')) + "/api/heartbeat"
    $resp = Invoke-RestMethod -Uri $uri -Method POST -ContentType "application/json" -Body $json -TimeoutSec 45
    if($resp.pending_messages) { foreach($m in $resp.pending_messages) { Add-Content -Path $MsgLog -Value ((Get-Date -Format s) + " " + ($m | ConvertTo-Json -Compress)) -Encoding UTF8 } }
    Write-Status @{ ok=$true; stage="posted"; sample=$i; samples=$Samples; machine_id=$resp.machine_id; server_url=$ServerUrl; payload=$PayloadPath; time=(Get-Date).ToString("o"); collector="Y8" }
    Write-Host ("Posted Y8 real sensor H/W + S/W + license payload sample {0}/{1} to {2}" -f $i,$Samples,$uri) -ForegroundColor Green
    if($i -lt $Samples) { Start-Sleep -Seconds $IntervalSeconds }
  }
  Write-Host "Payload saved: $PayloadPath" -ForegroundColor Cyan
  Write-Host "Status saved: $StatusPath" -ForegroundColor Cyan
} catch {
  Add-Log $_
  Write-Status @{ ok=$false; stage="error"; error=(Clean $_); server_url=$ServerUrl; time=(Get-Date).ToString("o"); collector="Y8" }
  Write-Error $_
  exit 1
}
