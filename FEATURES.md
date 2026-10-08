# Kosh: capabilities and comparison

Kosh is a local Windows research desk with original application code and an attributed offline citation processor, CSL styles and runtimes. Its library starts empty. It adapts research/writing workflows; another research product's accounts, subscriptions, application code and cloud infrastructure are not included. [CREDITS.md](CREDITS.md) and [THIRD_PARTY.md](THIRD_PARTY.md) identify the included dependencies.

This describes Kosh 1.0.0-rc.2, which corrects a reading-place loss when a source was reopened from the Library, keeps saved automatic-backup sets listable when their folder is unplugged, and adds suggested PDF details on import, incomplete-reference warnings on draft export, pre-filled editable Word fields and labelled revision comparison (rows 67-70). Unified streaming local backup/restore with progress and cancellation, Windows file selection, installation health, previewable diagnostics and durable update activation are RC additions. Saved revision comparison and larger automatic sets arrived in 0.6.0. The fixed agent registry remains at 63 tools. Historical rows retain introduction versions. Older installations keep their behavior until upgraded; 0.6.0 cannot discover RC tags. Source, invented test inputs, rendered output, installed release and independent Windows use are separate proof layers. See [acceptance](ACCEPTANCE.md) and matching release receipts for what was tested.

## Available workflow

| Task | Capability | Practical boundary |
|---|---|---|
| Organise | Workspaces, reading state/favorites, multiple tags, one collection label, filters/sorting, archive/unarchive | Collection is not a folder tree; explicit imports; originals/history retained |
| Import | PDF/DOCX/MD/TXT/CSV/BIB/RIS; bibliography and figure workflows | Per-file receipts; parsing coverage/size limits remain explicit |
| Read | Actual PDF page images/extracted sections, selectable PDF words, saved highlights/comments, cited-note creation and remembered reading place | Annotations are separate records; original PDF bytes stay unchanged; non-PDF units are not native Word pagination |
| Search | Lexical passages; optional local embedding index/search | Semantic similarity is a lead, not verified support |
| OCR | Explicit local scan-to-derived-PDF workflow | Available language data required; recognition requires image review |
| Write | Markdown, source beside draft, note/draft search, focus mode, section moves, outlines, formatted preview, read-only saved revision comparison and recovery | Comparison uses saved plain text with bounded/coarse/paginated views; edits and restoration remain separate |
| Review claims | Exact selected sentence beside a quoted source passage; Needs source / Source attached / Checked by me; stale detection and archive/restore | Text/location validation does not establish entailment; Checked by me is personal review, not AI verification |
| Compare duplicates | Read-only pairs from matching saved title/DOI | Suggestions need review; no automatic merge, deletion or citation-ID replacement |
| Insert | Managed figures, reviewed CSV/TSV tables and limited equations | Captions/data stay user-supplied; no automatic analysis |
| Cite | Offline citeproc-js; Vancouver/NLM, APA 7, IEEE, Chicago notes, 63 bundled locales and local styles/locales | Footnote/endnote choice; missing parent/locale must be local or separately retrieved with approval |
| Assist | Questions, continuation, grammar, translation, abstract, clarity, shortening, outline, critique, draft extraction | Exact preview; separate alternative or explicit eligible selection apply |
| Discover | Four indexes, bounded combined search, exact Crossref DOI/PubMed PMID | Catalogue metadata/available abstracts, not full-paper download or formal search |
| Attach | Reviewed catalogue metadata linked to an imported paper | Expected metadata version; both originals remain; identity needs review |
| Export | MD/static DOCX/editable native Word/PDF/compiled LaTeX PDF/TEX/TeX ZIP/BIB/RIS/CSL JSON/CSV/HTML/reading ZIP | Saved scope; audit opt-in; native Word styles separate from CSL |
| Format manuscript | Configurable research/review/case-report layout and optional blank outline | User supplies frontmatter; blinding omits supplied author frontmatter only; no named-journal compliance claim |
| Recover | Note/job history; streaming local ZIPs and automatic sets; progress/cancel before publication; fresh restore; copy-only upgrade | Browser/CLI transfers retain 47 MiB bound; ZIPs exclude browser/folder/job journals and embedding cache |
| Check installation | Explicit fixed-component availability check and optional previewable diagnostics JSON | No research scan, raw logs, paths, provider call or automatic upload; not a full installation-integrity test |
| Use agents | Fixed CLI and 63 MCP tools in 1.0.0-rc.2; 0.4.0 has 57 | No arbitrary command escape hatch; existing note-history reads saved versions; explicit scopes/versions |
| Edit files | Exact local diffs and optional chosen-file model proposals | Separate approval; retained originals; per-file publication may leave a partial batch |
| Use desktop | Getting started, Help, hover explanations, three layouts, light/dark | Preferences do not change research records |

