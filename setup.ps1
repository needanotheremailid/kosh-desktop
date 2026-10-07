param([string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
Write-Output 'Checking existing local prerequisites. Setup does not install or download software.'
$probeJson = & (Join-Path $appRoot 'check-runtime.ps1') -PythonPath $PythonPath
$probe = $probeJson | ConvertFrom-Json
& (Join-Path $appRoot 'build.ps1') -PythonPath $probe.python
Write-Output 'Setup complete. Open Research.cmd launches the app; no sample records were created.'
Write-Output 'To add Desktop and Start menu entries, run install-shortcuts.ps1 with your chosen application name.'
