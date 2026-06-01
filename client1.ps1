# Pointing to your local machine server
$Server = "http://156.156.40.51:8080"

$Hostname = hostname

# --- FIXED: Automatically detect the real Windows OS Name ---
# This grabs the official name (e.g., "Microsoft Windows 10 Pro" or "Microsoft Windows 11 Enterprise")
# and cleans up the text so it looks nice in your report.
$RealOS = (Get-CimInstance Win32_OperatingSystem).Caption.Replace("Microsoft ", "")

# --- Get ALL Active Adapters with Names and IPs ---
$NetworkAdapters = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.InterfaceAlias -notlike "*Loopback*"
} | ForEach-Object {
    $AdapterInfo = Get-NetAdapter -Name $_.InterfaceAlias -ErrorAction SilentlyContinue
    if ($AdapterInfo -and $AdapterInfo.Status -eq "Up") {
        [PSCustomObject]@{
            Name = $_.InterfaceAlias
            IP   = $_.IPAddress
        }
    }
}

# 1. Get CPU Health (% utilization)
$Cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average

# 2. Get RAM Health (% used)
$OsMemory = Get-CimInstance Win32_OperatingSystem
$Ram = (($OsMemory.TotalVisibleMemorySize - $OsMemory.FreePhysicalMemory) / $OsMemory.TotalVisibleMemorySize) * 100

# 3. Get Network Usage (Bytes sent/received)
$NetStats = Get-NetAdapterStatistics | Where-Object {$_.ReceivedBytes -gt 0} | Select-Object -First 1
$NetRx = $NetStats.ReceivedBytes
$NetTx = $NetStats.SentBytes

# Format JSON payload (Using the dynamic $RealOS variable now!)
$Body = @{
    hostname = $Hostname
    os       = $RealOS
    adapters = $NetworkAdapters
    cpu_load = $Cpu
    ram_used_pct = [math]::Round($Ram, 2)
    net_rx_bytes = $NetRx
    net_tx_bytes = $NetTx
} | ConvertTo-Json -Depth 3

# Push data to your local python server
Invoke-WebRequest -Uri $Server -Method Post -Body $Body -ContentType "application/json"