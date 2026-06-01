$ErrorActionPreference = "SilentlyContinue"
while ($true) {
    $ServerUrl = "http://156.156.40.51:8080"
    $CompName = [System.Net.Dns]::GetHostName().ToUpper().Trim()
    $RawOs = (Get-CimInstance Win32_OperatingSystem).Caption
    $CleanOs = $RawOs -replace "Microsoft ", ""
    $CpuInfo = Get-CimInstance Win32_Processor
    $CpuName = if ($CpuInfo.Name) { $CpuInfo.Name.Trim() } else { "Unknown Processor" }
    $CpuSR   = if ($CpuInfo.ProcessorId) { $CpuInfo.ProcessorId.Trim() } else { "N/A" }
    $RawRam = (Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum
    $TotalRamGB = if ($RawRam -gt 0) { [math]::Round($RawRam / 1GB, 1) } else { 0.0 }
    
    # 1. FIND ACTIVE INTERFACE INDEX NATIVELY
    $ActiveIP = "127.0.0.1"
    $AdapterName = ""
    $ActiveNet = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -eq $true -and $_.DefaultIPGateway -ne $null } | Select-Object -First 1
    if ($ActiveNet) { 
        $ActiveIP = $ActiveNet.IPAddress[0]
        $AdapterName = (Get-NetAdapter | Where-Object { $_.InterfaceIndex -eq $ActiveNet.InterfaceIndex }).Name
    }
    
    # 2. EXTRACT RAW INTEGER CONVERSIONS FROM PROPERTY WRAPPERS
    $CurrentRxRaw = 0 ; $CurrentTxRaw = 0
    if ($AdapterName) {
        $TargetStats = Get-NetAdapterStatistics -Name $AdapterName
        if ($TargetStats) {
            # [long] explicitly forces Windows to drop the CimProperty wrapper and provide the raw number
            $CurrentRxRaw = [long]($TargetStats.ReceivedBytes)
            $CurrentTxRaw = [long]($TargetStats.SentBytes)
        }
    } else {
        # Secure fallback for multiple active configurations
        $AllStats = Get-NetAdapterStatistics | Where-Object { $_.ReceivedBytes -gt 0 }
        if ($AllStats) {
            $CurrentRxRaw = [long]($AllStats | Measure-Object -Property ReceivedBytes -Sum).Sum
            $CurrentTxRaw = [long]($AllStats | Measure-Object -Property SentBytes -Sum).Sum
        }
    }
    
    $StorageDetails = @()
    $LogicalDrives = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"
    foreach ($Drive in $LogicalDrives) {
        if ($Drive.Size -gt 0) {
            $UsedPct = [math]::Round((($Drive.Size - $Drive.FreeSpace) / $Drive.Size) * 100, 1)
            $StorageDetails += @{ Model = "Drive $($Drive.DeviceID)"; Type = "SSD"; Size = "$([math]::Round($Drive.Size / 1GB, 1)) GB"; Used_Pct = $UsedPct }
        }
    }
    $GpuList = Get-CimInstance Win32_VideoController
    $GpuStrings = @()
    foreach ($Gpu in $GpuList) {
        if ($Gpu.Name -and $Gpu.Name -notlike "*Basic Render*") { $GpuStrings += "$($Gpu.Name.Trim())" }
    }
    $CombinedGpuName = $GpuStrings -join " + "
    if (-not $CombinedGpuName) { $CombinedGpuName = "Integrated Graphics" }
    $CpuLoadObj = Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average
    $CpuLoad = if ($CpuLoadObj.Average) { [math]::Round($CpuLoadObj.Average, 1) } else { 0.0 }
    $OsMemory = Get-CimInstance Win32_OperatingSystem
    $RamLoad = 0.0
    if ($OsMemory.TotalVisibleMemorySize -gt 0) { $RamLoad = [math]::Round((($OsMemory.TotalVisibleMemorySize - $OsMemory.FreePhysicalMemory) / $OsMemory.TotalVisibleMemorySize) * 100, 1) }
    
    $PayloadObject = @{ hostname = $CompName; ip_address = $ActiveIP; os = $CleanOs; cpu_name = $CpuName; cpu_serial = $CpuSR; ram_total_gb = [float]$TotalRamGB; storage = $StorageDetails; gpus = @(); adapters = @(@{ Interface = "Active"; IP = $ActiveIP }); peripherals = @(); cpu_load = [float]$CpuLoad; ram_used_pct = [float]$RamLoad; gpu_primary = $CombinedGpuName; gpu_load_pct = 0.0; net_rx_bytes = $CurrentRxRaw; net_tx_bytes = $CurrentTxRaw }
  # Create logs folder if it does not exist
$LogFolder = "C:\SystemLogs"
if (!(Test-Path $LogFolder)) {
    New-Item -ItemType Directory -Path $LogFolder | Out-Null
}

# File name based on computer name
$LogFile = "$LogFolder\$CompName.json"

# Save JSON data
$JsonBody | Out-File -FilePath $LogFile -Encoding utf8
    $JsonBody = $PayloadObject | ConvertTo-Json -Depth 5

# Save locally
$LogFolder = "C:\SystemLogs"
if (!(Test-Path $LogFolder)) {
    New-Item -ItemType Directory -Path $LogFolder | Out-Null
}

$LogFile = "$LogFolder\$CompName.json"
$JsonBody | Out-File -FilePath $LogFile -Encoding utf8

# Send to server
Invoke-WebRequest `
    -Uri $ServerUrl `
    -Method POST `
    -Body $JsonBody `
    -ContentType "application/json; charset=utf-8" `
    -TimeoutSec 10 `
    -UseBasicParsing | Out-Null
    Start-Sleep -Seconds 60
}