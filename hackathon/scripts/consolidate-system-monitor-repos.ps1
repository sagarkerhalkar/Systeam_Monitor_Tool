param(
    [string]$PrimaryRepository = 'sagarkerhalkar/Systeam_Monitor_Tool',
    [string]$HackathonRepository = 'sagarkerhalkar/System-Monitor-DORA-SOTA-Hackathon',
    [string]$LegacyRepository = 'sagarkerhalkar/SagarSystemHealthMonitor-V10',
    [string]$PrivateStagingRepository = 'sagarkerhalkar/Systeam_Monitor_Tool_Staging_Private',
    [string]$ExpectedWorkingCode = '9a0d02699cb4664e8bae98cffa1a368a1e15182e',
    [string]$ExpectedCommercial = '4d99c3a3dd2b9d09a1a699673655e287bf886b3f',
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ArchiveDate = '20260810'

function Run {
    param([string]$File, [string[]]$Arguments, [string]$WorkingDirectory = '')
    $old = Get-Location
    try {
        if ($WorkingDirectory) { Set-Location -LiteralPath $WorkingDirectory }
        & $File @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Command failed: $File $($Arguments -join ' ')" }
    }
    finally { Set-Location $old }
}

function Repo-Visibility([string]$Repository) {
    $json = & gh repo view $Repository --json visibility,nameWithOwner 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Cannot access repository: $Repository" }
    return ($json | ConvertFrom-Json).visibility.ToUpperInvariant()
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI is required.' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required.' }
Run gh @('auth','status','--hostname','github.com')

$primaryVisibility = Repo-Visibility $PrimaryRepository
$hackVisibility = Repo-Visibility $HackathonRepository
$legacyVisibility = Repo-Visibility $LegacyRepository
$stagingVisibility = Repo-Visibility $PrivateStagingRepository

if ($primaryVisibility -ne 'PUBLIC') { throw "$PrimaryRepository must remain PUBLIC." }
if ($hackVisibility -ne 'PUBLIC') { throw "$HackathonRepository must be PUBLIC before consolidation." }
if ($stagingVisibility -ne 'PRIVATE') { throw "$PrivateStagingRepository must remain PRIVATE." }

$temp = Join-Path ([IO.Path]::GetTempPath()) ('sagar-monitor-consolidate-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -Force | Out-Null

try {
    $clone = Join-Path $temp 'primary'
    Run gh @('repo','clone',$PrimaryRepository,$clone)
    Run git @('fetch','origin','--prune') $clone

    $workingSha = (& git -C $clone rev-parse 'origin/workingcode').Trim()
    $commercialSha = (& git -C $clone rev-parse 'origin/commercial-v1').Trim()
    if ($workingSha -ne $ExpectedWorkingCode) {
        throw "workingcode changed. Expected $ExpectedWorkingCode, found $workingSha"
    }
    if ($commercialSha -ne $ExpectedCommercial) {
        throw "commercial-v1 changed. Expected $ExpectedCommercial, found $commercialSha"
    }

    $legacyUrl = "https://github.com/$LegacyRepository.git"
    Run git @('remote','add','legacy',$legacyUrl) $clone
    Run git @('fetch','legacy','--prune') $clone

    $branches = @(
        & git -C $clone for-each-ref '--format=%(refname:short)' 'refs/remotes/origin/' |
            Where-Object { $_ -and $_ -ne 'origin/HEAD' } |
            ForEach-Object { $_ -replace '^origin/','' } |
            Where-Object { $_ -notin @('workingcode','commercial-v1') }
    )
    $legacyBranches = @(
        & git -C $clone for-each-ref '--format=%(refname:short)' 'refs/remotes/legacy/' |
            Where-Object { $_ } |
            ForEach-Object { $_ -replace '^legacy/','' }
    )

    Write-Host ''
    Write-Host '=== CONSOLIDATION PLAN ==='
    Write-Host "Primary public repo:   $PrimaryRepository"
    Write-Host "  keep branch workingcode   $workingSha"
    Write-Host "  keep branch commercial-v1 $commercialSha"
    Write-Host "Hackathon public repo: $HackathonRepository"
    Write-Host "Private staging:       $PrivateStagingRepository ($stagingVisibility)"
    Write-Host "Legacy repo:           $LegacyRepository ($legacyVisibility -> PRIVATE)"
    Write-Host ''
    Write-Host "Primary branches to archive as tags then remove: $($branches.Count)"
    $branches | ForEach-Object { Write-Host "  $_" }
    Write-Host "Legacy branches to preserve as tags: $($legacyBranches.Count)"
    $legacyBranches | ForEach-Object { Write-Host "  $_" }

    if (-not $Apply) {
        Write-Host ''
        Write-Host 'DRY RUN ONLY. Nothing changed.'
        Write-Host 'Re-run with -Apply after reviewing this plan.'
        exit 0
    }

    foreach ($branch in $branches) {
        $tag = "archive/primary/$branch-$ArchiveDate"
        $ref = "refs/remotes/origin/$branch"
        Run git @('tag','-a',$tag,$ref,'-m',"Archived branch $branch before two-branch consolidation on $ArchiveDate") $clone
        Run git @('push','origin',"refs/tags/$tag") $clone
    }

    foreach ($branch in $legacyBranches) {
        $tag = "archive/legacy-v10/$branch-$ArchiveDate"
        $ref = "refs/remotes/legacy/$branch"
        Run git @('tag','-a',$tag,$ref,'-m',"Preserved $LegacyRepository branch $branch before repository consolidation") $clone
        Run git @('push','origin',"refs/tags/$tag") $clone
    }

    Run gh @('repo','edit',$PrimaryRepository,'--default-branch','workingcode')

    foreach ($branch in $branches) {
        Run git @('push','origin','--delete',$branch) $clone
    }

    if ((Repo-Visibility $LegacyRepository) -eq 'PUBLIC') {
        Run gh @('repo','edit',$LegacyRepository,'--visibility','private','--accept-visibility-change-consequences')
    }

    $finalPrimary = Repo-Visibility $PrimaryRepository
    $finalHack = Repo-Visibility $HackathonRepository
    $finalLegacy = Repo-Visibility $LegacyRepository
    $finalStaging = Repo-Visibility $PrivateStagingRepository
    if ($finalPrimary -ne 'PUBLIC' -or $finalHack -ne 'PUBLIC') {
        throw 'Final public repository visibility verification failed.'
    }
    if ($finalLegacy -ne 'PRIVATE' -or $finalStaging -ne 'PRIVATE') {
        throw 'Final private repository visibility verification failed.'
    }

    $remaining = @(
        & git -C $clone ls-remote --heads origin |
            ForEach-Object { ($_ -split '\s+')[1] -replace '^refs/heads/','' }
    )
    $unexpected = @($remaining | Where-Object { $_ -notin @('workingcode','commercial-v1') })
    if ($unexpected.Count -gt 0) {
        throw "Unexpected public branches remain: $($unexpected -join ', ')"
    }

    Write-Host ''
    Write-Host 'CONSOLIDATION COMPLETE'
    Write-Host 'Public System Monitor repositories:'
    Write-Host "  https://github.com/$PrimaryRepository"
    Write-Host "  https://github.com/$HackathonRepository"
    Write-Host 'Primary branches:'
    Write-Host '  workingcode'
    Write-Host '  commercial-v1'
    Write-Host 'Legacy and staging repositories are private; removed branch history is preserved as archive/* tags.'
}
finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
