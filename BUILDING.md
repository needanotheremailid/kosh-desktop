# Building Kosh on Windows

This describes the maintained scripts and the manual inputs they require. It is a repeatable source/build procedure when the recorded inputs are available, **not a claim of byte-identical reproducible installers**. Build timestamps, the installed Python runtime, .NET compiler and prepared resource/legal payloads affect the output. No other-computer acceptance is implied.

This checkout targets **1.0.0-rc.4**. A release candidate is a package under verification, not a declaration of final 1.0 acceptance. Building or testing this source does not mean that its installer has been published. Check the actual GitHub release for available assets and its recorded checks. Signing remains pending; the builder produces an unsigned installer.

For a first contribution, start with a small source change and an invented fixture. Packaging the complete desktop runtime is a separate job with additional inputs; you do not need to assemble an installer to fix a typo or reproduce a narrowly scoped source bug.

## Source development

Use a separate writable checkout with synthetic test data. Requirements are 64-bit Windows 11, Microsoft Edge, the installed .NET Framework compiler, Python 3.12 and the pinned packages in [requirements.txt](requirements.txt). The installer builder copies the selected base Python installation, so a virtual environment alone is not a complete distribution runtime.

```powershell
Set-Location -LiteralPath 'C:\chosen\kosh'
python.exe -m pip install -r .\requirements.txt
powershell.exe -NoProfile -File .\check-runtime.ps1
powershell.exe -NoProfile -File .\build.ps1
```

The pip command is an explicit network/package installation step; use approved offline wheels instead when required. `build.ps1` checks the runtime, compiles `native/Launcher.cs` to `bin/ResearchDesktop.exe` and writes local `runtime.json`. Setup/build do not download packages. `setup.ps1 -PythonPath 'C:\chosen\python.exe'` can select an existing interpreter; Open Research.cmd launches the source app.

The citation runtime needs pinned local CSL/citeproc-js files and Node 24.14.1. `scripts/fetch_csl_components.py` is an explicit maintainer network action, never an app/setup hook. Review its full source/file list and the pins in `vendor/csl/components.json` before running it. It restores the recorded locale inventory, selected styles and matching Node binary/source archives into `tools/node` and `work/csl-components`. Ordinary exports do not download missing dependencies.

```powershell
python.exe -m unittest discover -s tests -v
node.exe --check ui/app.js
```

The full suite also needs its applicable local document/citation/compiler resources. Basic repository CI is a subset, not the complete Windows/installer/UI suite. Test in a separate data directory; inspect generated documents and the actual interface. Passing code tests does not prove pagination, scientific validity or installation elsewhere.

For the RC's component checks and local backup controls, run the closest checks first:

```powershell
python.exe -m unittest tests.test_installation_health tests.test_installation_health_ui tests.test_local_dialog tests.test_local_backup_jobs tests.test_local_backup_ui -v
node.exe --check ui/installation_health.js
node.exe --check ui/auto_backup.js
```

The UI tests use controlled DOM substitutes, and file-dialog tests substitute the chooser response. They check contracts, not whether a real Windows dialog is visible, receives keyboard focus, or returns a selected Unicode path. Compile `native/Launcher.cs` through `build.ps1`, then inspect those interactions in the actual desktop app when changing its dialog code. Keep the three layouts and their light/dark states in the verification plan.

`.github/workflows/checks.yml` checks syntax, compiles the native launcher, and exercises selected source/privacy/UI contracts on a hosted Windows runner. `.github/workflows/release-smoke.yml` is a separate, manually dispatched installed-package check. It needs the matching release assets to exist; it is not evidence that this RC is already published or that a different physical Windows 11 computer has been tested. If local resources are unavailable, report the skipped checks and why rather than describing a partial run as the full suite.

## Prepared installer inputs

`build-installer.ps1` requires all of the following already prepared. It downloads nothing:

