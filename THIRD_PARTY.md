# Third-party components and corresponding source

Kosh uses **AGPL-3.0-only** for its original application code; the full text is in [LICENSE](LICENSE). Imported papers, notes, figures and datasets are not relicensed merely because they are used in Kosh. Their permissions remain separate.

This inventory distinguishes the prepared baseline runtime, optional local components and system/provider prerequisites. Final package manifests and retained receipts determine the files actually distributed. The inventory is not a legal-compliance certificate or permission to replace matching sources with unrelated versions.

## Prepared document-runtime baseline

| Component | Baseline version | Inspected terms / notice material |
|---|---|---|
| Python | 3.12.10 | Runtime LICENSE.txt includes PSF and incorporated-component terms |
| SQLite | Included with that Python runtime | Retain the runtime's included SQLite/component notices/source material |
| PyMuPDF / MuPDF | 1.28.2 / 1.28.2 | AGPL route selected; Artifex's separate commercial route is not purchased by this release |
| python-docx | 1.2.0 | MIT |
| lxml | 6.1.1 | BSD-3-Clause and included-library notices in LICENSES.txt |
| typing_extensions | 4.15.0 | PSF-2.0 |

The prepared installer copies the identified Python runtime and selected document packages, retaining notices and matching source archives. Python/MuPDF source is separate from the PyMuPDF binding archive. The MuPDF source archive includes its upstream third-party material; do not assume the PyMuPDF archive alone supplies the engine's source.

