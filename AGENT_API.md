# Kosh agent interface

Use the fixed CLI or MCP stdio adapter to control the running local app. Start Kosh first. The bundled edition needs no system Python: use `.\runtime\python.exe -E -s agent.py ...` from its installation. The examples below use `python.exe` for a source edition; substitute the bundled interpreter as appropriate.

This source interface targets **Kosh 1.0.0-rc.5** and retains the same 63 tools as 0.6.0 and 0.5.0. This document describes the candidate source, not proof of publication or final 1.0 acceptance. The six additions for project/reviewer records and backup/update status were introduced in 0.5.0; streamed automatic sets and saved revision comparison were introduced in 0.6.0. The RC adds desktop local-file backup jobs and previewable installation diagnostics without adding generic HTTP, shell or execution tools. An older installation keeps its previous behavior until upgraded to a matching package.

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

Imports read only explicit files, not neighbouring folders. General files have a 32 MiB bound. From 1.0.0-rc.2 a PDF import whose source details are empty may receive a suggested `title` (embedded file details) and `doi` (first two pages) with a `provenance` line; the receipt lists them under `suggested_metadata`, metadata version stays 0 and the values are unverified. A draft `export --note` result adds `warning` and `incomplete_references` when the saved-version writing check finds cited sources with missing bibliography fields; the file is still written. From 1.0.0-rc.3, a whole-workspace `export` (any format except `csv`) adds the same fields from Project review's saved-draft checks, deduplicated by source, plus `checks_failed` when a draft check could not run. The `kosh_export` MCP tool returns the same fields. DOI completion stays a desktop review step; agents can use the existing `literature-lookup` and `save-metadata` commands with an explicit expected metadata version. Metadata writes require an explicit expected metadata version; note/evidence updates need both ID/version, creation omits both. A stale version is refused without changing saved records. History/alternative creation preserves prior work; no automatic conflict merge or pruning occurs.

`document --original --output ...` downloads the managed original. PDF `--page` images identify actual file pages. Other extracted units are not native Word pagination. Markdown markers `[[source:ID:PAGE]]` retain actual supplied locations; `[[reference:ID]]` is a document-level bibliography citation with no file locator. Scientific support remains unverified.

Metadata JSON supports explicit publication fields, family/given author objects or `{"literal":"Group name"}`, rather than guessed name splitting. Inspect the current schema/desktop fields; unsupported metadata is refused. Writing check is saved-version mechanical diagnosis, not plagiarism/statistical/scientific approval.

Kosh 0.6.0's **Write → Compare revisions** first saves ordinary pending edits in that window, then reads two saved versions of the same note as aligned plain-text titles/bodies. It reports removed/added body lines, changed blocks and title changes, with difference navigation. The display itself does not modify a draft, create a revision or restore a version; conflicted browser alternatives stay separate. Large changed blocks disclose coarse alignment; the full text remains accessible across 200-row pages. The existing `note-history` command and `kosh_note_history` tool already return current and prior saved versions; no comparison or history-write tool is added.

## Project review, reviewer records and status — 0.5.0

```powershell
python.exe agent.py project-review --workspace WORKSPACE_ID
python.exe agent.py reviewer-state --workspace WORKSPACE_ID
python.exe agent.py reviewer-save --workspace WORKSPACE_ID --version REVIEWER_VERSION --file 'C:\selected\reviewer change.json'
python.exe agent.py reviewer-export --workspace WORKSPACE_ID --version REVIEWER_VERSION --output 'C:\existing\outputs\response letter.txt'
python.exe agent.py backup-status
python.exe agent.py update-status
```

`project-review` reads all saved drafts and active recorded claim reviews in one selected workspace. It reports its check time, drafts without reviews, source-needed/stale/current checked claims, unresolved references, missing cited-source metadata and individual writing checks. Counts can overlap; unrecorded claims are unassessed. A failed draft check retains its error and makes incomplete reference/metadata totals unknown rather than zero. This is not scientific-support or readiness certification. The CLI reads saved state and cannot flush another browser's unsaved text. The desktop **More → Project review → Save & refresh** saves that window first.