## New in 0.6.0

| Workflow | Behavior | Practical boundary |
|---|---|---|
| Larger automatic backups — Settings or Exports & backup | Write/read ZIPs directly on disk, retain all-workspace history sets, validate an exact file-backed preview and restore into a fresh workspace | Removes automatic sets' former 47 MiB ceiling; about 31.3 GiB derived archive ceiling per workspace, 32 MiB per original/workspace manifest, 1,000 records per main collection and 5,000 revisions; manual browser/CLI ZIP transfer stays 47 MiB |
| Compare revisions — Write | Two saved versions of the same note, aligned plain-text title/body columns, removed/added line counts, title changes and difference navigation | Ordinary pending edits save before opening; the display makes no edit or restore; conflicted alternatives excluded; coarse large-block alignment disclosed, 200 rows per page |

The archive schema is unchanged. Size, extraction, nested-record and available-space checks still apply, so the larger archive bound does not make backups unlimited. Comparison counts describe text changes, not their scientific adequacy. The agent interface retains the same 63 tools.

## New in 0.5.0

Settings adds **Automatic local backups** and **Kosh updates**. More adds **Reviewer responses** and **Project review**. Backups retain saved workspace history; reviewer records stay separate from manuscript edits; project checks expose unknown results; update execution requires separate unsigned-publisher approval. Six agent additions bring the fixed registry to 63 tools. Details and limits follow the retained 0.4.0 overview.

## Reading and writing additions for 0.4.0

Version 0.4.0 includes local library metadata/type filters and imported/title/year sorting. These affect only the displayed list and are separate from workspace-wide passage search; they are not included in installer 0.3.1.

Notes and Write provide workspace-scoped title/body search, contextual excerpts and recently-saved/title sorting. Search includes the draft text currently held in this window and leaves the open editor in place, even when it is outside the results.

Write includes a searchable citation picker for workspace sources and bibliography records, optional valid file-page/section locators, archive opt-in, and insertion after selected words. The reference sidebar and Preview link both bibliography and location citations and expose unresolved markers. Export formatting continues to use the existing offline CSL engine.

Reading adds exact PDF word selection/highlight geometry, saved quoted passages/comments, source-linked note creation and return to saved locations. Reading state, favorites, multiple tags and a single collection label support library organisation. The last reading page is remembered; the next-action field is a user note, not an automation. Possible duplicate title/DOI pairs are suggestions only.

Focus writing retains the title/editor/writing controls and hides surrounding navigation, export and formatting controls, with visible Exit and Escape. Section arrows swap adjacent complete Markdown sections and keep nested content/markers together. The preamble remains in place; a missing final newline refuses the move rather than changing characters. Preview/conflicted drafts disable moves.

Claim review is user-driven: select an exact sentence, attach a passage from an actual source page/section, then personally mark it checked. Saved note/version, wording and source changes can make the record stale; unsaved edits are also marked stale in the current window. Changing a checked attachment requires review again and retains earlier attachments. Reading records are included in current/history workspace backups and remapped during fresh-workspace restore. Use Kosh 0.4.0 to access these controls.

## Backup, reviewer and update workflows in 0.5.0

These four workflows require Kosh 0.5.0. Their controls are found in Settings or More as shown below.

