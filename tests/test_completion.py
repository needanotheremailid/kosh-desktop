"""Completion endpoint checks on synthetic documents and temporary stores."""
import base64
import json
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zlib

from backend import AppError, Store
from assistance import Assistance
from completion import Completion


class CompletionAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "data")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch("POST", "/api/workspaces", {"title": "Synthetic widgets"})["id"]
        self.store.assistance = Assistance(self.store)
        self.complete = Completion(self.store)

    def call(self, route, **payload):
        return self.complete.dispatch("POST", route, {"workspace_id": self.workspace, **payload})

    def bibliography(self, text=None, format="bib"):
        return self.call("/api/bibliography/import", format=format, text=text or '@article{x,title={Synthetic widgets},author={Example, Ann},year={2024},doi={10.1234/widgets}}')

    def test_import_has_individual_records_and_dedupe_preserves_corrections(self):
        first = self.bibliography()
        doc = first["results"][0]["document"]
        self.assertEqual(doc["metadata"]["catalogue_source"], "Bibliography import")
        self.store.dispatch("POST", "/api/metadata", {"id": doc["id"], "expected_metadata_version": doc["metadata_version"], "metadata": {**doc["metadata"], "title": "Reviewed widgets"}})
        duplicate = self.bibliography('@article{newkey,title={Other title},doi={https://doi.org/10.1234/WIDGETS}}')
        self.assertEqual(duplicate["results"][0]["status"], "duplicate")
        self.assertEqual(duplicate["results"][0]["document"]["metadata"]["title"], "Reviewed widgets")
        self.assertEqual(len(self.store._state(self.workspace)["documents"]), 1)

    def test_bibliography_preview_is_readonly_and_csl_fields_are_explicit(self):
        content = json.dumps([{"id": "widget", "type": "article-journal", "title": "Widgets", "author": [{"family": "Example", "given": "Ann"}], "issued": {"date-parts": [[2024, 2, 3]]}, "container-title": "Widget Journal", "unknown-field": "Omitted"}])
        result = self.call("/api/bibliography/preview", format="csljson", text=content)
        self.assertEqual(result["records"][0]["year"], "2024")
        self.assertEqual(result["records"][0]["journal"], "Widget Journal")
        self.assertTrue(result["warnings"])
        self.assertEqual(self.store._state(self.workspace)["documents"], [])
        with self.assertRaises(AppError):
            self.call("/api/bibliography/preview", format="csljson", text='[{"issued":{"date-parts":[[true]]}}]')

    def test_each_ris_record_imports_separately_and_stable_content_dedupes(self):
        text = 'TY  - JOUR\nTI  - First widgets\nAU  - Example, Ann\nER  -\nTY  - JOUR\nTI  - Second widgets\nER  -\n'
        first = self.bibliography(text, "ris")
        self.assertEqual(first["imported"], 2)
        self.assertEqual(self.bibliography(text, "ris")["duplicates"], 2)
        self.assertEqual(len(self.store._state(self.workspace)["documents"]), 2)

    def test_doi_duplicate_matching_is_confined_to_current_workspace(self):
        first = self.bibliography()["results"][0]["document"]
        other = self.store.dispatch("POST", "/api/workspaces", {"title": "Other widgets"})["id"]
        second = self.call("/api/bibliography/import", workspace_id=other, format="bib", text='@article{x,title={Synthetic widgets},doi={10.1234/widgets}}')["results"][0]
        self.assertEqual(second["status"], "ready")
        self.assertNotEqual(second["document"]["id"], first["id"])

    def test_book_fields_and_literal_authors_survive_managed_import(self):
        imported = self.bibliography('@book{group,title={Widget manual},author={{Widget Consortium}},year={2024},publisher={Widget Press},address={Example City},edition={2},isbn={1234567890}}')
        self.assertEqual(imported["imported"], 1)
        metadata = imported["results"][0]["document"]["metadata"]
        self.assertEqual(metadata["type"], "book")
        self.assertEqual(metadata["author_list"], [{"literal": "Widget Consortium"}])
        self.assertEqual(metadata["publisher"], "Widget Press")
        self.assertEqual(metadata["publisher_place"], "Example City")
        self.assertEqual(metadata["edition"], "2")
        self.assertEqual(metadata["isbn"], "1234567890")

    def test_attach_is_versioned_keeps_original_and_catalogue_and_enables_evidence(self):
        catalogue = self.bibliography()["results"][0]["document"]
        paper = self.store._import({"workspace_id": self.workspace, "files": [{"name": "widgets.txt", "data": base64.b64encode(b'Thirty synthetic widgets were observed.').decode()}]})["results"][0]["document"]
        before = self.store._bytes(self.store._document(paper["id"]))
        linked = self.call("/api/catalogue/attach", catalogue_id=catalogue["id"], document_id=paper["id"], expected_metadata_version=paper["metadata_version"])
        self.assertEqual(linked["metadata"]["title"], "Synthetic widgets")
        self.assertNotIn("catalogue_source", linked["metadata"])
        self.assertIn("unverified", linked["metadata"]["provenance"])
        self.assertEqual(self.store._bytes(self.store._document(paper["id"])), before)
        self.assertEqual(self.store._document(catalogue["id"])["metadata"]["catalogue_source"], "Bibliography import")
        with self.assertRaises(AppError) as stale:
            self.call("/api/catalogue/attach", catalogue_id=catalogue["id"], document_id=paper["id"], expected_metadata_version=paper["metadata_version"])
        self.assertEqual(stale.exception.status, 409)
        other = self.store.dispatch("POST", "/api/workspaces", {"title": "Other widgets"})["id"]
        with self.assertRaises(AppError):
            self.call("/api/catalogue/attach", workspace_id=other, catalogue_id=catalogue["id"], document_id=paper["id"], expected_metadata_version=linked["metadata_version"])

    def test_note_history_includes_current_and_exact_previous_bodies(self):
        note = self.store._save_note({"workspace_id": self.workspace, "title": "Widget draft", "body": "First widgets"})
        self.store._save_note({**note, "body": "Second widgets"})
        history = self.complete.dispatch("GET", "/api/notes/history", {"id": note["id"]})["revisions"]
        self.assertEqual([(row["version"], row["body"]) for row in history], [(1, "First widgets"), (2, "Second widgets")])
        self.assertTrue(all(row["created_at"] for row in history))

    def test_assist_history_recovers_complete_results_and_is_workspace_scoped(self):
        preview = {"preview_id": "a" * 32, "workspace_id": self.workspace, "provider": "ollama", "task": "grammar", "prompt": "Synthetic", "expires_at": int(time.time()) + 300, "consent_version": 1}
        self.store.assistance.register(preview)
        self.store.assistance.start(preview["preview_id"])
        result = {"result_id": "b" * 32, "workspace_id": self.workspace, "proposal": "Reviewed widgets"}
        self.store.assistance.finish(preview["preview_id"], result)
        history = self.complete.dispatch("GET", "/api/assist/history", {"workspace_id": self.workspace})
        self.assertEqual(history["results"], [result])
        self.assertEqual(self.complete.dispatch("GET", "/api/assist/result", {"workspace_id": self.workspace, "result_id": result["result_id"]}), result)
        other = self.store.dispatch("POST", "/api/workspaces", {"title": "Other widgets"})["id"]
        self.assertEqual(self.complete.dispatch("GET", "/api/assist/history", {"workspace_id": other})["results"], [])

    def test_asset_import_validates_dimensions_before_publication(self):
        def chunk(kind, payload):
            return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
        png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\x20\x40\x60')) + chunk(b'IEND', b'')
        with patch.object(self.store, "_import", wraps=self.store._import) as publish:
            with self.assertRaises(AppError):
                self.call("/api/assets/import", name="widgets.png", data=base64.b64encode(b'not an image').decode())
            publish.assert_not_called()
        # Backend image kinds/extraction are integrated by the parent; this
        # endpoint must hand off the exact validated bytes and dimensions.
        with patch.object(self.store, "_import", return_value={"results": [{"status": "no_text"}]}) as publish:
            imported = self.call("/api/assets/import", name="widgets.png", data=base64.b64encode(png).decode())
            self.assertEqual(imported["dimensions"], {"width": 1, "height": 1})
            self.assertEqual(publish.call_args.args[0]["files"][0]["data"], base64.b64encode(png).decode())
        image = Mock()
        image.w.return_value, image.h.return_value = 5000, 5000
        with patch('backend.pdf_lib.mupdf.fz_new_image_from_buffer', return_value=image), patch('backend.pdf_lib.Pixmap') as decode, patch.object(self.store, "_import") as publish:
            with self.assertRaises(AppError) as oversized:
                self.call("/api/assets/import", name="widgets.png", data=base64.b64encode(png).decode())
            self.assertEqual(oversized.exception.status, 413)
            decode.assert_not_called()
            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
