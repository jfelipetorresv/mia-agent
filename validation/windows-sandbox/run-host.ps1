[CmdletBinding()]
param(
    [string]$SetupPath,
    [string]$LegacySetupPath,
    [string]$OutputRoot,
    [int]$TimeoutMinutes = 45,
    [switch]$PreflightOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$HarnessDirectory = $PSScriptRoot
Import-Module (Join-Path $HarnessDirectory 'WindowsSandboxHarness.psm1') -Force
$RepoRoot = Split-Path (Split-Path $HarnessDirectory -Parent) -Parent
$NsisDirectory = Join-Path $RepoRoot 'desktop\src-tauri\target\release\bundle\nsis'
$ReleaseManifestPath = Join-Path $NsisDirectory 'mia-release-manifest.json'
if (-not (Test-Path -LiteralPath $ReleaseManifestPath -PathType Leaf)) { throw 'Falta mia-release-manifest.json; no se selecciona setup por mtime ni versión arbitraria.' }
$ReleaseManifest = Get-Content -LiteralPath $ReleaseManifestPath -Raw | ConvertFrom-Json
if ($ReleaseManifest.schema_version -ne 1 -or $ReleaseManifest.product -ne 'Mia') { throw 'Release manifest incompatible.' }
if ([string]$ReleaseManifest.commit -notmatch '^[0-9a-f]{40}$') { throw 'Release manifest sin commit íntegro.' }
$CanonicalVersion = [version]$ReleaseManifest.version
$CanonicalSetupName = [string]$ReleaseManifest.installer.file
$CanonicalSetupPath = Join-Path $NsisDirectory $CanonicalSetupName
if (-not (Test-Path -LiteralPath $CanonicalSetupPath -PathType Leaf)) { throw "El setup declarado no existe: $CanonicalSetupName" }
$canonicalItem = Get-Item -LiteralPath $CanonicalSetupPath
$canonicalHash = (Get-FileHash -LiteralPath $CanonicalSetupPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($canonicalItem.Length -ne [long]$ReleaseManifest.installer.bytes -or
    $canonicalHash -ne ([string]$ReleaseManifest.installer.sha256).ToLowerInvariant()) {
    throw 'El setup vigente no coincide byte/hash con mia-release-manifest.json.'
}
$HeadCommit = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $HeadCommit -ne [string]$ReleaseManifest.commit) {
    throw "El release manifest pertenece a $($ReleaseManifest.commit), no al HEAD $HeadCommit."
}

function Resolve-SetupPath {
    param([string]$Explicit, [switch]$Legacy)
    if ($Explicit) {
        $item = Get-Item -LiteralPath $Explicit -ErrorAction Stop
        if ($item.Extension -ne '.exe') { throw "El setup debe ser .exe: $Explicit" }
        if (-not $Legacy -and
            ($item.Name -ne $CanonicalSetupName -or $item.FullName -ne $canonicalItem.FullName)) {
            throw "El setup explícito no es el declarado por mia-release-manifest.json: $($item.Name)."
        }
        if ($Legacy -and $item.Name -eq $CanonicalSetupName) {
            throw 'El setup legacy no puede ser el mismo artefacto vigente.'
        }
        return $item
    }
    $setups = @(Get-ChildItem -LiteralPath $NsisDirectory -Filter 'Mia_*_x64-setup.exe' -File -ErrorAction Stop)
    if (-not $setups) { throw "No hay setup actual en $NsisDirectory" }
    $rows = foreach ($item in $setups) {
        [pscustomobject]@{ Item = $item; Version = Get-MiaInstallerVersion $item.FullName; BuiltAt = $item.LastWriteTimeUtc }
    }
    if ($Legacy) {
        $legacyRows = @($rows | Where-Object { $_.Version -ne $CanonicalVersion })
        if (-not $legacyRows) { throw 'No existe un setup de versión distinta para auditar upgrade.' }
        return ($legacyRows | Sort-Object Version -Descending | Select-Object -First 1).Item
    }
    return $canonicalItem
}

$current = Resolve-SetupPath -Explicit $SetupPath
$legacy = Resolve-SetupPath -Explicit $LegacySetupPath -Legacy
$currentVersion = Get-MiaInstallerVersion $current.FullName
$legacyVersion = Get-MiaInstallerVersion $legacy.FullName
$upgradeDecision = Get-MiaUpgradeDecision `
    -CurrentVersion $legacyVersion -CandidateVersion $currentVersion `
    -CurrentBuiltAt $legacy.LastWriteTimeUtc -CandidateBuiltAt $current.LastWriteTimeUtc
$reinstallDecision = Get-MiaUpgradeDecision `
    -CurrentVersion $currentVersion -CandidateVersion $currentVersion `
    -CurrentBuiltAt $current.LastWriteTimeUtc -CandidateBuiltAt $current.LastWriteTimeUtc
$capability = Get-WindowsSandboxCapability

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot 'validation\windows-sandbox\runs'
}
$runId = 'sandbox-{0:yyyyMMdd-HHmmss}' -f [datetime]::Now
$output = Join-Path ([System.IO.Path]::GetFullPath($OutputRoot)) $runId
[System.IO.Directory]::CreateDirectory($output) | Out-Null

