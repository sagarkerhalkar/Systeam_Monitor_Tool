param(
    [Parameter(Mandatory=$true)][string]$CertificateFile,
    [Parameter(Mandatory=$true)][string]$PrivateKeyFile,
    [string]$BindHost = '0.0.0.0',
    [ValidateRange(1,65535)][int]$Port = 8443,
    [string]$PythonExe = 'python',
    [string]$OrganizationName = '',
    [string]$OrganizationId = '',
    [string]$AdminUsername = '',
    [string]$AdminPasswordFile = '',
    [string]$HealthUrl = '',
    [string]$CaBundle = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this installer from an elevated PowerShell window.'
    }
}

function Set-ProtectedAcl([string]$Path) {
    & icacls.exe $Path /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'BUILTIN\Administrators:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to protect ACL: $Path" }
}

function Write-Utf8NoBom([string]$Path, [string]$Value) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Value, $encoding)
}

Assert-Administrator
$CertificateFile = (Resolve-Path -LiteralPath $CertificateFile).Path
$PrivateKeyFile = (Resolve-Path -LiteralPath $PrivateKeyFile).Path
if ($AdminPasswordFile) { $AdminPasswordFile = (Resolve-Path -LiteralPath $AdminPasswordFile).Path }
if ($CaBundle) { $CaBundle = (Resolve-Path -LiteralPath $CaBundle).Path }

$InstallRoot = Join-Path $env:ProgramFiles 'SagarMonitorCommercialServer'
$VersionsRoot = Join-Path $InstallRoot 'versions'
$DataRoot = Join-Path $env:ProgramData 'SagarMonitorCommercialServer'
$ConfigRoot = Join-Path $DataRoot 'config'
$DatabaseRoot = Join-Path $DataRoot 'data'
$BackupRoot = Join-Path $DataRoot 'backups'
$TlsRoot = Join-Path $ConfigRoot 'tls'
$ConfigFile = Join-Path $ConfigRoot 'server.json'
$PointerFile = Join-Path $InstallRoot 'current.txt'
$TaskName = 'SagarMonitorCommercialServer'
$VersionName = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$VersionRoot = Join-Path $VersionsRoot $VersionName
$DatabaseFile = Join-Path $DatabaseRoot 'commercial.db'
$DatabaseExistedBefore = Test-Path -LiteralPath $DatabaseFile
$OldVersion = ''
$VersionPython = ''
$Entrypoint = ''
$InstalledCommercial = ''
$PreUpgradeBackup = ''
$ConfigurationRollbackRoot = ''
if (Test-Path -LiteralPath $PointerFile) {
    $OldVersion = (Get-Content -LiteralPath $PointerFile -Raw -Encoding UTF8).Trim([char]0xFEFF).Trim()
}

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$CommercialSource = Join-Path $RepositoryRoot 'commercial'
if (-not (Test-Path -LiteralPath (Join-Path $CommercialSource 'sagar_monitor'))) {
    throw "Commercial source folder is missing: $CommercialSource"
}

$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

