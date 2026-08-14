Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-MiaInstallerVersion {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $name = [System.IO.Path]::GetFileName($Path)
    $match = [regex]::Match($name, '^Mia_(?<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)_x64-setup\.exe$')
    if (-not $match.Success) {
        throw "Nombre de setup no canónico: $name"
    }
    try {
        return [version]($match.Groups['version'].Value -replace '-.*$', '')
    }
    catch {
        throw "Versión inválida en el setup: $name"
    }
}

function Get-MiaUpgradeDecision {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][version]$CurrentVersion,
        [Parameter(Mandatory)][version]$CandidateVersion,
        [datetime]$CurrentBuiltAt = [datetime]::MinValue,
        [datetime]$CandidateBuiltAt = [datetime]::MinValue
    )

    if ($CandidateVersion -eq $CurrentVersion) {
        return [ordered]@{
            allowed = $true
            operation = 'reinstall'
            reason = 'same_version_reinstall'
        }
    }
    if ($CandidateVersion -lt $CurrentVersion) {
        return [ordered]@{
            allowed = $false
            operation = 'downgrade_blocked'
            reason = 'candidate_version_is_lower'
        }
    }
    if ($CandidateBuiltAt -ne [datetime]::MinValue -and
        $CurrentBuiltAt -ne [datetime]::MinValue -and
        $CandidateBuiltAt -lt $CurrentBuiltAt) {
        return [ordered]@{
            allowed = $false
            operation = 'upgrade_blocked'
            reason = 'version_chronology_inverted'
        }
    }
    return [ordered]@{
        allowed = $true
        operation = 'upgrade'
        reason = 'semver_and_chronology_valid'
    }
}

function Get-WindowsSandboxCapability {
    [CmdletBinding()]
    param()

    $sandboxExe = Join-Path $env:WINDIR 'System32\WindowsSandbox.exe'
    $vmcompute = Get-Service -Name 'vmcompute' -ErrorAction SilentlyContinue
    $cmservice = Get-Service -Name 'cmservice' -ErrorAction SilentlyContinue
    $hypervisor = $null
    try {
        $hypervisor = [bool](Get-CimInstance Win32_ComputerSystem -ErrorAction Stop).HypervisorPresent
    }
    catch {
        $hypervisor = $null
    }
    $reasons = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $sandboxExe -PathType Leaf)) { $reasons.Add('windows_sandbox_exe_missing') }
    if ($null -eq $vmcompute) { $reasons.Add('vmcompute_service_missing') }
    if ($null -eq $cmservice) { $reasons.Add('cmservice_missing') }
    if ($hypervisor -eq $false) { $reasons.Add('hypervisor_not_present') }
    return [ordered]@{
        runnable = ($reasons.Count -eq 0)
        sandbox_exe = if (Test-Path -LiteralPath $sandboxExe) { $sandboxExe } else { $null }
        vmcompute = if ($vmcompute) { [string]$vmcompute.Status } else { 'missing' }
        cmservice = if ($cmservice) { [string]$cmservice.Status } else { 'missing' }
        hypervisor_present = $hypervisor
        blockers = @($reasons)
        feature_state_note = 'La consulta DISM/Get-WindowsOptionalFeature requiere elevación; runnable se prueba al lanzar la VM.'
    }
}

function ConvertTo-XmlEscapedText {
    param([Parameter(Mandatory)][string]$Value)
    return [System.Security.SecurityElement]::Escape($Value)
}

function New-MiaSandboxConfig {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$InstallerDirectory,
        [Parameter(Mandatory)][string]$HarnessDirectory,
        [Parameter(Mandatory)][string]$OutputDirectory,
        [Parameter(Mandatory)][string]$SetupName,
        [string]$LegacySetupName = '',
        [int]$MemoryInMB = 8192
    )

    foreach ($path in @($InstallerDirectory, $HarnessDirectory, $OutputDirectory)) {
        if (-not [System.IO.Path]::IsPathRooted($path)) { throw "La ruta debe ser absoluta: $path" }
    }
    $installer = ConvertTo-XmlEscapedText ([System.IO.Path]::GetFullPath($InstallerDirectory))
    $harness = ConvertTo-XmlEscapedText ([System.IO.Path]::GetFullPath($HarnessDirectory))
    $output = ConvertTo-XmlEscapedText ([System.IO.Path]::GetFullPath($OutputDirectory))
    $setupArg = ConvertTo-XmlEscapedText $SetupName
    $legacyArg = ConvertTo-XmlEscapedText $LegacySetupName
    $command = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File C:\MiaHarness\guest-lifecycle.ps1 -SetupPath C:\MiaInstallers\$setupArg -LegacySetupPath C:\MiaInstallers\$legacyArg -OutputDirectory C:\MiaOutput"
    return @"
<Configuration>
  <MappedFolders>
    <MappedFolder><HostFolder>$installer</HostFolder><SandboxFolder>C:\MiaInstallers</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>$harness</HostFolder><SandboxFolder>C:\MiaHarness</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>$output</HostFolder><SandboxFolder>C:\MiaOutput</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
  </MappedFolders>
  <Networking>Disable</Networking>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <PrinterRedirection>Disable</PrinterRedirection>
  <AudioInput>Disable</AudioInput>
  <VideoInput>Disable</VideoInput>
  <MemoryInMB>$MemoryInMB</MemoryInMB>
  <LogonCommand><Command>$command</Command></LogonCommand>
</Configuration>
"@
}

function Write-JsonAtomic {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)]$Value,
        [int]$Depth = 12
    )
    $full = [System.IO.Path]::GetFullPath($Path)
    $directory = [System.IO.Path]::GetDirectoryName($full)
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    $temp = "$full.tmp"
    $Value | ConvertTo-Json -Depth $Depth | Set-Content -LiteralPath $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $full -Force
}

Export-ModuleMember -Function Get-MiaInstallerVersion,Get-MiaUpgradeDecision,Get-WindowsSandboxCapability,New-MiaSandboxConfig,Write-JsonAtomic
