# Kosh 1.0 release-candidate acceptance

This checklist distinguishes automated release checks from someone using Kosh on their own computer. Agent reviews and hosted CI do not replace independent use. The installer remains unsigned.

## A complete first session

Use a permitted, non-sensitive source. Start with the empty library supplied by the installer.

1. Install into a new folder, open the shortcut and complete onboarding. Open Settings → Check this installation. Required components should be available; optional AI models may be absent.
2. Create a workspace, import a paper and open its pages. Find a phrase, highlight a passage, add a comment and turn it into a cited note. Quit and reopen; return to the saved reading position.
3. Write a short manuscript beside the source. Save a change, compare two revisions, and verify that both exact versions remain readable. Try two app windows editing the same draft; a conflict must preserve the alternative.
4. Enter or verify bibliography details. Insert two citations, change their order and export Word and PDF. Check all pages, tables, figures and equations. Static CSL exports and editable Word fields use different style systems; verify the chosen one.
5. Save a local workspace ZIP, preview it and restore into a separate workspace. Compare originals, drafts, annotations and revisions. Cancel a separate backup during copying; existing work and completed backups must remain usable.
6. Choose an automatic-backup folder only if wanted. Check the last successful set and the meaning of an unavailable destination. Do not use the application or data folder as the destination.
7. Preview a diagnostic report. Check that it contains no personal paths or manuscript material. Download only if useful; nothing is sent automatically.
8. After ordinary use, note any confusing control, unexpected delay or recovery problem. Report version, steps and expected/actual behavior without private documents or screenshots.

## Promotion to final 1.0

- Candidate package/source/installed-runtime and privacy checks pass.
- Upgrade preserves existing records, originals, browser recovery and the previous installation.
- No unresolved data-loss, privacy or blocking workflow defect remains.
- At least two independent Windows users complete the session above and a period of ordinary use, with their actual results recorded. A second physical Windows 11 installation is distinct from hosted Windows CI.
- Release notes describe the tested operating range and retained limitations accurately.

Independent user results are **pending**. No successful human trial is asserted here. Signing remains a separate distribution decision.

## Repeating the performance check

From the source root, run `python scripts/benchmark_local.py --output NEW_EMPTY_PATH` with the bundled document runtime. The output directory must not exist. Defaults generate 256 invented four-page PDFs with 2 MiB binary payloads, 50 long notes and 250 revisions, then measure source search and a greater-than-500-MiB backup/restore. It reads no personal library and makes no provider requests. Keep enough free disk space for the fixture, staged archive and restored copy. Timing includes local disk and background system load; these figures are not a capacity guarantee.