try {
    foreach ($directory in @($InstallRoot,$VersionsRoot,$DataRoot,$ConfigRoot,$DatabaseRoot,$BackupRoot,$TlsRoot,$VersionRoot)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    Set-ProtectedAcl $DataRoot
    Set-ProtectedAcl $InstallRoot

    $InstalledCommercial = Join-Path $VersionRoot 'commercial'
    New-Item -ItemType Directory -Path $InstalledCommercial -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $CommercialSource 'sagar_monitor') -Destination $InstalledCommercial -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $CommercialSource 'tools') -Destination $InstalledCommercial -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $CommercialSource 'migrations') -Destination $InstalledCommercial -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $CommercialSource 'requirements.lock') -Destination $InstalledCommercial -Force

    & $PythonExe -m venv (Join-Path $VersionRoot 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the commercial server virtual environment.' }
    $VersionPython = Join-Path $VersionRoot 'venv\Scripts\python.exe'
    & $VersionPython -m pip install --disable-pip-version-check --require-hashes -r (Join-Path $InstalledCommercial 'requirements.lock')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install locked commercial dependencies.' }
    & $VersionPython -c 'import ssl,sys; c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); c.load_cert_chain(sys.argv[1],sys.argv[2])' $CertificateFile $PrivateKeyFile
    if ($LASTEXITCODE -ne 0) { throw 'TLS certificate and private key do not form a valid server pair.' }

    if ((Test-Path -LiteralPath $ConfigFile) -or (Test-Path -LiteralPath (Join-Path $TlsRoot 'server.crt')) -or (Test-Path -LiteralPath (Join-Path $TlsRoot 'server.key'))) {
        $ConfigurationRollbackRoot = Join-Path $BackupRoot ('pre-upgrade-config-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))
        New-Item -ItemType Directory -Path $ConfigurationRollbackRoot -Force | Out-Null
        if (Test-Path -LiteralPath $ConfigFile) { Copy-Item -LiteralPath $ConfigFile -Destination (Join-Path $ConfigurationRollbackRoot 'server.json') -Force }
        if (Test-Path -LiteralPath (Join-Path $TlsRoot 'server.crt')) { Copy-Item -LiteralPath (Join-Path $TlsRoot 'server.crt') -Destination (Join-Path $ConfigurationRollbackRoot 'server.crt') -Force }
        if (Test-Path -LiteralPath (Join-Path $TlsRoot 'server.key')) { Copy-Item -LiteralPath (Join-Path $TlsRoot 'server.key') -Destination (Join-Path $ConfigurationRollbackRoot 'server.key') -Force }
        Set-ProtectedAcl $ConfigurationRollbackRoot
    }

    Copy-Item -LiteralPath $CertificateFile -Destination (Join-Path $TlsRoot 'server.crt') -Force
    Copy-Item -LiteralPath $PrivateKeyFile -Destination (Join-Path $TlsRoot 'server.key') -Force
    Set-ProtectedAcl $TlsRoot

    $config = [ordered]@{
        bind_host = $BindHost
        port = $Port
        database_path = $DatabaseFile
        certificate_file = (Join-Path $TlsRoot 'server.crt')
        private_key_file = (Join-Path $TlsRoot 'server.key')
        backup_directory = $BackupRoot
        max_body_bytes = 2097152
        max_header_bytes = 32768
        socket_timeout_seconds = 30
        allow_loopback_http = $false
        server_label = 'Sagar Monitor Commercial Server'
    }
    Write-Utf8NoBom $ConfigFile ($config | ConvertTo-Json -Depth 4)
    Set-ProtectedAcl $ConfigRoot

    $env:PYTHONPATH = $InstalledCommercial
    $Entrypoint = Join-Path $InstalledCommercial 'tools\run_commercial_server.py'
    if ($DatabaseExistedBefore) {
        $backupName = 'pre-upgrade-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '.db'
        $PreUpgradeBackup = Join-Path $BackupRoot $backupName
        & $VersionPython $Entrypoint --config $ConfigFile backup --output $PreUpgradeBackup
        if ($LASTEXITCODE -ne 0) { throw 'Pre-upgrade database backup failed.' }
        & $VersionPython $Entrypoint --config $ConfigFile migrate
        if ($LASTEXITCODE -ne 0) { throw 'Commercial database migration failed.' }
    } else {
        if (-not $OrganizationName -or -not $AdminUsername -or -not $AdminPasswordFile) {
            throw 'First installation requires OrganizationName, AdminUsername, and AdminPasswordFile.'
        }
        $BootstrapPasswordFile = Join-Path $ConfigRoot '.bootstrap-password'
        Copy-Item -LiteralPath $AdminPasswordFile -Destination $BootstrapPasswordFile -Force
        $bootstrapArgs = @(
            $Entrypoint,'--config',$ConfigFile,'bootstrap',
            '--organization-name',$OrganizationName,
            '--admin-username',$AdminUsername,
            '--password-file',$BootstrapPasswordFile
        )
        if ($OrganizationId) { $bootstrapArgs += @('--organization-id',$OrganizationId) }
        & $VersionPython @bootstrapArgs
        if ($LASTEXITCODE -ne 0) { throw 'First-run commercial administrator bootstrap failed.' }
    }

    & $VersionPython $Entrypoint --config $ConfigFile health
    if ($LASTEXITCODE -ne 0) { throw 'Local commercial server health validation failed.' }

    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'run-commercial-server.ps1') -Destination (Join-Path $InstallRoot 'run-commercial-server.ps1') -Force
    $PointerTemp = Join-Path $InstallRoot ('current.' + [guid]::NewGuid().ToString('N') + '.tmp')
    Write-Utf8NoBom $PointerTemp $VersionName
    Move-Item -LiteralPath $PointerTemp -Destination $PointerFile -Force

    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + (Join-Path $InstallRoot 'run-commercial-server.ps1') + '"')
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 4

    if ($HealthUrl) {
        $healthArgs = @($Entrypoint,'--config',$ConfigFile,'health','--remote','--url',$HealthUrl)
        if ($CaBundle) { $healthArgs += @('--ca-bundle',$CaBundle) }
        & $VersionPython @healthArgs
        if ($LASTEXITCODE -ne 0) { throw 'Running HTTPS endpoint failed the health check.' }
    } else {
        $test = Test-NetConnection -ComputerName '127.0.0.1' -Port $Port -WarningAction SilentlyContinue
        if (-not $test.TcpTestSucceeded) { throw "Commercial server did not open TCP port $Port." }
    }

    Write-Host "Commercial server installed successfully. Version: $VersionName"
    Write-Host "Configuration: $ConfigFile"
    Write-Host "Database: $DatabaseFile"
}
catch {
    $OriginalError = $_
    $DatabaseRollbackError = $null
    $ConfigurationRollbackError = $null
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($DatabaseExistedBefore -and $PreUpgradeBackup -and $VersionPython -and $Entrypoint -and (Test-Path -LiteralPath $PreUpgradeBackup)) {
        try {
            $env:PYTHONPATH = $InstalledCommercial
            & $VersionPython $Entrypoint --config $ConfigFile restore --backup $PreUpgradeBackup --confirm-service-stopped
            if ($LASTEXITCODE -ne 0) { throw 'Verified pre-upgrade database restore returned an error.' }
        }
        catch {
            $DatabaseRollbackError = $_
        }
    }
    if ($ConfigurationRollbackRoot) {
        try {
            if (Test-Path -LiteralPath (Join-Path $ConfigurationRollbackRoot 'server.json')) { Copy-Item -LiteralPath (Join-Path $ConfigurationRollbackRoot 'server.json') -Destination $ConfigFile -Force }
            if (Test-Path -LiteralPath (Join-Path $ConfigurationRollbackRoot 'server.crt')) { Copy-Item -LiteralPath (Join-Path $ConfigurationRollbackRoot 'server.crt') -Destination (Join-Path $TlsRoot 'server.crt') -Force }
            if (Test-Path -LiteralPath (Join-Path $ConfigurationRollbackRoot 'server.key')) { Copy-Item -LiteralPath (Join-Path $ConfigurationRollbackRoot 'server.key') -Destination (Join-Path $TlsRoot 'server.key') -Force }
            Set-ProtectedAcl $ConfigRoot
            Set-ProtectedAcl $TlsRoot
        }
        catch {
            $ConfigurationRollbackError = $_
        }
    }
    if ($OldVersion) {
        Write-Utf8NoBom $PointerFile $OldVersion
        if ($ExistingTask -and -not $DatabaseRollbackError -and -not $ConfigurationRollbackError) {
            Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        }
    } else {
        Remove-Item -LiteralPath $PointerFile -Force -ErrorAction SilentlyContinue
    }
    if (-not $DatabaseExistedBefore) {
        Remove-Item -LiteralPath $DatabaseFile -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath ($DatabaseFile + '-wal') -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath ($DatabaseFile + '-shm') -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath (Join-Path $ConfigRoot '.bootstrap-password') -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $VersionRoot -Recurse -Force -ErrorAction SilentlyContinue
    if ($DatabaseRollbackError -or $ConfigurationRollbackError) {
        throw "Installation failed and rollback was incomplete. Old service remains stopped. Original: $OriginalError Database: $DatabaseRollbackError Configuration: $ConfigurationRollbackError"
    }
    throw $OriginalError
}