| Input | Builder contract |
|---|---|
| Source ZIP | Produced by `export-source.ps1`; entry inventory/size/SHA-256 must match `release-manifest.json` and the source allowlist |
| Installed Windows Python 3.12 | Selected base interpreter, standard library/DLLs and exact package versions; bundled packages are read from that runtime's site-packages |
| `LegalDir` | Full `PyMuPDF-COPYING.txt`, six matching component source archives and `source-receipts.json` with package/version/file/bytes/SHA-256 |
| `ComponentsDir` | OCR `component-receipt.json`, English/Hindi/Punjabi traineddata and matching licence files; builder rechecks size/hash |
| CSL/Node payload | `vendor/csl/components.json`, exact local cited components/notices and matching Node source archive |
| TeX payload | `tools/tectonic/tectonic.exe`, `vendor/tex/kosh-tex.zip`, Tectonic licence/receipt, matching sources and historical resource-source audit under `work/tex-components` |
| .NET Framework compiler | Existing `%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe` |

See `scripts/build_installer.py` for exact filenames/version checks. The legal archive templates cover Python, PyMuPDF, MuPDF, python-docx, lxml and typing_extensions; source versions must match the copied runtime. Legal/source preparation is a separate maintainer task, not an automatic package download or licence certification. Release dependency-source assets and receipts are the reference inputs; do not substitute unrelated versions or fabricate matching hashes.

`scripts/fetch_local_components.py` prepares approved OCR files and receipts, but it also contacts the model registry/page in its normal path; `--pull-model` adds a local model pull. Inspect the exact arguments and network scope before use. Model weights are not an installer requirement or bundled payload. OCR upstream URLs may move; use the recorded receipt hashes to identify the actual release bytes rather than treating a current `main` URL as a timeless pin.

## Offline TeX preparation is partly manual

