"""Explicit local OCR derivatives and source-anchored optional embeddings."""
import base64
import json
import math
from pathlib import Path


TESSDATA = Path(r"C:\Program Files\Tesseract-OCR\tessdata")
BUNDLED_TESSDATA = Path(__file__).resolve().parent / 'tessdata'
OCR_LANGUAGES = ("eng", "hin", "pan")
CHUNK_SIZE = 800
INDEX_LIMIT = 200


def tessdata_for(language):
    if language not in OCR_LANGUAGES:
        return None
    for directory in (BUNDLED_TESSDATA, TESSDATA):
        if (directory / (language + '.traineddata')).is_file():
            return directory
    return None


def _vectors(response, count, dimension=None):
    import backend as b
    vectors = response.get("embeddings") if isinstance(response, dict) else None
    if not isinstance(vectors, list) or len(vectors) != count:
        raise b.AppError("Local embedding model returned an unexpected number of vectors.", 502)
    normalized = []
    for vector in vectors:
        if not isinstance(vector, list) or not 1 <= len(vector) <= 8192 or any(type(value) not in {int, float} or not math.isfinite(value) for value in vector):
            raise b.AppError("Local embedding vectors must contain bounded finite numbers.", 502)
        if dimension is None:
            dimension = len(vector)
        if len(vector) != dimension:
            raise b.AppError("Embedding dimensions changed or are inconsistent. Use the same installed embedding model for index and search.", 409)
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isfinite(norm) or norm == 0:
            raise b.AppError("Local embedding model returned an empty or invalid vector.", 502)
        normalized.append([value / norm for value in vector])
    return normalized