| Workflow | Current-source behavior | Practical boundary |
|---|---|---|
| Automatic local backups — Settings | Explicit opt-in, user-selected existing local folder, 15-minute–7-day interval, one launch catch-up, complete sets for all workspaces with history, readback/restore validation, last success/failure and exact restore preview; also available in Exports & backup | Runs only while Kosh is open; local manual ZIPs and automatic sets use streaming files in this RC, while browser/CLI ZIP transfer stays 47 MiB; no pruning or Windows scheduled task; browser-only recovery is excluded |
| Kosh updates — Settings | Separate public GitHub release check, named installer/checksum download and unsigned execution approval; fresh sibling installation, stopped data copy, startup/build/database checks before shortcut retarget | Installed-package execution only; old copy/data retained; interrupted work needs explicit resume/recovery; newer candidate records block automatic shortcut rollback |
| Reviewer responses — More | Exact saved manuscript passage/version/occurrence, manual comment/planned/revised/response fields, expected reviewer version, retained field/link changes, archive/restore and saved local text-letter export | Records do not edit the manuscript; stale links and revised-wording presence are disclosed; pending fields remain separate browser recovery; no provider request or submission |
| Project review — More | On-demand saved draft/active recorded-claim review across the selected workspace, timestamp, per-draft checks, unresolved references, missing metadata, stale/source-needed/current checked claim counts and draft navigation | Counts can overlap; unrecorded claims are unassessed; failed checks show reasons and Unknown incomplete totals; no scientific-support or readiness certification |

Update transfer wording is fixed: **Download matches the SHA-256 published in the same GitHub release. This does not verify the publisher; installers are unsigned.** Reading update status makes no network request. Checks, downloads and execution require separate user actions; library/notes/account information is not sent.

Kosh 0.5.0 ZIPs include reviewer passage snapshots and retained comment changes even with ordinary note revision history excluded. Old 0.4.0 ZIPs restore in 0.5.0 with empty reviewer state. New ZIPs carry the `reviewer` manifest field and cannot be restored by Kosh 0.4.0; use 0.5.0 to restore them. Workspace ZIPs remain unencrypted and distinct from a complete stopped-installation data copy.

Six new fixed CLI/MCP operations bring Kosh 0.5.0 to **63 tools**: selected-workspace project review, reviewer state/save/text export, automatic backup status and local update status. Backup/update tools read status only; they do not change preferences, run a backup, restore, contact GitHub, download or install. See [the agent interface](AGENT_API.md) for exact scopes and file/version contracts.

## Complete original 22-item ledger

The original approved Beeblio inspection produced these rows. Included means workflow coverage, not measured equivalence to Beeblio or a commercial service. Local additions/bounded adaptations are identified.

| # | Original workflow | Kosh implementation |
|---|---|---|
| 1 | Create/reopen workspaces | Separate saved local projects |
| 2 | Import formats | Managed documents, multi-record bibliography and figure imports |
| 3 | Read pages/text | Original PDF images, extraction notices and separately requested OCR copies |
| 4 | Search/open passages | Lexical and optional source-anchored local semantic retrieval |
| 5 | Save/conflicts | Expected versions, retained revisions, browser recovery |
| 6 | Citations/bibliography | Explicit file locators and document-level references; entered/imported metadata |
| 7 | Markdown/Word export | Formatted blocks, tables/figures; default static CSL results or separate editable native Word fields |
| 8 | Local-model questions | Installed Ollama or labelled excerpts without generation |
| 9 | Evidence scope | Bounded excerpts/citation-ID warnings; no entailment certification |
| 10 | Windows launch | Original native launcher and Edge app window |
| 11 | Backup/restore | Current snapshot or optional history; validated fresh workspace |
| 12 | Evidence/CSV | Manual records and formula-guarded CSV |
| 13 | Archive/unarchive | Reversible visibility; originals retained |
| 14 | PDF export | Formatted pages with tables, Unicode and embedded figures; supported equations use vector layout/selectable text; labelled fallback for unsupported expressions |
| 15 | BibTeX | Stable source keys; explicit fields; DOI/URL handling |
| 16 | Desktop appearance | Broadsheet/Stacks/Commonplace; light/dark; context panel |
| 17 | Autonomous shell | Excluded: no arbitrary command executor |
| 18 | Selected-folder editing | Bounded adaptation: named text files, exact diff approval, hashes/recovery |
| 19 | Online discovery | Bounded adaptation: explicit single/combined index queries or identifier lookup |
| 20 | Cloud sharing/Office | Local reading exports/workspace transfer; no cloud sync or Office Online |
| 21 | LaTeX | Editable source/source-figure ZIP or bundled offline compilation of generated source |
| 22 | Agent control | CLI and MCP over the authenticated local service |

