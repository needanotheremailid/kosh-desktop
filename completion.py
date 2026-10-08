"""Explicit local bibliography, attachment, asset and recovery endpoints."""
import base64
import hashlib
import json
import math
from pathlib import Path
import re

from bibliography import BIB_FIELDS, BibliographyError, MAX_RECORDS, parse_bibliography


BIBLIOGRAPHIC_FIELDS = {"title", "authors", "author_list", "year", "doi", "type", "journal", "journal_abbreviation", "volume", "issue", "pages", "publisher", "publisher_place", "booktitle", "edition", "isbn", "issn", "url", "abstract", "note", "editors", "institution", "report_number", "thesis_type"}
CSL_FIELDS = {"title": "title", "DOI": "doi", "URL": "url", "volume": "volume", "issue": "issue", "page": "pages", "publisher": "publisher", "publisher-place": "publisher_place", "edition": "edition", "ISBN": "isbn", "ISSN": "issn", "abstract": "abstract", "note": "note", "container-title-short": "journal_abbreviation", "institution": "institution", "number": "report_number", "genre": "thesis_type"}
CSL_TYPES = {"article-journal": "journal_article", "book": "book", "chapter": "book_chapter", "report": "report", "thesis": "thesis", "document": "other"}


def _doi(value):
    value = str(value or "").strip()
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", value, flags=re.I).strip().casefold()


def _csl_text(value, field):
    import backend as b
    if field in {'volume', 'issue', 'page', 'number', 'edition'} and type(value) in {int, float}:
        if type(value) is float and not math.isfinite(value):
            raise b.AppError('CSL numeric variables must be finite values.')
        value = str(value)
    return b.text_value(value, field, 4000)


def _csl_record(item, number):
    import backend as b
    warnings = []
    allowed = {*CSL_FIELDS, "id", "type", "author", "editor", "issued", "container-title"}
    if not isinstance(item, dict):
        raise b.AppError("Every CSL JSON record must be an object.")
    kind = item.get("type", "document")
    if not isinstance(kind, str):
        raise b.AppError("CSL publication type must be text.")
    if kind not in CSL_TYPES:
        warnings.append(f"Record {number}: unsupported CSL type retained as other.")
    record = {"id": b.text_value(str(item.get("id", "")), "Record ID", 1000), "type": CSL_TYPES.get(kind, "other"), "title": "", "authors": "", "author_list": [], "year": ""}
    for source, target in CSL_FIELDS.items():
        if source in item:
            record[target] = _csl_text(item[source], source)
    if "container-title" in item:
        record["booktitle" if record["type"] == "book_chapter" else "journal"] = b.text_value(item["container-title"], "Container title", 4000)
    if "author" in item:
        authors = item["author"]
        if not isinstance(authors, list) or len(authors) > 200:
            raise b.AppError("CSL authors must be a list of at most 200 names.")
        for author in authors:
            if not isinstance(author, dict) or set(author) - {"literal", "family", "given"} or ("literal" in author and set(author) != {"literal"}):
                raise b.AppError("CSL authors support an explicit literal name or family/given fields.")
            if "literal" in author:
                record["author_list"].append({"literal": b.text_value(author["literal"], "Literal author", 200, False)})
            else:
                record["author_list"].append({"family": b.text_value(author.get("family"), "Author family", 200, False), "given": b.text_value(author.get("given", ""), "Author given", 200)})
        record["authors"] = "; ".join(author.get("literal") or author["family"] + (", " + author["given"] if author["given"] else "") for author in record["author_list"])
    if 'editor' in item:
        editors = item['editor']
        if not isinstance(editors, list) or len(editors) > 200:
            raise b.AppError('CSL editors must be a list of at most 200 explicit names.')
        names = []
        for editor in editors:
            if not isinstance(editor, dict) or set(editor) - {'literal', 'family', 'given'} or ('literal' in editor and set(editor) != {'literal'}):
                raise b.AppError('CSL editors support an explicit literal name or family/given fields.')
            if 'literal' in editor:
                names.append(b.text_value(editor['literal'], 'Editor literal name', 200, False))
            else:
                family = b.text_value(editor.get('family'), 'Editor family', 200, False)
                given = b.text_value(editor.get('given', ''), 'Editor given', 200)
                names.append(family + (', ' + given if given else ''))
        record['editors'] = '; '.join(names)
        if editors:
            warnings.append(f'Record {number}: editor names retained as entered text; structured editor formatting needs review.')
    if "issued" in item:
        issued = item["issued"]
        if not isinstance(issued, dict):
            raise b.AppError("CSL issued date must have explicit date-parts or literal text.")
        if "date-parts" in issued:
            parts = issued["date-parts"]
            if not isinstance(parts, list) or not parts or not isinstance(parts[0], list) or not 1 <= len(parts[0]) <= 3:
                raise b.AppError("CSL date-parts need an explicit integer publication year.")
            first = []
            for part in parts[0]:
                if type(part) is int:
                    first.append(part)
                elif isinstance(part, str) and re.fullmatch(r"[0-9]+", part) and len(part) <= 4:
                    first.append(int(part))
                else:
                    raise b.AppError("CSL date-parts need integer or digit-string components; booleans are not dates.")
            if not 1 <= first[0] <= 9999:
                raise b.AppError("CSL publication year is outside the supported range.")
            record["year"] = str(first[0])
            if len(parts[0]) > 1 or len(parts) > 1:
                warnings.append(f"Record {number}: publication year retained; finer date/range requires review.")
        elif "literal" in issued:
            record["year"] = b.text_value(issued["literal"], "Issued date", 1000)
        else:
            warnings.append(f"Record {number}: issued date has no supported explicit value.")
    unsupported = sorted(set(item) - allowed)
    if unsupported:
        warnings.append(f"Record {number}: unsupported CSL fields omitted: " + ", ".join(unsupported) + ".")
    return record, warnings


