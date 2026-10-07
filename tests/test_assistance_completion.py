"""Durable assistance checks using synthetic temporary storage only."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import time
import unittest

from backend import Store
from assistance import Assistance, AssistanceError, build_prompt, parse_evidence, selected_patch


class AssistanceCompletion(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "data"
        self.store = Store(self.root)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch("POST", "/api/workspaces", {"title": "Synthetic assistance"})["id"]
        self.journal = Assistance(self.store)

    def preview(self, **changes):
        return {"preview_id": "a" * 32, "workspace_id": self.workspace, "provider": "claude", "task": "grammar", "prompt": "Synthetic widget prompt", "citations": [], "note_id": None, "version": None, "expires_at": int(time.time()) + 300, "consent_version": 1, **changes}

    def test_durable_result_survives_restart_and_repeat_cannot_run(self):
        preview = self.preview()
        self.journal.register(preview)
        self.assertTrue(self.journal.start(preview["preview_id"], self.workspace)["should_run"])
        result = {"result_id": "b" * 32, "workspace_id": self.workspace, "proposal": "Reviewed synthetic widgets.", "note_title": "Widget draft"}
        self.journal.finish(preview["preview_id"], result)
        self.store.close()
        self.store = Store(self.root)
        self.addCleanup(self.store.close)
        journal = Assistance(self.store)
        self.assertEqual(journal.result(result["result_id"], self.workspace), result)
        self.assertFalse(journal.start(preview["preview_id"], self.workspace)["should_run"])
        self.assertEqual(journal.history(self.workspace)[0]["status"], "complete")
        self.assertNotIn("prompt", journal.history(self.workspace)[0])

    def test_crash_keeps_running_job_without_resending(self):
        self.journal.register(self.preview())
        self.journal.start("a" * 32)
        self.store.close()
        self.store = Store(self.root)
        self.addCleanup(self.store.close)
        journal = Assistance(self.store)
        retry = journal.start("a" * 32)
        self.assertFalse(retry["should_run"])
        self.assertEqual(retry["job"]["status"], "running")

    def test_concurrent_connections_claim_job_once(self):
        self.journal.register(self.preview())
        second_store = Store(self.root)
        self.addCleanup(second_store.close)
        second = Assistance(second_store)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(journal.start, "a" * 32) for journal in (self.journal, second)]
            claims = [future.result()["should_run"] for future in futures]
        self.assertEqual(sorted(claims), [False, True])

    def test_failure_is_retained_and_cannot_trigger_retry(self):
        self.journal.register(self.preview())
        self.journal.start("a" * 32)
        failed = self.journal.fail("a" * 32, "Provider failed; request may have been used.")
        self.assertEqual(failed["status"], "failed")
        self.assertFalse(self.journal.start("a" * 32)["should_run"])
        self.assertEqual(self.journal.history(self.workspace)[0]["error"], failed["error"])

    def test_expiry_and_foreign_scope_refused(self):
        self.journal.register(self.preview(expires_at=int(time.time()) - 1))
        with self.assertRaises(AssistanceError) as expired:
            self.journal.start("a" * 32)
        self.assertEqual(expired.exception.status, 409)
        other = self.store.dispatch("POST", "/api/workspaces", {"title": "Other synthetic workspace"})["id"]
        self.assertEqual(self.journal.history(other), [])
        with self.assertRaises(AssistanceError) as foreign:
            self.journal.get("a" * 32, other)
        self.assertEqual(foreign.exception.status, 404)

    def test_preview_identity_and_completed_result_are_immutable(self):
        preview = self.preview()
        self.journal.register(preview)
        self.assertEqual(self.journal.register(preview)["status"], "prepared")
        with self.assertRaises(AssistanceError):
            self.journal.register({**preview, "prompt": "Different prompt"})
        with self.assertRaises(AssistanceError):
            self.journal.finish("a" * 32, {"result_id": "b" * 32, "workspace_id": self.workspace})
        self.journal.start("a" * 32)
        result = {"result_id": "b" * 32, "workspace_id": self.workspace, "proposal": "Widgets"}
        self.journal.finish("a" * 32, result)
        self.assertEqual(self.journal.finish("a" * 32, result)["result"], result)
        with self.assertRaises(AssistanceError):
            self.journal.finish("a" * 32, {**result, "proposal": "Changed widgets"})

    def test_new_task_prompts_are_bounded_and_source_guarded(self):
        for task in ("continue", "grammar", "translate", "abstract", "extract"):
            prompt = build_prompt(task, "Synthetic instruction", "Synthetic widgets", [])
            self.assertIn("Do not invent", prompt)
            self.assertIn("untrusted", prompt)
        with self.assertRaises(AssistanceError):
            build_prompt("shell", "", "Widgets", [])
        with self.assertRaises(AssistanceError):
            build_prompt("grammar", "", "x" * 25_000, [])

    def test_selected_patch_requires_version_exact_offsets_and_markers(self):
        marker = "[[source:" + "c" * 32 + ":2]]"
        selected = "Synthetic widgets " + marker
        note = {"id": "d" * 32, "workspace_id": self.workspace, "version": 2, "body": "Before " + selected + " after"}
        preview = {"note_id": note["id"], "workspace_id": self.workspace, "version": 2, "selected_text": selected, "selected_start": 7, "selected_end": 7 + len(selected)}
        self.assertEqual(selected_patch(note, preview, "Reviewed widgets " + marker), "Before Reviewed widgets " + marker + " after")
        for changes, replacement in (({"version": 1}, "Reviewed widgets " + marker), ({"selected_start": 8}, "Reviewed widgets " + marker), ({}, "Widgets without marker")):
            with self.assertRaises(AssistanceError):
                selected_patch(note, {**preview, **changes}, replacement)
        repeated = {**note, "body": selected + " " + selected}
        with self.assertRaises(AssistanceError):
            selected_patch(repeated, {key: value for key, value in preview.items() if key not in {"selected_start", "selected_end"}}, selected)

    def test_evidence_requires_exact_quote_known_source_and_human_review(self):
        citations = [{"id": "C1", "document_id": "e" * 32, "page": 3, "text": "Thirty synthetic widgets were observed."}]
        proposal = '[{"citation_id":"C1","question":"How many widgets?","design":"Not stated","findings":"Thirty widgets","limitations":"Fixture only","quote":"Thirty synthetic widgets"}]'
        result = parse_evidence(proposal, citations)
        self.assertTrue(result["review_required"])
        self.assertEqual(result["rows"][0]["page"], 3)
        self.assertEqual(result["rows"][0]["document_id"], "e" * 32)
        for invalid in (proposal.replace("C1", "C99"), proposal.replace("Thirty synthetic widgets\"}", "Invented quote\"}")):
            with self.assertRaises(AssistanceError):
                parse_evidence(invalid, citations)

    def test_exact_single_json_fence_is_accepted_without_relaxing_quote_checks(self):
        citations = [{'id': 'C1', 'document_id': 'e' * 32, 'page': 3, 'text': 'Thirty synthetic widgets were observed.'}]
        value = '[{"citation_id":"C1","question":"Widgets?","design":"Not stated","findings":"Thirty widgets","limitations":"Synthetic","quote":"Thirty synthetic widgets"}]'
        for output in ('```json\n' + value + '\n```', ' \r\n```JSON\r\n' + value + '\r\n```\r\n ', '```\n' + value + '\n```'):
            with self.subTest(output=output):
                result = parse_evidence(output, citations)
                self.assertEqual(result['rows'][0]['quote'], 'Thirty synthetic widgets')
                self.assertTrue(result['review_required'])
        with self.assertRaises(AssistanceError):
            parse_evidence('```json\n' + value.replace('Thirty synthetic widgets', 'Invented quote') + '\n```', citations)

    def test_json_fence_with_surrounding_prose_or_extra_block_is_not_salvaged(self):
        value = '[{"citation_id":"C1","question":"Widgets?","design":"Not stated","findings":"Thirty widgets","limitations":"Synthetic","quote":"Thirty synthetic widgets"}]'
        citations = [{'id': 'C1', 'document_id': 'e' * 32, 'page': 3, 'text': 'Thirty synthetic widgets were observed.'}]
        for output in ('Explanation\n```json\n' + value + '\n```', '```json\n' + value + '\n```\nExplanation', '```json\n' + value + '\n```\n```json\n' + value + '\n```'):
            with self.subTest(output=output), self.assertRaises(AssistanceError):
                parse_evidence(output, citations)


if __name__ == "__main__":
    unittest.main()
