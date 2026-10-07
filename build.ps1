param([string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
Set-Location -LiteralPath $appRoot
$probeJson = & (Join-Path $appRoot 'check-runtime.ps1') -PythonPath $PythonPath
$probe = $probeJson | ConvertFrom-Json
$pythonPath = $probe.python
$buildHash = & $pythonPath -c "import server; print(server.source_hash())"
if ($LASTEXITCODE -ne 0) { throw 'Source identity could not be read.' }
$runtime = @{python=$pythonPath; build=$buildHash} | ConvertTo-Json
$compiler = $probe.compiler
New-Item -ItemType Directory -Path (Join-Path $appRoot 'bin') -Force | Out-Null
& $compiler /nologo /target:winexe /optimize+ /reference:System.Windows.Forms.dll /reference:System.Web.Extensions.dll /win32icon:"$appRoot\assets\App.ico" /out:"$appRoot\bin\ResearchDesktop.exe" "$appRoot\native\Launcher.cs"
if ($LASTEXITCODE -ne 0) { throw 'Desktop launcher compilation failed.' }
[IO.File]::WriteAllText((Join-Path $appRoot 'runtime.json'), $runtime, (New-Object Text.UTF8Encoding($false)))
Write-Output 'Built bin\ResearchDesktop.exe. Open Research.cmd starts the app.'
