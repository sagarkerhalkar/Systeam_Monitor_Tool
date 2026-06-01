$ErrorActionPreference = "SilentlyContinue"
$Server = "http://156.156.40.51:8080"
$Hostname = [System.Net.Dns]::GetHostName().ToUpper().Trim()
$OsObj = Get-CimInstance -ClassName Win32_OperatingSystem
$RealOS = $OsObj.Caption.Replace("Microsoft ", "")

while ($true) {
    try {
        $CpuLoadObj = (Get-CimInstance -ClassName Win32_Processor | Measure-Object -Property LoadPercentage -Average)
        $Cpu = if ($CpuLoadObj.Average) { [math]::Round($CpuLoadObj.Average, 1) } else { 0.0 }
        $CpuInfo = Get-CimInstance -ClassName Win32_Processor
        $CpuSerial = if ($CpuInfo.ProcessorId) { $CpuInfo.ProcessorId.Trim() } else { "N/A" }
        $CpuName = if ($CpuInfo.Name) { $CpuInfo.Name.Trim() } else { "Unknown Processor" }

        $Ram = (($OsObj.TotalVisibleMemorySize - $OsObj.FreePhysicalMemory) / $OsObj.TotalVisibleMemorySize) * 100
        $RamUsedPct = [math]::Round($Ram, 1)
        $RawRam = (Get-CimInstance -ClassName Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum
        $TotalRamGB = if ($RawRam -gt 0) { [math]::Round($RawRam / 1GB, 1) } else { 0.0 }

        $NetworkAdapters = @()
        $NetRx = [long]0; $NetTx = [long]0
        $AllIPs = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" }
        $SeenAdapters = @{}

        foreach ($IPItem in $AllIPs) {
            $AdapterObj = Get-NetAdapter -Name $IPItem.InterfaceAlias -ErrorAction SilentlyContinue
            if ($AdapterObj -and $AdapterObj.Status -eq "Up") {
                if (-not $SeenAdapters.ContainsKey($AdapterObj.Name)) {
                    $NetStats = Get-NetAdapterStatistics -Name $AdapterObj.Name -ErrorAction SilentlyContinue
                    if ($NetStats) {
                        $NetRx += [long]$NetStats.ReceivedBytes
                        $NetTx += [long]$NetStats.SentBytes
                    }
                    $SeenAdapters[$AdapterObj.Name] = $true
                }
                $NetworkAdapters += @{ Interface = $AdapterObj.Name; IP = $IPItem.IPAddress }
            }
        }

        $PrimaryIP = "127.0.0.1"
        $BestRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue | Sort-Object Metric | Select-Object -First 1
        if ($BestRoute) { $PrimaryIP = (Get-NetIPAddress -InterfaceIndex $BestRoute.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress }
        if (-not $PrimaryIP -and $NetworkAdapters.Count -gt 0) { $PrimaryIP = $NetworkAdapters[0].IP }

        $StorageDetails = @()
        $LogicalDrives = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DriveType=3"
        foreach ($LogicalDisk in $LogicalDrives) {
            if ($LogicalDisk.Size -gt 0) {
                $DriveLetter = $LogicalDisk.DeviceID; $DiskModel = "Local Fixed Disk"; $DiskSerial = "N/A"; $DiskType = "SSD"
                $DiskDriveObj = Get-CimAssociatedInstance -InputObject $LogicalDisk -Association Win32_LogicalDiskToPartition | ForEach-Object { Get-CimAssociatedInstance -InputObject $_ -Association Win32_DiskToPartition } | ForEach-Object { Get-CimAssociatedInstance -InputObject $_ -Association Win32_DiskDriveToDiskPartition }
                if ($DiskDriveObj) {
                    $DiskModel = $DiskDriveObj.Model
                    if ($DiskDriveObj.SerialNumber) { $DiskSerial = $DiskDriveObj.SerialNumber.Trim() }
                    if ($DiskDriveObj.Model -match "HDD" -or $DiskDriveObj.InterfaceType -eq "IDE") { $DiskType = "HDD" }
                }
                $StorageDetails += @{ Model = $DiskModel.Trim(); Serial = $DiskSerial; DriveLetter = $DriveLetter; Type = $DiskType; Size = "$([math]::Round($LogicalDisk.Size / 1GB, 1)) GB"; Used_Pct = [math]::Round((($LogicalDisk.Size - $LogicalDisk.FreeSpace) / $LogicalDisk.Size) * 100, 1) }
            }
        }

        $GpuList = Get-CimInstance -ClassName Win32_VideoController
        $GpuStrings = @()
        $GpuVRAM = 0.0

        foreach ($Gpu in $GpuList) {
            if ($Gpu.Name -and $Gpu.Name -notlike "*Basic Render*" -and $Gpu.Name -notlike "*Basic Display*") {
                $GpuStrings += $Gpu.Name.Trim()
                if ($Gpu.Name -match "Intel|UHD|Iris|Radeon Graphics|Vega") {
                    $CalculatedVRAM = 0.0
                } else {
                    $TrueBytes = [uint64]($Gpu.AdapterRAM -band 4294967295)
                    if ($TrueBytes -eq 0 -and $Gpu.AdapterRAM -gt 0) { $TrueBytes = [uint64]$Gpu.AdapterRAM }
                    $CalculatedVRAM = [math]::Round(($TrueBytes / 1GB), 1)
                }
                $GpuVRAM += $CalculatedVRAM
            }
        }
        $CombinedGpuName = if ($GpuStrings) { $GpuStrings -join " + " } else { "Integrated Graphics" }

        $PeripheralList = @()
        $RawDevices = Get-CimInstance -ClassName Win32_PnPEntity
        foreach ($Device in $RawDevices) {
            if ($Device.Name) {
                $DeviceClass = $Device.PNPClass
                if ($DeviceClass -eq "Keyboard" -or $DeviceClass -eq "Mouse" -or $DeviceClass -eq "HIDClass" -or $DeviceClass -eq "USB") {
                    $DeviceName = $Device.Name.Trim()
                    if ($DeviceName -notlike "*Root Hub*" -and $DeviceName -notlike "*Host Controller*" -and $DeviceName -notlike "*Virtual*" -and $DeviceName -notlike "*Composite*" -and $DeviceName -notlike "*Controller*") { 
                        $PeripheralList += @{ Name = $DeviceName } 
                    }
                }
            }
        }

        $Body = @{
            hostname     = $Hostname
            ip_address   = $PrimaryIP
            os           = $RealOS
            cpu_name     = $CpuName
            cpu_serial   = $CpuSerial
            ram_total_gb = [float]$TotalRamGB
            adapters     = $NetworkAdapters
            cpu_load     = [float]$Cpu
            ram_used_pct = [float]$RamUsedPct
            storage      = $StorageDetails
            gpu_primary  = $CombinedGpuName
            gpu_vram_gb  = [float]$GpuVRAM
            gpu_load_pct = 0.0
            peripherals  = $PeripheralList
            net_rx_bytes = [long]$NetRx
            net_tx_bytes = [long]$NetTx
        } | ConvertTo-Json -Depth 5

        Invoke-WebRequest -Uri $Server -Method Post -Body $Body -ContentType "application/json; charset=utf-8" -TimeoutSec 15 -UseBasicParsing | Out-Null
    } catch {}
    Start-Sleep -Seconds 10
}
