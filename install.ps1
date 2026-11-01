# Blackboard Sentinel - Windows Installer
# Configures environment and registers startup launcher (Tray App or Task Scheduler)

[CmdletBinding()]
param (
    [ValidateSet("Tray", "Background", "Interactive")]
    [string]$Mode = "Interactive"
)

$ErrorActionPreference = "Stop"

Write-Host "=========================================================="
Write-Host "        Blackboard Sentinel - Windows Installer           "
Write-Host "=========================================================="
Write-Host ""

# 0. Gracefully close any running instances before updating files
Write-Host "Checking for active Blackboard Sentinel processes..."
$RunningProcesses = Get-Process -Name "BlackboardSentinel" -ErrorAction SilentlyContinue
if ($RunningProcesses) {
    Write-Host "-> Stopping running Blackboard Sentinel process for clean update..."
    $RunningProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
}
Get-Process -Name "pythonw" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "tray_app.py"
} | Stop-Process -Force -ErrorAction SilentlyContinue

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$EnvFile = Join-Path $ScriptDir ".env"
$IcoFile = Join-Path $ScriptDir "assets\icon_base.ico"

# 1. Check Python installation
$PythonExe = (Get-Command "python.exe" -ErrorAction SilentlyContinue).Source
$PythonwExe = (Get-Command "pythonw.exe" -ErrorAction SilentlyContinue).Source

if (-not $PythonExe) {
    Write-Error "Python 3 was not found in PATH. Please install Python 3.10+ and re-run."
    exit 1
}

if (-not $PythonwExe) {
    $PythonwExe = $PythonExe
}

# 2. Check and prompt for LMS credentials
$ExistingUrl = ""
$ExistingUser = ""
$ExistingDir = ""

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^LMS_URL=(.+)$') { $ExistingUrl = $matches[1].Trim('"''') }
        if ($_ -match '^LMS_USER_ID=(.+)$') { $ExistingUser = $matches[1].Trim('"''') }
        if ($_ -match '^LMS_STORAGE_DIR=(.+)$') { $ExistingDir = $matches[1].Trim('"''') }
    }
}

if (-not $ExistingUser) {
    Write-Host "Please enter your Blackboard portal configuration:"
    $LmsUrl = Read-Host "LMS Base URL (e.g. https://lms.university.edu)"
    while (-not $LmsUrl) {
        $LmsUrl = Read-Host "LMS Base URL cannot be empty. Please enter URL"
    }
    $LmsUrl = $LmsUrl.TrimEnd("/")

    $LmsUser = Read-Host "Username / Student ID"
    $LmsPass = Read-Host "Password" -AsSecureString
    $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($LmsPass)
    $PlainPass = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

    $DefaultStorage = Join-Path $HOME "Documents\University"
    $StorageInput = Read-Host "Course storage folder [default: $DefaultStorage]"
    if (-not $StorageInput) { $StorageInput = $DefaultStorage }

    # Save to .env
    $EnvContent = @"
# Blackboard Sentinel Configuration
LMS_URL="$LmsUrl"
LMS_USER_ID="$LmsUser"
LMS_PASSWORD="$PlainPass"
LMS_STORAGE_DIR="$StorageInput"
"@
    Set-Content -Path $EnvFile -Value $EnvContent -Encoding UTF8
    New-Item -ItemType Directory -Path $StorageInput -Force | Out-Null
    Write-Host "-> Saved credentials securely to $EnvFile"
} else {
    Write-Host "-> Found existing configuration for user: $ExistingUser"
}

# 3. Choose Installation Mode
if ($Mode -eq "Interactive") {
    Write-Host ""
    Write-Host "Select execution mode:"
    Write-Host "  [1] System Tray App (Runs at startup, icon in notification area near clock)"
    Write-Host "  [2] Headless Background Task (Windows Task Scheduler, zero RAM, silent)"
    $Choice = Read-Host "Choice (1 or 2) [default: 1]"
    if ($Choice -eq "2") {
        $Mode = "Background"
    } else {
        $Mode = "Tray"
    }
}

