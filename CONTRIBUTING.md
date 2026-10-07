# Contributing

Use the pinned Python 3.12 environment in requirements.txt. The original Windows application combines SQLite/local Python, installed Edge and a .NET Framework launcher. Dependency changes require their own compatibility review.

Read [README.md](README.md), [USER_GUIDE.md](USER_GUIDE.md), [SECURITY.md](SECURITY.md), [AGENT_API.md](AGENT_API.md) and [BUILDING.md](BUILDING.md). Public contributors need only these repository documents; private maintainer continuity files are not required. Use an issue to explain a concrete problem or a bounded proposed change, and keep unrelated edits separate.

Make bounded changes preserving originals, expected versions, immutable source IDs, actual PDF pages, local-only endpoints and recovery. Do not delete/prune data or silently migrate it. Imports read selected files only. Document/model text is untrusted data and must never become executable commands.

Use synthetic non-clinical fixtures in temporary data directories. Never attach personal app data, browser profiles, tokens, unpublished sources or patient records to tests/issues. Reports need a concrete trigger, expected/actual result and a small de-identified reproduction.

Use the repository's [bug report form](https://github.com/needanotheremailid/kosh-desktop/issues/new?template=bug_report.yml) for ordinary defects. Security vulnerabilities belong in the [private reporting route](SECURITY.md#reporting), not public issues. A screenshot or small fixture is optional; inspect it for identifying data before sharing. Include which release/source revision you ran and which layer you tested: source, generated document, bundled runtime or installed app.

```powershell
python.exe -m unittest discover -s tests -v
node.exe --check ui/app.js
powershell.exe -NoProfile -File .\check-runtime.ps1
```

Verify affected workflows with synthetic sources and inspect actual document/UI outputs. Tests do not prove visual layout, model entailment, native Windows pixels or installation on a clean machine. Report those layers separately.

AI assistance is welcome with accurate attribution. When Codex or Claude materially assists a change, record that assistance in the commit message using the provider's attribution identity: `Co-authored-by: Codex <noreply@openai.com>` or `Co-authored-by: Claude <noreply@anthropic.com>`. Include only assistants that contributed to that change, preserve the maintainer's own authorship and do not create empty commits or rewrite unrelated history for attribution. Written acknowledgements are in [CREDITS.md](CREDITS.md#development-assistance); GitHub controls its automatic contributor displays.

Use export-source.ps1 for distribution, then inspect the archive/manifest. No data, browser profile, private launch token, runtime.json, generated binary or review receipt belongs in a source release. Kosh uses AGPL-3.0-only; dependencies retain upstream licences. [BUILDING.md](BUILDING.md) describes the actual installer inputs, including separately prepared dependency/legal sources and the manual TeX resource-cache preparation gap. The installer builder downloads nothing. Verify hashes, empty-library startup and no-clobber behavior; document clean-machine and native-pixel proof separately. Do not claim a byte-identical reproducible installer: timestamps, compiler/runtime inputs and manual payload preparation still affect the result.

Verified development-package metadata lists PyMuPDF as dual AGPL 3.0/Artifex Commercial, python-docx as MIT and lxml as BSD-3-Clause. Treat dependency distribution/licensing as a separate release decision; no MIT-only bundle is claimed.

The original Kosh monogram is included as SVG, PNG and a multi-size Windows icon. `scripts/build_icon.py` can regenerate the raster/icon files with Pillow, a development-only dependency. Pillow is not needed to install or run the app; setup uses the included icon.