$manifest = [ordered]@{
    schema_version = 'mia-windows-sandbox/v1'
    run_id = $runId
    created_at = [datetime]::UtcNow.ToString('o')
    host = [ordered]@{
        os = [Environment]::OSVersion.VersionString
        machine = $env:COMPUTERNAME
        sandbox = $capability
    }
    current_setup = [ordered]@{
        name = $current.Name
        version = $currentVersion.ToString()
        bytes = $current.Length
        built_at = $current.LastWriteTimeUtc.ToString('o')
        sha256 = (Get-FileHash -LiteralPath $current.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    release_manifest = [ordered]@{
        file = 'mia-release-manifest.json'
        sha256 = (Get-FileHash -LiteralPath $ReleaseManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        commit = [string]$ReleaseManifest.commit
        head_commit = $HeadCommit
        installer_hash_verified = $true
        installer_size_verified = $true
    }
    legacy_setup = [ordered]@{
        name = $legacy.Name
        version = $legacyVersion.ToString()
        bytes = $legacy.Length
        built_at = $legacy.LastWriteTimeUtc.ToString('o')
        sha256 = (Get-FileHash -LiteralPath $legacy.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    upgrade_decision = $upgradeDecision
    reinstall_decision = $reinstallDecision
    expected_lifecycle = @('silent_install','first_health','restart_health','backup_verify','restore','same_version_reinstall','uninstall','residue_audit')
    security = [ordered]@{
        synthetic_only = $true
        secrets_passed = $false
        installer_mapping_read_only = $true
        harness_mapping_read_only = $true
        networking_disabled = $true
    }
}
Write-JsonAtomic -Path (Join-Path $output 'host-manifest.json') -Value $manifest

$config = New-MiaSandboxConfig `
    -InstallerDirectory $current.Directory.FullName `
    -HarnessDirectory $HarnessDirectory `
    -OutputDirectory $output `
    -SetupName $current.Name `
    -LegacySetupName $legacy.Name
$wsbPath = Join-Path $output 'mia-lifecycle.wsb'
$config | Set-Content -LiteralPath $wsbPath -Encoding UTF8

Write-Host "Manifest: $(Join-Path $output 'host-manifest.json')"
Write-Host "Setup vigente: $($current.Name) ($currentVersion)"
Write-Host "Setup anterior: $($legacy.Name) ($legacyVersion)"
if (-not $upgradeDecision.allowed) {
    Write-Warning "Upgrade bloqueado: $($upgradeDecision.reason). No se ejecutará como upgrade."
}
if ($PreflightOnly) {
    Write-Host 'Preflight solamente; no se lanzó Windows Sandbox.'
    exit 0
}
if (-not $capability.runnable) {
    Write-Error "Windows Sandbox no está disponible: $($capability.blockers -join ', ')"
}

$sandboxProcess = Start-Process -FilePath $capability.sandbox_exe -ArgumentList @("`"$wsbPath`"") -PassThru
$resultPath = Join-Path $output 'result.json'
$deadline = [datetime]::UtcNow.AddMinutes($TimeoutMinutes)
while ([datetime]::UtcNow -lt $deadline -and -not (Test-Path -LiteralPath $resultPath)) {
    Start-Sleep -Seconds 5
    if ($sandboxProcess.HasExited -and -not (Test-Path -LiteralPath $resultPath)) { break }
}
if (-not (Test-Path -LiteralPath $resultPath)) {
    $timeout = [ordered]@{
        schema_version = 'mia-windows-sandbox/v1'
        run_id = $runId
        outcome = 'blocked'
        blocker = if ($sandboxProcess.HasExited) { 'sandbox_closed_without_result' } else { 'sandbox_timeout' }
        sandbox_exit_code = if ($sandboxProcess.HasExited) { $sandboxProcess.ExitCode } else { $null }
        model_or_secret_activity = 'none'
        observed_at = [datetime]::UtcNow.ToString('o')
    }
    Write-JsonAtomic -Path (Join-Path $output 'host-failure.json') -Value $timeout
    throw "Sandbox no produjo result.json; ver $output"
}
$result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
Write-Host "Resultado Sandbox: $($result.outcome)"
Write-Host "Evidencia: $output"
if ($result.outcome -ne 'pass') { exit 2 }
exit 0
