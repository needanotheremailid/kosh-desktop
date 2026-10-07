# Kosh

A local research desk for Windows: read selected sources, keep linked notes, write manuscripts, review writing proposals and export work you can take elsewhere. The normal library starts empty. Kosh combines original application code with the attributed local citation processor, styles and runtimes described in [CREDITS.md](CREDITS.md).

**[Download Kosh 0.3.0 Windows beta installer](https://github.com/needanotheremailid/kosh-desktop/releases/download/v0.3.0/Kosh-0.3.0-final-Setup.exe)** · [Release notes and assets](https://github.com/needanotheremailid/kosh-desktop/releases/tag/v0.3.0) · [User guide](USER_GUIDE.md)

## Install and try one paper

1. Download the installer above. Requirements: **64-bit Windows 11, Microsoft Edge and .NET Framework**. Python, document libraries, Node, OCR data and offline TeX resources are bundled; no separate Python/Node/TeX installation is needed.
2. Install into a new writable folder for your Windows user. Administrator access and install-time package downloads are not required. Preserve an existing installation when upgrading; use the [copy-only upgrade guide](USER_GUIDE.md#upgrade-a-bundled-installation).
3. Open the Kosh shortcut. Create a workspace and import one trusted paper you have permission to use. Read the import receipt.
4. Open Read, select a passage and save a source-linked note. In Write, save a short draft, then export it to Word or PDF.

**Unsigned beta:** the installer has no trusted publisher signature. Windows may warn about an unknown publisher. Check its repository release origin and compare SHA-256 with the release verification material before deciding whether to run it. Keep backups and start with non-sensitive material. Testing on the maintainer's computer is not evidence for every Windows computer.

Reading, saving, lexical search, citations, export and backup work without AI. OCR runs locally when language data is available. Semantic search uses an explicitly selected installed local embedding model. Approved Codex/Claude requests may use provider cloud services; discovery sends your submitted query/identifier to the chosen index. Kosh has no account, telemetry, cloud sync or public tunnel.

**AI is optional and provider use is not included in a free Kosh download.** Codex/Claude assistance needs a supported installed CLI, your authenticated account and provider access; subscriptions, limits and charges are your responsibility. Previewed Kosh content may reach that provider, and its CLI can add instructions/environment metadata. Detection is not sign-in or model-readiness proof. Local AI/semantic search needs separately installed Ollama, a suitable model and sufficient hardware; Kosh downloads no weights. Source excerpts work without generation. Discover sends only the query/identifier you submit. Official CSL retrieval requires explicit consent for named files/dependencies; ordinary export and local import work offline.

## Source edition

Most users should use the installer above. Developers can follow [BUILDING.md](BUILDING.md) for the source edition and installer prerequisites. The capabilities below describe 0.3.0; an existing older installation retains its previous behavior until upgraded. A successful build or a test on one computer is not clean-machine acceptance. Optional signing requires an already provisioned trusted publisher identity; see [SIGNING.md](SIGNING.md).

The source edition needs Python 3.12, Edge, the pinned versions in [requirements.txt](requirements.txt), and the local Node.js 24.14.1 citation runtime:

1. Extract into a stable writable folder; do not run inside the ZIP.
2. Check/install prerequisites separately. `check-runtime.ps1` checks the configured environment.
3. Run **Setup Research.cmd**, then **Open Research.cmd**. Setup uses the existing .NET Framework compiler and downloads no packages/models.
4. Create a workspace, import a permitted source, read a passage, save a linked note and export it.

If you explicitly choose to install missing source-edition libraries, this separate command may download packages:

```powershell
python.exe -m pip install -r .\requirements.txt
```

Use an approved offline wheel source when needed. A Python outside PATH can be selected with `setup.ps1 -PythonPath 'C:\chosen\python.exe'`.

Citation formatting uses `tools/node/node.exe` when included; the development fallback is an already installed `C:\Program Files\nodejs\node.exe`. Use the matching Node version recorded in [vendor/csl/components.json](vendor/csl/components.json). If components are missing, a maintainer can run `scripts/fetch_csl_components.py` only after explicit approval of its pinned source/file list. The app, setup and installer never run this download helper automatically.

```powershell
powershell.exe -NoProfile -File .\install-shortcuts.ps1 -AppName 'Kosh'
```

The shortcut helper preserves existing links unless explicit matching-target replacement is requested.

## What you can do

- Import/read managed source copies and exact passages; preview multi-record bibliographies and validated figure assets.
- Draft Markdown with source context, outlines, figures, tables, limited equations, save/conflict recovery and history.
- Format citations offline with citeproc-js, pinned Vancouver/NLM, APA 7, IEEE and Chicago note styles, 63 bundled CSL language locales, or local imported styles/locales. Choose footnotes/endnotes for note styles. Missing official parent styles/locales require explicit approved retrieval; ordinary exports never fetch them.
- Ask sources or request continue/grammar/translate/abstract/clarity/shorten/outline/critique/extraction proposals. Review the preview/result, then save an alternative or explicitly apply an eligible selection.
- Search four indexes individually or together, look up a DOI/PMID, save catalogue metadata and attach it to a separately imported paper.
- Create local OCR derivatives and explicitly index/search concepts with an installed embedding model.
- Export static CSL Word/PDF, or editable native Word citation/bibliography fields with document-local sources. Configure research/review/case-report layouts, or compile generated LaTeX to PDF with bundled offline Tectonic. Markdown, bibliography data, evidence CSV, HTML and figure-bearing reading/TeX ZIPs remain available.
- Keep Broadsheet, Stacks and Commonplace, light/dark appearance, optional hover explanations and reopenable Getting started/Help.

[USER_GUIDE.md](USER_GUIDE.md) covers the complete workflow. [FEATURES.md](FEATURES.md) retains the workflow coverage ledger without a product-equivalence claim. [AGENT_API.md](AGENT_API.md) documents the fixed CLI and **50 local MCP tools**. No client configuration is changed automatically.

The screenshots below show the actual current interface with synthetic, non-sensitive content.

![Kosh writing view with a synthetic draft](assets/screenshots/kosh-writing.png)

![Kosh manuscript layout and citation options](assets/screenshots/kosh-export-options.png)

## Sharing, backup and upgrade

| Goal | Use | Contents |
|---|---|---|
| Give someone the software | Verified installer/source release | Application/runtime/notices; no personal research/model weights |
| Give someone a readable manuscript | HTML or portable reading ZIP | Manuscript/references and selected figures; no restorable database |
| Transfer a research workspace | Validated workspace ZIP | Managed originals/current records; optional history; fresh-workspace restore |
| Move complete local state to a fresh installation | Stopped copy using `upgrade.py` | Originals, database/revisions, Edge/browser recovery and folder-edit recovery |

Review exports before sharing. Export does not redact identifiers or verify scientific claims. Workspace ZIPs are unencrypted and exclude unsaved browser drafts, Edge profile, external-folder recovery, the separate assistance-job/result journal and rebuildable embedding cache. A stopped complete data-copy upgrade preserves that local state.

For an upgrade, quit both apps/browser profiles. Install the new edition **without launching**, leaving its `data` directory absent. `upgrade.py` defaults to a dry-run, verifies both packages, copies stopped data into staging, checks hashes/SQLite logical contents and publishes without clobbering. It retains the old installation/recovery material. Optional shortcut retargeting only changes exact old-launcher targets. See the guide for commands and partial-failure handling.

## Optional local components

OCR uses local English/Hindi/Punjabi data (`eng`, `hin`, `pan`), preferring bundled `tessdata/` when supplied by the verified release, otherwise supported local Tesseract data. Clicking OCR downloads nothing and creates a separately mapped derivative.

Semantic retrieval needs a separately installed embedding-capable Ollama model. The capability check assesses `nomic-embed-text:latest` when present. Inventory, declared capability and successful current execution are distinct states. Kosh downloads no weights and uses no cloud embedding fallback. Install optional components only through an explicitly chosen process. Final package receipts determine the OCR data/notices actually included.

## Data, distribution and development

`data/` is inside the installation. Originals are immutable managed copies; archive is reversible. Exact-byte reimport repairs a missing original while retaining its ID/notes; changed originals are refused. Save browser edits before CLI export/backup: another process cannot flush the unsaved editor.

Kosh follows the free **AGPL-3.0-only** route. [LICENSE](LICENSE), [CREDITS.md](CREDITS.md) and [THIRD_PARTY.md](THIRD_PARTY.md) identify application/dependency terms. Your papers/notes are not relicensed. Preserve applicable notices and corresponding source when distributing a release.

```powershell
python.exe -m unittest discover -s tests -v
node.exe --check ui/app.js
powershell.exe -NoProfile -File .\check-runtime.ps1
```

Tests use synthetic records. Node runs the offline CSL citation processor as well as development syntax checks; the prepared installer carries its executable, licence and matching source archive. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

```powershell
powershell.exe -NoProfile -File .\export-source.ps1 -OutputZip 'C:\existing\outputs\Kosh source.zip'
powershell.exe -NoProfile -File .\build-installer.ps1 -SourceZip 'C:\existing\outputs\Kosh source.zip' -OutputExe 'C:\existing\outputs\Kosh Setup.exe' -LegalDir 'C:\prepared\legal' -ComponentsDir 'C:\prepared\local-components'
```

Inspect the allowlisted source archive/hash manifest before publication. Never share a raw installation folder: it may contain research, profile, private session capability and recovery. `build-installer.ps1` uses prepared source/legal material without dependency downloads. Release receipts establish build, tests, rendering and installation separately.

The loopback service validates Host/Origin and uses a private per-launch capability. It assumes a trusted local user; storage is unencrypted and parsing/compiler execution is not an OS sandbox. CSL styles and required locales must be local before export. The separate approved retrieval action sends only official CSL identifiers/file requests, never research content.

Static `docx` preserves CSL results; `docxlive` embeds Word `CITATION`/`BIBLIOGRAPHY` fields and sources. Refresh in Word with Ctrl+A, then F9. Native IEEE, APA sixth edition and ISO 690 numerical differ from CSL APA 7/Vancouver/journal styles. Deleting a citation renumbers remaining citations; removing its bibliography entry also requires removing the uncited source from Word's Current List.

Templates are user-configured layouts, not named-journal compliance. Blinding omits only supplied author frontmatter and does not redact manuscript content. Profile outlines append only by explicit choice. Compiled LaTeX uses generated/escaped document structure and an advanced equation allowlist, not arbitrary uploaded TeX commands; shell escape is disabled, with no OS-sandbox claim. Missing-font characters refuse PDF output with a generic error. TeX Gyre Termes/Heros provide equivalent serif/sans families, not exact Word fonts. Standard non-template PDF retains its bounded vector-math renderer and labelled fallback. Native pagination, real-paper acceptance, signing and another clean computer still need their own proof.