`reviewer-state` returns `{schema_version, workspace_id, version, comments}` with current manuscript-link `stale`, `stale_reasons`, `current_note_version` and `revised_verification` fields. Its `version` belongs to the workspace's reviewer records, separately from note and reading-state versions. Read it before a write/export and use the returned `REVIEWER_VERSION`; read saved state again after a write.

`reviewer-save` reads one explicitly selected UTF-8 JSON object, at most 128 KiB. Omit `workspace_id` and `expected_version`: the flags provide those fields. Creating a comment requires `note_id`, `note_version`, `passage_start`, `passage_end`, `passage`, `reviewer` and `comment`. The passage must match the saved manuscript at the exact offsets and version. Offsets count Unicode characters from zero; the end is exclusive. Choose the intended occurrence when wording repeats. Optional manual fields are `planned_text`, `revised_text`, `response`, `status` and boolean `archived`.

Updating a comment requires its `id` and the explicitly changed fields. The saved comment stays linked to its original note. Explicit relinking supplies all four anchor fields together: `note_version`, `passage_start`, `passage_end`, `passage`. Progress values are `open`, `planned`, `revised` or `responded`; revised/responded require non-empty revised wording/response respectively. Every actual field/link change retains its prior snapshot. Archive/unarchive is reversible. The state has a 4 MiB bound, up to 1,000 comments and up to 200 retained changes per comment; an exceeded limit refuses without pruning history. A stale expected version returns 409 without replacing saved records; keep the selected JSON, reload and review before retrying.

These are manual reviewer-response records, not manuscript edits or attributed reviewer approval. Make actual manuscript changes through the normal versioned note workflow. `reviewer-export` writes a local `.txt` response letter from the expected saved reviewer version, excluding archived records and pending browser fields. It uses the existing explicit-output/no-clobber rules. The desktop export can choose a title and explicitly select **Include archived comments in the letter**, which starts unchecked; **Show archived comments** changes the list only and does not affect export inclusion. Both letter paths report stale links and whether recorded revised wording is exactly present in the current saved manuscript; a match does not establish its location, context or adequacy. Review the manuscript/letter before sharing; no provider call, email or submission occurs.

`backup-status` reads application-wide automatic backup preferences, last attempt/success/failure, last completed set path, next due time and errors. It creates no backup, changes no preferences and restores nothing. Desktop **Settings → Automatic local backups** is the separate opt-in flow: user-selected existing local folder outside application/data paths, runs while the app is open with one catch-up on launch, all workspace ZIPs with history and no pruning/Windows scheduled task. In 0.6.0, those sets are written and validated directly from files, removing their former 47 MiB per-workspace ceiling. They retain the unchanged 32 MiB per-original/workspace-manifest, 1,000-per-main-collection and 5,000-revision bounds, with a derived archive limit of about 31.3 GiB per workspace. Completed sets retain byte/hash/count/build receipts. Exact file-backed restore preview precedes creation of a fresh workspace. ZIPs contain saved data, not unsaved browser recovery or pending reviewer fields. The CLI/MCP `backup`/`restore` transfer path remains bounded at 47 MiB; use desktop automatic sets or the RC's local-file jobs for a larger archive.

`update-status` reads locally known update/receipt/previous-installation information only. It contacts no network, downloads no file and executes nothing. Desktop **Settings → Kosh updates** separately requires an explicit public GitHub release check, installer/checksum download and installed-package execution approval. **Download matches the SHA-256 published in the same GitHub release. This does not verify the publisher; installers are unsigned.** Installation saves/closes, waits for the stopped service/browser, copies into a fresh sibling install and verifies startup before matching shortcut retargeting. After a close-wait timeout, the desktop may offer **Save, close and resume retained update**: fresh explicit unsigned/job approval rechecks the retained installer without downloading again, then waits for the window to close. A still-running worker refuses another start; uncertain partial installation requires receipt-based recovery. Resume/activation remain desktop actions and have no CLI/MCP execution tool. Old installation/data remain retained; opening an older version shows older data and can create diverged histories. These global status reads do not grant an agent automatic backup/update write authority.

