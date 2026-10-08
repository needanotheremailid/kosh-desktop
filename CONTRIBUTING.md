# Contributing

This checkout targets **1.0.0-rc.5**. Candidate source and passing checks do not establish a published final 1.0 release, independent human acceptance, or a signed installer. The release record owns those claims. Signing remains pending.

A useful contribution starts with a concrete problem, a focused change and evidence that the affected workflow still works. Documentation improvements, small synthetic reproductions and tests are useful first contributions; assembling the whole installer is not a prerequisite.

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

## A first change

1. Reproduce the problem in a separate checkout/data directory with invented non-clinical content. Record the current version, trigger and result. Keep the real installation and originals out of the experiment.
2. Open or reference an issue that explains the intended behavior. Discuss retention, authentication, archive formats, migrations and dependency changes before implementing them; these can affect recovery beyond the visible screen.
3. Add the narrow regression check and observe it fail before fixing a defect. Use an independently known expected result or a worked fixture, not an assertion calculated from the implementation being changed.
4. Make the smallest coherent fix. Preserve expected versions, source identities and recovery. Update the relevant guide and source/package manifests if a command, route or runtime file changes.
5. Run the closest tests first, then the full source suite once the change is ready and its resources are available. State skipped checks and limitations. For UI changes, inspect the actual result in Broadsheet, Stacks and Commonplace, including keyboard focus and light/dark states.

For current installation/privacy and backup work, the focused checks are:

```powershell
python.exe -m unittest tests.test_installation_health tests.test_installation_health_ui tests.test_local_dialog tests.test_local_backup_jobs tests.test_local_backup_ui -v
```

The health preview is deliberately a positive allowlist. Do not add raw logs, paths, source names, settings, model inventory or session capabilities to its diagnostic JSON. Native chooser and DOM substitutes in tests do not prove actual Windows picker interaction; describe that remaining manual check honestly.

## Review and issue triage

Review should address potential disclosure, unintended writes/data loss, authentication and recovery defects before style nits. Then consider incorrect results, compatibility and measured performance. Cosmetic changes should stay focused and preserve the app's three layouts rather than replacing its design system as a side effect.

Reports may be confirmed, need more information, duplicate an existing issue, fall outside Kosh's scope, or be deferred. A triage explanation should name the evidence or trade-off and the next useful check. Clear reproduction steps make assessment easier; neither an issue nor a pull request guarantees a response date, merge or support commitment. Do not post a vulnerability or private data publicly to make a report more urgent.

In a pull request, explain the trigger and before/after behavior, list the checks actually run, and name remaining proof gaps. Keep unrelated cleanup separate. If a reviewer disagrees, resolve the concrete behavior or evidence before changing code merely to satisfy a stylistic preference. Keep discussion about the change, not the contributor.

AI assistance is welcome with accurate attribution. When Codex or Claude materially assists a change, record that assistance in the commit message using the provider's attribution identity: `Co-authored-by: Codex <noreply@openai.com>` or `Co-authored-by: Claude <noreply@anthropic.com>`. Include only assistants that contributed to that change, preserve the maintainer's own authorship and do not create empty commits or rewrite unrelated history for attribution. Written acknowledgements are in [CREDITS.md](CREDITS.md#development-assistance); GitHub controls its automatic contributor displays.

Use export-source.ps1 for distribution, then inspect the archive/manifest. No data, browser profile, private launch token, runtime.json, generated binary or review receipt belongs in a source release. Kosh uses AGPL-3.0-only; dependencies retain upstream licences. [BUILDING.md](BUILDING.md) describes the actual installer inputs, including separately prepared dependency/legal sources and the manual TeX resource-cache preparation gap. The installer builder downloads nothing. Verify hashes, empty-library startup and no-clobber behavior; document clean-machine and native-pixel proof separately. Do not claim a byte-identical reproducible installer: timestamps, compiler/runtime inputs and manual payload preparation still affect the result.

Verified development-package metadata lists PyMuPDF as dual AGPL 3.0/Artifex Commercial, python-docx as MIT and lxml as BSD-3-Clause. Treat dependency distribution/licensing as a separate release decision; no MIT-only bundle is claimed.

The original Kosh monogram is included as SVG, PNG and a multi-size Windows icon. `scripts/build_icon.py` can regenerate the raster/icon files with Pillow, a development-only dependency. Pillow is not needed to install or run the app; setup uses the included icon.

Before closing a contribution, stop owned test services and remove disposable generated fixtures and scratch outputs. Keep reusable tools in the maintained repository and retain necessary verification records privately. Follow the [build-input cleanup guidance](BUILDING.md#keep-build-inputs-separate-from-temporary-work); never treat a real library or recovery copy as a test fixture merely because it sits beside development files.
