# Kosh agent interface

Use the fixed CLI or MCP stdio adapter to control the running local app. Start Kosh first. The bundled edition needs no system Python: use `.\runtime\python.exe -E -s agent.py ...` from its installation. The examples below use `python.exe` for a source edition; substitute the bundled interpreter as appropriate.

This interface describes the source for 0.3.0. An existing 0.2.1 installation does not gain these commands merely because the source changed; the new package must be separately verified and installed. No installation or publication claim follows from this guide.

Only current user authority for the named workspace, files and actions permits access. Local tools are not permission for private-data inspection, provider sends, formal screening, clinical abstraction or submission.

```powershell
Set-Location -LiteralPath 'C:\chosen\Kosh'
python.exe agent.py --help
python.exe agent.py health
python.exe agent.py workspaces
python.exe agent.py state --workspace WORKSPACE_ID
```

Global options precede the command: `--data-dir 'C:\explicit\app-data'` and `--timeout 180` when required. Successful commands return UTF-8 JSON. Errors return JSON/nonzero status; imports return individual receipts and retain successful records when another file fails. Placeholder IDs must be replaced from actual results.

The client privately reads the per-launch `data/agent-session.json`, verifies loopback app/build before sending the token, disables proxies/redirects and uses the header `X-App-Token`. Never read that file into a prompt, print, copy, commit or transfer it. A timed-out write/provider request may have completed: read saved state/history before retrying.

## Core reads and versioned writes

```powershell
python.exe agent.py create-workspace --title 'Selected reading project'
python.exe agent.py import --workspace WORKSPACE_ID 'C:\selected\paper.pdf'
python.exe agent.py search --workspace WORKSPACE_ID --query 'distinctive phrase' --document SOURCE_ID
python.exe agent.py document --id SOURCE_ID
python.exe agent.py document --id SOURCE_ID --page 2 --output 'C:\existing\outputs\page.png'
python.exe agent.py notes --workspace WORKSPACE_ID
python.exe agent.py save-note --workspace WORKSPACE_ID --title 'Reading notes' --body-file 'C:\selected\draft.md'
python.exe agent.py save-note --workspace WORKSPACE_ID --id NOTE_ID --version 1 --title 'Reading notes' --body-file 'C:\selected\revision.md'
python.exe agent.py note-history --note NOTE_ID
python.exe agent.py save-metadata --document SOURCE_ID --version 0 --file 'C:\selected\metadata.json'
python.exe agent.py archive --document SOURCE_ID
python.exe agent.py unarchive --document SOURCE_ID
python.exe agent.py evidence --workspace WORKSPACE_ID
python.exe agent.py save-evidence --workspace WORKSPACE_ID --document SOURCE_ID --question 'Manual question' --findings 'Reviewed source finding'
python.exe agent.py writing-check --workspace WORKSPACE_ID --note NOTE_ID --version 1
```

Imports read only explicit files, not neighbouring folders. General files have a 32 MiB bound. Metadata writes require an explicit expected metadata version; note/evidence updates need both ID/version, creation omits both. A stale version is refused without changing saved records. History/alternative creation preserves prior work; no automatic conflict merge or pruning occurs.

`document --original --output ...` downloads the managed original. PDF `--page` images identify actual file pages. Other extracted units are not native Word pagination. Markdown markers `[[source:ID:PAGE]]` retain actual supplied locations; `[[reference:ID]]` is a document-level bibliography citation with no file locator. Scientific support remains unverified.

Metadata JSON supports explicit publication fields, family/given author objects or `{"literal":"Group name"}`, rather than guessed name splitting. Inspect the current schema/desktop fields; unsupported metadata is refused. Writing check is saved-version mechanical diagnosis, not plagiarism/statistical/scientific approval.

## Bibliography, assets and discovery

