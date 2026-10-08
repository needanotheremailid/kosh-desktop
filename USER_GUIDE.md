# Kosh user guide

Start with [installation](#first-launch-and-a-first-useful-session) and [your first workspace](#your-first-workspace). Return to [reading](#reading-place-organisation-and-saved-passages), [writing](#drafting-material-and-history), [citations](#citations-and-evidence), [exports](#exports-reading-bundles-and-workspace-transfer), [backup and recovery](#new-in-100-rc1), [upgrading](#upgrade-a-bundled-installation) or [troubleshooting](#troubleshooting-and-privacy) when needed.

## First launch and a first useful session

**[Download the Kosh 1.0.0-rc.2 Windows installer](https://github.com/needanotheremailid/kosh-desktop/releases/download/v1.0.0-rc.2/Kosh-1.0.0-rc.2-Setup.exe)** from [this repository's release](https://github.com/needanotheremailid/kosh-desktop/releases/tag/v1.0.0-rc.2). Use 64-bit Windows 11 with Microsoft Edge and .NET Framework. The installer is unsigned; Windows may warn about an unknown publisher. Check the release origin and published checksum before deciding whether to run it. Keep a backup and try a permitted non-sensitive paper first. No separate Python, Node, TeX, AI account or model is required for the ordinary bundled reading/writing/export workflow.

The bundled edition installs with `Kosh-1.0.0-rc.2-Setup.exe` into a new folder for your Windows user. Edge and .NET Framework are prerequisites; the prepared Python/document runtime and Node.js 24.14.1 local citation tool are included. Installation does not need an administrator or download packages. Existing shortcuts are preserved.

This guide targets Kosh 1.0.0-rc.2. Historical sections retain their introduction versions. Older installations keep their prior behavior until upgraded to a matching package. The optional [signing workflow](SIGNING.md) requires an already provisioned trusted publisher identity; the installer is not signed just because that workflow is available. Tests on one computer do not prove another clean Windows computer or every real manuscript. Independent trials remain pending in [the acceptance checklist](ACCEPTANCE.md).

## New in 1.0.0-rc.2

- **Reading place kept.** Opening a source from the Library returns to its remembered page instead of page 1; earlier candidates overwrote the saved page a moment after a plain open. Search results, highlights, claim links and citation chips still open their own page.
- **Suggested PDF details.** Importing a PDF fills an empty title from the file's embedded details and a DOI found on its first two pages. Source details shows a provenance line for these suggestions; verify them against the publication, or use the DOI in **More → Discover references → Lookup exact DOI or PMID** to fetch catalogue metadata. No author or year is guessed and nothing is sent anywhere.
- **Incomplete-reference warning.** After a draft export, Kosh runs the saved-version writing check and names cited sources whose bibliography fields are missing, because their reference entries are incomplete in that file. The CLI `export --note` command returns the same warning.
- **Editable Word fields read correctly before refresh.** Citations and the bibliography carry the rendered default-style text, so reviewers without a field refresh still see numbers and references; Word regenerates them into its own style on update.
- **Clearer revision comparison.** Citation markers display as source titles (the exact marker stays in the tooltip) and swapped words within a changed line pair are highlighted.
- **Backup folder status.** Re-saving backup preferences clears the previous failure message, and an unplugged folder lists no sets with an explanation instead of failing the dialog; saved sets remain where they were written.

## New in 1.0.0-rc.1

**One local backup flow.** Open Settings → Automatic local backups or Exports & backup → Local workspace backup & restore. Choose **Save workspace ZIP locally** to select a new filename; history is included and an existing ZIP is never overwritten. Choose **Choose ZIP & preview restore** for an existing local archive. You can also expand the path controls and enter an exact local path. Review the preview and explicitly approve restoration into a separate workspace. Cancelling file selection changes nothing. The optional browser-transfer controls retain the older 47 MiB limit; ordinary local ZIPs use streaming files.

Progress shows the current copying/validation phase and bytes when measurable. **Cancel current operation** requests cancellation at the next safe checkpoint. A native PDF/image parser must finish its current operation first. Cancellation is unavailable once publication or an approved restore starts. Existing saved work and completed backups are retained. Incomplete files/folders may be retained for recovery; the panel reports their location when available. They are not completed backups and are never pruned automatically. Preview needs temporary disk space approximately equal to the selected ZIP; restoration also needs room for the extracted originals and database.

If a progress request is interrupted, the panel retries a few times. **Resume tracking** reconnects to that same job; it does not start another backup or restore. Wait for its result before starting a replacement operation.

**Automatic backup schedule.** Choose an existing folder with the folder button or enter its path, select the interval, then save. The schedule remains off until enabled. Manual workspace ZIPs work while the schedule is off. An unavailable drive reports failure without removing earlier backups or changing existing work. Reconnect it or select an available folder. Backup ZIPs are unencrypted; select storage accordingly.

**Check this installation.** In Settings, choose that button to inspect component availability and remedies. Optional local AI is not contacted. The check reads fixed local components; it does not scan your research or verify every file in the installer. Choose **Preview diagnostics JSON**, read it, then **Download this preview** if useful. The exact preview becomes the local report. It omits research content, titles, filenames, user paths, counts, settings, logs and tokens; nothing is uploaded.

**Update recovery.** A verified installation retains local activation proof so losing an old download cache does not lock it again. A failed final readiness write can be recovered only from matching retained verification records. A candidate without proof remains read-only. Keep the previous installation until the new one is working. Version 0.6.0 cannot discover RC tags, so use the copy-only upgrade below for this transition. RC and pre-1.0 builds can offer prereleases; final 1.0+ builds offer final releases only. Checks inspect the first ten published release records from the fixed repository.

If an update worker stops unexpectedly, an unattended verification service releases its local port after about two idle minutes. An open Kosh window keeps its service alive, so use **Quit app** and close that candidate window before reopening the previous installation for recovery. Successful activation restores the normal idle setting. Never merge the old and new data folders by hand.

### Workspace backup or full recovery copy?

| Copy | Includes | Use it for |
| --- | --- | --- |
| Workspace ZIP | Managed originals, saved documents/notes/evidence/chats, reading/reviewer records and selected history | Moving one workspace or restoring it separately |
| Automatic set | A validated workspace ZIP with history for every workspace | Routine saved-work recovery while Kosh is open |
| Complete stopped `data` folder | Database and originals plus browser profile/unsaved recovery, separate assistance/folder journals, settings and caches | Full recovery or a copy-only installation upgrade |

For a full recovery copy, first preserve or resolve pending edits, use **Quit app**, close its Kosh window, and copy the entire `data` folder inside the installation to a separate destination. Keep the original. Do not merge individual SQLite, browser-profile or original files from different snapshots. A full data copy contains private material and is not a portable sharing ZIP.

### Removing Kosh while retaining your work

Kosh uses a self-contained per-user folder and shortcuts; this installer does not register an automatic uninstaller. Quit Kosh and close its window first. Locate the exact installation through the shortcut's target, preserve and verify a separate full data-folder copy, then remove that installation and its matching shortcuts through Windows when you choose. Data lives inside that installation: deleting the whole folder also deletes its data. Older installations kept during an upgrade are separate recovery copies. Downloaded backups and reports in other folders are not removed. Reinstalling into a new folder does not automatically reconnect old data; use the copy-only upgrade or a workspace restore.

### Measured operating range

One local Windows run used 256 four-page PDFs, 50 drafts of about 60,000 characters and 250 saved revisions. A 556,711,930-byte ZIP backed up in 6.28 seconds, previewed in 10.46 seconds and restored in 23.84 seconds; original hashes, note versions, revision counts and SQLite integrity matched. These backup measurements preceded the RC progress controls. After the search correction, the same library's five searches had a 0.112-second median and 0.220-second maximum at the service layer. This is an invented nonclinical workload, not a benchmark of your papers or a maximum capacity claim. Disk, document complexity and background load matter. The approximately 31.3 GiB validation ceiling is **not** a tested operating size. The [repeatable benchmark and independent-use checklist](ACCEPTANCE.md) state the method and remaining checks.

## Your first workspace

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

**Filter source details** narrows the library by saved title, filename, author, year or DOI as you type. Words may match across fields; matching ignores case and accents. Combine it with **File type**, or sort by recently imported, title or publication year. Year sorting uses a four-digit saved year, newest first, with missing or nonnumeric years last. These controls change only the displayed list, not your records. Filters survive opening a source and returning; changing workspace clears them. **Clear filters** restores the full active or archived list. The Stacks reading sidebar continues to show all active sources.

**Search passages** is separate: it searches extracted text across all active sources in the workspace, regardless of list filters. Its results show that scope explicitly. List controls pause while searching or showing passage results; **Source list** restores your existing filters and keeps your query available. Editing the passage query clears old results before the next submission. Clearing, cancelling or changing scope discards late responses; a failed search shows a retry action. Ctrl+K still focuses passage search. These library improvements require Kosh 0.4.0; installer 0.3.1 retains its earlier controls.

PDF page numbers are actual one-based file pages even when printed numbering differs. Read can show the original image and extracted text. DOCX/text locations are extraction sections, not native Word pagination. DOCX extraction includes paragraphs/tables and headers/footers, with exclusions for text boxes, drawings and embedded objects. Check the extraction notice.

Lexical search returns matching extracted passages. Open the source and inspect context; a different term can miss relevant material. Importing/searching a document does not mean every page was automatically analysed.

For a scanned PDF, select **Create OCR copy of this page**. Local capabilities determine which English/Hindi/Punjabi languages (`eng`, `hin`, `pan`) are available. Bundled language data is preferred when present; a supported local Tesseract installation can supply it otherwise. Clicking OCR downloads nothing and sends no audio or document to a cloud OCR service.

OCR creates a separate managed PDF. Original bytes and existing source citations stay intact. The receipt maps derived-page numbers to original file pages. Captures from the derivative refer to its own ID/pages; consult the mapping to inspect the original. Recognition can change words, digits and negation, so review against images before using it as evidence. The CLI can select up to 20 distinct actual pages, sorted into a derivative; each page has a 20-million-pixel limit and the output has a 32 MiB limit.

The bundled Windows installer includes English, Hindi and Punjabi OCR data and its licence notices. Optional embedding weights remain a separate installation.

## Reading place, organisation and saved passages

In Read, expand **Reading place and organization**. Choose **Unread**, **Reading** or **Read**, mark a favorite, enter comma-separated tags and one collection label, and record a next action. Choose **Save reading place and details** to save those fields. Opening a source page remembers its reading position automatically. Opening that source again from the Library, or through the Library's **Continue reading**, returns to the saved page; search results, highlights and citation links open their own page instead. A next action is your own note, not a scheduled task.

Library filters for reading state, favorites, an exact tag and collection narrow the displayed source list alongside the existing metadata/type controls. Tags are multiple labels; Collection is one label per source, not a nested folder tree. Switching workspace clears the display filters. Passage search still searches all active sources and pauses the list filters.

For a PDF with extracted words, select complete words over the original page image, add a comment and choose **Save highlight**. Text view can also capture a quote; PDF quotes must match complete, consecutive source words. If the same quote occurs more than once on the page, select it on the image to identify the exact occurrence. Image-only pages need a separately created OCR copy before word selection is available. For DOCX/text, select a passage in extracted text and choose **Save passage**; its locator is an extraction section, not Word pagination.

Saved passages show the exact quote and your separate comment. **Go to passage** opens the saved location; PDF highlights overlay that page in Kosh. **Create cited note** creates a separate Markdown note containing the source locator, quoted passage and comment. Annotations are stored separately from the source: Kosh does not write highlights or comments into the original PDF or replace its bytes. Saving a passage is not verification of its meaning. Failed or conflicting saves retain the capture for review and retry.

In Library, expand **Review possible duplicate sources** and choose **Find review candidates**. Kosh compares saved title and DOI values and displays possible pairs with source details. This is a read-only suggestion list: matching metadata does not establish identical papers, and Kosh never merges records, rewrites citation IDs or deletes originals automatically.

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

**Find drafts** in Write and **Find notes** in the Notes panel search titles and Markdown bodies in the active workspace. Every word you enter must occur somewhere in the title/body; matching ignores case and accents. Excerpts show context near a matching word. Unsaved text held in this window participates, with an Unsaved or Conflict label where applicable. **Recently saved** uses the last saved date; **Title A–Z** sorts by the displayed title. Filtering and sorting do not change your text or switch the open draft. If it falls outside the results, a notice explains why it is still open. **Clear search** restores the list; navigation retains the search, and switching workspace clears it. These controls require Kosh 0.4.0 and are not in installer 0.3.1.

Choose **Focus writing** to hide navigation, the source sidebar, export controls and formatting toolbar while keeping the title, editor and writing controls visible. **Exit focus · Esc** or Escape returns to the normal layout. An open dialog keeps its normal Escape behavior. Focus mode changes the view only; Markdown, citations, autosave and recovery keep their existing behavior.

Expand **Claim review & sections** to navigate or reorder Markdown sections. A single document title stays in the preamble when peer sections exist below it. The arrows swap adjacent complete sections, including their nested headings, tables, quotes and citation markers; they do not convert Markdown into rich text. Moves are disabled in Preview or for a conflicted draft. If the final section has no trailing newline, Kosh asks you to add one before moving it so every existing character stays intact. Normal autosave and revision history apply.

Import a permitted PNG/JPEG/WebP figure with the figure control and supply its caption. Managed markers use `![Caption](kosh-asset:ID)`; exports resolve only workspace-scoped managed bytes. No external-image URL is fetched. Figures have size/dimension validation, captions and alt text. An imported image's empty extraction unit is not a bibliographic source or textual evidence locator.

For tables, choose CSV/TSV or paste delimited cells, preview exact rows and insert them. The first row becomes headings. Unequal widths are refused; cell line breaks become spaces in Markdown. Original input is unchanged; insertion performs no statistics or derived findings.

Use `$x^2$` for inline equations or `$$...$$` for display equations. A limited safe grammar supports native MathML in readable HTML, native OMML equations in Word and mathematical source in LaTeX. The subset includes fractions, square/indexed roots, superscripts/subscripts, Greek and basic operators. Unsupported commands stay visible/literal; arbitrary HTML/TeX is not executed. Reimporting Word converts supported equations to bounded linear notation and explicitly reports unsupported equations omitted from extraction. This preserves mathematical structure rather than flattening fractions or losing scripts; inspect the original for complete formatting. Native Word visual/pagination proof and TeX compilation remain separate from package/XML tests.

PDF typesets the supported parsed equation subset using vector layout and selectable text, including fractions, roots and scripts. Unsupported or empty expressions, or glyphs unavailable to the renderer, retain source notation in a labelled literal fallback. Inspect the exported equation and its fallback notice before sharing; arbitrary TeX and every mathematical construct are outside this grammar.

Note and draft title/body edits trigger autosave after 900 milliseconds without another edit. The status bar shows pending edits, **Saving…**, **All changes saved**, or a conflict. You can also choose **Save now** or press Ctrl+S. Genuine edits retain prior versions; unchanged saves create no new revision. Saved history lets you inspect earlier bodies without silently overwriting the current draft. Ctrl+K focuses search; Escape dismisses dialogs.

In note search, Escape first clears a non-empty query while keeping the panel and search focus. Selecting a note places keyboard focus in its title. Note-search and sorting controls have optional hover explanations, controlled by the existing Settings preference.

Expected versions protect concurrent writers. A stale update returns a conflict and leaves saved data intact; autosave pauses for that conflicted draft. Your edits remain in the window and browser recovery. Compare both versions and use **Keep mine as a new draft** to preserve an alternative, or **Load saved & preserve mine** to open the saved version after saving your edits as a separate note. When saving fails, keep the window open and read the error. Browser recovery is separate from server-saved history and ZIP backups. A CLI/another window cannot flush your unsaved draft.

## Citations and evidence

The app inserts `[[source:ID:PAGE_OR_UNIT]]` for an explicitly captured location. `[[reference:ID]]` cites bibliographic metadata without asserting a file page. Evidence-matrix source headings use document references; they never invent page 1. Missing/foreign/invalid markers remain explicit export warnings.

Choose **Write → Insert citation** to search the active workspace by title, filename, author, year or DOI. Select a reference, then choose **Bibliography reference** or, when available, **Page / section locator**. PDF locators use actual file pages; other documents use extracted sections. Bibliography-only records cannot supply a paper page. Archived sources are hidden unless you enable **Include archived references**. Insertion uses your saved cursor and follows any selected text without replacing it; from Preview it appends to the draft. Cancel leaves the draft unchanged. Normal autosave applies, and your export style formats the citation.

The writer's **Source references** sidebar lists both citation types, their repeated occurrences and unresolved markers. Open a bibliography chip to review saved metadata, or a location chip to read that source page/section. Preview displays the same readable links. Code examples remain literal. These navigation aids do not establish that a source supports a claim; use **Writing check** and inspect the original. The picker and expanded reference navigation require Kosh 0.4.0 and are not in installer 0.3.1.

### Review an exact claim beside its source

1. In Edit Markdown, select one exact sentence on a single line and choose **Review selected claim**. Kosh retains that selected wording; it does not identify or judge every claim automatically.
2. Leave the source empty to record **Needs source**, or select an imported text source and its actual PDF file page/extracted section. Choose **Read this location**, select a passage in the displayed source text and choose **Use selected source passage**, or paste an exact passage from that location.
3. Choose **Save claim review**. Pending draft edits save first. The attachment must be present at the stated source location; catalogue-only references and image records cannot supply an evidence passage. A successful match establishes text/location, not support for the claim.
4. Read the original and its context, then choose **Checked by me** when you have personally checked the claim. This is your review decision, not AI verification or scientific approval.

Saved reviews show claim and source passage side by side. Changing the saved note version, losing the recorded wording, or changing/unavailable source text can mark a review **Review stale**; unsaved edits also make it stale in this window. **Review current wording** starts a new review for the current sentence. **Edit attachment** changes its source passage and resets a checked attachment to Source attached; earlier attachments remain retained. Archive/restore changes review visibility without deleting it. A conflicting save loads the latest review state while retaining your pending selection/fields for review; do not blindly retry an old check.

**Before export** reports the saved review count, stale reviews and claims needing a source. **Save & run writing check** invokes the existing saved-draft mechanical check. Neither is a readiness certificate: inspect figures, captions, required sections, metadata and claim support yourself before sharing. Claim-review records stay separate from manuscript text; saving a review does not insert or rewrite a citation.

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

Workspace backup is different: current originals/notes/metadata/chats/evidence plus reading organisation, saved resume position, annotations and claim reviews, including retained attachment history. Saved note/evidence revisions are optional; neither choice prunes local history. Restore validates schema/paths/sizes/hashes and creates a fresh workspace, remapping source/note links in the reading records. Save and verify restored records. ZIPs are unencrypted and exclude source/runtime/model weights, Edge/unsaved browser recovery, external-folder journals, rebuildable embeddings and the separate assistance-job/result journal. Use a stopped complete data-copy upgrade when that local job history/recovery must travel too.

Bounds include 32 MiB per imported file, 47 MiB per ordinary export or browser/CLI backup transfer, 1,000 items per main backup collection and 5,000 included revisions, with separate extraction/manifest limits. Streaming local manual ZIPs and automatic sets use the larger file-backed bound; the browser/CLI transfer envelope is unchanged. Oversized history/archive is refused without deleting records.

After restore, PDF/Word quotes that no longer match the current text extractor are retained in chat audit history as unverified and excluded from active citations. The restore warning reports their count. Original files and notes still recover; inspect the originals before relying on old answers. Identity, hash and source-bound checks still apply. A workspace ZIP is not an authenticity signature.

## New in 0.6.0

### Larger automatic backup sets

Use **Settings → Automatic local backups**, or **Exports & backup → Large local backups & restore**, for a library that exceeds the manual ZIP limit. Kosh writes each automatic-set workspace ZIP directly to disk and validates it from that file. Select a completed set and its workspace, choose **Validate restore preview**, then approve **Restore into new workspace**. This route keeps the ZIP on disk instead of sending its contents through the browser's JSON upload envelope. Restore still creates a separate workspace; it does not merge or replace existing work.

The automatic route removes the former 47 MiB per-workspace ceiling. The archive has a derived upper bound of about 31.3 GiB per workspace; that is a validation ceiling, not a promise that every library of that size can be backed up. The existing schema and limits remain: 32 MiB per original and per workspace manifest, at most 1,000 items in each main backup collection and 5,000 included revisions. The automatic set's catalogue manifest remains limited to 4 MiB. Extraction, nested-record validation and available disk space can require a smaller set. Preview/restore needs temporary space for a checked archive copy and extraction, plus space for the restored originals. An exceeded limit reports a failure without deleting records or replacing an earlier completed backup. Earlier smaller automatic sets can still use this restore route.

**Download portable workspace ZIP**, manual browser restore and the existing CLI `backup`/`restore` still use the 47 MiB transfer limit. In 0.6.0, larger ZIPs used the automatic-set restore panel; this RC also opens an individual larger archive with **Choose ZIP & preview restore**. Local ZIPs remain unencrypted. Automatic sets contain saved records and history; unsaved browser recovery and pending reviewer fields stay separate. Scheduling, launch catch-up, retained earlier sets and the explicit restore approval follow the controls below.

### Compare saved manuscript revisions

Open a note in **Write → Compare revisions**. Ordinary pending edits save first; resolve a draft conflict before opening comparison. Choose two saved versions of that same note using **Compare from** and **Compare to**. **Load earlier versions** adds older saved-version choices, and **Save & refresh** reloads after the usual save step. The display shows titles and Markdown bodies as plain text in aligned columns, with removed/added body-line counts, changed blocks and a separate title-change indication. **Previous change** and **Next change** navigate differences. Citation and figure markers remain text; comparison does not render or fetch their content. The display itself applies no edit, creates no revision and restores no earlier version.

Only server-saved versions participate; browser recovery and conflicted unsaved alternatives are separate. Line endings count exactly, including LF, CRLF and a missing final newline. For a large changed block, Kosh marks a bounded coarse alignment that pairs its lines by position rather than claiming a minimal line diff. The display pages 200 aligned rows at a time, with full text available across those pages. Read the mode and page notices before interpreting counts or assuming every changed line is visible. A text difference is not an assessment of scientific meaning. **Revision history → Restore this body as a new save** remains a separate action.

## New in 0.5.0

The following four workflows require **Kosh 0.5.0**. The manual bundled-installation upgrade instructions follow them.

### Automatic local backups

Open **Settings → Automatic local backups**, or **Exports & backup → Large local backups & restore**. Enable backups, paste the absolute path of an existing local folder outside Kosh's application/data folders, choose an interval from 15 minutes to 7 days and save the preferences. A separate drive provides better protection against loss of this computer. Fixed or removable local drives are supported; network shares, mapped network drives and linked/reparse paths are refused.

While Kosh is open, the scheduler makes a separate set containing one ZIP for every workspace, always including saved revision history. It catches up once on launch when due, rather than creating one set for every missed interval. No Windows scheduled task is installed. **Back up saved work now** first saves pending edits in this window. Automatic background backups contain server-saved records; unsaved browser drafts and pending reviewer fields remain in browser recovery and are not in a ZIP.

Status shows the last success, last failure, destination/set path, next due time and any current error. Each completed set retains a manifest with build identity, workspace counts, ZIP sizes and SHA-256 values. ZIP bytes are read back and fully restore-validated before success is recorded. A failed or oversized workspace prevents publication of a completed set; the error remains visible alongside any earlier success date. An unavailable drive can still be disabled. A future saved success timestamp is flagged and treated as due. Kosh 0.5.0 limited every workspace ZIP to 47 MiB; the file-backed automatic route in 0.6.0 uses the larger bounded archive described above, while retaining record/history limits.

Refresh the saved sets, select a workspace and choose **Validate restore preview**. Review its title, counts, included history and any unverified citations. Preview changes no workspace. Approve that exact preview, then choose **Restore into new workspace**; Kosh rechecks the ZIP and creates a separate restored workspace. It does not merge or replace existing work. Changed, corrupt or expired previews require another preview.

Earlier backups and incomplete output are retained; nothing is pruned or deleted automatically. Workspace ZIPs remain unencrypted and exclude the browser profile/recovery, external-folder journals, separate assistance-job history and embedding cache. Manual ZIP download and browser recovery remain available.

### Reviewer comments and response letters

Open **More → Reviewer responses**. Choose **New comment**, select a saved manuscript, enter the reviewer/editor label and comment, and provide the exact saved manuscript passage. If it appears more than once, choose its matching occurrence before **Link saved passage**. Save manuscript edits and resolve conflicts before linking. The record retains the saved manuscript version, exact Unicode character offsets and passage, so repeated wording is not silently linked to the first occurrence.

Record **Planned wording / action**, **Revised wording** and **Response for the letter**, then choose **Save comment & response**. Progress is your own record: Open, Planned, Revised wording recorded or Response recorded. Revised status requires recorded revised wording; response status requires a response. These fields do not edit the manuscript. Make and save the actual changes in Write, then explicitly relink the passage when required.

Earlier saved fields and links remain in **Latest saved record & retained changes**. **Archive comment** hides it while retaining its complete record; **Show archived comments** allows review/restoration. Version conflicts retain pending fields and show the latest saved record for comparison. Pending fields are scoped to the workspace and retained in the window/browser recovery; they require an explicit save and are not exported as saved records.

**Export response letter (.txt)** prepares a local text letter from saved records. Archived comments are excluded unless you explicitly select **Include archived comments in the letter**, which starts unchecked. **Show archived comments** changes the list only and does not include them in an export. The letter reports stale manuscript links and whether the recorded revised wording is exactly present in the current saved manuscript. Presence is a text match, not proof of location, context, scientific adequacy or completion of the reviewer's request. Check the actual manuscript and letter before sharing; no submission or message is sent.

Kosh 0.5.0 workspace ZIPs include saved reviewer records, their passage snapshots and retained changes even when ordinary note revision history is excluded. Restore validates/remaps manuscript identities. Old 0.4.0 ZIPs restore in 0.5.0 with empty reviewer records. New ZIPs contain a `reviewer` manifest field that Kosh 0.4.0 does not support; restore them with Kosh 0.5.0 rather than the 0.4.0 installer.

### Project review

Open **More → Project review** for the active workspace. **Save & refresh** saves this window's pending edits, then checks all saved drafts and active recorded claim reviews in that workspace. It displays a check time, drafts without recorded reviews, claims needing a source, stale/current checked claims, unresolved reference occurrences, missing cited-source metadata and per-draft writing checks. Select **Open draft** to address the saved result, or **Reviewer responses** to work on reviewer records.

This is an on-demand saved-state report for one selected workspace. Counts can overlap, and unrecorded claims have not been assessed. A failed draft check displays its reason; incomplete reference/metadata totals are Unknown, not zero. Resolve save conflicts or unavailable checks and refresh. A current claim marked Checked by you records your prior review; the report does not certify entailment, scientific support or submission readiness. It changes no manuscript or source and does not run a provider request.

### In-app updates

Open **Settings → Kosh updates**. Status reads local information only. **Check for updates** explicitly contacts the public `needanotheremailid/kosh-desktop` GitHub releases API. It sends no library, notes or account information. A release must have a newer supported semantic version; RC numeric identifiers are ordered numerically and prerelease status is shown. The channel rules for this RC are described above. A separate **Download installer and checksum** action retrieves the named release installer and its checksum, with bounded HTTPS host/size checks.

**Download matches the SHA-256 published in the same GitHub release. This does not verify the publisher; installers are unsigned.** A matching size/hash proves transfer consistency, not a trusted publisher identity. Changed or incomplete downloads are retained and refused execution.

In a matching installed Windows package, explicitly accept the unsigned publisher status and choose **Save, close and install**. Kosh saves edits, stops its service and backup scheduler, then waits for the dedicated browser window/profile to close. A detached worker installs into a new sibling folder, copies the complete stopped data tree with the existing copy-only helper, verifies candidate startup/build/database, and only then retargets matching shortcuts. The old installation, data and recovery remain intact. A source/development copy can check/download but cannot perform this installed-package action.

If the wait for closing the old window expires, reopen the old Kosh copy and inspect **Settings → Kosh updates**. When a recoverable job is offered, explicitly approve its retained unsigned installer and choose **Save, close and resume retained update**, then close the dedicated window promptly. Kosh rechecks the retained job/installer and resumes without another download. A still-running worker cannot be started again; a partial candidate or uncertain copy/startup needs receipt-based recovery rather than a fresh overwrite. If a checked new copy is awaiting activation, **Finish opening this updated copy** verifies its recorded startup state before enabling edits and its configured backup schedule.

Read the local update receipt on interruption or failure; partial files/candidate staging are retained and no automatic retry overwrites them. Automatic shortcut restoration is limited to an unchanged candidate before ordinary use; newer candidate records refuse that rollback. **Previous installation retained** names the old/current data paths when a valid upgrade receipt is present. Opening an older version shows its older data: newer changes are not copied back, and editing both versions creates separate histories. Choosing to reopen an older installation remains an explicit decision.

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