For rebuilding from released component bytes, use the offline donor recipe below; manual cache preparation is needed only when regenerating or changing the component set. The public [0.3.1 release](https://github.com/needanotheremailid/kosh-desktop/releases/tag/v0.3.1) provides the installer, application source and dependency-source assets. The installer contains the already prepared runtime/resources/receipts; the dependency-source asset supplies corresponding source material. This is reuse of verified released components, not rebuilding Python, Node, Tectonic or fonts from their upstream source.

That link and the 0.3.1 paths below are a retained reference recipe. For 1.0.0-rc.4, use the exact component receipts required by the selected RC source. An older installed donor is suitable only when its dependency/resource receipts match; its version number alone is not sufficient. Never copy its application `data` or browser profile into a build checkout.

The compiler is Tectonic 0.17.0. `vendor/tex/receipt.json` records the compiler binary/source archive hashes, official bundle URL/identity, selected resource filenames/hashes and payload inventory. The runtime only reads the bundled subset and never uses network package fallback.

`scripts/fetch_tex_components.py` **does not fetch or bootstrap Tectonic**. Despite its filename, it packages an already populated, approved isolated cache. A maintainer must first obtain the recorded compiler/source inputs, populate an isolated cache using a synthetic feature fixture against the recorded official bundle, and prepare matching historical TeX/LaTeX/font source and licence archives. That cache-population fixture and a one-command legal-source bootstrap are not maintained build scripts in this repository. Do not claim a clean checkout can recreate the exact resource subset automatically.

After those inputs are prepared and checked, the helper accepts:

```powershell
python.exe scripts\fetch_tex_components.py --cache 'C:\prepared\tectonic-cache' --output '.\vendor\tex' --binary-archive 'C:\prepared\tectonic-0.17.0-windows-msvc.zip' --source-archive 'C:\prepared\tectonic-0.17.0-source.tar.gz' --legal-input 'C:\prepared\tex-source-inputs'
```

The executable must already be present at `tools/tectonic/tectonic.exe`. The helper requires exactly one bundle index in `cache/bundles/data`, preserves selected resource bytes, uses stable ZIP entry dates and writes resource/payload receipts. Matching external source/licence coverage and `source-version-audit.json` must still be supplied for distribution. The installer builder refuses incomplete or mismatched TeX inventory. Consult [THIRD_PARTY.md](THIRD_PARTY.md) for the distribution boundary.

## Offline rebuild using a verified installed component donor

Install the matching 0.3.1 release into a separate folder without launching it or copying user data. Verify its installed manifest against the release verification material. Use a fresh source checkout from that same release and empty preparation directories. The donor and checkout must have matching `vendor/tex/receipt.json` and `vendor/csl/components.json`; do not pair an older resource subset with newer source receipts.

The paths below are examples to replace with your exact verified donor/checkout locations. Only runtime and dependency/legal components are copied: no `data`, browser profile, user documents, session capability or recovery tree. The installed layout supplies `legal/node-v24.14.1.tar.xz`, base component sources/receipts, `legal/tex/*`, `tessdata`, `licences`, `tools/node` and `tools/tectonic`.

```powershell
$donorInstall = 'C:\isolated\Kosh-0.3.1'
$buildCheckout = 'C:\chosen\kosh-desktop'
$preparedLegal = 'C:\prepared\kosh-legal'
$preparedOcr = 'C:\prepared\kosh-ocr'
foreach ($receiptRelative in @('vendor\tex\receipt.json','vendor\csl\components.json')) {
    $donorDigest = (Get-FileHash -LiteralPath (Join-Path $donorInstall $receiptRelative) -Algorithm SHA256).Hash
    $checkoutDigest = (Get-FileHash -LiteralPath (Join-Path $buildCheckout $receiptRelative) -Algorithm SHA256).Hash
    if ($donorDigest -ne $checkoutDigest) { throw 'Donor and source receipts differ; use matching release inputs.' }
}
foreach ($newDirectory in @($preparedLegal,$preparedOcr,(Join-Path $buildCheckout 'tools\node'),(Join-Path $buildCheckout 'tools\tectonic'),(Join-Path $buildCheckout 'work\csl-components'),(Join-Path $buildCheckout 'work\tex-components'))) {
    if (Test-Path -LiteralPath $newDirectory) { throw 'Use fresh, empty component destination paths; nothing was overwritten.' }
}
if (Test-Path -LiteralPath (Join-Path $buildCheckout 'vendor\tex\kosh-tex.zip')) { throw 'Use a fresh component destination; existing TeX ZIP was retained.' }
New-Item -ItemType Directory -Path $preparedLegal,$preparedOcr,(Join-Path $buildCheckout 'tools'),(Join-Path $buildCheckout 'work\csl-components'),(Join-Path $buildCheckout 'work\tex-components') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $donorInstall 'tools\node') -Destination (Join-Path $buildCheckout 'tools') -Recurse
Copy-Item -LiteralPath (Join-Path $donorInstall 'tools\tectonic') -Destination (Join-Path $buildCheckout 'tools') -Recurse
Copy-Item -LiteralPath (Join-Path $donorInstall 'vendor\tex\kosh-tex.zip') -Destination (Join-Path $buildCheckout 'vendor\tex\kosh-tex.zip')
Copy-Item -LiteralPath (Join-Path $donorInstall 'legal\node-v24.14.1.tar.xz') -Destination (Join-Path $buildCheckout 'work\csl-components')
Get-ChildItem -LiteralPath (Join-Path $donorInstall 'legal\tex') -File | Copy-Item -Destination (Join-Path $buildCheckout 'work\tex-components')
Get-ChildItem -LiteralPath (Join-Path $donorInstall 'legal') -File | Where-Object { $_.Name -notin @('node-v24.14.1.tar.xz','ocr-receipts.json') } | Copy-Item -Destination $preparedLegal
Copy-Item -LiteralPath (Join-Path $donorInstall 'tessdata') -Destination $preparedOcr -Recurse
Copy-Item -LiteralPath (Join-Path $donorInstall 'licences') -Destination $preparedOcr -Recurse
Copy-Item -LiteralPath (Join-Path $donorInstall 'legal\ocr-receipts.json') -Destination (Join-Path $preparedOcr 'component-receipt.json')
Set-Location -LiteralPath $buildCheckout
powershell.exe -NoProfile -File .\export-source.ps1 -OutputZip 'C:\existing\outputs\Kosh rebuilt source.zip'
powershell.exe -NoProfile -File .\build-installer.ps1 -SourceZip 'C:\existing\outputs\Kosh rebuilt source.zip' -OutputExe 'C:\existing\outputs\Kosh rebuilt Setup.exe' -PythonPath (Join-Path $donorInstall 'runtime\python.exe') -LegalDir $preparedLegal -ComponentsDir $preparedOcr
```

Using the donor's `runtime/python.exe` makes the builder copy its exact base runtime/package origins. Base legal archives, `source-receipts.json` and full `PyMuPDF-COPYING.txt` go into `LegalDir`; renamed OCR receipts and their two directories go into `ComponentsDir`. The builder revalidates source manifests, component sizes/hashes, versions and required source inventories. Matching bytes are a necessary input check, not licence certification or a claim of an identical installer binary. There is still no maintained from-scratch upstream compiler/resource build or automatic signing step.

## Create source ZIP and unsigned installer

Create the output directory beforehand. Use new output names; existing outputs are preserved/refused.

```powershell
powershell.exe -NoProfile -File .\export-source.ps1 -OutputZip 'C:\existing\outputs\Kosh source.zip'
powershell.exe -NoProfile -File .\build-installer.ps1 -SourceZip 'C:\existing\outputs\Kosh source.zip' -OutputExe 'C:\existing\outputs\Kosh Setup.exe' -PythonPath 'C:\chosen\Python312\python.exe' -LegalDir 'C:\prepared\legal' -ComponentsDir 'C:\prepared\local-components'
```

Source export includes allowlisted code/docs/assets/tests and a hash manifest. It excludes personal data, browser profiles, session tokens, local runtime paths, private review/continuity files and generated application binaries. The installer bundles application source, runtime, notices and corresponding dependency sources from the verified inputs. It is unsigned; an optional separately verified signed copy needs an existing trusted publisher identity via [SIGNING.md](SIGNING.md).

For the RC distribution, the updater expects the installer asset name `Kosh-1.0.0-rc.4-Setup.exe` and a matching entry in `SHA256SUMS.txt`. Local working artifacts may use other names. Checksum the exact final bytes after any separately approved signing operation; changing a filename or completing a build is not publication.

Before publishing, verify every archive/payload digest, no private data, included licence/source material, startup with an empty library, exported synthetic documents, no-clobber refusal and a fresh-install/upgrade workflow. Report source, packaged runtime, installed behavior, rendered output and clean-machine checks separately. Never upload a raw working installation folder.

## Keep build inputs separate from temporary work

Use a maintained checkout for source and a separate private location for verified component inputs and release receipts. Temporary task folders are disposable only after their needed contents have been identified and preserved. A successful upload does not establish that every local file is redundant.

Keep one verified current component donor, its matching licences and corresponding sources, the final release checksums, and the evidence needed to explain the release. Retain any explicitly required history-recovery backup privately. Check that a relocated donor still matches its manifest and that a moved Git checkout has the expected commit and clean working tree before deleting the old location.

Old test installations, intermediate installers, extracted duplicate components, generated fixtures and cache files can then be removed from exact inventoried paths. Stop the owned test processes first; reject links or paths that resolve outside the intended temporary directory. Preserve real libraries, browser recovery and previous personal installations. Save a small cleanup receipt and update the maintained instructions when paths change. A documentation-only maintenance commit does not require replacing an already verified release installer or moving its tag.