## Desktop local-file backup jobs and installation diagnostics — 1.0.0-rc.1

These fixed, authenticated desktop service routes are not new CLI/MCP commands. They use the existing session header and local application authority. Do not extract the session capability to call them from an unrelated client or treat an available route as permission to read a private file.

| Operation | Route and selected input |
|---|---|
| Choose a local path | POST `/api/local-dialog`, for example `{"kind":"folder"}`; `kind` is `folder`, `backup-open` or `backup-save`. Returns a selected path or cancellation, without writing that path |
| Start local work | POST `/api/local-backup/jobs`; backup selects `{operation:"backup",workspace_id,path,include_history}`, ZIP preview selects `{operation:"preview",path}`, saved-set preview selects `{operation:"preview-set",set_id,workspace_id}`, and automatic backup selects `{operation:"automatic"}` |
| Read progress | GET `/api/local-backup/jobs?job_id=ID`; reads only the selected session job |
| Request cancellation | POST `/api/local-backup/cancel`, `{job_id}`; inspect `accepted` and the returned job rather than assuming cancellation completed |
| Apply a reviewed preview | POST `/api/local-backup/restore`, `{preview_id,approve:true}`; uses the exact retained preview and creates a fresh workspace |
| Check components | GET `/api/installation-health`; explicit local availability check, not a document test or complete installation hash verification |

Local jobs expose phase/state, copied-byte progress, cancellation state and retained recovery locations. An unknown byte total is not a completion percentage. Cancellation waits for the current copying/parser section and is refused after publication or approved apply starts; read the final state before starting another job. Existing outputs are not overwritten, and uncertain partial bytes are retained for review. The user can choose a single local workspace ZIP without enabling automatic backup scheduling. Automatic sets still require an explicit existing local destination and opt-in.

Larger local-file archives use the existing source/record/history bounds and file-backed validation from 0.6.0; the native chooser does not remove those limits. The CLI/MCP ZIP transfer remains limited to 47 MiB. A completed job proves its saved records/originals and retained receipt, not preservation of unsaved fields in another browser window. Back up the complete stopped data directory separately when browser recovery, assistance journals and other app-private recovery are needed.

**Settings → Check this installation** reports required Python/PDF/Word/CSL availability and optional TeX/OCR/language support. Local AI is explicitly not contacted. Its optional diagnostics JSON allows only app version/build, OS family/version, fixed component statuses/origins/codes, and the English/Hindi/Punjabi status records. The desktop shows the exact JSON before a separate local download; it sends or uploads nothing. It excludes paths, filenames, usernames, machine identifiers, document titles/content/counts, settings, logs and session tokens. Review even this limited preview before sharing it.

`backup-status` and `update-status` are different reports: they may contain private local paths and error text. Do not post their raw output or whole status dictionaries as diagnostics. Use the dedicated allowlisted preview for a public bug report when useful; it is optional.

The RC update path compares semantic versions, including numeric prerelease identifiers. An RC may see newer prereleases and final releases; a final 1.0-or-later build defaults to final releases. Transfer checksum verification remains separate from publisher identity, and signing is still pending. Retained completion/activation evidence must agree before an updated copy permits editing; a missing global update cache alone is not evidence that a previously completed installation became unsafe. Older copies and later divergent saved work must be reviewed separately, not silently rolled back.

The 0.6.0 updater accepted numeric release tags only, so it cannot discover a `1.0.0-rc.1` tag using its old in-app check. That compatibility limit is not proof that no candidate exists. Use the separately approved fresh-install/copy-only route for that older copy, preserving its installation and data; the RC's semantic-version update behavior applies after the matching package is installed.

## Reading organisation, annotations and personal claim reviews

The seven reading commands use an explicit workspace. Reads make no provider call. Writes use one shared reading-state version across source organisation, resume position, annotations and claims; this is separate from a note's edit version.

