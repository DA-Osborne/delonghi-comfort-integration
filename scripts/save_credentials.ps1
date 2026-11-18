<#
.SYNOPSIS
  Save the De'Longhi development credentials once, encrypted to your Windows account.

.DESCRIPTION
  Asks for your De'Longhi account email and password, then stores them with
  Export-Clixml. The password is encrypted with the Windows Data Protection API, so
  only your Windows account on this computer can decrypt it. Nothing is written to the
  repository or to OneDrive.

  To remove the credentials later, delete the file:
      Remove-Item "$env:LOCALAPPDATA\delonghi-comfort-dev\credentials.xml"

  Run it in your own PowerShell window:
      .\scripts\save_credentials.ps1
#>
param(
    [string]$Language = "en-au",
    [int]$DeviceIndex = 0,
    [string]$Path = (Join-Path $env:LOCALAPPDATA "delonghi-comfort-dev\credentials.xml")
)

New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
$credential = Get-Credential -Message "De'Longhi Comfort account. Enter the account email as the user name."
if (-not $credential) {
    Write-Error "Cancelled."
    return
}
@{ Credential = $credential; Language = $Language; DeviceIndex = $DeviceIndex } | Export-Clixml -Path $Path
Write-Host "Saved to $Path (encrypted for your Windows account)."
