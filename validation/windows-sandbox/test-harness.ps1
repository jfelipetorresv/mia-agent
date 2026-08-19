Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'WindowsSandboxHarness.psm1') -Force

$checks = New-Object System.Collections.Generic.List[object]
function Check([string]$Name, [bool]$Condition) {
    $checks.Add([pscustomobject]@{ Name = $Name; Passed = $Condition })
    Write-Host "$(if ($Condition) {'PASS'} else {'FAIL'}) $Name"
}

foreach ($script in @('run-host.ps1','guest-lifecycle.ps1','test-harness.ps1')) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $PSScriptRoot $script), [ref]$tokens, [ref]$errors)
    Check "sintaxis válida: $script" ($errors.Count -eq 0)
}

Check 'extrae versión canónica del setup' ((Get-MiaInstallerVersion 'Mia_0.1.0_x64-setup.exe').ToString() -eq '0.1.0')
$invalidRejected = $false
try { Get-MiaInstallerVersion 'setup.exe' | Out-Null } catch { $invalidRejected = $true }
Check 'rechaza setup sin versión canónica' $invalidRejected

$inverted = Get-MiaUpgradeDecision `
    -CurrentVersion ([version]'0.2.0') -CandidateVersion ([version]'0.1.0') `
    -CurrentBuiltAt ([datetime]'2026-08-12') -CandidateBuiltAt ([datetime]'2026-08-14')
Check '0.1.0 sobre 0.2.0 se bloquea como downgrade' (-not $inverted.allowed -and $inverted.operation -eq 'downgrade_blocked')

$fakeForward = Get-MiaUpgradeDecision `
    -CurrentVersion ([version]'0.1.0') -CandidateVersion ([version]'0.2.0') `
    -CurrentBuiltAt ([datetime]'2026-08-14') -CandidateBuiltAt ([datetime]'2026-08-12')
Check 'versión mayor con artefacto más viejo se bloquea' (-not $fakeForward.allowed -and $fakeForward.reason -eq 'version_chronology_inverted')

$validForward = Get-MiaUpgradeDecision `
    -CurrentVersion ([version]'0.1.0') -CandidateVersion ([version]'0.2.0') `
    -CurrentBuiltAt ([datetime]'2026-08-12') -CandidateBuiltAt ([datetime]'2026-08-14')
Check 'upgrade semántico y cronológico válido se permite' ($validForward.allowed -and $validForward.operation -eq 'upgrade')

$valid030 = Get-MiaUpgradeDecision -CurrentVersion ([version]'0.2.0') -CandidateVersion ([version]'0.3.0') -CurrentBuiltAt ([datetime]'2026-08-12') -CandidateBuiltAt ([datetime]'2026-08-14')
Check 'upgrade 0.2.0 a 0.3.0 válido se permite' ($valid030.allowed -and $valid030.operation -eq 'upgrade')

$reinstall = Get-MiaUpgradeDecision -CurrentVersion ([version]'0.1.0') -CandidateVersion ([version]'0.1.0')
Check 'reinstalación de versión idéntica se distingue de upgrade' ($reinstall.allowed -and $reinstall.operation -eq 'reinstall')

$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("mia-sandbox-test-" + [guid]::NewGuid().ToString('N'))
[System.IO.Directory]::CreateDirectory($temp) | Out-Null
try {
    $config = New-MiaSandboxConfig `
        -InstallerDirectory $temp -HarnessDirectory $temp -OutputDirectory $temp `
        -SetupName 'Mia_0.1.0_x64-setup.exe' -LegacySetupName 'Mia_0.2.0_x64-setup.exe'
    [xml]$xml = $config
    Check 'WSB es XML válido' ($xml.Configuration.MappedFolders.MappedFolder.Count -eq 3)
    Check 'instaladores y harness se mapean read-only' (
        $xml.Configuration.MappedFolders.MappedFolder[0].ReadOnly -eq 'true' -and
        $xml.Configuration.MappedFolders.MappedFolder[1].ReadOnly -eq 'true')
    Check 'salida es el único mapping escribible' ($xml.Configuration.MappedFolders.MappedFolder[2].ReadOnly -eq 'false')
    Check 'red y portapapeles quedan deshabilitados' (
        $xml.Configuration.Networking -eq 'Disable' -and $xml.Configuration.ClipboardRedirection -eq 'Disable')
    Check 'comando guest no contiene secretos' ($xml.OuterXml -notmatch '(?i)(api[_-]?key|password|token|secret)=')
}
finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}

$guest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'guest-lifecycle.ps1') -Raw
$hostScript = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'run-host.ps1') -Raw
Check 'setup vigente viene del release manifest, no de mtime' (
    $hostScript -match 'mia-release-manifest\.json' -and
    $hostScript -match 'installer\.sha256' -and
    $hostScript -match 'installer\.bytes' -and
    $hostScript -match 'rev-parse HEAD' -and
    $hostScript -notmatch 'Sort-Object LastWriteTime')
Check 'instalación y desinstalación usan modo silencioso' ($guest -match "ArgumentList @\('/S'\)" -and $guest -match "arguments \+= '/S'")
Check 'restore usa source y confirmación exacta de base' ($guest.Contains("'--source',`$latestBackup.FullName,'--confirm-database','mia'") -and $guest.Contains("'--confirm-database','wrong-name'"))
Check 'restore prueba centinela y safety backup antes de aprobar' ($guest -match 'restore_sentinel_mismatch' -and $guest -match 'restore_safety_backup_missing' -and $guest -match "Add-Step 'restore' 'pass'")
Check 'upgrade 0.2 a 0.3 instala ambas versiones y preserva centinela' ($guest -match 'Invoke-ProcessChecked \$LegacySetupPath' -and $guest -match 'upgrade_sentinel_mismatch' -and $guest -match "Add-Step 'upgrade' 'pass'")
Check 'resultados ejecutados dependen de gates reales' ($guest -match 'upgrade_executed = \$upgradeExecuted' -and $guest -match 'restore_executed = \$restoreExecuted')
Check 'gate exige health en primer arranque y reinicio' ($guest -match "Add-Step 'first_health' 'pass'" -and $guest -match "Add-Step 'restart_health' 'pass'")
$allLifecycleSteps = $true
foreach ($name in @('backup_verify','same_version_reinstall','uninstall','residue_audit')) {
    if (-not $guest.Contains("Add-Step '$name'")) { $allLifecycleSteps = $false }
}
Check 'gate audita backup, reinstalación, uninstall y residuos' $allLifecycleSteps

$failed = @($checks | Where-Object { -not $_.Passed })
Write-Host "`nRESULT: $($checks.Count - $failed.Count)/$($checks.Count) PASS"
if ($failed) { exit 1 }
exit 0
