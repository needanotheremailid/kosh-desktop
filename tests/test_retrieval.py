"""Local retrieval checks: literal mocked vectors and one synthetic OCR image."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import AppError, Store
from retrieval import Retrieval


class RetrievalAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "data")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch("POST", "/api/workspaces", {"title": "Synthetic retrieval"})["id"]
        self.retrieval = Retrieval(self.store)
        self.models = patch.object(self.store, "models", return_value={"models": [{"name": "fixture-embed:latest", "size": 1024}], "available": True})
        self.models.start()
        self.addCleanup(self.models.stop)

    def document(self, text="Mechanical widgets advance rapidly.", workspace=None):
        return self.store._import({"workspace_id": workspace or self.workspace, "files": [{"name": "widgets.txt", "data": base64.b64encode(text.encode()).decode()}]})["results"][0]["document"]

    def call(self, route, **payload):
        return self.retrieval.dispatch("POST", route, {"workspace_id": self.workspace, "model": "fixture-embed:latest", **payload})

    def test_paraphrase_search_uses_vectors_and_retains_actual_source_locator(self):
        document = self.document()
        query = "Machines improve quickly"
        self.assertEqual(self.store._search({"workspace_id": self.workspace, "query": query}), [])
        with patch('backend.ollama_request', return_value={"embeddings": [[1.0, 0.0]]}) as embed:
            indexed = self.call("/api/retrieval/index")
            result = self.call("/api/retrieval/search", query=query)
        self.assertEqual(indexed["indexed"], 1)
        self.assertEqual(result["results"][0]["document_id"], document["id"])
        self.assertEqual(result["results"][0]["page"], 1)
        self.assertEqual(result["results"][0]["text"], "Mechanical widgets advance rapidly.")
        self.assertAlmostEqual(result["results"][0]["score"], 1.0)
        self.assertEqual(embed.call_args.args[0], '/api/embed')

    def test_bundled_ocr_data_is_preferred_per_language_with_installed_fallback(self):
        from retrieval import tessdata_for
        bundled = Path(self.temp.name) / 'bundled-tessdata'
        installed = Path(self.temp.name) / 'installed-tessdata'
        bundled.mkdir()
        installed.mkdir()
        (bundled / 'eng.traineddata').write_bytes(b'Synthetic bundle path marker')
        (installed / 'eng.traineddata').write_bytes(b'Synthetic installed path marker')
        (installed / 'hin.traineddata').write_bytes(b'Synthetic installed path marker')
        with patch('retrieval.BUNDLED_TESSDATA', bundled), patch('retrieval.TESSDATA', installed):
            self.assertEqual(tessdata_for('eng'), bundled)
            self.assertEqual(tessdata_for('hin'), installed)
            self.assertIsNone(tessdata_for('pan'))

    def test_embedding_capability_metadata_is_separate_from_runtime_proof(self):
        with patch.object(self.store, 'models', return_value={'available': True, 'models': [{'name': 'nomic-embed-text:latest'}]}), patch('backend.ollama_request', return_value={'capabilities': ['embedding'], 'model_info': {'general.architecture': 'nomic-bert', 'nomic-bert.embedding_length': 768}}) as request:
            capability = self.retrieval.dispatch('GET', '/api/retrieval/capabilities', {})['semantic']
        self.assertTrue(capability['recommended_model_installed'])
        self.assertTrue(capability['recommended_model_supports_embedding'])
        self.assertFalse(capability['runtime_verified_in_this_process'])
        self.assertEqual(capability['embedding_dimension'], 768)
        self.assertEqual(request.call_args.args[0], '/api/show')

    def test_repeated_index_skips_existing_and_cap_continues(self):
        self.document("x" * 160_800)
        def embed(route, payload, timeout):
            return {"embeddings": [[1.0, 0.0] for _ in payload["input"]]}
        with patch('backend.ollama_request', side_effect=embed) as request:
            first = self.call("/api/retrieval/index")
            second = self.call("/api/retrieval/index")
            third = self.call("/api/retrieval/index")
        self.assertEqual((first["indexed"], second["indexed"], third["indexed"]), (200, 1, 0))
        self.assertTrue(first["warnings"])
        self.assertEqual(request.call_count, 8)
        self.assertLessEqual(max(len(call.args[1]['input']) for call in request.call_args_list), 32)

    def test_invalid_vectors_are_rejected_without_partial_cache(self):
        self.document("x" * 1600)
        for vectors in ([[1.0, float('nan')], [1.0, 0.0]], [[1.0, 0.0], [1.0]], [[0.0, 0.0], [1.0, 0.0]], [[True, 0.0], [1.0, 0.0]]):
            with self.subTest(vectors=vectors), patch('backend.ollama_request', return_value={"embeddings": vectors}):
                with self.assertRaises(AppError):
                    self.call("/api/retrieval/index")
            self.assertEqual(self.store.db.execute('SELECT count(*) FROM semantic_chunks').fetchone()[0], 0)

    def test_foreign_catalogue_and_cloud_models_are_refused_before_embedding(self):
        other = self.store.dispatch("POST", "/api/workspaces", {"title": "Other widgets"})["id"]
        foreign = self.document(workspace=other)
        own = self.document()
        self.store.dispatch("POST", "/api/metadata", {"id": own["id"], "expected_metadata_version": 0, "metadata": {"catalogue_source": "Synthetic catalogue"}})
        with patch('backend.ollama_request') as embed:
            for payload in ({"document_ids": [foreign["id"]]}, {"document_ids": [own["id"]]}, {"model": "cloud:remote"}):
                with self.assertRaises(AppError):
                    self.call("/api/retrieval/index", **payload)
            embed.assert_not_called()

    def test_invalid_document_id_shapes_are_clear_boundary_errors(self):
        with patch('backend.ollama_request') as embed:
            for identifiers in ([{}], [True], ["not an ID"]):
                with self.subTest(identifiers=identifiers), self.assertRaises(AppError) as invalid:
                    self.call('/api/retrieval/index', document_ids=identifiers)
                self.assertEqual(invalid.exception.status, 400)
            embed.assert_not_called()

    def test_ocr_page_limit_and_pixel_limit_precede_rendering(self):
        import pymupdf
        source = pymupdf.open()
        source.new_page(width=2000, height=2000)
        raw = source.tobytes()
        source.close()
        document = self.store._import({"workspace_id": self.workspace, "files": [{"name": "oversized synthetic.pdf", "data": base64.b64encode(raw).decode()}]})['results'][0]['document']
        with patch.object(pymupdf.Page, 'get_pixmap') as render:
            with self.assertRaises(AppError) as oversized:
                self.retrieval.dispatch('POST', '/api/ocr', {"workspace_id": self.workspace, "document_id": document['id'], "language": "eng", "pages": [1]})
            self.assertEqual(oversized.exception.status, 413)
            for pages in ([1, 1], [True], [1] * 21):
                with self.assertRaises(AppError) as invalid:
                    self.retrieval.dispatch('POST', '/api/ocr', {"workspace_id": self.workspace, "document_id": document['id'], "language": "eng", "pages": pages})
                self.assertEqual(invalid.exception.status, 400)
            render.assert_not_called()

    def test_changed_original_is_ignored_and_cache_survives_restart(self):
        document = self.document()
        with patch('backend.ollama_request', return_value={"embeddings": [[1.0, 0.0]]}):
            self.call("/api/retrieval/index")
        self.store.close()
        self.store = Store(Path(self.temp.name) / 'data')
        self.addCleanup(self.store.close)
        retrieval = Retrieval(self.store)
        with patch.object(self.store, 'models', return_value={"models": [{"name": "fixture-embed:latest"}], "available": True}), patch('backend.ollama_request', return_value={"embeddings": [[1.0, 0.0]]}):
            good = retrieval.dispatch('POST', '/api/retrieval/search', {"workspace_id": self.workspace, "model": "fixture-embed:latest", "query": "Machines"})
            self.assertEqual(len(good['results']), 1)
            (self.store.root / self.store._document(document['id'])['path']).write_bytes(b'Changed source')
            stale = retrieval.dispatch('POST', '/api/retrieval/search', {"workspace_id": self.workspace, "model": "fixture-embed:latest", "query": "Machines"})
        self.assertEqual(stale['results'], [])
        self.assertTrue(stale['warnings'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM semantic_chunks').fetchone()[0], 1)

    def test_actual_synthetic_ocr_creates_derivative_and_preserves_original(self):
        capabilities = self.retrieval.dispatch('GET', '/api/retrieval/capabilities', {})
        if not capabilities['ocr']['available'] or 'eng' not in capabilities['ocr']['languages']:
            self.skipTest('Installed local English OCR is unavailable.')
        import pymupdf
        source = pymupdf.open()
        page = source.new_page(width=500, height=120)
        page.insert_text((30, 65), 'THIRTY SYNTHETIC WIDGETS', fontsize=20)
        image = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes('png')
        image_pdf = pymupdf.open()
        image_pdf.new_page(width=500, height=120).insert_image(pymupdf.Rect(0, 0, 500, 120), stream=image)
        raw = image_pdf.tobytes()
        source.close()
        image_pdf.close()
        document = self.store._import({"workspace_id": self.workspace, "files": [{"name": "synthetic image.pdf", "data": base64.b64encode(raw).decode()}]})['results'][0]['document']
        self.assertEqual(document['status'], 'no_text')
        ocr = self.retrieval.dispatch('POST', '/api/ocr', {"workspace_id": self.workspace, "document_id": document['id'], "language": "eng", "pages": [1]})
        derivative = ocr['results'][0]['document']
        self.assertNotEqual(derivative['id'], document['id'])
        self.assertEqual(self.store._bytes(self.store._document(document['id'])), raw)
        text = self.store.dispatch('GET', '/api/document?id=' + derivative['id'])['text_pages'][0]['text'].upper()
        self.assertIn('SYNTHETIC WIDGETS', text)
        self.assertEqual(ocr['page_mapping'], [{"derived_page": 1, "source_page": 1}])
        self.assertTrue(ocr['warnings'])


if __name__ == '__main__':
    unittest.main()
