param([string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
if (-not $PythonPath) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) { $PythonPath = $pythonCommand.Source }
    if (-not $PythonPath) {
        $pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($pythonLauncher) {
            $PythonPath = & $pythonLauncher.Source -3.12 -c 'import sys; print(sys.executable)'
            if ($LASTEXITCODE -ne 0) { $PythonPath = '' }
        }
    }
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw 'Python 3.12 was not found. Install Python 3.12 separately or pass -PythonPath to its existing python.exe. No download was attempted.'
}
$runtimeJson = & $PythonPath (Join-Path $appRoot 'scripts\check_runtime.py')
$runtimeExit = $LASTEXITCODE
try { $runtimeProbe = $runtimeJson | ConvertFrom-Json } catch { throw 'Python prerequisite probe returned invalid output.' }
if ($runtimeExit -ne 0 -or -not $runtimeProbe.ok) {
    throw (($runtimeProbe.errors -join [Environment]::NewLine) + [Environment]::NewLine + 'Install the pinned requirements only when you choose to do so, then rerun setup. No download was attempted.')
}
$edgePath = ''
foreach ($basePath in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, $env:LOCALAPPDATA)) {
    if ($basePath) {
        $candidatePath = Join-Path $basePath 'Microsoft\Edge\Application\msedge.exe'
        if (Test-Path -LiteralPath $candidatePath -PathType Leaf) { $edgePath = $candidatePath; break }
    }
}
if (-not $edgePath) { throw 'Microsoft Edge is required and was not found. Install it separately; no browser download was attempted.' }
$compilerPath = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compilerPath -PathType Leaf)) { $compilerPath = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }
if (-not (Test-Path -LiteralPath $compilerPath -PathType Leaf)) { throw 'The Windows .NET Framework compiler is unavailable. No installer was run.' }
[pscustomobject]@{python=$runtimeProbe.python; python_version=$runtimeProbe.python_version; packages=$runtimeProbe.packages; edge=$edgePath; compiler=$compilerPath} | ConvertTo-Json -Depth 4
