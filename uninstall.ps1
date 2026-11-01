# Blackboard Sentinel - Windows Uninstaller
# Fully stops processes, removes autostart registrations, and wipes all configuration & state files

[CmdletBinding()]
param (
    [switch]$KeepConfig
)

$ErrorActionPreference = "Continue"

Write-Host "=========================================================="
Write-Host "       Blackboard Sentinel - Windows Uninstaller          "
Write-Host "=========================================================="
Write-Host ""

# 1. Stop running processes
Get-Process -Name "BlackboardSentinel" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name "pythonw" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "tray_app.py" -or $_.CommandLine -match "check_lms.py"
} | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "-> Stopped active processes."

# 2. Remove Startup and Start Menu Shortcuts
$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "BlackboardSentinel.lnk"
if (Test-Path $ShortcutPath) {
    Remove-Item -Path $ShortcutPath -Force
    Write-Host "-> Removed Startup shortcut."
}

$ProgramsFolder = [Environment]::GetFolderPath("Programs")
$StartMenuShortcut = Join-Path $ProgramsFolder "Blackboard Sentinel.lnk"
if (Test-Path $StartMenuShortcut) {
    Remove-Item -Path $StartMenuShortcut -Force
    Write-Host "-> Removed Start Menu shortcut."
}
$UninstShortcut = Join-Path $ProgramsFolder "Uninstall Blackboard Sentinel.lnk"
if (Test-Path $UninstShortcut) {
    Remove-Item -Path $UninstShortcut -Force
    Write-Host "-> Removed Start Menu uninstall shortcut."
}

# Remove Windows Add/Remove Programs registry entry
$RegKeyPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackboardSentinel"
if (Test-Path $RegKeyPath) {
    Remove-Item -Path $RegKeyPath -Recurse -Force
    Write-Host "-> Removed Windows Add/Remove Programs registry entry."
}

# Remove installed binary directory if installed via install.ps1
$InstalledAppDir = Join-Path $env:LOCALAPPDATA "Programs\BlackboardSentinel"
if (Test-Path $InstalledAppDir) {
    Remove-Item -Path $InstalledAppDir -Recurse -Force
    Write-Host "-> Removed installed application directory: $InstalledAppDir"
}

# 3. Unregister Scheduled Task
$TaskName = "BlackboardSentinel"
$TaskExists = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($TaskExists) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null
    Write-Host "-> Unregistered Scheduled Task '$TaskName'."
}

# 4. Wipe Configuration and State Files (unless -KeepConfig specified)
if (-not $KeepConfig) {
    $AppDataDir = Join-Path $env:APPDATA "BlackboardSentinel"
    if (Test-Path $AppDataDir) {
        Remove-Item -Path $AppDataDir -Recurse -Force
        Write-Host "-> Removed configuration directory: $AppDataDir"
    }

    $LocalAppDataDir = Join-Path $env:LOCALAPPDATA "BlackboardSentinel"
    if (Test-Path $LocalAppDataDir) {
        Remove-Item -Path $LocalAppDataDir -Recurse -Force
        Write-Host "-> Removed local app data: $LocalAppDataDir"
    }

    $LocalEnv = Join-Path $PSScriptRoot ".env"
    if (Test-Path $LocalEnv) {
        Remove-Item -Path $LocalEnv -Force
        Write-Host "-> Removed local configuration: $LocalEnv"
    }

    $StateFile = Join-Path $HOME ".hermes\state\lms_tracker_state.json"
    if (Test-Path $StateFile) {
        Remove-Item -Path $StateFile -Force
        Write-Host "-> Cleared tracker state cache: $StateFile"
    }
}

Write-Host ""
Write-Host "Blackboard Sentinel has been uninstalled successfully."