## Expanded approved workflows

| # | Workflow | Implementation and limits |
|---|---|---|
| 23 | Empty library/onboarding | No development records in normal installation; reopenable Getting started/Help |
| 24 | Three retained designs | Structurally separate Broadsheet, Stacks, Commonplace; appearance changes no research data |
| 25 | Hover explanations | Optional visual hints; explanatory labels remain available to assistive technology |
| 26 | Citation formats | Offline CSL engine; APA 7/IEEE/Vancouver/NLM and Chicago notes; local style/locale import; 63 bundled locales; footnote/endnote placement |
| 27 | Citation ambiguity | Selected CSL style controls sorting, grouping and ambiguity through citeproc-js; metadata still requires review |
| 28 | Clean manuscripts | Title/body/References; file locators and review material only in explicit audit |
| 29 | Bibliography exchange | Multi-record RIS/BibTeX/CSL JSON preview/import; unsupported fields/macros reported |
| 30 | Catalogue attachment | Versioned metadata link; both records/originals remain |
| 31 | Figures | Scoped PNG/JPEG/WebP assets, captions/alt text; no external-image fetch |
| 32 | Data tables | Reviewed CSV/TSV into Markdown; real DOCX/PDF tables; no computed findings |
| 33 | Equations | Safe parsed subset: HTML MathML, native Word OMML, editable LaTeX and PDF vector layout/selectable text; unsupported/empty/unavailable-glyph PDF expressions use labelled literal fallback |
| 34 | Writing proposals | Continue/grammar/translate/abstract plus earlier tasks, selected saved text and preview |
| 35 | Reviewed apply | Separate alternative or explicit eligible replacement; version/selection/marker checks |
| 36 | Extraction proposals | Exact quote/citation anchors for review; interpreted fields remain unverified |
| 37 | Durable history | Draft revisions and assistance job/results; interrupted provider jobs not automatically resent |
| 38 | Local OCR | Selected actual pages; separate derivative, language/provenance and original-page mapping |
| 39 | Local embeddings | Explicit index/search; hash/text rechecks; incremental 200-chunk requests; rebuildable cache |
| 40 | Combined discovery/lookup | First bounded page from four indexes; DOI dedupe; failed-index disclosure; exact DOI/PMID |
| 41 | Chosen-file agent work | Exact files into provider preview; generated diff; separate target-write approval |
| 42 | Portable reading | HTML or HTML/figure ZIP; manuscript, workspace backup and software are distinct packages |
| 43 | Copy-only upgrade | Verified fresh install; stopped complete data copy; staged SQLite backup/hashes/recovery |
| 44 | Shortcut retarget | Explicit flag; exact old-launcher targets only, retained backups/readback |
| 45 | MCP | 57 schemas in 0.4.0; 63 in 0.5.0 and 0.6.0 with the six project/reviewer/status additions; no generic command escape hatch or unsolicited registration |
| 46 | Free source/distribution | AGPL route including citeproc-js option, CSL CC-BY-SA-3.0 attribution, Node executable/licence/matching source, retained dependency notices and source receipts |
| 47 | Editable Word citations | Document-local sources and native CITATION/BIBLIOGRAPHY fields; IEEE/APA sixth edition/ISO 690 numerical; refresh in Word |
| 48 | Manuscript layout | User-chosen page/font/spacing/margins/numbering/frontmatter; profiles are not named-journal certification; explicit optional outline append |
| 49 | Official CSL retrieval | Explicit approval for named official style/locale and dependencies; no research content, no export-time network |
| 50 | Compiled typesetting | Bundled Tectonic/resources, generated escaped TeX and advanced equation allowlist; no arbitrary TeX upload or OS-sandbox claim; missing glyphs refuse output |
| 51 | Library and note navigation | Metadata/type/reading filters and sorting; title/body draft search includes unsaved text without replacing the open editor |
| 52 | Citation picker | Workspace search, bibliography or valid location marker, archive opt-in; selected text retained |
| 53 | Reading annotation | PDF word selection and separate highlight/quote/comment records; source location and cited-note creation; no original-file edits |
| 54 | Reading organisation | Unread/Reading/Read, favorites, multiple tags, one collection label, reading position and next action; no scheduled task |
| 55 | Duplicate review | Read-only matching title/DOI candidates; no merge/delete/citation-ID rewrite |
| 56 | Focus and sections | Visible Exit/Escape; complete adjacent Markdown section moves through ordinary save/recovery |
| 57 | Personal claim review | Exact saved sentence/source passage, personal review states, stale guards, retained attachment history and archive/restore; no machine support certification |
| 58 | Automatic backup — 0.5.0 | Opt-in local sets for every workspace with history, honest success/failure and exact restore preview; app-open scheduling/catch-up, no pruning; larger file-backed sets in 0.6.0 |
| 59 | In-app updates — 0.5.0 | Separate check/download/unsigned execution approvals, stopped complete copy, verified startup before shortcut change; retained old version/data and bounded rollback |
| 60 | Reviewer responses — 0.5.0 | Exact passage occurrence/version, manual planned/revised/response records, retained changes and saved text-letter export; no manuscript mutation or submission |
| 61 | Project review — 0.5.0 | Selected-workspace saved draft/recorded-claim checks with timestamp and Unknown incomplete totals; no support/readiness certification |
| 62 | Larger automatic sets — 0.6.0 | File-backed ZIP creation/validation/restore within unchanged file/manifest/record/history bounds; manual browser/CLI transfer still capped at 47 MiB |
| 63 | Saved revision comparison — 0.6.0 | Read-only title/body plain text, selected saved versions, aligned differences/counts/navigation and labelled coarse/paginated display; no restore or new revision |
| 64 | Unified local recovery — 1.0.0-rc.1 | Windows selection or typed local path, streaming manual ZIPs even with scheduling off, background progress and cancellation before publication; approved apply creates a separate workspace |
| 65 | Installation diagnostics — 1.0.0-rc.1 | Fixed local component checks and remedies, exact allowlisted JSON preview and optional download; no document scans or automatic uploads |
| 66 | Durable update activation — 1.0.0-rc.1 | Bound local activation proof and retained-record recovery, numeric RC version ordering and explicit release-channel policy |
| 67 | Suggested PDF details — 1.0.0-rc.2 | Import reads an embedded PDF title and a DOI found on the first two pages into otherwise empty source details, marked with a provenance line and shown in the import receipt; nothing is looked up online | Unverified suggestions at metadata version 0; no author or year guesses; verify before citing or use the DOI with the exact catalogue lookup |
| 68 | Incomplete-reference warning — 1.0.0-rc.2 | Draft exports from Write and the CLI run the saved-version writing check afterwards and report cited sources whose bibliography fields are missing | The export is still written; whole-workspace exports rely on Project review |
| 69 | Pre-filled editable Word fields — 1.0.0-rc.2 | Editable Word citations and the bibliography carry the rendered default-style text before any field refresh | Plain cached text until Word refreshes into its own style; adjacent fields stay separate |
| 70 | Labelled revision comparison — 1.0.0-rc.2 | Citation markers display as source titles with the exact marker retained, and changed line pairs highlight the words that moved | Display only; comparison counts and saved text are unchanged |
| 71 | Complete missing details — after 1.0.0-rc.2 | From an export warning, the writing check or Source details, look up each saved DOI through Crossref and save only the fields you tick; provenance records fields, DOI and retrieval time | Explicit lookup sends only the DOI; catalogue values are unverified; existing values change only when ticked; sources without a DOI go to Source details |
| 72 | Workspace export warning — after 1.0.0-rc.2 | Whole-workspace exports from the desktop and CLI name cited sources with missing bibliography fields using Project review's saved-draft checks | Saved drafts only; failed draft checks are reported; evidence CSV is not checked |
| 73 | Import pointer to Source details — after 1.0.0-rc.2 | The import receipt names imported sources missing citation fields and opens Source details for the first | Longer explanation on the first such import only; figures and bibliography files excluded |

