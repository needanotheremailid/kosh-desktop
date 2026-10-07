param(
    [Parameter(Mandatory=$true)][string]$SourceZip,
    [Parameter(Mandatory=$true)][string]$OutputExe,
    [string]$PythonPath = '',
    [Parameter(Mandatory=$true)][string]$LegalDir,
    [Parameter(Mandatory=$true)][string]$ComponentsDir
)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
if (-not $PythonPath) { $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw 'Installed .NET Framework compiler is required; no download was attempted.' }
if (-not (Test-Path -LiteralPath $SourceZip -PathType Leaf)) { throw 'A verified source release ZIP is required.' }
if (-not (Test-Path -LiteralPath $LegalDir -PathType Container)) { throw 'The prepared legal source bundle directory is required.' }
$buildArgs = @('-E','-s',(Join-Path $appRoot 'scripts\build_installer.py'), '--source-zip', $SourceZip, '--output', $OutputExe, '--compiler', $compiler, '--legal-dir', $LegalDir, '--components-dir', $ComponentsDir)
& $PythonPath @buildArgs
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed. Existing app data and outputs were preserved.' }
Write-Output 'This build is unsigned. Use scripts/sign-release.ps1 with a validated publisher certificate to produce a separately verified signed copy. See SIGNING.md.'
