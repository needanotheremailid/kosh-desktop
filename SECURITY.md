# Security and privacy

## Intended boundary

The app runs for a trusted local Windows user. The service binds to 127.0.0.1, checks Host/Origin, constrains browser resources and requires a per-launch token for API/file access. Fixed-loopback Ollama calls refuse proxies and redirects. There is no Kosh account, telemetry, public tunnel or remote sync. Explicit catalogue queries contact fixed public indexes. Individually approved Codex/Claude requests use the installed provider and may reach its cloud services. Preview displays the bounded content Kosh supplies; the installed CLI can add its own instructions and environment metadata.

This is not OS-user isolation or encryption. Other local processes can potentially read the data folder/private launch capability. Do not expose the service beyond loopback. Keep data/agent-session.json, browser profiles, originals and SQLite files private.

Document parsing runs in process, not a hostile-file sandbox. Size/page/text/archive/path bounds address particular failure modes; they do not prove malicious documents safe. Import trusted authorised sources. Document/model output never authorises shell commands, remote requests or original-file edits.

Model drafts are not verified clinical advice. Bibliography is manually entered or explicitly imported from a labelled catalogue; citations do not prove entailment. A manual evidence table is not formal screening or restricted-data abstraction. Installed-agent requests use a one-use ticket for previewed Kosh-supplied content, restricted fixed CLI arguments and bounded output. Instruction/tool suppression is configured, not independently verified in a live provider request. The UI requires explicit consent; the CLI consent flag attests caller authorization and cannot verify that a human approved it. A local caller able to prepare a preview can also consume it. These restrictions are not OS isolation or a guarantee of provider confidentiality. No arbitrary shell-command API is exposed.

The selected-folder editor accepts only explicit existing targets and proposed bounded UTF-8 text paths. Exact diffs, original hashes and changed-byte checks guard accidental overwrite, and recovery originals stay inside private app data. Preview discloses line-ending changes and UTF-8 BOM removal; retained copies preserve original bytes. UI approval is explicit; a CLI approval flag is caller-attested permission rather than a verified human gate. Path/reparse restrictions are not OS account isolation against a malicious concurrent local process. There is no delete/shell API. Publication is atomic per file, not an all-or-nothing multi-file transaction. Batch receipts report partial application; workspace ZIPs exclude external-folder files and this separate journal. Preserve the full stopped app data folder as well as the selected folder's own backups. Windows reparse points, including some cloud placeholders, are refused; an ordinary cloud-synced folder is not automatically excluded.

## Reporting

Report suspected vulnerabilities through [GitHub private vulnerability reporting for this repository](https://github.com/needanotheremailid/kosh-desktop/security/advisories/new), using **Security → Report a vulnerability** when available. Do not use public issues for exploit details, tokens, personal data folders, patient identifiers or unpublished sources. If GitHub does not offer the private report action, do not disclose sensitive material publicly; an ordinary issue may ask for a private reporting route without including the vulnerability or private data. No private email address or response-time promise is specified.

Include app/source identity, Windows/Python version and the concrete trigger. Prefer a synthetic fixture. Do not copy credentials into logs, screenshots or prompts.

For the bundled beta, include release version and Windows architecture; system Python is not required. Give the affected boundary, minimal synthetic steps, expected/actual result and impact. Attach only a small sanitised fixture when needed, and retain originals privately. GitHub advisory access is separate from ordinary issue access.

## Beta support and additional boundaries

0.3.0 is an unsigned Windows beta. No trusted publisher identity or universal clean-machine acceptance is claimed. Older installations require a separate upgrade; no automatic updater is enabled. Preserve backups when testing.

Local CSL import does not use network access. The separately approved official retrieval action sends named style/locale identifiers and required dependency requests to fixed pinned CSL repositories; no manuscript content is sent, and export never automatically fetches missing resources. Compiled PDF uses bundled Tectonic/resources with generated escaped structure, an equation command/environment allowlist and shell escape disabled. It is not an arbitrary TeX upload interface or an OS filesystem sandbox. Missing glyphs refuse PDF output rather than silently discarding characters. Template blinding omits supplied author frontmatter only, not identifying material in the manuscript.

## Distribution

The source-export allowlist excludes data, runtime paths and private continuity/review files. Inspect it before upload. The bundled installer includes Python, the pinned document libraries, notices and matching dependency source archives under the documented AGPL route. It includes no signing certificate, models or Edge. Packaging is not proof of installation on another clean machine. The installer supports a new destination, not an in-place upgrade; quit before copying the entire data folder and retain the old installation for recovery. The alternative source release requires an explicitly installed runtime. See THIRD_PARTY.md and LICENSE.