```powershell
python.exe agent.py bibliography-preview --workspace WORKSPACE_ID --format ris --file 'C:\selected\references.ris'
python.exe agent.py bibliography-import --workspace WORKSPACE_ID --format csljson --file 'C:\selected\references.json'
python.exe agent.py citation-styles
python.exe agent.py citation-style-import --file 'C:\selected\journal.csl'
python.exe agent.py citation-locale-import --file 'C:\selected\locale.xml'
python.exe agent.py export-options
python.exe agent.py citation-retrieve --style-id american-medical-association --approve
python.exe agent.py citation-retrieve --style IMPORTED_STYLE_ID --approve
python.exe agent.py citation-retrieve --locale fr-FR --approve
python.exe agent.py asset-import --workspace WORKSPACE_ID --file 'C:\selected\figure.png'
python.exe agent.py catalogue-attach --workspace WORKSPACE_ID --catalogue CATALOGUE_ID --document PAPER_ID --version 0
python.exe agent.py literature-search --workspace WORKSPACE_ID --provider all --query 'explicit public query'
python.exe agent.py literature-lookup --workspace WORKSPACE_ID --provider crossref --identifier-type doi --identifier '10.1234/explicit-identifier'
python.exe agent.py literature-lookup --workspace WORKSPACE_ID --provider pubmed --identifier-type pmid --identifier '12345678'
python.exe agent.py literature-save --workspace WORKSPACE_ID --result RESULT_ID
```

Identifiers above are syntax placeholders, not claimed publications. Preview/import supports `bib`, `ris`, `csljson` and at most 1,000 records in bounded text. Import saves unverified metadata records, not papers; DOI duplicates retain existing corrections. Asset import validates PNG/JPEG/WebP bytes/dimensions. Catalogue attachment checks workspace/metadata version and preserves both originals.

`citation-styles` lists installed style IDs and locales without reading papers. Local `citation-style-import`/`citation-locale-import` read only the selected UTF-8 XML file, at most 1 MiB, with no download. Styles use returned `csl-<64 lowercase hex>` IDs. Bundled IDs are `vancouver`, `apa`, `ieee`, `chicago-note`; 63 CSL locales are bundled. Note styles support footnotes/endnotes. Dependent styles and language requirements must resolve locally before export.

