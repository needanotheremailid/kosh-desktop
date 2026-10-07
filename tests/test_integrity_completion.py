"""Synthetic integrity regressions: no private files, providers or installed app."""
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from backend import AppError, Store


def encoded(data):
    return base64.b64encode(data).decode("ascii")


class IntegrityCompletion(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "data")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch("POST", "/api/workspaces", {"title": "Synthetic widgets"})["id"]

    def document(self, workspace=None, text="Thirty synthetic widgets were observed."):
        return self.store.dispatch("POST", "/api/import", {
            "workspace_id": workspace or self.workspace,
            "files": [{"name": "widgets.txt", "data": encoded(text.encode())}],
        })["results"][0]["document"]

    def backup(self):
        return self.store.file_response("/api/backup", {"workspace_id": self.workspace})[0]

    def restore(self, data):
        return self.store.dispatch("POST", "/api/restore", {"data": encoded(data)})

    def test_maximum_selected_citation_round_trips_without_truncation(self):
        passage = "Synthetic widgets. " * 210 + "x" * 10
        self.assertEqual(len(passage), 4000)
        document = self.document(text=passage)
        chat = self.store.dispatch("POST", "/api/ask", {
            "workspace_id": self.workspace, "question": "Show widgets",
            "selected_source": {"document_id": document["id"], "page": 1, "text": passage},
        })
        self.assertEqual(chat["citations"][0]["text"], passage)
        restored = self.restore(self.backup())
        state = self.store.dispatch("GET", "/api/state?workspace_id=" + restored["workspace_id"])
        self.assertEqual(state["chats"][0]["citations"][0]["text"], passage)
        self.assertEqual(state["chats"][0]["answer"], chat["answer"])

    def test_scoped_state_filters_before_materializing_foreign_documents(self):
        own = self.document()
        other = self.store.dispatch("POST", "/api/workspaces", {"title": "Other widgets"})["id"]
        foreign = self.document(other, "Other synthetic widgets.")
        for workspace, document in ((self.workspace, own), (other, foreign)):
            self.store.dispatch("POST", "/api/notes", {"workspace_id": workspace, "title": "Draft", "body": "Synthetic draft"})
            self.store.dispatch("POST", "/api/matrix", {"workspace_id": workspace, "document_id": document["id"], "question": "Widgets?", "design": "Synthetic", "findings": "Widgets", "limitations": "Fixture"})
            self.store.dispatch("POST", "/api/ask", {"workspace_id": workspace, "question": "widgets"})
        with patch.object(self.store, "_document", wraps=self.store._document) as materialize:
            state = self.store.dispatch("GET", "/api/state?workspace_id=" + self.workspace)
        self.assertEqual([row["id"] for row in state["workspaces"]], [self.workspace])
        self.assertEqual([row["id"] for row in state["documents"]], [own["id"]])
        self.assertEqual([call.args[0] for call in materialize.call_args_list], [own["id"]])
        for collection in ("notes", "matrix", "chats"):
            self.assertEqual(len(state[collection]), 1)
            self.assertEqual(state[collection][0]["workspace_id"], self.workspace)
        self.assertEqual(len(self.store.dispatch("GET", "/api/state")["workspaces"]), 2)

    def test_unknown_scoped_workspace_is_refused(self):
        with self.assertRaises(AppError) as error:
            self.store.dispatch("GET", "/api/state?workspace_id=" + "f" * 32)
        self.assertEqual(error.exception.status, 404)

    def test_workspace_inventory_never_materializes_source_or_draft_contents(self):
        self.document()
        self.store.dispatch("POST", "/api/notes", {"workspace_id": self.workspace, "title": "Draft", "body": "Synthetic draft content"})
        with patch.object(self.store, "_document", wraps=self.store._document) as materialize:
            inventory = self.store.dispatch("GET", "/api/workspaces")
        self.assertEqual(set(inventory), {"workspaces"})
        self.assertEqual([row["id"] for row in inventory["workspaces"]], [self.workspace])
        materialize.assert_not_called()

    def test_stale_metadata_writer_is_refused_and_current_fields_survive(self):
        document = self.document()
        initial_version = document["metadata_version"]
        saved = self.store.dispatch("POST", "/api/metadata", {
            "id": document["id"], "expected_metadata_version": initial_version,
            "metadata": {"title": "Reviewed widgets", "authors": "Example Author"},
        })
        self.assertEqual(saved["metadata_version"], initial_version + 1)
        with self.assertRaises(AppError) as error:
            self.store.dispatch("POST", "/api/metadata", {
                "id": document["id"], "expected_metadata_version": initial_version,
                "metadata": {"title": "Stale widgets"},
            })
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.store._document(document["id"])["metadata"], saved["metadata"])

    def test_metadata_noop_preserves_version_and_missing_version_is_refused(self):
        document = self.document()
        first = self.store.dispatch("POST", "/api/metadata", {"id": document["id"], "expected_metadata_version": 0, "metadata": {"title": "Widgets"}})
        unchanged = self.store.dispatch("POST", "/api/metadata", {
            "id": document["id"], "expected_metadata_version": first["metadata_version"], "metadata": first["metadata"],
        })
        self.assertEqual(unchanged["metadata_version"], first["metadata_version"])
        with self.assertRaises(AppError) as error:
            self.store.dispatch("POST", "/api/metadata", {"id": document["id"], "expected_metadata_version": True, "metadata": {}})
        self.assertEqual(error.exception.status, 400)
        with self.assertRaises(AppError) as error:
            self.store.dispatch("POST", "/api/metadata", {"id": document["id"], "metadata": {"title": "No version"}})
        self.assertEqual(error.exception.status, 400)

    def test_metadata_version_and_fields_survive_backup_and_restart(self):
        document = self.document()
        saved = self.store.dispatch("POST", "/api/metadata", {"id": document["id"], "expected_metadata_version": 0, "metadata": {"title": "Entered widgets", "author_list": [{"family": "Example", "given": "Ann"}]}})
        restored = self.restore(self.backup())
        restored_doc = self.store._state(restored["workspace_id"])["documents"][0]
        self.assertEqual(restored_doc["metadata"], saved["metadata"])
        self.assertEqual(restored_doc["metadata_version"], saved["metadata_version"])
        self.store.close()
        self.store = Store(Path(self.temp.name) / "data")
        self.addCleanup(self.store.close)
        self.assertEqual(self.store._document(document["id"])["metadata_version"], saved["metadata_version"])

    def test_legacy_backup_without_metadata_version_still_restores(self):
        self.document()
        legacy = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.backup())) as source, zipfile.ZipFile(legacy, "w") as target:
            for name in source.namelist():
                data = source.read(name)
                if name == "manifest.json":
                    manifest = json.loads(data)
                    for document in manifest["documents"]:
                        document.pop("metadata_version", None)
                    data = json.dumps(manifest).encode()
                target.writestr(name, data)
        restored = self.restore(legacy.getvalue())
        self.assertEqual(self.store._state(restored["workspace_id"])["documents"][0]["metadata_version"], 0)


if __name__ == "__main__":
    unittest.main()
