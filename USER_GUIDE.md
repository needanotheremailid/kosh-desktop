# Kosh user guide

## First launch and a first useful session

**[Download the Kosh 0.3.1 Windows beta installer](https://github.com/needanotheremailid/kosh-desktop/releases/download/v0.3.1/Kosh-0.3.1-Setup.exe)** from [this repository's release](https://github.com/needanotheremailid/kosh-desktop/releases/tag/v0.3.1). Use 64-bit Windows 11 with Microsoft Edge and .NET Framework. The installer is unsigned; Windows may warn about an unknown publisher. Check the release origin and published checksum before deciding whether to run it. Keep a backup and try a permitted non-sensitive paper first. No separate Python, Node, TeX, AI account or model is required for the ordinary bundled reading/writing/export workflow.

The bundled edition installs with `Kosh-0.3.1-Setup.exe` into a new folder for your Windows user. Edge and .NET Framework are prerequisites; the prepared Python/document runtime and Node.js 24.14.1 local citation tool are included. Installation does not need an administrator or download packages. Existing shortcuts are preserved.

This guide describes 0.3.1. An existing older installation keeps its prior behavior until upgraded. The optional [signing workflow](SIGNING.md) requires an already provisioned trusted publisher identity; the installer is not signed just because that workflow is available. Tests on one computer do not prove another clean Windows computer or every real manuscript.

The library starts empty. Open the Kosh shortcut after setup; automatic launch is off by default so an upgrade can copy data before first use. Getting started opens on first use and can be reopened from Help. Skip/reopen it without changing research. Help explains reading, source locations, saving and controls. Choose Broadsheet, Stacks or Commonplace in the status-bar Layout control. Settings changes light/dark appearance and optional hover explanations; these are browser preferences, not changes to your papers.

1. Create a workspace for one project.
2. Import one trusted source you have permission to use; read its receipt.
3. Open Read and compare extracted text with the original PDF image when available.
4. Capture an exact passage into a source-linked note, or start a draft and insert its source locator.
5. Check/save the draft, then export it. Begin with a small source-to-note-to-export loop before adding optional models.

Keep the app in a stable writable folder. Its `data/` contains managed originals, SQLite records, revisions, the dedicated Edge profile and local recovery. Clearing that profile can remove browser draft recovery. Save state before moving or upgrading.

## Sources, references and attachment

General import handles selected PDF, DOCX, TXT, Markdown, CSV, BibTeX and RIS files. It makes managed copies and does not edit originals or inspect neighbouring folders. Each selected file gets an imported/duplicate/no-text/error receipt. A malformed file can retain its original with an error record.

Use **Import bibliography** for multiple RIS, BibTeX or CSL JSON publication records. Choose/paste a file, select its format, preview the records/warnings, then explicitly import that exact content. Each record is unverified reference metadata, not a full paper. Unsupported macros/fields are reported; absent names/dates/details are not invented. DOI duplicates retain existing corrections in the selected workspace.

**Discover references** searches PubMed, Crossref, Europe PMC or OpenAlex. Combined search takes the first bounded page from each, deduplicates DOI matches and discloses index failures; it is not exhaustive. Exact DOI lookup uses Crossref and PMID lookup uses PubMed. Abstracts appear only where the index supplies them. Queries/identifiers leave the computer; your private library is not automatically uploaded. Results expire; save a selected cached reference explicitly in its search workspace.

Obtain a permitted full paper separately and import it. In Source details, attach the reviewed catalogue reference to that imported paper at its current metadata version. This retains both records/originals. Confirm that the identifiers, title/authors and publication are actually the same; linking does not independently establish identity.

Enter/check bibliographic fields against the publication. Use explicit family/given names or literal group names; do not guess surnames to remove a warning. Publication pages belong to the article/book, while captured PDF file-page positions describe the local file. DOI absence can be legitimate. More publication fields can be supplied through the versioned metadata CLI; exported placeholders/warnings identify incomplete entries.

## Reading, exact search and OCR

PDF page numbers are actual one-based file pages even when printed numbering differs. Read can show the original image and extracted text. DOCX/text locations are extraction sections, not native Word pagination. DOCX extraction includes paragraphs/tables and headers/footers, with exclusions for text boxes, drawings and embedded objects. Check the extraction notice.

Lexical search returns matching extracted passages. Open the source and inspect context; a different term can miss relevant material. Importing/searching a document does not mean every page was automatically analysed.

For a scanned PDF, select **Create OCR copy of this page**. Local capabilities determine which English/Hindi/Punjabi languages (`eng`, `hin`, `pan`) are available. Bundled language data is preferred when present; a supported local Tesseract installation can supply it otherwise. Clicking OCR downloads nothing and sends no audio or document to a cloud OCR service.

OCR creates a separate managed PDF. Original bytes and existing source citations stay intact. The receipt maps derived-page numbers to original file pages. Captures from the derivative refer to its own ID/pages; consult the mapping to inspect the original. Recognition can change words, digits and negation, so review against images before using it as evidence. The CLI can select up to 20 distinct actual pages, sorted into a derivative; each page has a 20-million-pixel limit and the output has a 32 MiB limit.

The bundled Windows installer includes English, Hindi and Punjabi OCR data and its licence notices. Optional embedding weights remain a separate installation.

## Optional semantic retrieval

Local semantic search requires an already installed embedding-capable Ollama model. The capability view assesses `nomic-embed-text:latest` when available, separately reporting inventory, embedding capability, dimension and successful execution in the current process. Detection alone is not a completed embedding request. Installation of Ollama/models is a separate explicit choice; Kosh downloads no weights and uses no cloud fallback.

If you choose to download this model using an already installed Ollama CLI, run the following separately. It contacts Ollama's registry; it is not part of Kosh setup, OCR or ordinary search. Review the model's current terms and retain any receipt needed for reproducibility, because `latest` can change.

```powershell
ollama.exe pull nomic-embed-text:latest
```

Choose the installed embedding model, explicitly build the active workspace index, then submit a semantic query. Index requests process at most 200 new 800-character chunks. Repeat indexing if the receipt says the limit was reached; matching existing chunks are skipped. Selected CLI document IDs narrow the scope. Catalogue records, archived sources and unavailable text are excluded.

Results contain source ID, page, offset and excerpt, with current original hashes/text checked. A similarity score does not establish support for a claim. Open and read the original. The cache is rebuildable and excluded from workspace ZIPs; a complete installation-data upgrade copies it with the database.

## Drafting, material and history

Notes/Write store Markdown. The supported formatted subset includes headings, emphasis, links, lists, quotes, code and pipe tables. Source beside draft keeps the selected extracted source visible while writing. Outlines insert headings, not invented methods/results.

Import a permitted PNG/JPEG/WebP figure with the figure control and supply its caption. Managed markers use `![Caption](kosh-asset:ID)`; exports resolve only workspace-scoped managed bytes. No external-image URL is fetched. Figures have size/dimension validation, captions and alt text. An imported image's empty extraction unit is not a bibliographic source or textual evidence locator.

For tables, choose CSV/TSV or paste delimited cells, preview exact rows and insert them. The first row becomes headings. Unequal widths are refused; cell line breaks become spaces in Markdown. Original input is unchanged; insertion performs no statistics or derived findings.

Use `$x^2$` for inline equations or `$$...$$` for display equations. A limited safe grammar supports native MathML in readable HTML, native OMML equations in Word and mathematical source in LaTeX. The subset includes fractions, square/indexed roots, superscripts/subscripts, Greek and basic operators. Unsupported commands stay visible/literal; arbitrary HTML/TeX is not executed. Reimporting Word converts supported equations to bounded linear notation and explicitly reports unsupported equations omitted from extraction. This preserves mathematical structure rather than flattening fractions or losing scripts; inspect the original for complete formatting. Native Word visual/pagination proof and TeX compilation remain separate from package/XML tests.

PDF typesets the supported parsed equation subset using vector layout and selectable text, including fractions, roots and scripts. Unsupported or empty expressions, or glyphs unavailable to the renderer, retain source notation in a labelled literal fallback. Inspect the exported equation and its fallback notice before sharing; arbitrary TeX and every mathematical construct are outside this grammar.

Note and draft title/body edits trigger autosave after 900 milliseconds without another edit. The status bar shows pending edits, **Saving…**, **All changes saved**, or a conflict. You can also choose **Save now** or press Ctrl+S. Genuine edits retain prior versions; unchanged saves create no new revision. Saved history lets you inspect earlier bodies without silently overwriting the current draft. Ctrl+K focuses search; Escape dismisses dialogs.

Expected versions protect concurrent writers. A stale update returns a conflict and leaves saved data intact; autosave pauses for that conflicted draft. Your edits remain in the window and browser recovery. Compare both versions and use **Keep mine as a new draft** to preserve an alternative, or **Load saved & preserve mine** to open the saved version after saving your edits as a separate note. When saving fails, keep the window open and read the error. Browser recovery is separate from server-saved history and ZIP backups. A CLI/another window cannot flush your unsaved draft.

## Citations and evidence

The app inserts `[[source:ID:PAGE_OR_UNIT]]` for an explicitly captured location. `[[reference:ID]]` cites bibliographic metadata without asserting a file page. Evidence-matrix source headings use document references; they never invent page 1. Missing/foreign/invalid markers remain explicit export warnings.

Default manuscript exports replace markers using the offline citeproc-js CSL processor and include cited-only references. Built-in pinned styles are APA 7, IEEE and Vancouver using the official NLM citation-sequence independent parent. The selected style controls numbering or author-date text, sorting, citation grouping and ambiguity resolution across the chosen export scope. Valid DOI duplicates share a reference. Citation superscripts/subscripts are preserved in the supported manuscript export formats.

To use another citation style, open **More → Exports & backup → Import journal CSL style**, select a permitted local `.csl` file, and choose the imported style before exporting. Chicago notes is bundled alongside the in-text styles. Choose Footnotes or Endnotes for a note style; in-text styles remain in the text. CSL language choices include 63 bundled locales, a style-default option and locally imported locale XML. Language changes citation terms/date formatting, not manuscript prose.

A dependent style links to an independent parent rather than containing formatting rules. Missing parents/locales block formatting until available locally. In **CSL styles and languages**, import local files or enter an official style ID/locale code and explicitly check the retrieval consent. Retrieval contacts the pinned official CSL repositories for those files and required dependencies; it sends no research content. Consent resets after the operation. Exports never perform network retrieval automatically. CSL formatting does not verify publication metadata or establish journal compliance; inspect the actual result.

File locators stay in optional audit material. Bibliography pages are not reconstructed from captured file pages. Ordinary Word export (`docx`) contains static CSL results; changing a draft later requires another export. **Word with editable citations** (`docxlive`) instead embeds native Word fields and document-local source records. In Word use Ctrl+A, then F9 to regenerate citations and bibliography, and References → Manage Sources to edit metadata. Choose its separate native style: IEEE, APA sixth edition or ISO 690 numerical. These are not equivalents of CSL APA 7, Vancouver or an imported journal style. After deleting a citation, remaining citations renumber; remove its uncited source from Word's Current List if its bibliography entry should also disappear. Review missing-field/type/author/journal warnings before submission.

Evidence rows are manual notes for a source, question, reported design, findings and limitations. A model extraction proposal has exact quote/citation anchors but unverified interpretation. Review each quote and every proposed field before saving evidence. Kosh does not conduct formal screening or restricted clinical abstraction.

Writing check reads the exact saved draft version, reporting headings, words, unresolved locations and incomplete metadata. It changes no content. It is not plagiarism detection, statistical review, scientific fact checking or submission approval.

## Questions and writing proposals

AI is optional. Ordinary reading, notes, lexical search, citations, exports and backups need no provider account. Local AI needs a separately installed Ollama service/model and sufficient hardware. Codex/Claude help needs your own installed supported CLI, authenticated account and provider access; provider subscription/usage charges and limits are separate from Kosh. No free provider allowance is promised. Review the outbound preview before sending sensitive content, and inspect outputs before use.

Source excerpts is labelled retrieval without generation. An explicitly selected installed Ollama model can generate locally through loopback. Kosh also detects supported installed Codex/Claude entrypoints; detection does not establish sign-in, model readiness or free usage. Their providers may receive approved content outside this computer.

Available tasks include ask, continue, grammar, translate, abstract, clarity, shorten, outline, critique and draft extraction. Save/select exact writing or a source passage. Translation needs an explicit target language. Custom writing instructions are bounded and visible in the outbound preview. Missing methods/results remain author input, not a licence to invent them.

Review the exact content Kosh supplies, then approve that single request. Installed CLIs may add their own instructions/environment metadata; configured restrictions are not independently verified full-request privacy or OS isolation. A cancelled preview sends nothing. Five-minute prepared tickets are one-use; a changed source/draft needs a fresh preview. CLI/MCP consent flags attest the caller's authority, not a verified human approval.

Review the proposal and its source warning. Save a separate alternative to preserve the original, or explicitly apply an eligible reviewed selection. Apply checks the saved version, exact unique selection and protected source/figure markers. Only shortening, clarity, grammar and translation are eligible selection replacements. Abstract, continuation, outline, critique, ask, extraction and folder tasks stay separate proposals. Repeated/changed selections are refused; save an alternative when a fresh exact apply cannot be established. Continuation remains proposed writing to inspect, not automatic invented results.

Assistance history retains jobs/results. Completed jobs can be read back; a running/failed/uncertain job after interruption is not automatically resent, because provider usage may already have occurred. Inspect history before initiating another request. Citation-ID/quote checks locate supplied content, but do not certify claim entailment or model quality.

## Chosen-file editing

Folder edits selects one existing absolute folder and explicit relative UTF-8 paths. Prepare full replacement text or ask a supported installed/local provider to propose replacements for those exact files. A model preview lists selected content; approving that send only produces a diff. It does not authorize file publication.

Review target, before/after hashes, exact diffs and BOM/line-ending warnings, then separately approve the one-use 15-minute apply ticket. Limits are 10 files, 256 KiB each, 1 MiB combined originals/replacements and a 24 KB model prompt. Only MD/TXT/BIB/TEX/CSV with existing parents are supported. No recursive folder inventory, directory creation, deletion, arbitrary binary write or shell is exposed. Protected/reparse/traversal paths and changed files refuse.

Each target is rechecked; originals/receipts stay in app data. Publication is atomic per file, not an all-or-nothing batch, so inspect partial/error receipts. History can prepare recovery of replaced originals for another approval. Newly created files are not automatically deleted. Workspace ZIPs exclude external-folder targets and recovery journals; preserve the selected folder's own backups and stopped complete app data.

## Exports, reading bundles and workspace transfer

Save first. Writer exports the selected saved draft; Tools can export the workspace's notes/evidence. Default presentation contains title/body/References, without app instructions or internal file locators. Use explicit audit output for metadata/provenance warnings and separate genuine evidence/document references.

**Export options** retains per-workspace choices in this browser. Choose no template, research article, review or case report; A4/Letter, Times New Roman/Arial/Calibri, 9–14 pt, line spacing 1–3 and margins 15–40 mm. Page/line numbers, a title page and a running title are optional. Authors, affiliations, correspondence, abstract and keywords begin empty. You supply them; Kosh invents no frontmatter. Blinding omits supplied authors/affiliations/correspondence only, leaving the body, figures and references untouched. Review identifying content yourself. A configurable profile is not a named-journal template or submission certificate. Appending a profile outline is a separate explicit draft edit; changing export options alone never adds saved headings.

| Format | Use |
|---|---|
| MD | Editable Markdown; managed figure IDs still belong to Kosh |
| DOCX | Formatted Word text, lists, links, tables, figures and static citations |
| Word with editable citations | Native Word fields and embedded sources; update in Word using its separate native style |
| PDF | Formatted pages/tables/figures; supported equations use vector layout/selectable text, with labelled literal fallback for unsupported expressions |
| TEX | Editable XeLaTeX/LuaLaTeX source; managed figure caption placeholders |
| TeX ZIP | `main.tex` plus supplied local figures; compilation/fonts/journal finishing are separate |
| Compiled LaTeX PDF | Bundled offline Tectonic compiles Kosh-generated source and managed figures; advanced allowlisted equations |
| BIB / RIS / CSL JSON | Publication metadata exchange; no paper text or invented fields |
| CSV | Evidence records with leading formula guards; not statistical analysis |
| HTML | Self-contained readable manuscript/figures; limited native MathML |
| Portable reading ZIP | `index.html`, referenced figures and a dated README with citation style/unverified-metadata notice; extract the whole ZIP first |

Manuscript reference lists are cited-only. A selected-draft bibliography export uses its referenced metadata; a workspace bibliography can include all nonfigure records. Reading bundles are not restorable workspaces. Export does not redact identifiers or obtain permissions; inspect before giving research to someone.

Compiled LaTeX PDF (`texpdf`) uses the bundled compiler and resources without package downloads. PDF with a template or CSL note placement also uses that typesetting path; ordinary non-template in-text PDF retains the vector renderer described above. The compiled path supports allowlisted sums, integrals, matrices, aligned/cases environments and other advanced mathematical commands. Unsupported equation commands refuse compilation. Prose/document structure is generated and escaped; an imported arbitrary `.tex` document cannot be compiled through this export. Untrusted mode disables shell escape but is not OS filesystem isolation. Missing glyphs refuse output with a generic font error rather than returning a PDF with silently omitted characters. Use Word or HTML when the supplied characters cannot be rendered.

The portable TeX fonts are TeX Gyre Termes for the Times choice and TeX Gyre Heros for Arial/Calibri choices. These are equivalent serif/sans families, not exact Microsoft font matches. Inspect pagination and typography before sharing. If the compiler/resources are missing, the dialog reports that status and disables compiled PDF; source/figure ZIP exports remain available.

### PDF export fonts in 0.3.1

Version 0.3.1 corrects the incomplete default Latin Modern font bundle from 0.3.0. The bundled roman, sans and monospace font definitions now have all their referenced files, including optical sizes needed by footnotes. The default 11-point no-template Chicago-note export and the existing research-profile export are checked against the shipped runtime. You no longer need to switch manuscript profiles to work around that omission. This does not guarantee support for every Unicode character or arbitrary TeX command; review the exported document before sharing.

Workspace backup is different: current originals/notes/metadata/chats/evidence, with optional saved note/evidence revisions. Neither choice prunes local history. Restore validates schema/paths/sizes/hashes and creates a fresh workspace. Save and verify restored records. ZIPs are unencrypted and exclude source/runtime/model weights, Edge/unsaved browser recovery, external-folder journals, rebuildable embeddings and the separate assistance-job/result journal. Use a stopped complete data-copy upgrade when that local job history/recovery must travel too.

Bounds include 32 MiB per imported file, 47 MiB per export/backup ZIP, 1,000 items per main backup collection and 5,000 included revisions, with separate extraction/manifest limits. Oversized history/archive is refused without deleting records.

After restore, PDF/Word quotes that no longer match the current text extractor are retained in chat audit history as unverified and excluded from active citations. The restore warning reports their count. Original files and notes still recover; inspect the originals before relying on old answers. Identity, hash and source-bound checks still apply. A workspace ZIP is not an authenticity signature.

## Upgrade a bundled installation

1. Save and quit the old app; close its dedicated Edge window/profile.
2. Install the new edition into a new folder with **Open after installation unchecked** (or `--no-launch`). Do not open it: new `data` must be absent, even an empty directory refuses.
3. Run the new helper in dry-run mode with explicit old/new paths.
4. Review the summary, then repeat with `--apply`. Add `--retarget-shortcuts` only if you want matching old-launcher links retargeted.
5. Inspect `UPGRADE_RECEIPT.json`, open the new app and verify your saved records. Retain the old installation/recovery until satisfied.

```powershell
& 'C:\chosen\new Kosh\runtime\python.exe' -I 'C:\chosen\new Kosh\upgrade.py' --old-install 'C:\chosen\old Kosh' --new-install 'C:\chosen\new Kosh'
& 'C:\chosen\new Kosh\runtime\python.exe' -I 'C:\chosen\new Kosh\upgrade.py' --old-install 'C:\chosen\old Kosh' --new-install 'C:\chosen\new Kosh' --apply --retarget-shortcuts
```

The helper verifies installed manifests, stopped services/profiles, complete copy hashes, SQLite integrity/counts/logical hashes and supported schema version. SQLite backup operates on staging, retaining raw DB/WAL recovery and old bytes. It starts/stops no service and migrates no schema. Existing destination data/receipts are never overwritten. Shortcut changes retain backups and preserve unrelated targets.

Failures retain staging. Data can have published successfully even if a later receipt/shortcut action failed; read the reported publication state and retained error/receipt before retrying. Shortcut batches can be partial. A successful copy is not proof of launching the new app. The app's own supported schema initialization is a separate step.

## Source edition

The source edition needs the runtime in `requirements.txt` and matching local Node: `tools/node/node.exe`, or the already installed development fallback at `C:\Program Files\nodejs\node.exe`. Run `Setup Research.cmd`, then `Open Research.cmd`. Setup checks/builds without downloading software or models. A missing citation component requires repair or a separately approved run of the pinned component-fetch helper; it is never downloaded automatically. See [Build from source](BUILDING.md) for the offline preparation instructions. These steps are separate from the bundled installer workflow above.

## Troubleshooting and privacy

- Missing original: reimport identical bytes; its ID, notes and metadata remain. Changed originals refuse replacement.
- No extracted scan text: inspect the page and local OCR capability, then review a separate derivative.
- Embedding/model unavailable: continue with lexical search/excerpts; optional installation is a separate explicit action.
- Citation runtime/style unavailable: restore pinned local CSL/Node components, import required local parents/locales, or explicitly approve the separate official retrieval action. Export downloads nothing and uses no basic formatter fallback.
- Stale saved version: inspect current/history and preserve a separate alternative rather than blindly retrying.
- Interrupted provider request: inspect durable history; it may have consumed usage and is not automatically resent.
- New upgrade destination already has data: retain it; choose another fresh unlaunched installation.
- Startup error: read the launcher message; do not publish private session files or research contents. Reconfigure a moved source-edition Python using setup.

Data is local and unencrypted, with a trusted-local-user boundary and no hostile-file/compiler OS sandbox. Citation processing and local import stay local; explicit official CSL retrieval sends file identifiers, discovery queries reach selected indexes and approved installed-provider content may reach those providers. Actual runtime/model output, native pagination, real-paper acceptance, signing and another clean computer need separate proof. Removing a shortcut leaves research intact; no automatic deletion workflow is prescribed.

Imported CSL styles/locales live in local app settings (`data/citation-styles`). Keep original files and dependencies when transferring a workspace ZIP; import them on the receiving computer. A complete copy-only installation upgrade preserves them. A missing selected style/dependency is reported and must be resolved before relying on exported formatting.