def _csl(text):
    import backend as b
    text = b.text_value(text, "Bibliography JSON", 2_000_000)
    try:
        items = json.loads(text.lstrip("\ufeff"))
    except ValueError:
        raise b.AppError("CSL JSON must be a JSON array of explicit publication records.") from None
    if not isinstance(items, list) or len(items) > MAX_RECORDS:
        raise b.AppError("CSL JSON supports an array of at most 1,000 records.")
    records, numbers, warnings, errors, record_warnings = [], [], [], [], []
    for number, item in enumerate(items, 1):
        try:
            record, own_warnings = _csl_record(item, number)
            records.append(record)
            numbers.append(number)
            warnings.extend(own_warnings)
            record_warnings.append(own_warnings)
        except b.AppError as failure:
            identifier = item.get('id', str(number)) if isinstance(item, dict) else str(number)
            errors.append({'record_number': number, 'record_id': str(identifier)[:1000], 'status': 'error', 'error': str(failure), 'warnings': []})
    if errors and not records:
        raise b.AppError('No valid CSL records: Record ' + str(errors[0]['record_number']) + ': ' + errors[0]['error'])
    return {'records': records, 'record_numbers': numbers, 'warnings': warnings or ([] if records else ['No bibliography records found.']), 'record_warnings': record_warnings, 'errors': errors}


def _bib_bytes(metadata):
    """Stable local BibTeX subset; external source keys cannot defeat deduplication."""
    def escape(value):
        return str(value).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\r", " ").replace("\n", " ")
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    kinds = {"journal_article": "article", "book": "book", "book_chapter": "incollection", "report": "techreport", "thesis": "thesis"}
    fields = []
    for bib_field, source in BIB_FIELDS.items():
        if bib_field == 'school':
            continue
        if bib_field == 'institution' and metadata.get('type') == 'thesis':
            bib_field = 'school'
        if bib_field == 'number' and metadata.get('type') == 'report':
            source = 'report_number'
        if metadata.get(source):
            fields.append(bib_field + " = {" + escape(metadata[source]) + "}")
    authors = []
    for author in metadata.get("author_list", []):
        if "literal" in author:
            authors.append("{" + escape(author["literal"]) + "}")
        else:
            authors.append(escape(author["family"]) + (", " + escape(author.get("given", "")) if author.get("given") else ""))
    if not authors and metadata.get("authors"):
        authors = ["{" + escape(metadata["authors"]) + "}"]
    if authors:
        fields.append("author = {" + " and ".join(authors) + "}")
    if metadata.get('editors'):
        fields.append('editor = {{' + escape(metadata['editors']) + '}}')
    return ("@" + kinds.get(metadata.get("type"), "misc") + "{ref" + digest[:16] + ",\n  " + ",\n  ".join(fields) + "\n}\n").encode("utf-8")