Approved baseline source locations: [Python 3.12.10](https://www.python.org/ftp/python/3.12.10/), [PyMuPDF 1.28.2](https://pypi.org/project/PyMuPDF/1.28.2/#files), [MuPDF 1.28.2](https://mupdf.com/downloads/archive/mupdf-1.28.2-source.tar.gz), [python-docx 1.2.0](https://pypi.org/project/python-docx/1.2.0/#files), [lxml 6.1.1](https://pypi.org/project/lxml/6.1.1/#files), [typing_extensions 4.15.0](https://pypi.org/project/typing_extensions/4.15.0/#files). These identify the previously approved source set; no fresh download is implied by reading this document.

## Offline CSL citation components

| Component | Pinned source/version | Terms and retained material |
|---|---|---|
| [citeproc-js](https://github.com/Juris-M/citeproc-js) | `cc9153c45293af878de08cafddbefe6ea150c380` | Frank Bennett's AGPL v3-or-later option selected; upstream LICENSE and AGPL text retained |
| [CSL styles](https://github.com/citation-style-language/styles) | `89c63834393a5f806e375b0816dc110c3be93d44` | CC-BY-SA-3.0; APA 7, IEEE and NLM citation-sequence parent used for Vancouver; author/contributor metadata retained |
| [CSL locales](https://github.com/citation-style-language/locales) | `a89adece41013402236e2c9020972d7e931fbab8` | CC-BY-SA-3.0; local `en-US` data and translator metadata retained |
| [Node.js](https://nodejs.org/dist/v24.14.1/) | 24.14.1 Windows x64 | `tools/node/node.exe`, its LICENSE with incorporated-component notices, and matching `node-v24.14.1.tar.xz` source archive |

Attribution: Kosh uses styles/locales maintained by the **[Citation Style Language project](https://citationstyles.org/)**. Preserve the author/contributor lists inside style XML and translator lists inside locale XML when redistributing them. Upstream README/licence material accompanies the captured components. The locally named `vancouver.csl` is the pinned `nlm-citation-sequence.csl` independent parent, not an invented replacement for the dependent Vancouver/NLM style.

[vendor/csl/components.json](vendor/csl/components.json) records pinned commits, approved exact source URLs, byte counts and SHA256 for processor, styles, locale, Node archives and extracted executable/licence. Reconcile that receipt with the final installer/source/legal inventory before distribution; it does not establish that an already installed 0.2.0 release contains these additions. The processor source and licence material are included in the source package; the prepared installer supplies the local Node tool and matching Node source archive.

The source edition needs the matching Node runtime already installed at the supported location or prepared under `tools/node/`. `scripts/fetch_csl_components.py` is a separate maintainer tool, permitted only after explicit approval of its listed pinned sources/files. The app, setup and installer do not call it or download components automatically. User-imported styles retain their own attribution/licensing. Independent and dependent styles, note styles and locale imports are supported; official parent/locale retrieval is a separate explicit approved operation. Export never retrieves dependencies implicitly. The current bundle adds Chicago note and all 63 pinned official locales to the baseline styles above.

## Offline TeX components

The local compiler is [Tectonic 0.17.0](https://github.com/tectonic-typesetting/tectonic/releases/tag/tectonic%400.17.0), under its retained MIT licence and incorporated-component terms. The installer includes its official Windows executable, original release archive, matching compiler source archive and licence. A compact 563-resource subset of the official default v33 TeX bundle, including the 0.3.1 Latin Modern additions, supplies the generated manuscript workflow; it is not a full TeX distribution.

The package retains source/documentation archives for the selected LaTeX, amsmath, fontspec, geometry, hyperref, lineno, setspace, fancyhdr, graphics, TeX Gyre, hyph-utf8, unicode-data, AMS fonts, Computer Modern and Latin Modern material from the official initial TeX Live 2022 archive. Individual upstream terms apply, including LPPL and the font/data terms retained in those archives. Later 2022 final package versions were not substituted for the older runtime files. [vendor/tex/receipt.json](vendor/tex/receipt.json) pins all runtime members and 37 payload files; `legal/tex/texlive-source-receipt.json` and `legal/tex/source-version-audit.json` in the installer record the archives and compared package dates. These inventories document supplied files rather than providing legal certification.

The unchanged `pzdr.tfm` Zapf Dingbats metric matches the retained `legal/tex/zapfding.r61719.tar.xz` original. Its upstream TeX Live package records GPL attribution. That archive preserves the Adobe AFM copyright/trademark notice and the separate URW font program's GNU GPL notice with a PDF/PostScript embedding exception; the URW exception applies to that font program. Full GNU GPL v2 text is already supplied inside `legal/mupdf-1.28.2-source.tar.gz`, member `mupdf-1.28.2-source/thirdparty/freetype/docs/GPLv2.TXT` (17,994 bytes; SHA-256 `c4120c6752c910c299e3bd9cb3a46ff262c268303ca2069b61f92f10a5656c18`). The audit records package-level attribution and exact metric provenance without asserting a separate Adobe permission statement or full font-construction reproducibility.

Compilation runs offline on Kosh-generated escaped source and validated equation notation. TeX Gyre Termes/Heros are the bundled PDF equivalents for the selectable Word fonts; Microsoft fonts are not redistributed. Missing glyphs fail explicitly. The source edition needs the receipted compiler/bundle prepared separately; the installer bundles them and does not fetch them at first use.

## Prepared local OCR data

| Data | Captured upstream source | Inspected notice |
|---|---|---|
| English `eng.traineddata` | [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) | Apache License 2.0 |
| Hindi `hin.traineddata` | [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) | Apache License 2.0 |
| Punjabi `pan.traineddata` | [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) | Apache License 2.0 |

The prepared local-component receipt records approved source URLs, captured byte counts and SHA-256 hashes for these three files and the two repository licence texts. Hashes pin the fetched bytes even though the upstream repository URLs refer to moving branches. A release bundling the data must retain those notices/receipts and verify its actual payload matches them. Preparation does not establish final installer inclusion.

Kosh's OCR calls the available local document runtime and language data. It does not silently install a Tesseract executable or download language data when OCR is requested. A source edition can use a supported separately installed local Tesseract data directory. The source's capability result identifies the languages and whether each comes from bundled or installed data. Engine/runtime terms and language-data terms remain distinct.

## Optional embeddings and installed providers

The approved prepared [nomic-embed-text Ollama](https://ollama.com/library/nomic-embed-text) receipt records the selected manifest/layers and a captured Apache-2.0 licence layer. It concerns those captured bytes, not every future `latest` tag. Model installation is explicit and separate; Kosh's normal installer does not bundle model weights or alter unrelated installed models.

Ollama, installed Codex/Claude clients, accounts and provider services retain their own terms. Detection is not provider authentication or entitlement to free usage. Approved provider sends may incur usage and transmit selected content outside the computer. No provider account/token belongs in a source release, installer or public log.

## System prerequisites and redistribution checks

Microsoft Edge and .NET Framework are system prerequisites and are not bundled. Their terms remain separate. Public-index metadata/abstracts and imported full papers have their own use conditions; saving a record does not confer rights to a paper.

Before distributing a build, reconcile its runtime/component versions, manifest hashes, retained notices and corresponding-source archives. Inspect optional OCR/model receipt scope separately. The package must exclude personal app data, browser profiles, private session capabilities and upgrade/folder recovery. Prepared legal material, a passing test and a local install do not establish signing, another clean computer or every redistribution arrangement.