class Retrieval:
    ROUTES = {("GET", "/api/retrieval/capabilities"), ("POST", "/api/ocr"), ("POST", "/api/retrieval/index"), ("POST", "/api/retrieval/search")}

    def __init__(self, store):
        self.store = store
        with store.lock, store.db:
            if not hasattr(store, '_embedding_verified_models'):
                store._embedding_verified_models = set()
            store.db.execute("""CREATE TABLE IF NOT EXISTS semantic_chunks(
                document_id TEXT NOT NULL REFERENCES documents(id), model TEXT NOT NULL,
                page INTEGER NOT NULL, offset INTEGER NOT NULL, source_sha256 TEXT NOT NULL,
                text TEXT NOT NULL, vector TEXT NOT NULL, dimension INTEGER NOT NULL,
                PRIMARY KEY(document_id,model,page,offset,source_sha256))""")

    @staticmethod
    def supports(method, route):
        return (method.upper(), route) in Retrieval.ROUTES

    @staticmethod
    def capabilities(store=None):
        import backend as b
        languages = [language for language in OCR_LANGUAGES if tessdata_for(language) is not None]
        semantic = {"optional": True, "provider": "local Ollama", "chunk_characters": CHUNK_SIZE, "chunks_per_request": INDEX_LIMIT,
                    "recommended_model": "nomic-embed-text:latest", "recommended_model_installed": False,
                    "recommended_model_supports_embedding": None, "embedding_dimension": None,
                    "runtime_verified_in_this_process": False, "readiness": "not_checked",
                    "notice": "Installed model capability and successful embedding execution are separate checks. This readiness summary assesses nomic-embed-text only; other installed models are not assessed. Cache is excluded from workspace ZIP backups and can be rebuilt; no cloud fallback."}
        if store is not None:
            inventory = store.models()
            semantic['ollama_available'] = bool(inventory.get('available'))
            installed = {row['name'] for row in inventory.get('models', [])}
            semantic['recommended_model_installed'] = 'nomic-embed-text:latest' in installed
            semantic['readiness'] = 'not_installed' if inventory.get('available') else 'ollama_unavailable'
            if semantic['recommended_model_installed']:
                try:
                    info = b.ollama_request('/api/show', {'model': 'nomic-embed-text:latest'}, timeout=3)
                    semantic['recommended_model_supports_embedding'] = 'embedding' in info.get('capabilities', [])
                    architecture = info.get('model_info', {}).get('general.architecture', '')
                    dimension = info.get('model_info', {}).get(architecture + '.embedding_length')
                    semantic['embedding_dimension'] = dimension if type(dimension) is int and dimension > 0 else None
                    semantic['readiness'] = 'installed_embedding_capability_verified' if semantic['recommended_model_supports_embedding'] else 'installed_without_embedding_capability'
                except b.AppError:
                    semantic['readiness'] = 'installed_capability_unverified'
                semantic['runtime_verified_in_this_process'] = 'nomic-embed-text:latest' in getattr(store, '_embedding_verified_models', set())
        return {"ocr": {"available": b.pdf_lib is not None and bool(languages), "languages": languages,
                        "language_sources": {language: 'bundled' if tessdata_for(language) == BUNDLED_TESSDATA else 'installed' for language in languages},
                        "max_pages": 20, "max_pixels_per_page": 20_000_000,
                        "notice": "Local OCR creates a separate derived PDF. Review recognised text against the original images."},
                "semantic": semantic}

    def dispatch(self, method, route, payload):
        import backend as b
        if not self.supports(method, route):
            raise b.AppError("This retrieval operation is not available.", 404)
        if not isinstance(payload, dict):
            raise b.AppError("Retrieval request must be an object.")
        if route == "/api/retrieval/capabilities":
            return self.capabilities(self.store)
        if route == "/api/ocr":
            return self._ocr(payload)
        return self._index(payload) if route.endswith("/index") else self._search(payload)

    def _model(self, value):
        import backend as b
        model = b.text_value(value, "Local embedding model", 200, False).strip()
        inventory = self.store.models()
        installed = {row['name'] for row in inventory.get('models', [])}
        if model not in installed and model + ':latest' in installed:
            model += ':latest'
        if not inventory.get("available") or model not in installed:
            raise b.AppError("Choose an installed local Ollama embedding model. No model is downloaded and no cloud fallback is used.", 503)
        return model

    def _documents(self, payload):
        """Called under Store lock; never materialize a foreign workspace row."""
        import backend as b
        workspace_id = self.store._workspace(payload.get("workspace_id"))["id"]
        ids = payload.get("document_ids")
        if ids is not None:
            if not isinstance(ids, list) or not 1 <= len(ids) <= 1000:
                raise b.AppError("Choose one to 1,000 distinct source IDs.")
            ids = [b.identifier(value) for value in ids]
            if len(set(ids)) != len(ids):
                raise b.AppError("Choose one to 1,000 distinct source IDs.")
            documents = [self.store._document(value, workspace_id) for value in ids]
            if any(row["status"] != "ready" or row["archived"] or row["metadata"].get("catalogue_source") for row in documents):
                raise b.AppError("Embedding retrieval requires ready, unarchived paper text; catalogue metadata is excluded.")
        else:
            documents = [self.store._document(row[0], workspace_id) for row in self.store.db.execute("SELECT id FROM documents WHERE workspace_id=? AND status='ready' AND archived=0 ORDER BY created_at,id", (workspace_id,)).fetchall()]
            documents = [row for row in documents if not row["metadata"].get("catalogue_source")]
        return workspace_id, documents

    def _index(self, payload):
        import backend as b
        model = self._model(payload.get("model"))
        chunks, selected, limited = [], {}, False
        with self.store.lock:
            self.store._ensure_open()
            workspace_id, documents = self._documents(payload)
            for document in documents:
                self.store._bytes(document)
                existing = {(row[0], row[1]) for row in self.store.db.execute("SELECT page,offset FROM semantic_chunks WHERE document_id=? AND model=? AND source_sha256=?", (document["id"], model, document["sha256"]))}
                for page in self.store.db.execute("SELECT page,text FROM pages WHERE document_id=? ORDER BY page", (document["id"],)):
                    for offset in range(0, len(page["text"]), CHUNK_SIZE):
                        excerpt = page["text"][offset:offset + CHUNK_SIZE]
                        if not excerpt.strip() or (page["page"], offset) in existing:
                            continue
                        if len(chunks) == INDEX_LIMIT:
                            limited = True
                            break
                        chunks.append({"document_id": document["id"], "model": model, "page": page["page"], "offset": offset, "source_sha256": document["sha256"], "text": excerpt})
                        selected[document["id"]] = document
                    if limited:
                        break
                if limited:
                    break
            dimensions = {row[0] for row in self.store.db.execute("SELECT DISTINCT dimension FROM semantic_chunks WHERE model=? AND document_id IN (SELECT id FROM documents WHERE workspace_id=?)", (model, workspace_id))}
        if len(dimensions) > 1:
            raise b.AppError("Cached model dimensions conflict. Choose a consistent installed model.", 409)
        if chunks:
            vectors = []
            dimension = next(iter(dimensions), None)
            for offset in range(0, len(chunks), 32):
                batch = chunks[offset:offset + 32]
                values = _vectors(b.ollama_request("/api/embed", {"model": model, "input": [chunk["text"] for chunk in batch]}, timeout=120), len(batch), dimension)
                dimension = len(values[0])
                vectors.extend(values)
            with self.store.lock, self.store.db:
                self.store._ensure_open()
                self.store._embedding_verified_models.add(model)
                current_dimensions = {row[0] for row in self.store.db.execute("SELECT DISTINCT dimension FROM semantic_chunks WHERE model=? AND document_id IN (SELECT id FROM documents WHERE workspace_id=?)", (model, workspace_id))}
                if current_dimensions and current_dimensions != {len(vectors[0])}:
                    raise b.AppError("Cached model dimensions changed during indexing. No new embeddings were saved.", 409)
                for document in selected.values():
                    current = self.store._document(document["id"], workspace_id)
                    self.store._bytes(current)
                    if current["sha256"] != document["sha256"] or current["archived"] or current["metadata"].get("catalogue_source"):
                        raise b.AppError("Selected source changed while indexing. No embeddings were saved.", 409)
                indexed = 0
                for chunk, vector in zip(chunks, vectors):
                    indexed += self.store.db.execute("INSERT OR IGNORE INTO semantic_chunks(document_id,model,page,offset,source_sha256,text,vector,dimension) VALUES(:document_id,:model,:page,:offset,:source_sha256,:text,:vector,:dimension)", {**chunk, "vector": json.dumps(vector), "dimension": len(vector)}).rowcount
        else:
            indexed = 0
        with self.store.lock:
            total = self.store.db.execute("SELECT count(*) FROM semantic_chunks WHERE model=? AND document_id IN (SELECT id FROM documents WHERE workspace_id=?)", (model, workspace_id)).fetchone()[0]
        return {"workspace_id": workspace_id, "model": model, "indexed": indexed, "total": total,
                "warnings": ["Request reached the 200-chunk limit. Repeat indexing to continue; existing chunks are retained and skipped."] if limited else [],
                "notice": "Local embeddings only. Semantic similarity does not verify claims or citation entailment. Cache is outside workspace ZIP backups and may be rebuilt."}

    def _search(self, payload):
        import backend as b
        model = self._model(payload.get("model"))
        query = b.text_value(payload.get("query"), "Semantic query", 4000, False).strip()
        warnings, candidates = [], []
        with self.store.lock:
            self.store._ensure_open()
            workspace_id, documents = self._documents(payload)
            for document in documents:
                try:
                    self.store._bytes(document)
                except b.AppError:
                    warnings.append("A changed or missing managed source was excluded from semantic results.")
                    continue
                rows = self.store.db.execute("SELECT * FROM semantic_chunks WHERE document_id=? AND model=? AND source_sha256=? ORDER BY page,offset", (document["id"], model, document["sha256"])).fetchall()
                for row in rows:
                    page = self.store.db.execute("SELECT text FROM pages WHERE document_id=? AND page=?", (document["id"], row["page"])).fetchone()
                    if page is None or page["text"][row["offset"]:row["offset"] + len(row["text"])] != row["text"]:
                        warnings.append("An outdated extracted-text cache entry was ignored.")
                        continue
                    candidates.append((document, dict(row)))
        if not candidates:
            return {"results": [], "warnings": warnings + ["No current indexed text for this model and scope. Index selected paper text first."], "model": model}
        dimension = candidates[0][1]["dimension"]
        vector = _vectors(b.ollama_request("/api/embed", {"model": model, "input": [query]}, timeout=120), 1, dimension)[0]
        ranked = []
        with self.store.lock:
            self.store._ensure_open()
            self.store._embedding_verified_models.add(model)
            checked = {}
            for document, row in candidates:
                if document["id"] not in checked:
                    try:
                        current = self.store._document(document["id"], workspace_id)
                        self.store._bytes(current)
                        checked[document["id"]] = current["sha256"] == document["sha256"] and not current["archived"] and not current["metadata"].get("catalogue_source")
                    except b.AppError:
                        checked[document["id"]] = False
                if not checked[document["id"]]:
                    warnings.append("A source changed during semantic search and was excluded.")
                    continue
                try:
                    source_vector = _vectors({"embeddings": [json.loads(row["vector"])]}, 1, dimension)[0]
                except (b.AppError, ValueError):
                    warnings.append("An invalid or inconsistent cached vector was ignored.")
                    continue
                score = sum(left * right for left, right in zip(vector, source_vector))
                ranked.append({"document_id": document["id"], "name": document["name"], "page": row["page"], "offset": row["offset"], "text": row["text"], "score": max(-1.0, min(1.0, score))})
        ranked.sort(key=lambda row: (-row["score"], row["document_id"], row["page"], row["offset"]))
        return {"results": ranked[:10], "warnings": list(dict.fromkeys(warnings)), "model": model,
                "notice": "Source-linked semantic similarity only; read the original context and verify every claim."}

    def _ocr(self, payload):
        import backend as b
        language = payload.get("language", "eng")
        tessdata = tessdata_for(language)
        if tessdata is None:
            raise b.AppError("Choose an installed local OCR language: eng, hin or pan. No language download is performed.", 503)
        if b.pdf_lib is None:
            raise b.AppError("PDF OCR is unavailable in this runtime.", 503)
        with self.store.lock:
            self.store._ensure_open()
            workspace_id = self.store._workspace(payload.get("workspace_id"))["id"]
            document = self.store._document(payload.get("document_id"), workspace_id)
            if document["kind"] != "pdf" or document["metadata"].get("catalogue_source"):
                raise b.AppError("OCR requires a selected managed PDF original.")
            original = self.store._bytes(document)
        combined = b.pdf_lib.open()
        try:
            with b.pdf_lib.open(stream=original, filetype="pdf") as source:
                pages = payload.get("pages", list(range(1, source.page_count + 1)))
                if not isinstance(pages, list) or not 1 <= len(pages) <= 20 or any(type(page) is not int or not 1 <= page <= source.page_count for page in pages) or len(set(pages)) != len(pages):
                    raise b.AppError("Select one to twenty distinct actual PDF pages for this OCR request.")
                pages = sorted(pages)
                output_size = 0
                for number in pages:
                    page = source[number - 1]
                    if math.ceil(page.rect.width * 300 / 72) * math.ceil(page.rect.height * 300 / 72) > 20_000_000:
                        raise b.AppError("OCR page exceeds the 20-million-pixel rendering limit.", 413)
                    pixmap = page.get_pixmap(dpi=300, colorspace=b.pdf_lib.csRGB, alpha=False)
                    recognised = pixmap.pdfocr_tobytes(language=language, tessdata=str(tessdata))
                    output_size += len(recognised)
                    if output_size > b.FILE_LIMIT:
                        raise b.AppError("Combined OCR derivative exceeds the 32 MiB output limit.", 413)
                    with b.pdf_lib.open(stream=recognised, filetype="pdf") as part:
                        combined.insert_pdf(part)
                output = combined.tobytes(garbage=3, deflate=True)
                if len(output) > b.FILE_LIMIT:
                    raise b.AppError("Combined OCR derivative exceeds the 32 MiB output limit.", 413)
        except b.AppError:
            raise
        except Exception:
            raise b.AppError("Local OCR failed. Check the installed Tesseract language data; the original PDF was retained.", 503) from None
        finally:
            combined.close()
        mapping = [{"derived_page": index + 1, "source_page": number} for index, number in enumerate(pages)]
        provenance = ("Unverified local OCR derivative of retained source " + document["id"] + "; language " + language + "; derived-page to original-file-page mapping: " + ", ".join(str(row["derived_page"]) + "->" + str(row["source_page"]) for row in mapping) + ". Review recognised text against original images.")[:1000]
        with self.store.lock:
            self.store._ensure_open()
            current = self.store._document(document["id"], workspace_id)
            self.store._bytes(current)
            if current["sha256"] != document["sha256"]:
                raise b.AppError("Original changed during OCR. No derivative was imported.", 409)
            name = Path(document["name"]).stem[:210] + " OCR.pdf"
            receipt = self.store._import({"workspace_id": workspace_id, "files": [{"name": name, "data": base64.b64encode(output).decode("ascii")}]})
            imported = receipt["results"][0]
            if imported.get("document") and imported["status"] != "duplicate":
                derivative = imported["document"]
                metadata = b.metadata_value({**document["metadata"], "provenance": b.append_provenance(provenance, document['metadata'].get('provenance', ''))})
                with self.store.db:
                    self.store.db.execute("UPDATE documents SET metadata=?,metadata_version=metadata_version+1 WHERE id=?", (json.dumps(metadata, ensure_ascii=False), derivative["id"]))
                imported["document"] = self.store._public_doc(self.store._document(derivative["id"], workspace_id))
        return {**receipt, "source_document_id": document["id"], "page_mapping": mapping, "provenance": provenance,
                "warnings": ["OCR creates a derived PDF, not corrected source evidence. Its source markers refer to derived file pages; mapping identifies original pages. Review recognition errors against images. Original files and existing citations were retained."]}