class Completion:
    ROUTES = {("POST", "/api/bibliography/preview"), ("POST", "/api/bibliography/import"), ("POST", "/api/catalogue/attach"), ("POST", "/api/assets/import"), ("GET", "/api/notes/history"), ("GET", "/api/assist/history"), ("GET", "/api/assist/result")}

    def __init__(self, store):
        self.store = store

    @staticmethod
    def supports(method, route):
        return (method.upper(), route) in Completion.ROUTES | {('POST', '/api/assist/apply'), ('POST', '/api/manuscript/preview'), ('GET', '/api/citation/styles'), ('POST', '/api/citation/styles/import'), ('POST','/api/citation/styles/retrieve'), ('POST','/api/citation/locales/import'), ('GET','/api/export/options')}

    def dispatch(self, method, route, payload):
        import backend as b
        if not isinstance(payload, dict):
            raise b.AppError("Completion request must be an object.")
        if not self.supports(method, route):
            raise b.AppError("This completion operation is not available.", 404)
        with self.store.lock:
            self.store._ensure_open()
            if route == '/api/export/options':
                from manuscript_templates import PROFILES, DEFAULTS, OUTLINES
                from word_citations import WORD_STYLES
                from tex_compile import compiler_status
                from csl_styles import StyleLibrary
                return {'profiles':PROFILES,'defaults':DEFAULTS,'outlines':OUTLINES,'word_styles':{key:value[1] for key,value in WORD_STYLES.items()},'locales':StyleLibrary(self.store.root).list_locales(),'compiler':compiler_status()}
            if route in {'/api/citation/styles', '/api/citation/styles/import','/api/citation/styles/retrieve','/api/citation/locales/import'}:
                from csl_styles import StyleLibrary, StyleError, describe
                from csl_engine import render, CSLError
                library = StyleLibrary(self.store.root)
                try:
                    if route == '/api/citation/locales/import':
                        return {'locale':library.import_locale(payload.get('xml')),'locales':library.list_locales(),'styles':library.list_styles()}
                    if route.endswith('/retrieve'):
                        if payload.get('approved') is not True:raise StyleError('Approve official CSL retrieval for this request.')
                        if payload.get('style'):
                            library.retrieve_dependencies(payload['style'],language=payload.get('language') or None,approved=True)
                            row={'id':payload['style']}
                        else:
                            row=library.retrieve_official(style_id=payload.get('style_id'),locale=payload.get('locale'),approved=True)
                        return {'style':row,'styles':library.list_styles(),'locales':library.list_locales()}
                    if route.endswith('/import'):
                        xml = payload.get('xml')
                        describe(xml)
                        details=describe(xml)
                        # Dependent imports can be saved before their parent; exports
                        # fail explicitly until approved retrieval/local import resolves it.
                        if not details['parent']:
                            render([{'id': 'style-check', 'type': 'article-journal', 'title': 'Style validation'}], [['style-check']], style_xml=xml,locales=library._locales())
                        return {'style': library.import_style(xml), 'styles': library.list_styles(),'locales':library.list_locales()}
                    return {'styles': library.list_styles(),'locales':library.list_locales()}
                except (StyleError, CSLError) as error:
                    raise b.AppError(str(error)) from None
            if route == '/api/assist/apply':
                from assistance import selected_patch
                result = self.store.assistance.result(payload.get('result_id'))
                if not result.get('note_id') or result.get('task') not in {'shorten', 'clarity', 'grammar', 'translate'}:
                    raise b.AppError('This result is a separate proposal, not a selected-text replacement.')
                note = self.store._assist_note(result['note_id'], result['workspace_id'], payload.get('expected_version'))
                row = self.store.db.execute('SELECT payload FROM assist_jobs WHERE result_id=?', (result['result_id'],)).fetchone()
                preview = json.loads(row['payload'])
                if payload.get('selected_text') != preview.get('selected_text'):
                    raise b.AppError('Selected text differs from the reviewed request.', 409)
                body = selected_patch(note, preview, result['proposal'])
                return self.store._save_note({**note, 'body': body})
            if route == '/api/manuscript/preview':
                from manuscript import render_html
                from exports import FIGURE_KINDS
                workspace_id = self.store._workspace(payload.get('workspace_id'))['id']
                note = self.store._assist_note(payload.get('note_id'), workspace_id, payload.get('version'))
                assets = {}
                asset_bytes = 0
                def asset_url(target):
                    nonlocal asset_bytes
                    if target in assets:
                        return assets[target]
                    match = re.fullmatch(r'kosh-asset:([a-f0-9]{32})', target)
                    if not match:
                        raise b.AppError('Choose a managed figure from this workspace.')
                    document = self.store._document(match[1], workspace_id)
                    if document['kind'] not in FIGURE_KINDS:
                        raise b.AppError('Only imported figures can be displayed as an image.')
                    mime = 'jpeg' if document['kind'] in {'jpg', 'jpeg'} else document['kind']
                    data = self.store._bytes(document)
                    asset_bytes += len(data)
                    if asset_bytes > 47 * 1024 * 1024:
                        raise b.AppError('Preview figures exceed the 47 MiB bound. Export or preview a smaller draft.', 413)
                    assets[target] = 'data:image/' + mime + ';base64,' + base64.b64encode(data).decode('ascii')
                    return assets[target]
                return {'html': render_html(note['body'], image_url=asset_url)}
            if route in {"/api/bibliography/preview", "/api/bibliography/import"}:
                workspace_id = self.store._workspace(payload.get("workspace_id"))["id"]
                format = payload.get("format")
                if not isinstance(format, str) or format not in {"bib", "ris", "csljson"}:
                    raise b.AppError("Choose bib, ris or csljson bibliography input.")
                try:
                    parsed = _csl(payload.get("text")) if format == "csljson" else parse_bibliography(payload.get("text"), format)
                except BibliographyError as error:
                    raise b.AppError(str(error)) from None
                return parsed if route.endswith("/preview") else self._bibliography_import(workspace_id, parsed, format)
            if route == "/api/catalogue/attach":
                return self._attach(payload)
            if route == "/api/assets/import":
                return self._asset(payload)
            if route == "/api/notes/history":
                note = self.store.db.execute("SELECT * FROM notes WHERE id=?", (b.identifier(payload.get("id")),)).fetchone()
                if note is None:
                    raise b.AppError("Note not found.", 404)
                if set(payload) != {'id'}:
                    return self._paged_note_history(dict(note), payload)
                records = [json.loads(row[0]) for row in self.store.db.execute("SELECT payload FROM revisions WHERE entity_type='note' AND entity_id=? ORDER BY version", (note["id"],))] + [dict(note)]
                return {"revisions": [{"id": row["id"], "title": row["title"], "body": row["body"], "version": row["version"], "created_at": row["updated_at"]} for row in records]}
            workspace_id = self.store._workspace(payload.get("workspace_id"))["id"]
            try:
                if route == "/api/assist/result":
                    return self.store.assistance.result(payload.get("result_id"), workspace_id)
                jobs = [job for job in self.store.assistance.history(workspace_id) if job.get('task') != 'folder']
                return {"jobs": jobs, "results": [self.store.assistance.result(job["result_id"], workspace_id) for job in jobs if job["status"] == "complete"]}
            except ValueError as error:
                raise b.AppError(str(error), getattr(error, "status", 400)) from None

    def _paged_note_history(self, note, payload):
        """List bounded metadata or read one exact body from a pinned snapshot."""
        import backend as b
        if set(payload) - {'id','workspace_id','expected_version','metadata_only','before','version'}:
            raise b.AppError('Unsupported revision comparison option.')
        if b.identifier(payload.get('workspace_id')) != note['workspace_id']:
            raise b.AppError('Note not found in this workspace.', 404)

        def version(key):
            value = str(payload.get(key, ''))
            if not re.fullmatch(r'[1-9][0-9]{0,6}', value) or int(value) > 1_000_000:
                raise b.AppError('Revision versions must be positive integers within the supported range.')
            return int(value)

        if version('expected_version') != note['version']:
            raise b.AppError('The saved draft changed. Reopen comparison to use its current revisions.', 409)
        metadata = payload.get('metadata_only') == '1'
        if ('metadata_only' in payload and not metadata) or metadata == ('version' in payload) or ('before' in payload and not metadata):
            raise b.AppError('Choose a metadata page or one exact saved version.')
        rows = []
        if metadata:
            before = version('before') if 'before' in payload else note['version'] + 1
            if note['version'] < before:
                rows.append({key:note[key] for key in ('id','title','version','updated_at')})
            cursor = self.store.db.execute("SELECT payload FROM revisions WHERE entity_type='note' AND entity_id=? AND version<? ORDER BY version DESC LIMIT 101", (note['id'], min(before,note['version'])))
            for record in cursor:
                row = json.loads(record[0])
                rows.append({key:row[key] for key in ('id','title','version','updated_at')})
                if len(rows) > 100:
                    break
            next_before = rows[99]['version'] if len(rows) > 100 else None
            rows = rows[:100]
        else:
            selected = version('version')
            if selected == note['version']:
                row = note
            else:
                record = self.store.db.execute("SELECT payload FROM revisions WHERE entity_type='note' AND entity_id=? AND version=?", (note['id'],selected)).fetchone()
                if record is None:
                    raise b.AppError('Saved revision not found.',404)
                row = json.loads(record[0])
            rows = [row]
            next_before = None
        revisions = [{**{key:row[key] for key in ('id','title','version')},'created_at':row['updated_at'],**({} if metadata else {'body':row['body']})} for row in rows]
        return {'note_id':note['id'],'workspace_id':note['workspace_id'],'current_version':note['version'],
                'revisions':revisions,'next_before':next_before}

    def _bibliography_import(self, workspace_id, parsed, format):
        import backend as b
        results = [dict(error) for error in parsed.get('errors', [])]
        numbers = parsed.get('record_numbers', list(range(1, len(parsed['records']) + 1)))
        for index, (number, record) in enumerate(zip(numbers, parsed["records"])):
            identifier = record.get('id') or str(number)
            own_warnings = list(parsed['record_warnings'][index])
            receipt = {"record_number": number, "record_id": identifier, "warnings": own_warnings}
            try:
                fields = {key: value for key, value in record.items() if key in BIBLIOGRAPHIC_FIELDS}
                fields["catalogue_source"] = "Bibliography import"
                fields["provenance"] = ("Unverified local " + format + " bibliography import; publication fields require review. " + " ".join(own_warnings))[:1000]
                metadata = b.metadata_value(fields)
                doi = _doi(metadata.get("doi"))
                duplicate = None
                if doi:
                    for row in self.store.db.execute("SELECT id,metadata FROM documents WHERE workspace_id=? ORDER BY created_at,id", (workspace_id,)).fetchall():
                        if _doi(json.loads(row["metadata"]).get("doi")) == doi:
                            duplicate = self.store._public_doc(self.store._document(row["id"], workspace_id))
                            break
                if duplicate:
                    receipt.update(status="duplicate", document=duplicate)
                else:
                    data = _bib_bytes({key: value for key, value in metadata.items() if key not in {"catalogue_source", "provenance"}})
                    imported = self.store._import({"workspace_id": workspace_id, "files": [{"name": "reference-" + hashlib.sha256(data).hexdigest()[:12] + ".bib", "data": base64.b64encode(data).decode("ascii")}]})["results"][0]
                    receipt.update(imported)
                    if imported.get("document") and imported["status"] != "duplicate":
                        document_id = imported["document"]["id"]
                        with self.store.db:
                            self.store.db.execute("UPDATE documents SET metadata=?,metadata_version=metadata_version+1 WHERE id=?", (json.dumps(metadata, ensure_ascii=False), document_id))
                        receipt["document"] = self.store._public_doc(self.store._document(document_id, workspace_id))
            except b.AppError as error:
                receipt.update(status="error", error=str(error))
            results.append(receipt)
        results.sort(key=lambda row: row['record_number'])
        return {"results": results, "warnings": parsed["warnings"], "imported": sum(row["status"] in {"ready", "no_text"} for row in results), "duplicates": sum(row["status"] == "duplicate" for row in results)}

    def _attach(self, payload):
        import backend as b
        workspace_id = self.store._workspace(payload.get("workspace_id"))["id"]
        catalogue = self.store._document(payload.get("catalogue_id"), workspace_id)
        target = self.store._document(payload.get("document_id"), workspace_id)
        if not catalogue["metadata"].get("catalogue_source") or target["metadata"].get("catalogue_source") or target["kind"] not in {"pdf", "docx", "txt", "md"}:
            raise b.AppError("Choose a catalogue reference and a separate imported paper/text source.")
        expected = payload.get("expected_metadata_version")
        if type(expected) is not int or expected < 0:
            raise b.AppError("Expected metadata version is required before linking.")
        if target["metadata_version"] != expected:
            raise b.AppError("Paper details changed. Review the current details before linking.", 409)
        self.store._bytes(target)
        metadata = {key: value for key, value in target["metadata"].items() if key not in BIBLIOGRAPHIC_FIELDS | {"catalogue_source", "provenance"}}
        metadata.update({key: value for key, value in catalogue["metadata"].items() if key in BIBLIOGRAPHIC_FIELDS})
        metadata["provenance"] = b.append_provenance(target['metadata'].get('provenance', ''), "User-linked unverified bibliography from retained catalogue source " + catalogue["id"] + ". Check publication identity and fields against this imported paper.", catalogue["metadata"].get("provenance", ""))
        metadata = b.metadata_value(metadata)
        with self.store.db:
            updated = self.store.db.execute("UPDATE documents SET metadata=?,metadata_version=metadata_version+1 WHERE id=? AND metadata_version=?", (json.dumps(metadata, ensure_ascii=False), target["id"], expected))
            if updated.rowcount != 1:
                raise b.AppError("Paper details changed during linking. Saved details were retained.", 409)
        return self.store._public_doc(self.store._document(target["id"], workspace_id))

    def _asset(self, payload):
        import backend as b
        workspace_id = self.store._workspace(payload.get("workspace_id"))["id"]
        name = b.safe_name(payload.get("name"))
        kind = Path(name).suffix.lower().lstrip(".")
        if kind not in {"png", "jpg", "jpeg", "webp"}:
            raise b.AppError("Assets support PNG, JPEG or WebP images only.")
        if b.pdf_lib is None:
            raise b.AppError("Image validation is unavailable in this runtime.", 503)
        data = b.decode_base64(payload.get("data"), b.FILE_LIMIT)
        try:
            signature_matches = (data.startswith(b"\x89PNG\r\n\x1a\n") if kind == "png" else data.startswith(b"\xff\xd8\xff") if kind in {"jpg", "jpeg"} else data.startswith(b"RIFF") and data[8:12] == b"WEBP")
            if not signature_matches:
                raise b.AppError("Image bytes do not match the chosen file type.")
            # Use the native image object for dimensions before full decode.
            # This runtime's image_profile(bytes) has a SWIG array conversion
            # defect; its underlying buffer/image API accepts the same bytes.
            buffer = b.pdf_lib.mupdf.fz_new_buffer_from_copied_data(data)
            image = b.pdf_lib.mupdf.fz_new_image_from_buffer(buffer)
            width, height = image.w(), image.h()
            if not 1 <= width * height <= 20_000_000:
                raise b.AppError("Images support at most 20 million pixels.", 413)
            # Header/profile limits precede full decode; malformed image payloads
            # must never enter the managed originals collection.
            b.pdf_lib.Pixmap(data)
        except b.AppError:
            raise
        except Exception:
            raise b.AppError("Image content could not be validated; no asset was saved.") from None
        result = self.store._import({"workspace_id": workspace_id, "files": [{"name": name, "data": payload["data"]}]})
        return {**result, "dimensions": {"width": width, "height": height}}
