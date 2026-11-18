<#
.SYNOPSIS
  Load the De'Longhi development credentials into environment variables.

.DESCRIPTION
  Reads an encrypted credential file (created once with save_credentials.ps1) and sets
  DELONGHI_USERNAME, DELONGHI_PASSWORD, DELONGHI_LANGUAGE and DELONGHI_DEVICE_INDEX for
  the current PowerShell session, so scripts/inspect_device.py and scripts/explorer.py
  need no prompts.

  The file is encrypted with the Windows Data Protection API, so only your Windows
  account on this computer can read it. It lives under %LOCALAPPDATA%, outside the
  repository and outside OneDrive.

  Use it by dot-sourcing, so the variables stay in your session:
      . .\scripts\load_credentials.ps1
#>
param(
    [string]$Path = (Join-Path $env:LOCALAPPDATA "delonghi-comfort-dev\credentials.xml")
)

if (-not (Test-Path $Path)) {
    Write-Error "No credential file at $Path. Run scripts\save_credentials.ps1 once to create it."
    return
}

$saved = Import-Clixml -Path $Path
$env:DELONGHI_USERNAME = $saved.Credential.UserName
$env:DELONGHI_PASSWORD = $saved.Credential.GetNetworkCredential().Password
$env:DELONGHI_LANGUAGE = if ($saved.Language) { $saved.Language } else { "en-au" }
$env:DELONGHI_DEVICE_INDEX = "$($saved.DeviceIndex)"