## Other approved references

These identify sources used in the earlier approved inspection. They describe observed/advertised patterns, not a fresh vendor release comparison or equal writing quality.

| Reference | Workflow pattern | Kosh scope / difference |
|---|---|---|
| [Jenni](https://docs.jenni.ai/docs/writing/document-editor/) | Assisted writing, outlines, citations, exports | Reviewed continuation/apply, source context and exports; no service-equivalence claim |
| [Paperpal](https://paperpal.com/paperpal-for-researchers) | Editing and submission checks | Grammar/clarity/abstract proposals and mechanics; no plagiarism or journal-approval certificate |
| [SciSpace](https://scispace.com/ai-writer) | Literature-supported drafting | Sources beside drafts, discovery/lookup and proposals; no automatic claim validation |
| [Yomu](https://www.yomu.ai/) | Selected-text/document help | Scoped preview, alternatives and explicit apply; provider/account terms separate |
| [Elicit](https://elicit.com/) | Discovery/structured extraction | Four-index discovery and anchored draft rows; formal screening/verified interpretation remain separate |
| [Zotero](https://www.zotero.org/support/word_processor_integration) | Bibliographic exchange/styles | RIS/BibTeX/CSL data, offline CSL notes/locales and separate native Word fields; no Zotero field/add-in integration or product-equivalence claim |

“Papercraft” was clarified as general paper-writing capabilities, not a verified named product. Subscription, payment and account features of those services are outside this local app.

## Remaining boundaries and proof

Kosh does not certify scientific claims, clinical decisions, ethics approval, formal searches, screening, recruitment, submission or acceptance. Metadata, OCR and proposals require review. Exact quotes/locators prove supplied text/location, not the model's interpretation.

Ordinary `docx` contains static CSL references. `docxlive` instead embeds native Word fields and document-local sources, refreshed with Ctrl+A/F9. Its IEEE, APA sixth edition and ISO 690 numerical styles differ from CSL APA 7/Vancouver/journal styles. Deleted citations renumber; uncited sources remain in Word's bibliography until removed from its Current List. Native Word visual/pagination acceptance remains separate from package tests.

CSL note placement and languages run offline. Dependent styles require local parents/locales; a separate explicit approved official retrieval action can supply them, while export never fetches automatically. Configurable manuscript profiles format supplied content; they do not establish named-journal compliance. Blinding omits supplied author frontmatter only, and optional outlines require explicit draft edits.

Standard non-template PDF uses the bounded parsed vector-math subset with labelled fallback for unsupported/empty/unavailable-glyph expressions. Compiled LaTeX PDF and template/note PDF use bundled offline Tectonic with generated/escaped structure and an advanced equation allowlist. Arbitrary document commands/TeX uploads are not compiled. Shell escape is disabled without claiming OS filesystem isolation. Missing-font glyphs refuse output with a generic message. TeX Gyre Termes/Heros provide equivalent serif/sans families rather than exact Word fonts. Reimport retains supported Word equation structure as linear notation and reports omitted unsupported structures. Source-only TEX has figure placeholders; TeX ZIP carries supplied assets. External images are not fetched.

No automatic full-paper downloader, cloud sync, arbitrary shell or permanent deletion is exposed. Installed providers can send approved content to their own services; invocation restrictions are not OS isolation. CLI/MCP consent flags attest caller permission, not a verified human approval.

Data is local and unencrypted; parsing is not a hostile-document sandbox. The prepared installer includes Node.js 24.14.1 for local CSL processing with its licence and matching source archive. The source edition requires matching Node already present or a separately approved component-fetch helper; no app/setup/installer download runs automatically. The optional [signing workflow](SIGNING.md) is available, but the installer remains unsigned until a trusted identity is provisioned and the exact release signed/verified. Native installer/Word pagination and another clean computer need their own acceptance. Mocked model/index tests establish guards/contracts, not live generation quality, authentication or index availability. Actual OCR/embedding execution requires current runtime proof.

Design observations came from Lekh and public Mobbin screens. No reference research application's code/assets are included; the attributed citeproc-js/CSL/Node components are dependencies. Release receipts establish source/test/render/install proof; no build identity or aggregate pass count is inferred here.
