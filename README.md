# Kosh

**From papers to a manuscript, in one local workspace.**

Kosh is a free, open-source research desk for Windows. Keep your papers, reading notes, citations and manuscript together, with a clear route back from your writing to the sources behind it.

**[Download for Windows](https://github.com/needanotheremailid/kosh-desktop/releases/download/v1.0.0-rc.6/Kosh-1.0.0-rc.6-Setup.exe)** · [Website](https://prateekguptasurgery.com/sidequests/kosh) · [User guide](USER_GUIDE.md)

Requires Windows 11 (64-bit), Microsoft Edge and .NET Framework. No administrator rights needed.

![Kosh reading view with a highlighted passage and controls for citing the original PDF page](assets/screenshots/kosh-reading-100rc5.png)

*Read the original page, highlight a passage and keep your comment beside it.*

## How it works

Choose a workspace. **Overview** shows saved progress and a suggested next action. The sidebar follows seven steps:

1. **Find.** Search indexes, look up a DOI or PMID, import files or add bibliography records. Kosh keeps managed copies of imported documents.
2. **Screen.** Save criteria and record your own title/abstract and full-text decisions, reasons and history. Screening is manual.
3. **Read.** Choose a source, search passages, save highlights and comments, and return to the page where you stopped.
4. **Extract.** Save source-linked evidence rows with your notes on the question, design, findings and limitations.
5. **Synthesise.** Prepare a reading packet, compare saved evidence, start a checklist or hand selected sources and a question to Agent assistance.
6. **Write.** Draft with a source beside your writing, insert citations and compare saved revisions. Export to Word, PDF, Markdown, HTML or LaTeX, or export reference records.
7. **Verify.** Review saved claim links, citations, writing checks and references needing details. You decide whether the source supports a claim.

![Kosh draft beside its original PDF source, with citation controls and a highlighted passage](assets/screenshots/kosh-writing-100rc5.png)

*Write with the original source beside your draft and cite without leaving the page.*

## Keep the source beside your writing

Open **Source beside** in Write to read, highlight and cite while keeping your draft in view. **Cite this page** and **Cite in draft** insert at your cursor without replacing selected text. Type **@** in a draft to choose a citation.

Find commands, sources, drafts and passages with **Ctrl+K**. Use **Find** for files, DOI or PMID lookups, pasted reference lists and bibliography files. [User guide](USER_GUIDE.md).

## Tools for the whole research workflow

| What you need to do | What Kosh provides |
| --- | --- |
| Organise a library | Workspaces, tags, reading states, favourites, collection labels, filters and sorting |
| Find a paper | Search PubMed, Crossref, Europe PMC and OpenAlex; review catalogue metadata before importing it |
| Work with scanned pages | Create a local OCR copy, then inspect the recognised text against the page |
| Find a passage | Text search and optional local semantic search with an installed embedding model |
| Check a claim | Attach an exact source passage to a selected sentence and record your own review; changed text can flag an earlier check as stale |
| Handle reviewer comments | Keep comments, planned changes and responses linked to saved draft passages, then export a response letter |
| Review a project | Check saved drafts for unresolved references, missing metadata and outstanding recorded claim reviews |
| Recover your work | Autosave, saved revisions, local backup/restore and optional automatic backups while Kosh is open |
| Share a workspace | Export a portable workspace ZIP; importing restores it as a separate workspace |
| Work with an agent | Use the CLI or 66 MCP tools, including scoped reading, writing and export operations |
| Edit a chosen folder | Review an agent's proposed changes to selected text files and approve the exact changes before they are applied |
| Learn the controls | Getting started, Help, hover explanations you can turn off, and an installation check |

Citation metadata, OCR and generated writing still need your review. Claim-review labels record your judgement; they do not certify that a source supports a conclusion. [Detailed capabilities and boundaries](FEATURES.md).

<details>
<summary>See citation and export options</summary>

![Kosh export controls for citation styles and document formats](assets/screenshots/kosh-export-options-100rc5.png)

Choose your citation style, manuscript settings and output format in **Exports & backup**. Native Word citation fields use Word's own bibliography styles; the standard exports use CSL.

</details>

## Choose your workspace

Kosh has three layouts, each available in light and dark themes.

- **Broadsheet:** a wide workspace.
- **Stacks:** a compact style.
- **Commonplace:** a centred reading and writing column.

All three use the same research-path sidebar.

<details>
<summary>See all three layouts</summary>

**Broadsheet**

![Kosh library in Broadsheet](assets/screenshots/kosh-library-100rc5.png)

**Stacks**

![Kosh library in Stacks](assets/screenshots/kosh-stacks-100rc5.png)

**Commonplace**

![Kosh library in Commonplace](assets/screenshots/kosh-commonplace-100rc5.png)

</details>

## Watch the workflow

![Kosh walkthrough showing reading, writing, export and the three layouts](assets/presentation/Kosh%20Walkthrough.gif)

[Watch or download the 32-second video](https://github.com/needanotheremailid/kosh-desktop/raw/refs/heads/main/assets/presentation/Kosh%20Walkthrough.mp4). A silent, captioned tour of the working app and an actual PDF export.

## Local first, with optional AI

Your library is stored on your computer. Kosh has no application account, telemetry or cloud sync. Reading, writing, citations, exports and local backups work without AI.

For AI assistance, use an installed local Ollama model or your own authenticated Codex or Claude CLI. Preview the content to be sent, review the returned proposal, and choose whether to save an alternative or apply an eligible edit. Provider access, charges and limits are separate from Kosh.

Online literature searches send the query or identifier you submit. Optional style retrieval and update checks contact their named sources when you request them. Codex or Claude assistance sends approved content to that provider; its CLI may also include instructions or environment metadata. Local files and backup ZIPs are not encrypted. See the [user guide](USER_GUIDE.md) and [security information](SECURITY.md).

## Start with one paper

1. Download the installer and open Kosh. The document runtime, citation processor, OCR language data and offline TeX resources are included.
2. Follow **Getting started** to create your first workspace and import a paper.
3. Save a passage, write a short note, insert its citation and export a draft.
4. Choose a local backup location when you are ready to keep working.

Your library starts empty. Screenshots and the walkthrough use nonclinical example material. No AI account or separate Python, Node or TeX installation is needed for the core workflow.

<details>
<summary>Download details</summary>

Current package: **1.0.0-rc.6 (release candidate)**. The installer is not code-signed, so Windows may show an unknown-publisher warning.

[Release and files](https://github.com/needanotheremailid/kosh-desktop/releases/tag/v1.0.0-rc.6) · [SHA-256 checksums](https://github.com/needanotheremailid/kosh-desktop/releases/download/v1.0.0-rc.6/SHA256SUMS.txt)

Run this in PowerShell from the folder containing the installer, then compare it with the published checksum:

```powershell
(Get-FileHash .\Kosh-1.0.0-rc.6-Setup.exe -Algorithm SHA256).Hash
```

A matching checksum confirms transfer consistency with the published file; it does not verify the publisher.

</details>

## Open source and credits

Kosh is free under **AGPL-3.0-only**. Your papers and notes are not relicensed. [Licence](LICENSE).

Built with assistance from **OpenAI Codex** and **Anthropic Claude**, including Claude Opus. The research-workspace inspiration came from **Beeblio by Al Harkan**; no Beeblio application code or assets were copied. Included document, citation and runtime components retain their own credits and licences. [Full credits](CREDITS.md) · [Third-party notices](THIRD_PARTY.md).

[Build from source](BUILDING.md) · [Agent interface](AGENT_API.md) · [Contribute](CONTRIBUTING.md) · [Report a bug](https://github.com/needanotheremailid/kosh-desktop/issues/new?template=bug_report.yml) · [Media provenance](assets/presentation/README.md)
