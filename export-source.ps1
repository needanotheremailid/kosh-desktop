param([Parameter(Mandatory=$true)][string]$OutputZip)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$outputPath = [IO.Path]::GetFullPath($OutputZip)
if (Test-Path -LiteralPath $outputPath) { throw 'The release ZIP already exists. Choose a new output filename; nothing was overwritten.' }
$outputParent = Split-Path -Parent $outputPath
if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) { throw 'The release ZIP parent directory must already exist.' }
$files = @('backend.py','server.py','agent.py','literature.py','folder_edits.py','build.ps1','build-installer.ps1','check-runtime.ps1','setup.ps1','install-shortcuts.ps1','export-source.ps1','Open Research.cmd','Setup Research.cmd','requirements.txt','README.md','USER_GUIDE.md','FEATURES.md','CONTRIBUTING.md','SECURITY.md','AGENT_API.md','CREDITS.md','THIRD_PARTY.md','.gitignore','scripts/check_runtime.py','scripts/build_icon.py','scripts/build_installer.py')
foreach ($folder in @('native','ui','tests')) {
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $appRoot $folder) -File -Recurse) {
        if ($file.Extension -in @('.cs','.html','.css','.js','.py')) { $files += $file.FullName.Substring($appRoot.Length + 1).Replace('\','/') }
    }
}
$files += @('LICENSE', 'runtime-files.json', 'scripts/fetch_local_components.py', 'scripts/fetch_csl_components.py', 'scripts/fetch_tex_components.py', 'scripts/sign-release.ps1', 'SIGNING.md','vendor/tex/receipt.json','vendor/tex/LICENSE.tectonic')
foreach ($vendorFile in Get-ChildItem -LiteralPath (Join-Path $appRoot 'vendor\csl') -File -Recurse) {
    $files += $vendorFile.FullName.Substring($appRoot.Length + 1).Replace('\','/')
}
$runtimeFiles = Get-Content -LiteralPath (Join-Path $appRoot 'runtime-files.json') -Raw | ConvertFrom-Json
$files += 'BUILDING.md'
$files += 'scripts/release_smoke.py'
$files += $runtimeFiles
foreach ($asset in @('assets/App.ico','assets/Kosh.svg','assets/Kosh.png')) {
    if (Test-Path -LiteralPath (Join-Path $appRoot $asset) -PathType Leaf) { $files += $asset }
}
if (Test-Path -LiteralPath (Join-Path $appRoot 'assets/screenshots') -PathType Container) {
    foreach ($screenshot in Get-ChildItem -LiteralPath (Join-Path $appRoot 'assets/screenshots') -Filter '*.png' -File) {
        $files += $screenshot.FullName.Substring($appRoot.Length + 1).Replace('\','/')
    }
}
$files = @($files | Sort-Object -Unique)
$manifestFiles = @()
foreach ($relative in $files) {
    $sourcePath = Join-Path $appRoot $relative
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw ('Required source release file missing: ' + $relative) }
    $hashAlgorithm = [Security.Cryptography.SHA256]::Create()
    try { $sourceDigest = [BitConverter]::ToString($hashAlgorithm.ComputeHash([IO.File]::ReadAllBytes($sourcePath))).Replace('-','').ToLowerInvariant() } finally { $hashAlgorithm.Dispose() }
    $manifestFiles += [ordered]@{path=$relative; size=(Get-Item -LiteralPath $sourcePath).Length; sha256=$sourceDigest}
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stream = [IO.File]::Open($outputPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    $archive = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        foreach ($relative in $files) {
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, (Join-Path $appRoot $relative), $relative, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
        }
        $manifest = [ordered]@{format=1; kind='source-release'; generated_utc=[DateTime]::UtcNow.ToString('o'); includes_user_data=$false; requires_existing_runtime=$true; files=$manifestFiles} | ConvertTo-Json -Depth 5
        $entry = $archive.CreateEntry('release-manifest.json')
        $writer = New-Object IO.StreamWriter($entry.Open(), (New-Object Text.UTF8Encoding($false)))
        try { $writer.Write($manifest) } finally { $writer.Dispose() }
    } finally { $archive.Dispose() }
} finally { $stream.Dispose() }
Write-Output ('Created source-only release: ' + $outputPath)
Write-Output 'Excluded data, browser profile, local runtime paths, binaries, work, replica/review logs and continuity files. This is not a bundled installer.'
