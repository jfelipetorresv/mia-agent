[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SetupPath,
    [string]$LegacySetupPath = '',
    [Parameter(Mandatory)][string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module 'C:\MiaHarness\WindowsSandboxHarness.psm1' -Force
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$transcript = Join-Path $OutputDirectory 'guest-transcript.log'
Start-Transcript -LiteralPath $transcript -Force | Out-Null

$steps = New-Object System.Collections.Generic.List[object]
$failures = New-Object System.Collections.Generic.List[string]
$blockers = New-Object System.Collections.Generic.List[string]
$installedVersion = $null
$installDirectory = $null
$appExe = $null

function Add-Step {
    param([string]$Name, [string]$Outcome, [string]$Detail, [datetime]$Started)
    $steps.Add([ordered]@{
        name = $Name
        outcome = $Outcome
        detail = $Detail
        started_at = $Started.ToUniversalTime().ToString('o')
        finished_at = [datetime]::UtcNow.ToString('o')
        duration_ms = [math]::Round(([datetime]::UtcNow - $Started.ToUniversalTime()).TotalMilliseconds)
    })
    if ($Outcome -eq 'fail') { $failures.Add("$Name`:$Detail") }
    if ($Outcome -eq 'blocked') { $blockers.Add("$Name`:$Detail") }
}

function Invoke-ProcessChecked {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [int]$TimeoutSeconds = 900,
        [int[]]$AllowedExitCodes = @(0)
    )
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try { $process.Kill() } catch { }
        throw "timeout_${TimeoutSeconds}s:$([System.IO.Path]::GetFileName($FilePath))"
    }
    if ($AllowedExitCodes -notcontains $process.ExitCode) {
        throw "exit_$($process.ExitCode):$([System.IO.Path]::GetFileName($FilePath))"
    }
    return $process.ExitCode
}

function Get-MiaRegistration {
    $paths = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    foreach ($path in $paths) {
        $rows = @(Get-ItemProperty -Path $path -ErrorAction SilentlyContinue | Where-Object {
            $_.DisplayName -eq 'Mia' -or $_.DisplayName -like 'Mia *'
        })
        if ($rows) { return $rows[0] }
    }
    return $null
}

function Resolve-AppExe {
    param($Registration)
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($Registration.InstallLocation) { $candidates.Add((Join-Path $Registration.InstallLocation 'Mia.exe')) }
    if ($Registration.DisplayIcon) { $candidates.Add(([string]$Registration.DisplayIcon).Trim('"').Split(',')[0]) }
    $candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\Mia\Mia.exe'))
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Get-Item -LiteralPath $candidate).FullName
        }
    }
    return $null
}

function Wait-Health {
    param([int]$TimeoutSeconds = 900)
    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    $last = 'not_started'
    while ([datetime]::UtcNow -lt $deadline) {
        try {
            $backend = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 5
            $frontend = Invoke-WebRequest -Uri 'http://127.0.0.1:3100' -UseBasicParsing -TimeoutSec 5
            if ($backend.StatusCode -eq 200 -and $frontend.StatusCode -ge 200 -and $frontend.StatusCode -lt 500) {
                return [ordered]@{ backend = $backend.StatusCode; frontend = $frontend.StatusCode }
            }
        }
        catch { $last = $_.Exception.GetType().Name }
        Start-Sleep -Seconds 3
    }
    throw "health_timeout:$last"
}

function Stop-MiaTree {
    param([string]$Root)
    if (-not $Root) { return }
    $normalized = ([System.IO.Path]::GetFullPath($Root)).TrimEnd('\') + '\'
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($normalized, [System.StringComparison]::OrdinalIgnoreCase)
    })
    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 3
}

function Split-UninstallCommand {
    param([Parameter(Mandatory)][string]$Command)
    $trimmed = $Command.Trim()
    if ($trimmed.StartsWith('"')) {
        $match = [regex]::Match($trimmed, '^"(?<exe>[^"]+\.exe)"(?<args>.*)$')
    }
    else {
        $match = [regex]::Match($trimmed, '^(?<exe>.+?\.exe)(?<args>.*)$')
    }
    if (-not $match.Success) { throw 'uninstall_string_unparseable' }
    return [ordered]@{ exe = $match.Groups['exe'].Value; args = $match.Groups['args'].Value.Trim() }
}

function Find-BundledTool {
    param([string]$Root, [string]$Name)
    return Get-ChildItem -LiteralPath $Root -Filter $Name -File -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}

