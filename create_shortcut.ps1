param(
    [string]$Destination = ""
)

$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Destination) {
    $Destination = Join-Path $Project "启动 Codex 桌宠.lnk"
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($Destination)
$Shortcut.TargetPath = Join-Path $Project "run_pet.bat"
$Shortcut.WorkingDirectory = $Project
$Shortcut.IconLocation = (Join-Path $Project "assets\codex-pet.ico") + ",0"
$Shortcut.Description = "启动 Codex 桌宠"
$Shortcut.WindowStyle = 7
$Shortcut.Save()

Write-Host "Created shortcut: $Destination"