```powershell
python.exe agent.py reading-state --workspace WORKSPACE_ID
python.exe agent.py reading-duplicates --workspace WORKSPACE_ID
python.exe agent.py reading-geometry --workspace WORKSPACE_ID --document PDF_ID --page 2
python.exe agent.py reading-source-save --workspace WORKSPACE_ID --version READING_VERSION --file 'C:\selected\source change.json'
python.exe agent.py reading-resume-save --workspace WORKSPACE_ID --version READING_VERSION --file 'C:\selected\resume change.json'
python.exe agent.py reading-annotation-save --workspace WORKSPACE_ID --version READING_VERSION --file 'C:\selected\annotation change.json'
python.exe agent.py reading-claim-save --workspace WORKSPACE_ID --version READING_VERSION --file 'C:\selected\claim change.json'
```

Replace placeholder IDs and `READING_VERSION` with values returned by current reads. Each save reads one explicitly named UTF-8 JSON object, at most 64 KiB. Omit `workspace_id` and `expected_version` from that file: `--workspace` and `--version` supply them. Unknown fields are rejected. Use the returned reading version for the next write, and read back the record. A stale version returns 409 without changing saved state; retain the local JSON, reload current records and review the intended change before retrying.

`reading-state` returns `{schema_version, workspace_id, version, sources, resume, annotations, claims}`. Public annotation/claim records include derived `stale` and `stale_reasons`; use this read when assessing their current condition. `reading-duplicates` returns possible pairs and match reasons from saved title/DOI metadata. This operation is read-only: it does not establish document identity or merge/delete anything. `reading-geometry` returns one actual PDF page's dimensions, text words and normalized rectangles. An index is meaningful only for that exact source page; it is not a publication page or an arbitrary drawing coordinate.

The save JSON fields are:

| Command | Selected-file change object |
|---|---|
| `reading-source-save` | `document_id`; optional `status` (`unread`, `reading`, `read`), boolean `favorite`, unique string `tags`, one string `collection`, and `last_page` |
| `reading-resume-save` | Optional `document_id`, `page`, `note_id`, `view`, `panel`, `next_action`; source/note IDs must belong to the workspace, and a page needs a source |
| `reading-annotation-save` create | `document_id`, actual `page`, exact `quote`; optional `comment`, `color`, `word_indices`. PDFs require consecutive actual word indices matching the quote; non-PDF records use extracted section 1 |
| `reading-annotation-save` update | Existing `id` plus optional `comment`, `color`, boolean `archived`; source/page/quote stay immutable |
| `reading-claim-save` create | `note_id`, saved `note_version`, exact `claim_anchor`, `status` (`needs_source`, `attached`, `checked`); optional `document_id`, actual `page`, exact `excerpt` |
| `reading-claim-save` update | Existing `id` plus optional `status`, `document_id`, `page`, `excerpt`, boolean `archived`; recorded note/version/wording stay immutable |

For an unattached claim, use `needs_source` with `document_id:null`, `page:null` and an empty `excerpt`. Attached/checked claims require an available passage from imported source text, not a catalogue-only reference or image. The selected anchor must occur in the current saved note at `note_version`. Save browser edits first; the CLI cannot flush them.

The `checked` status records the caller's attestation of personal review, displayed as **Checked by me**. It is not an AI verification result. A stale note/anchor cannot be marked checked. Changing a checked source attachment requires another review and retains the previous attachment in `attachment_history`; it does not silently carry the previous check forward. Archive/restore changes visibility without deleting the record. Reading collections have bounded size; a refused operation preserves existing records.

Annotations and reading records are separate local data. Creating a highlight does not change the original PDF, replace a source ID or insert a citation into a draft. The UI's **Create cited note** explicitly creates a separate Markdown note from a saved passage. Workspace snapshots include reading organisation/resume/annotations/claims and attachment history; restore validates and remaps their source/note links in a fresh workspace. Unsaved browser fields remain outside the ZIP.

These operations use authenticated GET `/api/reading`, `/api/reading/duplicates`, `/api/reading/geometry` and POST `/api/reading/source`, `/api/reading/resume`, `/api/reading/annotation`, `/api/reading/claim`. POST bodies require `workspace_id` and `expected_version`; geometry requires `workspace_id`, `document_id` and a one-based `page`. They are fixed routes, not a generic HTTP/SQL capability.

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