try {
    $started = [datetime]::UtcNow
    if (-not (Test-Path -LiteralPath $SetupPath -PathType Leaf)) { throw 'setup_missing' }
    $expectedVersion = (Get-MiaInstallerVersion $SetupPath).ToString()
    Add-Step 'setup_preflight' 'pass' "setup=$([System.IO.Path]::GetFileName($SetupPath));sha256=$((Get-FileHash $SetupPath -Algorithm SHA256).Hash.ToLowerInvariant())" $started

    $started = [datetime]::UtcNow
    Invoke-ProcessChecked -FilePath $SetupPath -ArgumentList @('/S') -TimeoutSeconds 900 | Out-Null
    $registration = Get-MiaRegistration
    if ($null -eq $registration) { throw 'installer_registry_entry_missing' }
    $installedVersion = [string]$registration.DisplayVersion
    if ($installedVersion -ne $expectedVersion) { throw "installed_version_mismatch:$installedVersion/$expectedVersion" }
    $appExe = Resolve-AppExe $registration
    if (-not $appExe) { throw 'installed_app_exe_missing' }
    $installDirectory = Split-Path $appExe -Parent
    Add-Step 'silent_install' 'pass' "version=$installedVersion" $started

    $started = [datetime]::UtcNow
    Start-Process -FilePath $appExe | Out-Null
    $health = Wait-Health -TimeoutSeconds 900
    $appData = Join-Path $env:LOCALAPPDATA 'Mia'
    foreach ($required in @('.mia-setup-complete','.env','pgdata\PG_VERSION')) {
        if (-not (Test-Path -LiteralPath (Join-Path $appData $required))) { throw "first_run_artifact_missing:$required" }
    }
    Add-Step 'first_health' 'pass' "backend=$($health.backend);frontend=$($health.frontend)" $started

    $started = [datetime]::UtcNow
    Stop-MiaTree $installDirectory
    Start-Process -FilePath $appExe | Out-Null
    $health = Wait-Health -TimeoutSeconds 300
    Add-Step 'restart_health' 'pass' "backend=$($health.backend);frontend=$($health.frontend)" $started

    $started = [datetime]::UtcNow
    $backendExe = Find-BundledTool $installDirectory 'mia-backend.exe'
    $pgBinTool = Find-BundledTool $installDirectory 'pg_dump.exe'
    if (-not $backendExe -or -not $pgBinTool) { throw 'maintenance_tools_missing' }
    $pgBin = Split-Path $pgBinTool -Parent
    $privateRecovery = Join-Path $env:TEMP 'mia-recovery-key.txt'
    Invoke-ProcessChecked $backendExe @('--maintenance','export-key','--pg-bin',$pgBin,'--pg-port','55432','--app-dir',$appData,'--destination',$privateRecovery) 300 | Out-Null
    Invoke-ProcessChecked $backendExe @('--maintenance','confirm-key','--pg-bin',$pgBin,'--pg-port','55432','--app-dir',$appData) 120 | Out-Null
    Remove-Item -LiteralPath $privateRecovery -Force -ErrorAction SilentlyContinue
    Invoke-ProcessChecked $backendExe @('--maintenance','backup','--pg-bin',$pgBin,'--pg-port','55432','--app-dir',$appData) 600 | Out-Null
    $backupDirectory = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Mia Backups'
    $latestBackup = Get-ChildItem -LiteralPath $backupDirectory -Filter '*.mia-backup' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latestBackup) { throw 'backup_file_missing' }
    Invoke-ProcessChecked $backendExe @('--maintenance','verify','--pg-bin',$pgBin,'--pg-port','55432','--app-dir',$appData,'--source',$latestBackup.FullName) 600 | Out-Null
    Add-Step 'backup_verify' 'pass' "backup=$($latestBackup.Name);bytes=$($latestBackup.Length)" $started

    $started = [datetime]::UtcNow
    $maintenanceHelp = & $backendExe --maintenance --help 2>&1 | Out-String
    if ($maintenanceHelp -notmatch '(?m)\brestore\b') {
        Add-Step 'restore' 'blocked' 'maintenance_cli_has_no_restore_action' $started
    }
    else {
        Add-Step 'restore' 'blocked' 'restore_action_present_but_no_non_destructive_target_contract' $started
    }

    $started = [datetime]::UtcNow
    if ($LegacySetupPath -and (Test-Path -LiteralPath $LegacySetupPath -PathType Leaf)) {
        $legacyVersion = Get-MiaInstallerVersion $LegacySetupPath
        $legacyBuiltAt = (Get-Item $LegacySetupPath).LastWriteTimeUtc
        $currentBuiltAt = (Get-Item $SetupPath).LastWriteTimeUtc
        $decision = Get-MiaUpgradeDecision -CurrentVersion $legacyVersion -CandidateVersion ([version]$expectedVersion) -CurrentBuiltAt $legacyBuiltAt -CandidateBuiltAt $currentBuiltAt
        if (-not $decision.allowed) {
            Add-Step 'upgrade' 'blocked' "$($decision.reason):legacy=$legacyVersion;current=$expectedVersion" $started
        }
        else {
            Add-Step 'upgrade' 'blocked' 'unexpected_upgrade_candidate_requires_separate_vm_baseline' $started
        }
    }
    else {
        Add-Step 'upgrade' 'blocked' 'legacy_setup_missing' $started
    }

    $started = [datetime]::UtcNow
    Stop-MiaTree $installDirectory
    Invoke-ProcessChecked -FilePath $SetupPath -ArgumentList @('/S') -TimeoutSeconds 900 | Out-Null
    $registration = Get-MiaRegistration
    if (-not $registration -or [string]$registration.DisplayVersion -ne $expectedVersion) { throw 'same_version_reinstall_failed' }
    $appExe = Resolve-AppExe $registration
    Start-Process -FilePath $appExe | Out-Null
    $health = Wait-Health -TimeoutSeconds 300
    Add-Step 'same_version_reinstall' 'pass' "backend=$($health.backend);frontend=$($health.frontend)" $started

    $started = [datetime]::UtcNow
    Stop-MiaTree $installDirectory
    $registration = Get-MiaRegistration
    if (-not $registration -or -not $registration.UninstallString) { throw 'uninstall_string_missing' }
    $uninstall = Split-UninstallCommand ([string]$registration.UninstallString)
    $arguments = @()
    if ($uninstall.args) { $arguments += $uninstall.args }
    $arguments += '/S'
    Invoke-ProcessChecked -FilePath $uninstall.exe -ArgumentList $arguments -TimeoutSeconds 600 | Out-Null
    Start-Sleep -Seconds 3
    if (Get-MiaRegistration) { throw 'uninstall_registry_residue' }
    if (Test-Path -LiteralPath $appExe -PathType Leaf) { throw 'uninstall_binary_residue' }
    Add-Step 'uninstall' 'pass' 'registry_and_main_binary_removed' $started

    $started = [datetime]::UtcNow
    $installResidue = @()
    if (Test-Path -LiteralPath $installDirectory) {
        $installResidue = @(Get-ChildItem -LiteralPath $installDirectory -Force -Recurse -ErrorAction SilentlyContinue | Select-Object -First 50 -ExpandProperty FullName)
    }
    $dataResidue = @()
    if (Test-Path -LiteralPath $appData) {
        $dataResidue = @(Get-ChildItem -LiteralPath $appData -Force -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
    }
    $listening = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in @(4000,55432,8000,3100) })
    if ($installResidue.Count -gt 0) { throw "unexpected_install_residue:$($installResidue.Count)" }
    if ($listening.Count -gt 0) { throw "listening_ports_after_uninstall:$($listening.LocalPort -join ',')" }
    Add-Step 'residue_audit' 'pass' "user_data_preserved=$($dataResidue.Count);install_residue=0;listeners=0" $started
}
catch {
    $failures.Add($_.Exception.Message)
}
finally {
    if ($installDirectory) { Stop-MiaTree $installDirectory }
    $outcome = if ($failures.Count -gt 0) { 'fail' } elseif ($blockers.Count -gt 0) { 'blocked' } else { 'pass' }
    $result = [ordered]@{
        schema_version = 'mia-windows-sandbox/v1'
        outcome = $outcome
        completed_at = [datetime]::UtcNow.ToString('o')
        installed_version = $installedVersion
        steps = @($steps)
        failures = @($failures)
        blockers = @($blockers)
        secrets_exported_to_host = $false
        upgrade_executed = $false
        restore_executed = $false
    }
    Write-JsonAtomic -Path (Join-Path $OutputDirectory 'result.json') -Value $result
    Stop-Transcript | Out-Null
    Start-Process -FilePath "$env:WINDIR\System32\shutdown.exe" -ArgumentList @('/s','/t','3') -WindowStyle Hidden | Out-Null
}
