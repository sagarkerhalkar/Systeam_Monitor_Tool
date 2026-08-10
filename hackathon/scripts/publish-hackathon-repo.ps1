param(
    [string]$SourceRepository = 'sagarkerhalkar/Systeam_Monitor_Tool',
    [string]$SourceBranch = 'hackathon/dora-sota-monitor-20260810',
    [string]$TargetRepository = 'sagarkerhalkar/System-Monitor-DORA-SOTA-Hackathon',
    [string]$GitHubCli = 'gh',
    [string]$GitExe = 'git'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Checked {
    param([string]$File, [string[]]$Arguments, [string]$WorkingDirectory = '')
    $old = Get-Location
    try {
        if ($WorkingDirectory) { Set-Location -LiteralPath $WorkingDirectory }
        & $File @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed ($LASTEXITCODE): $File $($Arguments -join ' ')"
        }
    }
    finally {
        Set-Location $old
    }
}

function Test-GitHubRepositoryExists {
    param([string]$Repository)

    # Windows PowerShell 5.1 turns native stderr into ErrorRecord objects. A normal
    # GitHub 404 during an existence probe must not terminate the publisher.
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'SilentlyContinue'
        & $GitHubCli repo view $Repository --json visibility 1>$null 2>$null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $savedPreference
    }

    if ($exitCode -eq 0) { return $true }
    if ($exitCode -eq 1) { return $false }
    throw "Unable to check target repository existence (gh exit code $exitCode): $Repository"
}

if (-not (Get-Command $GitHubCli -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI (gh) is required. Install from https://cli.github.com/ and run gh auth login.'
}
if (-not (Get-Command $GitExe -ErrorAction SilentlyContinue)) {
    throw 'Git is required.'
}

Invoke-Checked $GitHubCli @('auth','status','--hostname','github.com')

$repoRoot = (& $GitExe rev-parse --show-toplevel 2>$null).Trim()
if (-not $repoRoot) { throw 'Run this script from a clone of Systeam_Monitor_Tool.' }

$origin = (& $GitExe -C $repoRoot remote get-url origin).Trim()
if ($origin -notmatch [regex]::Escape($SourceRepository)) {
    throw "Wrong source repository. Expected $SourceRepository but origin is $origin"
}

Invoke-Checked $GitExe @('-C',$repoRoot,'fetch','origin',$SourceBranch,'--no-tags')
$sourceSha = (& $GitExe -C $repoRoot rev-parse 'FETCH_HEAD').Trim()
if ($sourceSha -notmatch '^[0-9a-f]{40}$') { throw 'Unable to resolve source branch SHA.' }

if (Test-GitHubRepositoryExists -Repository $TargetRepository) {
    throw "Target repository already exists: $TargetRepository. Refusing to overwrite it."
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('sagar-monitor-hackathon-publish-' + [guid]::NewGuid().ToString('N'))
$worktree = Join-Path $tempRoot 'source'
$publish = Join-Path $tempRoot 'publish'
New-Item -ItemType Directory -Path $tempRoot,$publish -Force | Out-Null

try {
    Invoke-Checked $GitExe @('-C',$repoRoot,'worktree','add','--detach',$worktree,$sourceSha)

    foreach ($item in @('commercial','hackathon')) {
        $source = Join-Path $worktree $item
        if (-not (Test-Path -LiteralPath $source)) { throw "Required source path missing: $item" }
        Copy-Item -LiteralPath $source -Destination (Join-Path $publish $item) -Recurse -Force
    }

    New-Item -ItemType Directory -Path (Join-Path $publish '.github\workflows') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $worktree '.github\workflows\hackathon-phase1-ci.yml') `
        -Destination (Join-Path $publish '.github\workflows\hackathon-phase1-ci.yml') -Force

    Copy-Item -LiteralPath (Join-Path $worktree 'hackathon\README.md') -Destination (Join-Path $publish 'README.md') -Force

    @"
# Source provenance

This repository was exported from `$SourceRepository` branch `$SourceBranch`.

Source commit: `$sourceSha`

The production `workingcode` branch is intentionally not included. This repository is an isolated hackathon/cloud-native implementation.
"@ | Set-Content -LiteralPath (Join-Path $publish 'SOURCE_PROVENANCE.md') -Encoding UTF8

    @"
hackathon/.env
*.db
*.db-wal
*.db-shm
.env
*.pem
*.key
*.crt
.terraform/
terraform.tfstate*
"@ | Set-Content -LiteralPath (Join-Path $publish '.gitignore') -Encoding UTF8

    Invoke-Checked $GitExe @('init','-b','main') $publish
    Invoke-Checked $GitExe @('config','user.name','Sagar Kerhalkar') $publish
    Invoke-Checked $GitExe @('config','user.email','85802314+sagarkerhalkar@users.noreply.github.com') $publish
    Invoke-Checked $GitExe @('add','--all') $publish
    Invoke-Checked $GitExe @('commit','-m',"Initial DORA + SOTA hackathon project from $sourceSha") $publish

    Invoke-Checked $GitHubCli @(
        'repo','create',$TargetRepository,
        '--public',
        '--description','System Monitor DORA + SOTA DevOps Hackathon: EKS, GitOps, progressive delivery, AI Ops, supply-chain security and DORA metrics',
        '--source',$publish,
        '--remote','origin',
        '--push'
    )

    Invoke-Checked $GitHubCli @(
        'repo','edit',$TargetRepository,
        '--add-topic','devops',
        '--add-topic','dora',
        '--add-topic','kubernetes',
        '--add-topic','gitops',
        '--add-topic','argo-rollouts',
        '--add-topic','devsecops',
        '--add-topic','observability',
        '--add-topic','aiops'
    )

    Write-Host ''
    Write-Host 'Hackathon repository created successfully:'
    Write-Host "https://github.com/$TargetRepository"
    Write-Host "Source commit: $sourceSha"
    Write-Host 'Visibility: PUBLIC'
}
finally {
    try { Invoke-Checked $GitExe @('-C',$repoRoot,'worktree','remove','--force',$worktree) } catch { }
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
