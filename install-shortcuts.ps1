param(
    [Parameter(Mandatory=$true)][string]$AppName,
    [ValidateSet('Both','Desktop','StartMenu')][string]$Location = 'Both',
    [switch]$ReplaceMatching
)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
if (-not $AppName.Trim() -or $AppName.Length -gt 80 -or $AppName.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or $AppName -match '[\. ]$') { throw 'Choose a plain application name without reserved filename characters.' }
$targetPath = Join-Path $appRoot 'bin\ResearchDesktop.exe'
if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) { throw 'Run setup.ps1 first. The compiled desktop launcher is missing.' }
$destinations = @()
if ($Location -eq 'Both' -or $Location -eq 'Desktop') { $destinations += Join-Path ([Environment]::GetFolderPath('Desktop')) ($AppName + '.lnk') }
if ($Location -eq 'Both' -or $Location -eq 'StartMenu') { $destinations += Join-Path (Join-Path ([Environment]::GetFolderPath('Programs')) $AppName) ($AppName + '.lnk') }
$shell = New-Object -ComObject WScript.Shell
foreach ($shortcutPath in $destinations) {
    if (Test-Path -LiteralPath $shortcutPath) {
        $existing = $shell.CreateShortcut($shortcutPath)
        if (-not $ReplaceMatching -or $existing.TargetPath -ne $targetPath) { throw ('Shortcut already exists and was preserved: ' + $shortcutPath + '. -ReplaceMatching permits replacing only a shortcut already targeting this app.') }
    }
}
foreach ($shortcutPath in $destinations) {
    [IO.Directory]::CreateDirectory((Split-Path -Parent $shortcutPath)) | Out-Null
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetPath
    $shortcut.WorkingDirectory = $appRoot
    $shortcut.Description = $AppName + ' - local research workspace'
    $iconPath = Join-Path $appRoot 'assets\App.ico'
    if (Test-Path -LiteralPath $iconPath -PathType Leaf) { $shortcut.IconLocation = $iconPath + ',0' } else { $shortcut.IconLocation = $targetPath + ',0' }
    $shortcut.Save()
    Write-Output ('Created shortcut: ' + $shortcutPath)
}
