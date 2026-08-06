[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://')]
    [string]$ServerUrl,

    [string]$EnrollmentTokenFile = '',
    [string]$PythonExe = 'python.exe',
    [string]$InstallRoot = "$env:ProgramFiles\SagarMonitorCommercialAgent",
    [string]$StateRoot = "$env:ProgramData\SagarMonitorCommercialAgent\state",
    [string]$TimezoneName = 'Asia/Kolkata',
    [int]$HeartbeatSeconds = 60
)

$ErrorActionPreference = 'Stop'
$SystemTaskName = 'SagarMonitorCommercialAgent'
$NotifierTaskName = 'SagarMonitorCommercialNotifier'
$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$Stage = "${InstallRoot}.new.$([guid]::NewGuid().ToString('N'))"
$Rollback = "${InstallRoot}.rollback"
$MovedExisting = $false

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this installer from an elevated PowerShell window.'
    }
}

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Description)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "${Description} failed with exit code $LASTEXITCODE"
    }
}

function Stop-AgentTasks {
    foreach ($name in @($SystemTaskName, $NotifierTaskName)) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($null -ne $task) {
            Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        }
    }
}

function Register-AgentTasks {
    $systemRunner = Join-Path $InstallRoot 'run-system-agent.ps1'
    $notifierRunner = Join-Path $InstallRoot 'run-user-notifier.ps1'
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew

    $systemAction = New-ScheduledTaskAction `
        -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$systemRunner`""
    $systemTrigger = New-ScheduledTaskTrigger -AtStartup
    Register-ScheduledTask `
        -TaskName $SystemTaskName `
        -Action $systemAction `
        -Trigger $systemTrigger `
        -Principal $principal `
        -Settings $settings `
        -Description 'Sagar Monitor commercial system agent' `
        -Force | Out-Null

    $notifierAction = New-ScheduledTaskAction `
        -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
        -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$notifierRunner`""
    $notifierTrigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask `
        -TaskName $NotifierTaskName `
        -Action $notifierAction `
        -Trigger $notifierTrigger `
        -Principal $principal `
        -Settings $settings `
        -Description 'Sagar Monitor commercial interactive message notifier' `
        -Force | Out-Null
}

Assert-Administrator
if ($HeartbeatSeconds -lt 10 -or $HeartbeatSeconds -gt 3600) {
    throw 'HeartbeatSeconds must be between 10 and 3600.'
}
if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot 'commercial\sagar_monitor\edge\runtime.py'))) {
    throw 'Commercial agent source is incomplete.'
}

$pythonCommand = Get-Command $PythonExe -ErrorAction Stop
$versionText = & $pythonCommand.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or [version]$versionText -lt [version]'3.12') {
    throw 'Python 3.12 or newer is required.'
}

Stop-AgentTasks
try {
    New-Item -ItemType Directory -Force -Path $Stage | Out-Null
    Copy-Item -LiteralPath (Join-Path $SourceRoot 'commercial') -Destination $Stage -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'run-system-agent.ps1') -Destination $Stage -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'run-user-notifier.ps1') -Destination $Stage -Force

    $venv = Join-Path $Stage 'venv'
    Invoke-Checked -Description 'Python virtual environment creation' -Command {
        & $pythonCommand.Source -m venv $venv
    }
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $lockFile = Join-Path $Stage 'commercial\requirements.lock'
    Invoke-Checked -Description 'Locked dependency installation' -Command {
        & $venvPython -m pip install --disable-pip-version-check --require-hashes -r $lockFile
    }

    New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $StateRoot 'messages') | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $Stage 'config') | Out-Null
    $config = [ordered]@{
        server_url = $ServerUrl.TrimEnd('/')
        state_directory = $StateRoot
        enrollment_token_file = (Join-Path $StateRoot 'enrollment.token')
        timezone_name = $TimezoneName
        heartbeat_interval_seconds = $HeartbeatSeconds
        max_heartbeats_per_cycle = 20
        max_receipts_per_cycle = 50
        queue_limit = 10000
        timeout_seconds = 20
        allow_loopback_http = $false
        registration_metadata = @{ installer = 'windows-pilot-v1' }
    }
    $config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Stage 'config\agent.json') -Encoding UTF8

    $credentialPath = Join-Path $StateRoot 'credential.json'
    $tokenTarget = Join-Path $StateRoot 'enrollment.token'
    if (-not (Test-Path -LiteralPath $credentialPath)) {
        if ($EnrollmentTokenFile) {
            if (-not (Test-Path -LiteralPath $EnrollmentTokenFile)) {
                throw 'EnrollmentTokenFile does not exist.'
            }
            $token = (Get-Content -LiteralPath $EnrollmentTokenFile -Raw).Trim()
        }
        else {
            $secure = Read-Host 'Enrollment token' -AsSecureString
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            try {
                $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
            }
            finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
            }
        }
        if ([string]::IsNullOrWhiteSpace($token)) {
            throw 'A non-empty enrollment token is required for first installation.'
        }
        Set-Content -LiteralPath $tokenTarget -Value $token -Encoding UTF8 -NoNewline
        $token = $null
    }

    if (Test-Path -LiteralPath $Rollback) {
        Remove-Item -LiteralPath $Rollback -Recurse -Force
    }
    if (Test-Path -LiteralPath $InstallRoot) {
        Move-Item -LiteralPath $InstallRoot -Destination $Rollback
        $MovedExisting = $true
    }
    Move-Item -LiteralPath $Stage -Destination $InstallRoot

    # Locale-independent SIDs: SYSTEM and Builtin Administrators only.
    & icacls.exe $StateRoot '/inheritance:r' '/grant:r' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to protect the state directory ACL.' }
    & icacls.exe $InstallRoot '/inheritance:r' '/grant:r' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to protect the installation directory ACL.' }

    Register-AgentTasks
    Start-ScheduledTask -TaskName $SystemTaskName
    Write-Host 'Sagar Monitor commercial pilot agent installed successfully.'
    Write-Host "System task: $SystemTaskName"
    Write-Host "Notifier task: $NotifierTaskName"
    Write-Host "Install root: $InstallRoot"
    Write-Host "State root: $StateRoot"
}
catch {
    Stop-AgentTasks
    foreach ($name in @($SystemTaskName, $NotifierTaskName)) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $InstallRoot) {
        Remove-Item -LiteralPath $InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($MovedExisting -and (Test-Path -LiteralPath $Rollback)) {
        Move-Item -LiteralPath $Rollback -Destination $InstallRoot -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $Stage) {
        Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
    }
    throw
}