Identifiers above are syntax placeholders, not claimed publications. Preview/import supports `bib`, `ris`, `csljson` and at most 1,000 records in bounded text. Import saves unverified metadata records, not papers; DOI duplicates retain existing corrections. From 1.0.0-rc.5, PubMed results include `pmid`, and `literature-save` treats a workspace source with the same DOI or PMID as already saved. Each index refuses a second request within one second, so pace consecutive lookups. Asset import validates PNG/JPEG/WebP bytes/dimensions. Catalogue attachment checks workspace/metadata version and preserves both originals.

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

Backup defaults to current originals/notes/metadata/chats/evidence and reading organisation, resume position, annotations, claims and retained attachment history. Since Kosh 0.5.0 it also includes saved reviewer comments, passage snapshots and retained changes even when ordinary note revision history is excluded. Saved note/evidence revision history is opt-in for manual ZIPs; automatic sets include it. Neither option prunes local revisions. Restore validates nested reading/reviewer records and remaps their source/note IDs into a fresh workspace. Old 0.4.0 backups restore in 0.5.0 or later with empty reviewer records; newer ZIPs have a `reviewer` manifest field unsupported by Kosh 0.4.0. Manual CLI/browser ZIP backup and restore retain the 47 MiB envelope. The larger automatic-set route requires 0.6.0, reads/writes local files directly and keeps the existing archive schema/file/record/history guards. ZIPs are unencrypted. Automatic scheduling runs only while Kosh is open, with catch-up on launch. Browser drafts/profile, external-folder journals, the separate assistance-job/result journal and rebuildable embedding cache are excluded. Save browser edits first; CLI cannot flush another window. Complete copy-only upgrade preserves the whole stopped data tree; it is a separate helper, not a running MCP action. See USER_GUIDE.md.

## MCP stdio configuration

`mcp_server.py` exposes **63 tools** in 1.0.0-rc.5, retaining 0.6.0 and 0.5.0's fixed registry. Version 0.4.0 has 57, including seven reading-state/duplicate/geometry reads and source/resume/annotation/claim saves. The six additions in 0.5.0 are project review, reviewer state/save/export and backup/update status; 0.6.0 and this RC add no tools. It uses standard-library JSON-RPC stdio and the same authenticated CLI operations, with supported protocol versions `2024-11-05`, `2025-03-26`, `2025-06-18`. It does not register itself or edit Codex/Claude settings. Configure a chosen client explicitly; a typical configuration shape is:

```json
{"mcpServers":{"kosh":{"command":"C:\\chosen\\Kosh\\runtime\\python.exe","args":["-E","-s","C:\\chosen\\Kosh\\mcp_server.py"]}}}
```

For a separate data directory, append `--data-dir` and its explicit path. Start Kosh before invoking content tools. Never place its private session token in configuration. Configuration syntax and actual client acceptance are client-specific proof layers; the example is not a claim that a client was registered/tested.

| Tools | Corresponding CLI / effect |
|---|---|
| `kosh_health`, `kosh_workspaces`, `kosh_workspace_state` | Identity, workspace metadata or explicitly scoped state reads |
| `kosh_project_review` | Selected-workspace saved-draft and recorded-claim checks, with Unknown incomplete totals; no readiness certification |
| `kosh_reviewer_state`, `kosh_reviewer_save`, `kosh_reviewer_export` | Selected-workspace response reads, reviewed JSON/version save or explicit local saved-text export; manuscript text is unchanged |
| `kosh_backup_status`, `kosh_update_status` | Global local status reads only; no preference write, backup/restore, network check/download or installation |
| `kosh_reading_state`, `kosh_reading_duplicates`, `kosh_reading_geometry` | Scoped reading records, read-only duplicate candidates or actual PDF word geometry |
| `kosh_reading_source_save`, `kosh_reading_resume_save`, `kosh_reading_annotation_save`, `kosh_reading_claim_save` | Selected JSON changes with expected reading-state version; personal checked status is caller attestation |
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