if ($Mode -eq "Tray") {
    Write-Host ""
    $PrebuiltExe = $null
    $CandidateExes = @(
        (Join-Path $ScriptDir "dist\BlackboardSentinel.exe"),
        (Join-Path $HOME "Downloads\BlackboardSentinel.exe")
    )
    foreach ($ce in $CandidateExes) {
        if (Test-Path $ce) {
            $PrebuiltExe = $ce
            break
        }
    }

    $StartupFolder = [Environment]::GetFolderPath("Startup")
    $ShortcutPath = Join-Path $StartupFolder "BlackboardSentinel.lnk"
    $ProgramsFolder = [Environment]::GetFolderPath("Programs")
    $StartMenuShortcut = Join-Path $ProgramsFolder "Blackboard Sentinel.lnk"
    $WshShell = New-Object -ComObject WScript.Shell

    if ($PrebuiltExe) {
        $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\BlackboardSentinel"
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        $InstalledExe = Join-Path $InstallDir "BlackboardSentinel.exe"
        Copy-Item -Path $PrebuiltExe -Destination $InstalledExe -Force
        Write-Host "-> Installed standalone application to: $InstalledExe"

        # Copy uninstall.exe if available
        $PrebuiltUninst = $null
        $CandidateUninst = @(
            (Join-Path $ScriptDir "dist\uninstall.exe"),
            (Join-Path $HOME "Downloads\uninstall.exe")
        )
        foreach ($cu in $CandidateUninst) {
            if (Test-Path $cu) {
                $PrebuiltUninst = $cu
                break
            }
        }
        $InstalledUninst = Join-Path $InstallDir "uninstall.exe"
        if ($PrebuiltUninst) {
            Copy-Item -Path $PrebuiltUninst -Destination $InstalledUninst -Force
            Write-Host "-> Installed uninstaller to: $InstalledUninst"
        }

        # 1. Startup Shortcut
        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $InstalledExe
        $Shortcut.WorkingDirectory = $InstallDir
        $Shortcut.Description = "Blackboard Sentinel Course Monitor"
        $Shortcut.Save()

        # 2. Start Menu Shortcut
        $MenuShortcut = $WshShell.CreateShortcut($StartMenuShortcut)
        $MenuShortcut.TargetPath = $InstalledExe
        $MenuShortcut.WorkingDirectory = $InstallDir
        $MenuShortcut.Description = "Blackboard Sentinel Course Monitor"
        $MenuShortcut.Save()

        # 3. Start Menu Uninstall Shortcut
        if (Test-Path $InstalledUninst) {
            $UninstShortcutPath = Join-Path $ProgramsFolder "Uninstall Blackboard Sentinel.lnk"
            $UninstShortcut = $WshShell.CreateShortcut($UninstShortcutPath)
            $UninstShortcut.TargetPath = $InstalledUninst
            $UninstShortcut.WorkingDirectory = $InstallDir
            $UninstShortcut.Description = "Uninstall Blackboard Sentinel"
            $UninstShortcut.Save()
        }

        # 4. Register in Windows Add/Remove Programs (Installed apps)
        $RegKeyPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackboardSentinel"
        New-Item -Path $RegKeyPath -Force | Out-Null
        Set-ItemProperty -Path $RegKeyPath -Name "DisplayName" -Value "Blackboard Sentinel"
        Set-ItemProperty -Path $RegKeyPath -Name "DisplayVersion" -Value "1.0.0"
        Set-ItemProperty -Path $RegKeyPath -Name "Publisher" -Value "Developer"
        Set-ItemProperty -Path $RegKeyPath -Name "InstallLocation" -Value $InstallDir
        Set-ItemProperty -Path $RegKeyPath -Name "DisplayIcon" -Value "$InstalledExe,0"
        if (Test-Path $InstalledUninst) {
            Set-ItemProperty -Path $RegKeyPath -Name "UninstallString" -Value "`"$InstalledUninst`""
            Set-ItemProperty -Path $RegKeyPath -Name "QuietUninstallString" -Value "`"$InstalledUninst`" --quiet"
        }
        Set-ItemProperty -Path $RegKeyPath -Name "NoModify" -Value 1 -Type DWord
        Set-ItemProperty -Path $RegKeyPath -Name "NoRepair" -Value 1 -Type DWord

        Write-Host "-> Created Windows Startup shortcut: $ShortcutPath"
        Write-Host "-> Created Start Menu shortcut: $StartMenuShortcut"
        Write-Host "-> Registered in Windows Add/Remove Programs."
        Write-Host "-> Blackboard Sentinel will launch automatically whenever you log into Windows."

        Write-Host ""
        $LaunchNow = Read-Host "Launch System Tray app right now? (Y/n)"
        if ($LaunchNow -ne "n" -and $LaunchNow -ne "N") {
            Start-Process -FilePath $InstalledExe -WorkingDirectory $InstallDir
            Write-Host "-> Launched Blackboard Sentinel in notification area."
        }
    } else {
        Write-Host "Installing dependencies for Python System Tray mode..."
        & $PythonExe -m pip install -q -r (Join-Path $ScriptDir "requirements.txt")

        if (-not (Test-Path $IcoFile)) {
            & $PythonExe (Join-Path $ScriptDir "scripts\generate_icon_png.py")
        }

        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $PythonwExe
        $Shortcut.Arguments = "`"$ScriptDir\tray_app.py`""
        $Shortcut.WorkingDirectory = $ScriptDir
        if (Test-Path $IcoFile) {
            $Shortcut.IconLocation = "$IcoFile,0"
        }
        $Shortcut.Description = "Blackboard Sentinel Course Monitor"
        $Shortcut.Save()

        Write-Host "-> Created Windows Startup shortcut: $ShortcutPath"
        Write-Host "-> Blackboard Sentinel will launch automatically whenever you log into Windows."

        Write-Host ""
        $LaunchNow = Read-Host "Launch System Tray app right now? (Y/n)"
        if ($LaunchNow -ne "n" -and $LaunchNow -ne "N") {
            Start-Process -FilePath $PythonwExe -ArgumentList "`"$ScriptDir\tray_app.py`"" -WorkingDirectory $ScriptDir
            Write-Host "-> Launched Blackboard Sentinel in notification area."
        }
    }
}
elseif ($Mode -eq "Background") {
    Write-Host ""
    Write-Host "Configuring Windows Task Scheduler for headless execution..."
    
    $TaskName = "BlackboardSentinel"
    $Action = New-ScheduledTaskAction -Execute $PythonwExe -Argument "`"$ScriptDir\check_lms.py`"" -WorkingDirectory $ScriptDir
    $Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    # Unregister existing task if already present
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Blackboard Sentinel Hourly LMS Monitor" | Out-Null

    Write-Host "-> Registered Scheduled Task '$TaskName' to run hourly in the background."
}

Write-Host ""
Write-Host "Installation complete! Blackboard Sentinel is fully configured."