`citation-retrieve` is a separate network action requiring current approval for the named official style/locale/dependencies. Exactly one of `--style-id` (official slug), `--style` (selected installed style's dependencies) or `--locale` is accepted. `--approve` attests caller authority; it does not verify human approval. The fixed pinned official CSL repositories receive identifiers/file requests only, with no paper/draft content. Export never retrieves missing files automatically. `export-options` reads profiles/defaults, available languages, native Word styles, outlines and compiler status.

Individual providers are `pubmed`, `crossref`, `europepmc`, `openalex`; `all` is bounded combined discovery. Only explicit queries/identifiers go to fixed public metadata endpoints. First pages/DOI deduplication/provider errors are visible; this is not an exhaustive formal search. Exact lookup uses Crossref DOI or PubMed PMID without fuzzy fallback. Available abstracts are unverified catalogue content. Save must use cached results from the original workspace; results expire after 30 minutes. No full paper is downloaded automatically.

## Local retrieval and OCR

```powershell
python.exe agent.py retrieval-capabilities
python.exe agent.py models
python.exe agent.py retrieval-index --workspace WORKSPACE_ID --model nomic-embed-text:latest --document SOURCE_ID
python.exe agent.py retrieval-search --workspace WORKSPACE_ID --model nomic-embed-text:latest --document SOURCE_ID --query 'concept to inspect'
python.exe agent.py ocr --workspace WORKSPACE_ID --document PDF_ID --language eng --page 2 --page 4
python.exe agent.py ask --workspace WORKSPACE_ID --document SOURCE_ID --question 'What does this source report?'
python.exe agent.py ask --workspace WORKSPACE_ID --document SOURCE_ID --model INSTALLED_LOCAL_MODEL --question 'What does this source report?'
```

OCR uses available local `eng`/`hin`/`pan` language data and creates a separate PDF derivative. Select at most 20 distinct actual pages; provenance maps derived pages back to originals. Existing originals/markers remain intact. Review recognition against images.

Embeddings require an installed local Ollama model, explicitly selected scope/index/search and consistent dimensions. Requests index at most 200 new chunks; repeat when the receipt reports the limit. Hash/text/archival/catalogue guards exclude stale or unsupported source material. Cache is outside workspace ZIPs. Inventory, capability and actual executed model output are distinct proof states; mocks prove contracts only. No downloads or cloud embedding fallback occur.

`ask` without a model returns labelled excerpts without generation. Explicit local generation can fall back to excerpts with warnings. Read `mode`, `citations`, `warning`, `audit`; exact citation IDs do not establish claim entailment.

## Provider proposals and explicit apply

```powershell
python.exe agent.py installed-agent-list
python.exe agent.py assist-preview --workspace WORKSPACE_ID --provider ollama --model INSTALLED_LOCAL_MODEL --task grammar --note NOTE_ID --version 1 --selected-text-file 'C:\selected\selection.txt'
python.exe agent.py assist-preview --workspace WORKSPACE_ID --provider codex --task ask --document SOURCE_ID --question 'Question about this source'
python.exe agent.py assist-send --preview PREVIEW_ID --consent-to-provider-send
python.exe agent.py assist-history --workspace WORKSPACE_ID
python.exe agent.py assist-result --workspace WORKSPACE_ID --result RESULT_ID
python.exe agent.py assist-save-alternative --result RESULT_ID --version 1
python.exe agent.py assist-apply --result RESULT_ID --version 1 --selected-text-file 'C:\selected\selection.txt'
```

Providers are `codex`, `claude`, `ollama`; local assistance needs `--model`. Tasks are `ask`, `outline`, `shorten`, `clarity`, `critique`, `continue`, `grammar`, `translate`, `abstract`, `extract`. Translation's question supplies the target language. `--custom-instructions` adds up to 2,000 reviewed characters to the preview. Writing needs a saved note/version and exact UTF-8 selection. `--selected-source-file` supplies explicit JSON `{document_id,page,text}` for source/extraction context.

Preview sends nothing. A reviewed five-minute prepared ticket can be claimed once; source/note hashes/versions are rechecked. Consent flags are caller attestation, not a verified human gate. Installed providers may send content to cloud services and incur usage; their CLIs can add instructions/environment metadata. Restrictions/temporary working directories are not an OS sandbox or proof of complete outbound privacy.

History retains completed/failed/running jobs and results. A completed send returns its saved result; an uncertain interrupted job is not automatically resent. Inspect history before a new request. Alternatives create another note. Apply modifies only shorten/clarity/grammar/translate selections after version/unique-selection/marker checks. All other tasks remain separate proposals. The named selection file must still match the stored preview. No provider result silently overwrites a draft. MCP rereads the private session on each operation to follow app restarts; it does not replay a write automatically after a connection failure.

Extraction yields draft rows with exact quote/citation anchors and `review_required`; interpretation remains unverified. Review every row before manual evidence save. No formal screening/submission authority follows from an extraction response.

## Chosen-file model work and exact diffs

```powershell
python.exe agent.py folder-preview --target 'C:\chosen\folder' --changes-file 'C:\selected\changes.json'
python.exe agent.py folder-apply --preview PREVIEW_ID --approve
python.exe agent.py folder-history
python.exe agent.py folder-recovery-preview --receipt RECEIPT_ID
python.exe agent.py folder-assist-preview --workspace WORKSPACE_ID --target 'C:\chosen\folder' --path draft.md --provider claude --instruction-file 'C:\selected\instruction.txt'
python.exe agent.py folder-assist-run --preview PREVIEW_ID --consent-to-provider-send
```

Changes JSON is an array of `{path,content}` complete replacements. Model proposals read only named relative paths; send approval returns a reviewed diff, not applied files. A separate `folder-apply --approve` is required for exact publication. Consent/apply flags attest caller authority and cannot verify a human approval.

MD/TXT/BIB/TEX/CSV only; 10 files, 256 KiB each, 1 MiB originals/replacements, 24 KB model preview. Existing parents, no traversal/reparse/protected paths, no deletion, recursive discovery, arbitrary binary writes or shell. Changed targets refuse. BOM/newline transformations are disclosed; originals/receipts remain. Per-file publication may leave a partial batch. Recovery requires another exact preview/apply; new files are not automatically removed. Workspace ZIPs exclude external-folder files/journal.

## Outputs and backups

```powershell
python.exe agent.py export --workspace WORKSPACE_ID --note NOTE_ID --format docx --citation-style apa --output 'C:\existing\outputs\draft.docx'
python.exe agent.py export --workspace WORKSPACE_ID --note NOTE_ID --format docxlive --word-style ieee --template-file 'C:\selected\layout.json' --output 'C:\existing\outputs\editable.docx'
python.exe agent.py export --workspace WORKSPACE_ID --note NOTE_ID --format docx --citation-style chicago-note --citation-language fr-FR --note-placement endnote --output 'C:\existing\outputs\notes.docx'
python.exe agent.py export --workspace WORKSPACE_ID --note NOTE_ID --format texpdf --template-file 'C:\selected\layout.json' --output 'C:\existing\outputs\typeset.pdf'
python.exe agent.py export --workspace WORKSPACE_ID --note NOTE_ID --format share --output 'C:\existing\outputs\reading.zip'
python.exe agent.py export --workspace WORKSPACE_ID --note NOTE_ID --format texzip --output 'C:\existing\outputs\tex.zip'
python.exe agent.py export --workspace WORKSPACE_ID --format md --audit --output 'C:\existing\outputs\audit.md'
python.exe agent.py backup --workspace WORKSPACE_ID --output 'C:\existing\outputs\workspace.zip'
python.exe agent.py backup --workspace WORKSPACE_ID --include-history --output 'C:\existing\outputs\workspace history.zip'
python.exe agent.py restore --file 'C:\selected\workspace.zip'
```

Formats: `md`, `docx`, `docxlive`, `pdf`, `texpdf`, `tex`, `texzip`, `bib`, `ris`, `csljson`, `csv`, `html`, `share`. `--note` scopes the saved draft and referenced metadata; ordinary presentation contains title/body/References. `--audit` separately includes review/file-location material. Selected draft CSV has no workspace evidence rows. Workspace bibliography data can include all nonfigure records; presentation references begin cited-only.

Outputs need explicit filenames/existing parents, refuse existing files unless `--overwrite`, and return path/bytes/content type. Plain TEX keeps caption placeholders; TeX ZIP carries figures. HTML is self-contained; reading ZIP is not a restorable workspace. CSL rules run locally; `--citation-language` chooses a local language and `--note-placement footnote|endnote` applies to note styles.

`docx` preserves static CSL results. `docxlive` embeds native Word CITATION/BIBLIOGRAPHY fields and document-local sources. Native `--word-style ieee|apa6|iso690-numeric` does not inherit the CSL style. Refresh in Word with Ctrl+A/F9; edit source records using Manage Sources. After citation deletion, remove its uncited source from Current List to remove its bibliography entry. APA sixth edition is not CSL APA 7; native ISO 690 is not Vancouver.

`--template-file` reads one explicit JSON object, at most 64 KiB. Supported keys: `profile` (`none|research|review|case-report`), `page_size` (`a4|letter`), `font` (`Times New Roman|Arial|Calibri`), `font_size` (9–14), `line_spacing` (1–3), `margin_mm` (15–40), boolean `page_numbers`, `line_numbers`, `title_page`, `blinded`, and strings `authors`, `affiliations`, `correspondence`, `abstract`, `keywords`, `running_title`. Defaults contain no author/abstract facts. Blinding omits only supplied author frontmatter. Profiles are configurable layouts, not named-journal compliance; export does not append saved draft outlines.

`texpdf` compiles generated/escaped TeX and managed figures using bundled offline Tectonic/resources. Template/note PDF also uses this path. Advanced equations use a command/environment allowlist; unsupported commands refuse. Arbitrary uploaded TeX is not compiled. Shell escape is disabled without claiming an OS sandbox. Missing glyphs refuse output with a generic font message. TeX Gyre Termes/Heros are equivalent serif/sans choices, not exact Word fonts. Source, package, rendered output and installed release remain distinct proof layers.

The UI/CLI export uses authenticated POST `/api/export` with JSON fields `workspace_id`, optional `note_id`, `format`, `citation_style`, optional `citation_language`, `note_placement`, `word_style`, `template` and optional `audit`. Frontmatter stays out of URL query strings. GET `/api/export/options` returns `{profiles, defaults, locales, word_styles, compiler, outlines}`. POST `/api/citation/styles/retrieve` takes `{style_id|style|locale, approved:true}`; POST `/api/citation/locales/import` takes `{xml}`. These are fixed local service routes, not a generic agent HTTP escape hatch.

Backup defaults to current originals/notes/metadata/chats/evidence. Saved note/evidence revision history is opt-in; neither option prunes local revisions. Restore creates a fresh workspace. The 47 MiB ZIP limit fits the bounded restore envelope. Browser drafts/profile, external-folder journals, the separate assistance-job/result journal and rebuildable embedding cache are excluded. Save browser edits first; CLI cannot flush another window. Complete copy-only upgrade preserves the whole stopped data tree; it is a separate helper, not a running MCP action. See USER_GUIDE.md.

## MCP stdio configuration

`mcp_server.py` exposes **50 tools**, verified from its current fixed registry. It uses standard-library JSON-RPC stdio and the same authenticated CLI operations, with supported protocol versions `2024-11-05`, `2025-03-26`, `2025-06-18`. It does not register itself or edit Codex/Claude settings. Configure a chosen client explicitly; a typical configuration shape is:

```json
{"mcpServers":{"kosh":{"command":"C:\\chosen\\Kosh\\runtime\\python.exe","args":["-E","-s","C:\\chosen\\Kosh\\mcp_server.py"]}}}
```

For a separate data directory, append `--data-dir` and its explicit path. Start Kosh before invoking content tools. Never place its private session token in configuration. Configuration syntax and actual client acceptance are client-specific proof layers; the example is not a claim that a client was registered/tested.

| Tools | Corresponding CLI / effect |
|---|---|
| `kosh_health`, `kosh_workspaces`, `kosh_workspace_state` | Identity, workspace metadata or explicitly scoped state reads |
| `kosh_models`, `kosh_installed_agents` | Local inventory/detection; no generation/download |
| `kosh_create_workspace` | Create an empty workspace |
| `kosh_notes`, `kosh_evidence`, `kosh_document`, `kosh_search` | Scoped saved/source reads |
| `kosh_import_files`, `kosh_import_asset` | Explicit selected file/image imports |
| `kosh_save_note`, `kosh_save_metadata`, `kosh_save_evidence` | Versioned explicit writes |
| `kosh_writing_check`, `kosh_note_history` | Saved diagnostics/history |
| `kosh_archive`, `kosh_unarchive` | Reversible archive state |
| `kosh_bibliography_preview`, `kosh_bibliography_import`, `kosh_catalogue_attach` | Reviewed bibliographic records/attachment |
| `kosh_citation_styles`, `kosh_citation_style_import` | Installed CSL style IDs or one explicitly selected local style import |
| `kosh_export_options`, `kosh_citation_locale_import`, `kosh_citation_retrieve` | Local capabilities, selected locale import or separately approved official retrieval |
| `kosh_literature_search`, `kosh_literature_lookup`, `kosh_literature_save` | Explicit query/identifier sends and selected metadata save |
| `kosh_ask`, `kosh_assist_preview`, `kosh_assist_send` | Excerpts/model proposal preparation and consented send |
| `kosh_assist_save_alternative`, `kosh_assist_apply`, `kosh_assist_history`, `kosh_assist_result` | Alternative/reviewed apply or retained result reads |
| `kosh_retrieval_capabilities`, `kosh_retrieval_index`, `kosh_retrieval_search`, `kosh_ocr` | Local capabilities, explicit embeddings or OCR derivative |
| `kosh_folder_preview`, `kosh_folder_apply`, `kosh_folder_history`, `kosh_folder_recovery_preview` | Exact local diff/apply/recovery |
| `kosh_folder_assist_preview`, `kosh_folder_assist_run` | Explicit chosen-file model preview/send; separate apply remains required |
| `kosh_export`, `kosh_backup`, `kosh_restore` | Explicit saved outputs or fresh-workspace restore |

Schemas reject unknown properties/commands; consent/approval tools require true caller-attestation fields. Stdio notifications never execute writes. No generic HTTP route, direct SQL, arbitrary shell, automatic provider registration or app shutdown tool is exposed. Mocked tool/provider tests establish schema/contracts, not real provider authentication, output quality or client compatibility. Consult current help/schemas rather than assuming a stale agent command list.
