"""Agent-friendly CLI for the running Research Desk loopback service.

No direct database access, arbitrary HTTP endpoints or shell execution. Bounded
folder edits use previews, caller-attested approval and recovery copies.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from assistance import TASKS
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent
APP_ID = 'pg-research-desktop'
MAX_REQUEST = 64 * 1024 * 1024
MAX_RESPONSE = 128 * 1024 * 1024
FILE_LIMIT = 32 * 1024 * 1024
RESTORE_FILE_LIMIT = 47 * 1024 * 1024
CSL_FILE_LIMIT = 1024 * 1024
CITATION_STYLE_PATTERN = r'^(?:vancouver|apa|ieee|chicago-note|csl-[a-f0-9]{64})$'


class AgentError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise AgentError(message, 2)


def citation_style(value):
    if not re.fullmatch(CITATION_STYLE_PATTERN, value):
        raise argparse.ArgumentTypeError('Choose vancouver, apa, ieee or an imported csl-<64 lowercase hex> style ID.')
    return value


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise AgentError('Local service redirect refused.')


def read_session(data_dir):
    path = Path(data_dir) / 'agent-session.json'
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
            raise AgentError('Private agent session is missing or invalid. Open Research.cmd first.')
        record = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise AgentError('Private agent session cannot be read. Reopen Research.cmd.') from None
    if not isinstance(record, dict):
        raise AgentError('Private agent session is invalid. Reopen Research.cmd.')
    port, token, build, pid = (record.get(key) for key in ('port', 'token', 'build', 'pid'))
    if type(port) is not int or not 1 <= port <= 65535:
        raise AgentError('Private agent session has an invalid loopback port.')
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', token):
        raise AgentError('Private agent session has an invalid credential. Reopen Research.cmd.')
    if not isinstance(build, str) or not re.fullmatch(r'[a-f0-9]{64}', build) or type(pid) is not int or pid <= 0:
        raise AgentError('Private agent session has invalid build or process metadata.')
    return {'port': port, 'token': token, 'build': build, 'pid': pid}


class Client:
    def __init__(self, session, timeout=150):
        self.base = 'http://127.0.0.1:' + str(session['port'])
        self.token = session['token']
        self.build = session['build']
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirects())

    def redacted(self, value):
        # Even a defective server response cannot print this launch credential.
        return str(value).replace(self.token, '[redacted]')

    def request(self, path, body=None, binary=False):
        if not path.startswith('/') or path.startswith('//') or '\\' in path:
            raise AgentError('Unsupported local route.')
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
        if data is not None and len(data) > MAX_REQUEST:
            raise AgentError('Encoded request exceeds 64 MB. Use a smaller file.', 413)
        headers = {'Accept': 'application/json'}
        if path.startswith('/api/'):
            headers['X-App-Token'] = self.token
        if data is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(self.base + path, data=data, headers=headers, method='GET' if data is None else 'POST')
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                content = response.read(MAX_RESPONSE + 1)
                if len(content) > MAX_RESPONSE:
                    raise AgentError('Local response exceeds the bounded client limit.')
                if binary:
                    return content, response.headers.get('Content-Type', 'application/octet-stream')
                result = json.loads(content.decode('utf-8'))
                if not isinstance(result, dict):
                    raise AgentError('Local service returned an invalid JSON object.')
                return result
        except HTTPError as error:
            message = 'Local request failed.'
            try:
                content = json.loads(error.read(8192).decode('utf-8'))
                if isinstance(content.get('error'), str):
                    message = content['error']
            except (ValueError, UnicodeError, AttributeError):
                pass
            if error.code == 401:
                message = 'App session expired. Reopen Research.cmd and retry; do not copy the session credential.'
            raise AgentError(self.redacted(message), error.code) from None
        except (URLError, TimeoutError, ConnectionError, OSError):
            raise AgentError('The local app is unavailable or timed out. Open Research.cmd and retry. A timed-out write may have completed; read state before repeating it.') from None
        except (ValueError, UnicodeError):
            raise AgentError('Local service returned invalid JSON.') from None

    def verify(self):
        health = self.request('/health')
        if health.get('app') != APP_ID or health.get('ready') is not True or health.get('build') != self.build:
            raise AgentError('The running service does not match this app session. Reopen Research.cmd.')
        return health


def selected_bytes(path, limit=FILE_LIMIT):
    path = Path(path)
    try:
        if not path.is_file():
            raise AgentError('Selected input is not a regular file.')
        if path.stat().st_size > limit:
            raise AgentError('Selected input exceeds the allowed size.', 413)
        data = path.read_bytes()
        if len(data) > limit:
            raise AgentError('Selected input changed beyond the allowed size.', 413)
        return data
    except OSError:
        raise AgentError('Selected input could not be read.') from None


def save_output(path, data, overwrite=False):
    target = Path(path).absolute()
    if target.is_symlink() or (target.exists() and not overwrite):
        raise AgentError('Output exists. Choose another filename or explicitly pass --overwrite.')
    if not target.parent.is_dir():
        raise AgentError('Output directory does not exist. Choose an existing directory.')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.research-export-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            # Atomic no-clobber publication: a competing output cannot be replaced.
            os.link(temporary, target)
        return {'output': str(target), 'bytes': len(data)}
    except OSError:
        raise AgentError('Output could not be published. Existing files were not intentionally replaced.') from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def build_parser():
    parser = Parser(description='Control Kosh locally. Provider sends and bounded folder writes require previews and caller-attested approval; Kosh cannot verify human approval. No arbitrary command executor.', epilog='Start Kosh first. Use --data-dir before the command for a separate app data folder. Installed-agent calls may need --timeout 180.')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data', help='App data folder containing private agent-session.json')
    parser.add_argument('--timeout', type=int, default=150, help='Local HTTP timeout in seconds (1–180); default covers the provider deadline')
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    for name in ('health', 'state', 'workspaces', 'models', 'installed-agent-list', 'citation-styles','export-options'):
        item = commands.add_parser(name)
        if name == 'state':
            item.add_argument('--workspace', help='Return only this workspace; omit for explicitly requested global state')
    commands.add_parser('folder-history',help='Read retained folder-edit receipts; no target writes')
    for name in ('reading-state', 'reading-duplicates', 'reading-geometry', 'project-review', 'reviewer-state'):
        item = commands.add_parser(name, help='Read explicitly scoped local reading records; no provider call')
        item.add_argument('--workspace', required=True)
        if name == 'reading-geometry':
            item.add_argument('--document', required=True)
            item.add_argument('--page', type=int, required=True)
    commands.add_parser('backup-status', help='Read automatic backup status; no files or preferences changed')
    commands.add_parser('update-status', help='Read local update status; no network request')
    item = commands.add_parser('reviewer-save', help='Save explicitly reviewed response fields without changing manuscript text')
    item.add_argument('--workspace', required=True)
    item.add_argument('--version', required=True, type=int)
    item.add_argument('--file', required=True, type=Path)
    item = commands.add_parser('reviewer-export', help='Export saved response records to a selected local text file')
    item.add_argument('--workspace', required=True)
    item.add_argument('--version', required=True, type=int)
    output_options(item)
    for name in ('reading-source-save', 'reading-resume-save', 'reading-annotation-save', 'reading-claim-save'):
        item = commands.add_parser(name, help='Save reviewed local reading fields with the expected reading-state version; no permanent deletion')
        item.add_argument('--workspace', required=True)
        item.add_argument('--version', required=True, type=int)
        item.add_argument('--file', required=True, type=Path, help='Explicit UTF-8 JSON change object; workspace/version come from flags')
    style_import = commands.add_parser('citation-style-import', help='Import one explicitly selected local UTF-8 CSL style; missing dependencies require separate approved retrieval')
    style_import.add_argument('--file', required=True, type=Path, help='Explicit local CSL XML file, at most 1 MiB')
    locale_import=commands.add_parser('citation-locale-import',help='Import selected local CSL locale XML')
    locale_import.add_argument('--file',required=True,type=Path)
    style_get=commands.add_parser('citation-retrieve',help='Explicit approved official pinned CSL retrieval; sends style/language identifiers only')
    group=style_get.add_mutually_exclusive_group(required=True)
    group.add_argument('--style-id');group.add_argument('--style',type=citation_style);group.add_argument('--locale')
    style_get.add_argument('--approve',action='store_true',required=True)
    folder_preview=commands.add_parser('folder-preview',help='Read only explicitly proposed UTF-8 paths and show exact diffs; no target writes')
    folder_preview.add_argument('--target',required=True,type=Path,help='Explicit existing absolute folder')
    folder_preview.add_argument('--changes-file',required=True,type=Path,help='Explicit UTF-8 JSON array of {path,content}; relative text paths only')
    folder_apply=commands.add_parser('folder-apply',help='Apply only a reviewed one-use preview; recovery copies retained locally')
    folder_apply.add_argument('--preview',required=True)
    folder_apply.add_argument('--approve',action='store_true',required=True,help='Caller attests user approval of the exact preview/hashes/target; not a verified human gate')
    folder_recovery=commands.add_parser('folder-recovery-preview',help='Preview original text recovery; another explicit apply approval is required')
    folder_recovery.add_argument('--receipt',required=True)
    assist = commands.add_parser('assist-preview', help='Prepare exact outbound content locally; does not call an external agent')
    assist.add_argument('--workspace', required=True)
    assist.add_argument('--provider', choices=('codex','claude','ollama'), required=True)
    assist.add_argument('--model', help='Installed local Ollama model; required with provider ollama')
    assist.add_argument('--task', choices=tuple(TASKS), default='ask')
    assist.add_argument('--question', default='')
    assist.add_argument('--custom-instructions', default='', help='Explicit writing preferences; included in the outbound preview (at most 2,000 characters)')
    assist.add_argument('--document', action='append')
    assist.add_argument('--note')
    assist.add_argument('--version', type=int)
    assist.add_argument('--selected-text-file', type=Path, help='Explicit UTF-8 selection matching the saved note')
    assist.add_argument('--selected-source-file', type=Path, help='Explicit UTF-8 JSON {document_id,page,text} source selection')
    send = commands.add_parser('assist-send', help='Explicitly authorize one reviewed preview; provider may send it outside this computer and incur usage')
    send.add_argument('--preview', required=True)
    send.add_argument('--consent-to-provider-send', action='store_true', required=True, help='Caller attests user consent; the installed CLI also adds its own instructions and environment metadata')
    alternative = commands.add_parser('assist-save-alternative', help='Create a separate note from a proposal; never overwrite the original')
    alternative.add_argument('--result', required=True)
    alternative.add_argument('--version', type=int, help='Expected original saved note version')
    apply = commands.add_parser('assist-apply', help='Apply an exact reviewed selection proposal with citation and saved-version guards')
    apply.add_argument('--result', required=True)
    apply.add_argument('--version', type=int, required=True)
    apply.add_argument('--selected-text-file', type=Path, required=True)
    literature = commands.add_parser('literature-search', help='Explicit public catalogue query; metadata only, no full-text download')
    literature.add_argument('--workspace', required=True)
    literature.add_argument('--provider', choices=('pubmed','crossref','europepmc','openalex','all'), required=True)
    literature.add_argument('--query', required=True)
    lookup = commands.add_parser('literature-lookup', help='Explicit DOI via Crossref or PMID via PubMed lookup')
    lookup.add_argument('--workspace', required=True)
    lookup.add_argument('--provider', choices=('crossref','pubmed'), required=True)
    lookup.add_argument('--identifier-type', choices=('doi','pmid'), required=True)
    lookup.add_argument('--identifier', required=True)
    literature_save = commands.add_parser('literature-save', help='Save cached catalogue metadata as a source reference')
    literature_save.add_argument('--workspace', required=True)
    literature_save.add_argument('--result', required=True)
    create = commands.add_parser('create-workspace', help='Create an empty managed workspace')
    create.add_argument('--title', required=True)
    import_ = commands.add_parser('import', help='Import only explicitly named files; one request per file')
    import_.add_argument('--workspace', required=True)
    import_.add_argument('files', nargs='+', type=Path)
    search = commands.add_parser('search', help='Search exact extracted passages')
    search.add_argument('--workspace', required=True)
    search.add_argument('--query', required=True)
    search.add_argument('--document', action='append', help='Restrict to source ID; repeat for multiple sources')
    document = commands.add_parser('document', help='Read extracted source JSON, or download original/PDF page with --output')
    document.add_argument('--id', required=True)
    binary = document.add_mutually_exclusive_group()
    binary.add_argument('--original', action='store_true')
    binary.add_argument('--page', type=int, help='Actual one-based PDF page image')
    output_options(document, required=False)
    for name in ('notes', 'evidence'):
        item = commands.add_parser(name, help='List saved '+name)
        item.add_argument('--workspace', required=True)
    metadata = commands.add_parser('save-metadata', help='Save explicitly reviewed bibliographic fields with conflict protection')
    metadata.add_argument('--document', required=True)
    metadata.add_argument('--version', type=int, required=True, help='Expected metadata_version from source details')
    metadata.add_argument('--file', type=Path, required=True, help='Selected UTF-8 JSON metadata object')
    check = commands.add_parser('writing-check', help='Check a saved note version for structure/citation diagnostics; no changes or scientific score')
    check.add_argument('--workspace', required=True)
    check.add_argument('--note', required=True)
    check.add_argument('--version', type=int, required=True, help='Expected saved note version')
    note = commands.add_parser('save-note', help='Create a note or update its explicit expected version')
    note.add_argument('--workspace', required=True)
    note.add_argument('--id')
    note.add_argument('--version', type=int, help='Expected current version; required with --id')
    note.add_argument('--title', required=True)
    body = note.add_mutually_exclusive_group(required=True)
    body.add_argument('--body', help='Markdown text; prefer --body-file for substantial/private writing')
    body.add_argument('--body-file', type=Path, help='Explicit UTF-8 Markdown file to read')
    matrix = commands.add_parser('save-evidence', help='Save a manual evidence row; no formal screening')
    matrix.add_argument('--workspace', required=True)
    matrix.add_argument('--document', required=True)
    matrix.add_argument('--id')
    matrix.add_argument('--version', type=int)
    for field in ('question', 'design', 'findings', 'limitations'):
        matrix.add_argument('--'+field, default='')
    ask = commands.add_parser('ask', help='Retrieve source excerpts, or explicitly select a real installed local model')
    ask.add_argument('--workspace', required=True)
    ask.add_argument('--question', required=True)
    ask.add_argument('--document', action='append')
    ask.add_argument('--model', default='', help='Installed local model name. Omit for excerpts without AI.')
    export = commands.add_parser('export')
    export.add_argument('--workspace', required=True)
    export.add_argument('--note', help='Export only this saved draft and its cited sources (MD/DOCX/PDF/LaTeX)')
    export.add_argument('--format', choices=('md', 'docx', 'docxlive', 'pdf', 'texpdf', 'bib', 'csv', 'tex', 'ris', 'csljson', 'html', 'share', 'texzip'), required=True)
    export.add_argument('--citation-style', type=citation_style, default='vancouver', help='Bundled vancouver/apa/ieee or imported csl-<64 lowercase hex> ID from citation-styles; the server checks installed styles')
    export.add_argument('--audit', action='store_true', help='Explicitly include source/provenance review notes in supported exports')
    export.add_argument('--citation-language',help='CSL locale code; see export-options')
    export.add_argument('--note-placement',choices=('footnote','endnote'),default='footnote')
    export.add_argument('--word-style',choices=('ieee','apa6','iso690-numeric'),default='ieee')
    export.add_argument('--template-file',type=Path,help='Explicit selected JSON template options, at most64KiB; metadata stays in POST body')
    output_options(export)
    backup = commands.add_parser('backup')
    backup.add_argument('--workspace', required=True)
    backup.add_argument('--include-history', action='store_true', help='Include saved revisions in this ZIP; local history is always retained')
    output_options(backup)
    restore = commands.add_parser('restore', help='Restore a selected validated ZIP into a fresh workspace')
    restore.add_argument('--file', type=Path, required=True)
    extension_commands(commands)
    return parser


def extension_commands(commands):
    item = commands.add_parser('asset-import', help='Import one explicitly selected PNG/JPEG/WebP asset through image validation')
    item.add_argument('--workspace', required=True)
    item.add_argument('--file', type=Path, required=True)
    for name in ('bibliography-preview', 'bibliography-import'):
        item = commands.add_parser(name, help='Read only this selected UTF-8 bibliography file; metadata is unverified')
        item.add_argument('--workspace', required=True)
        item.add_argument('--format', choices=('bib', 'ris', 'csljson'), required=True)
        item.add_argument('--file', type=Path, required=True)
    for name in ('archive', 'unarchive'):
        item = commands.add_parser(name, help='Archive state only; original files and saved notes remain')
        item.add_argument('--document', required=True)
    item = commands.add_parser('catalogue-attach', help='Link reviewed catalogue metadata to an imported paper with expected metadata version')
    for name in ('workspace', 'catalogue', 'document'):
        item.add_argument('--' + name, required=True)
    item.add_argument('--version', type=int, required=True)
    item = commands.add_parser('note-history', help='Read current and prior versions of this saved note')
    item.add_argument('--note', required=True)
    for name in ('assist-history', 'assist-result'):
        item = commands.add_parser(name, help='Read retained assistance jobs/results only in this workspace')
        item.add_argument('--workspace', required=True)
        if name == 'assist-result':
            item.add_argument('--result', required=True)
    commands.add_parser('retrieval-capabilities', help='Read local OCR/semantic feature capabilities')
    for name in ('retrieval-index', 'retrieval-search'):
        item = commands.add_parser(name, help='Explicit local Ollama embeddings only; no download or cloud fallback')
        item.add_argument('--workspace', required=True)
        item.add_argument('--model', required=True)
        item.add_argument('--document', action='append')
        if name == 'retrieval-search':
            item.add_argument('--query', required=True)
    item = commands.add_parser('ocr', help='Create a separate local OCR PDF derivative; originals/citations stay intact')
    item.add_argument('--workspace', required=True)
    item.add_argument('--document', required=True)
    item.add_argument('--language', choices=('eng', 'hin', 'pan'), default='eng')
    item.add_argument('--page', action='append', type=int, help='Actual source file page; repeat for at most twenty pages')
    item = commands.add_parser('folder-assist-preview', help='Read only chosen relative text paths into an exact outbound preview; no model send or write')
    item.add_argument('--workspace', required=True)
    item.add_argument('--target', type=Path, required=True)
    item.add_argument('--path', action='append', required=True)
    item.add_argument('--provider', choices=('codex', 'claude', 'ollama'), required=True)
    item.add_argument('--model')
    instruction = item.add_mutually_exclusive_group(required=True)
    instruction.add_argument('--instruction')
    instruction.add_argument('--instruction-file', type=Path)
    item = commands.add_parser('folder-assist-run', help='Caller attests consent to this reviewed prompt; returns a diff, never applies it')
    item.add_argument('--preview', required=True)
    item.add_argument('--consent-to-provider-send', action='store_true', required=True)


def output_options(parser, required=True):
    parser.add_argument('--output', type=Path, required=required)
    parser.add_argument('--overwrite', action='store_true', help='Explicitly replace this output filename')


def execute(args, client):
    command = args.command
    health = client.verify()
    if command == 'health':
        return health
    if command == 'workspaces':
        return client.request('/api/workspaces')
    if command in ('backup-status', 'update-status'):
        return client.request('/api/auto-backup' if command == 'backup-status' else '/api/updates/status')
    if command in ('reading-state', 'reading-duplicates', 'reading-geometry', 'project-review', 'reviewer-state'):
        query = {'workspace_id': args.workspace}
        route = {'reading-state':'/api/reading', 'reading-duplicates':'/api/reading/duplicates', 'reading-geometry':'/api/reading/geometry', 'project-review':'/api/project-review', 'reviewer-state':'/api/reviewer'}[command]
        if command == 'reading-geometry': query.update(document_id=args.document, page=args.page)
        return client.request(route+'?'+urlencode(query))
    if command == 'reviewer-export':
        result = client.request('/api/reviewer/export', {'workspace_id':args.workspace,'expected_version':args.version})
        return {**save_output(args.output, result['content'].encode('utf-8'), args.overwrite), 'notice':result['notice']}
    if command == 'reviewer-save':
        try:
            change = json.loads(selected_bytes(args.file, 128*1024).decode('utf-8-sig'))
        except (ValueError, UnicodeError):
            raise AgentError('Reviewer changes must be a UTF-8 JSON object.') from None
        if not isinstance(change, dict) or {'workspace_id', 'expected_version'} & change.keys():
            raise AgentError('Explicit workspace/version flags supply scope; do not include them in the file.')
        return client.request('/api/reviewer/comment', {**change,'workspace_id':args.workspace,'expected_version':args.version})
    if command in ('reading-source-save', 'reading-resume-save', 'reading-annotation-save', 'reading-claim-save'):
        try:
            change = json.loads(selected_bytes(args.file, 64*1024).decode('utf-8-sig'))
        except (ValueError, UnicodeError):
            raise AgentError('Reading changes must be a UTF-8 JSON object.') from None
        if not isinstance(change, dict) or {'workspace_id', 'expected_version'} & change.keys():
            raise AgentError('Use a change object without workspace_id or expected_version; explicit CLI flags supply scope and version.')
        if args.version < 0: raise AgentError('Expected reading-state version must be non-negative.')
        route = {'reading-source-save':'source', 'reading-resume-save':'resume', 'reading-annotation-save':'annotation', 'reading-claim-save':'claim'}[command]
        return client.request('/api/reading/'+route, {**change, 'workspace_id':args.workspace, 'expected_version':args.version})
    if command == 'citation-styles':
        return client.request('/api/citation/styles')
    if command == 'export-options': return client.request('/api/export/options')
    if command == 'citation-retrieve':
        return client.request('/api/citation/styles/retrieve',{key:value for key,value in {'style_id':args.style_id,'style':args.style,'locale':args.locale,'approved':args.approve}.items() if value is not None})
    if command in ('citation-style-import','citation-locale-import'):
        try:
            xml = selected_bytes(args.file, CSL_FILE_LIMIT).decode('utf-8-sig')
        except UnicodeError:
            raise AgentError('Selected CSL style file must be UTF-8.') from None
        return client.request('/api/citation/styles/import' if command=='citation-style-import' else '/api/citation/locales/import', {'xml': xml})
    if command in ('state', 'notes', 'evidence'):
        workspace = getattr(args, 'workspace', None)
        state = client.request('/api/state' + ('?' + urlencode({'workspace_id': workspace}) if workspace else ''))
        if command == 'state':
            return state
        if not any(w['id'] == args.workspace for w in state['workspaces']):
            raise AgentError('Workspace not found.', 404)
        key = 'matrix' if command == 'evidence' else 'notes'
        return {key: [item for item in state[key] if item['workspace_id'] == args.workspace]}
    if command == 'models':
        return client.request('/api/models')
    if command=='folder-history':
        return client.request('/api/folder-edits/history')
    if command=='folder-preview':
        try:
            files=json.loads(selected_bytes(args.changes_file,2*1024*1024).decode('utf-8-sig'))
        except (UnicodeError,ValueError):
            raise AgentError('Changes file must be a UTF-8 JSON array of explicit {path,content} text replacements.') from None
        if not args.target.is_absolute(): raise AgentError('Folder target must be an explicit absolute path.')
        return client.request('/api/folder-edits/preview',{'target_path':str(args.target),'files':files})
    if command=='folder-apply':
        return client.request('/api/folder-edits/apply',{'preview_id':args.preview,'approve':args.approve,'approval_version':1})
    if command=='folder-recovery-preview':
        return client.request('/api/folder-edits/recovery-preview',{'receipt_id':args.receipt})
    if command == 'installed-agent-list':
        return client.request('/api/assist/providers')
    if command == 'assist-preview':
        body={'workspace_id':args.workspace,'provider':args.provider,'task':args.task,'question':args.question}
        if args.custom_instructions:
            if len(args.custom_instructions) > 2000: raise AgentError('Writing instructions support at most 2,000 characters.')
            body['custom_instructions'] = args.custom_instructions
        if args.provider == 'ollama':
            if not args.model: raise AgentError('Local assistance requires --model.')
            body['model'] = args.model
        if args.selected_source_file:
            try: body['selected_source'] = json.loads(selected_bytes(args.selected_source_file, 32_000).decode('utf-8-sig'))
            except (UnicodeError, ValueError): raise AgentError('Selected source file must contain UTF-8 JSON {document_id,page,text}.') from None
        if args.document is not None: body['document_ids']=args.document
        if args.note:
            if args.version is None or args.selected_text_file is None:
                raise AgentError('Writing previews require --note, --version and --selected-text-file.')
            try: selected=selected_bytes(args.selected_text_file,32_000).decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
            except UnicodeError: raise AgentError('Selected text must be UTF-8.') from None
            body.update(note_id=args.note,version=args.version,selected_text=selected)
        return client.request('/api/assist/preview',body)
    if command == 'asset-import':
        return client.request('/api/assets/import', {'workspace_id': args.workspace, 'name': args.file.name, 'data': base64.b64encode(selected_bytes(args.file)).decode('ascii')})
    if command in ('bibliography-preview', 'bibliography-import'):
        try: text = selected_bytes(args.file, 2_000_000).decode('utf-8-sig')
        except UnicodeError: raise AgentError('Selected bibliography file must be UTF-8.') from None
        return client.request('/api/bibliography/' + command.split('-')[1], {'workspace_id': args.workspace, 'format': args.format, 'text': text})
    if command in ('archive', 'unarchive'):
        return client.request('/api/archive', {'id': args.document, 'archived': command == 'archive'})
    if command == 'catalogue-attach':
        if args.version < 0: raise AgentError('Expected metadata version must be zero or greater.')
        return client.request('/api/catalogue/attach', {'workspace_id': args.workspace, 'catalogue_id': args.catalogue, 'document_id': args.document, 'expected_metadata_version': args.version})
    if command == 'note-history':
        return client.request('/api/notes/history?' + urlencode({'id': args.note}))
    if command in ('assist-history', 'assist-result'):
        query = {'workspace_id': args.workspace}
        if command == 'assist-result': query['result_id'] = args.result
        return client.request('/api/assist/' + command.split('-')[1] + '?' + urlencode(query))
    if command == 'retrieval-capabilities':
        return client.request('/api/retrieval/capabilities')
    if command in ('retrieval-index', 'retrieval-search'):
        body = {'workspace_id': args.workspace, 'model': args.model}
        if args.document is not None: body['document_ids'] = args.document
        if command == 'retrieval-search': body['query'] = args.query
        return client.request('/api/retrieval/' + command.split('-')[1], body)
    if command == 'ocr':
        if args.page is not None and (len(args.page) > 20 or any(number < 1 for number in args.page)):
            raise AgentError('OCR requires at most twenty positive actual file pages.')
        body = {'workspace_id': args.workspace, 'document_id': args.document, 'language': args.language}
        if args.page is not None: body['pages'] = args.page
        return client.request('/api/ocr', body)
    if command == 'folder-assist-preview':
        if not args.target.is_absolute(): raise AgentError('Folder target must be an explicit absolute path.')
        try: instruction = selected_bytes(args.instruction_file, 16_000).decode('utf-8-sig') if args.instruction_file else args.instruction
        except UnicodeError: raise AgentError('Instruction file must be UTF-8.') from None
        body = {'workspace_id': args.workspace, 'target_path': str(args.target), 'paths': args.path, 'provider': args.provider, 'instruction': instruction}
        if args.provider == 'ollama':
            if not args.model: raise AgentError('Local folder assistance requires --model.')
            body['model'] = args.model
        return client.request('/api/folder-assist/preview', body)
    if command == 'folder-assist-run':
        return client.request('/api/folder-assist/run', {'preview_id': args.preview, 'consent': args.consent_to_provider_send, 'consent_version': 1})
    if command == 'assist-send':
        return client.request('/api/assist/run',{'preview_id':args.preview,'consent':args.consent_to_provider_send,'consent_version':1})
    if command == 'assist-save-alternative':
        return client.request('/api/assist/save-alternative',{'result_id':args.result,'expected_version':args.version})
    if command == 'assist-apply':
        try:
            selection = selected_bytes(args.selected_text_file, 32_000).decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
        except UnicodeDecodeError:
            raise AgentError('Selected writing must be UTF-8 text.') from None
        return client.request('/api/assist/apply', {'result_id': args.result, 'expected_version': args.version, 'selected_text': selection})
    if command == 'literature-lookup':
        return client.request('/api/literature/lookup', {'workspace_id': args.workspace, 'provider': args.provider, 'identifier_type': args.identifier_type, 'identifier': args.identifier})
    if command == 'literature-search':
        return client.request('/api/literature/search',{'workspace_id':args.workspace,'provider':args.provider,'query':args.query})
    if command == 'literature-save':
        return client.request('/api/literature/save',{'workspace_id':args.workspace,'result_id':args.result})
    if command == 'create-workspace':
        return client.request('/api/workspaces', {'title': args.title})
    if command == 'save-metadata':
        if args.version < 0:
            raise AgentError('Metadata version must be zero or greater.')
        try:
            metadata = json.loads(selected_bytes(args.file, 64_000).decode('utf-8-sig'))
        except (ValueError, UnicodeError):
            raise AgentError('Metadata file must contain a UTF-8 JSON object.') from None
        if not isinstance(metadata, dict):
            raise AgentError('Metadata file must contain a JSON object.')
        return client.request('/api/metadata', {'id': args.document, 'metadata': metadata, 'expected_metadata_version': args.version})
    if command == 'writing-check':
        if args.version < 1:
            raise AgentError('Writing checks require a positive expected saved --version.', 409)
        return client.request('/api/writing-check', {'workspace_id': args.workspace, 'note_id': args.note, 'version': args.version})
    if command == 'import':
        results = []
        for path in args.files:
            try:
                data = base64.b64encode(selected_bytes(path)).decode('ascii')
                response = client.request('/api/import', {'workspace_id': args.workspace, 'files': [{'name': path.name, 'data': data}]})
                results.extend(response['results'])
            except AgentError as error:
                results.append({'name': path.name, 'status': 'error', 'error': str(error)})
        return {'results': results}
    if command in ('search', 'ask'):
        body = {'workspace_id': args.workspace, 'query' if command == 'search' else 'question': args.query if command == 'search' else args.question}
        if args.document is not None:
            body['document_ids'] = args.document
        if command == 'ask':
            body['model'] = args.model
        return client.request('/api/'+command, body)
    if command == 'document':
        if args.original or args.page is not None:
            if args.output is None or (args.page is not None and args.page < 1):
                raise AgentError('Downloading an original/PDF page requires --output and a positive page number.')
            query = {'id': args.id}
            if args.page is not None:
                query['page'] = args.page
            path = '/api/file' if args.original else '/api/page'
            content, mime = client.request(path+'?'+urlencode(query), binary=True)
            return {**save_output(args.output, content, args.overwrite), 'content_type': mime}
        if args.output is not None:
            raise AgentError('Use --original or --page with --output.')
        return client.request('/api/document?'+urlencode({'id': args.id}))
    if command in ('save-note', 'save-evidence'):
        if bool(args.id) != (args.version is not None) or (args.version is not None and args.version < 1):
            raise AgentError('Updates require both --id and the positive expected --version; creation omits both.', 409)
        body = {'workspace_id': args.workspace}
        if args.id:
            body.update(id=args.id, version=args.version)
        if command == 'save-note':
            try:
                text = selected_bytes(args.body_file, 2_000_000).decode('utf-8-sig') if args.body_file else args.body
            except UnicodeError:
                raise AgentError('Note body file must be UTF-8.') from None
            body.update(title=args.title, body=text)
        else:
            body.update(document_id=args.document, **{field: getattr(args, field) for field in ('question', 'design', 'findings', 'limitations')})
        return client.request('/api/notes' if command == 'save-note' else '/api/matrix', body)
    if command in ('export', 'backup'):
        query = {'workspace_id': args.workspace}
        if command == 'export':
            query['format'] = args.format
            query['citation_style'] = args.citation_style
            if getattr(args, 'audit', False): query['audit'] = '1'
            if getattr(args,'note',None): query['note_id']=args.note
            for field in ('citation_language','note_placement','word_style'):
                if getattr(args,field,None):query[field]=getattr(args,field)
            if getattr(args,'template_file',None):
                try:query['template']=json.loads(selected_bytes(args.template_file,65536).decode('utf-8-sig'))
                except (UnicodeError,ValueError):raise AgentError('Selected template file must contain a UTF-8 JSON object.') from None
        else:
            query['history'] = '1' if args.include_history else '0'
        content, mime = client.request('/api/export',query,binary=True) if command=='export' else client.request('/api/backup?'+urlencode(query), binary=True)
        return {**save_output(args.output, content, args.overwrite), 'content_type': mime}
    if command == 'restore':
        data = base64.b64encode(selected_bytes(args.file, RESTORE_FILE_LIMIT)).decode('ascii')
        return client.request('/api/restore', {'data': data})
    raise AgentError('Unsupported command.')


def main(argv=None, out=None):
    out = out or sys.stdout
    client = None
    try:
        args = build_parser().parse_args(argv)
        if not 1 <= args.timeout <= 180:
            raise AgentError('--timeout must be between 1 and 180 seconds.')
        client = Client(read_session(args.data_dir), args.timeout)
        result = execute(args, client)
        serialized = json.dumps(result, ensure_ascii=False)
        out.write(client.redacted(serialized)+'\n')
        return 1 if args.command in {'import', 'asset-import', 'bibliography-import', 'ocr'} and any(r.get('status') == 'error' for r in result.get('results', [])) else 0
    except AgentError as error:
        message = client.redacted(error) if client else str(error)
        out.write(json.dumps({'error': message, **({'status': error.status} if error.status is not None else {})}, ensure_ascii=False)+'\n')
        return 2 if error.status == 2 else 1
    except KeyboardInterrupt:
        out.write(json.dumps({'error': 'Client waiting cancelled. The server may finish; read state before repeating a write.'})+'\n')
        return 130
    except Exception:
        # A malformed response or local write error must not emit a traceback,
        # document content, private session fields or credentials.
        out.write(json.dumps({'error': 'The local operation returned unexpected data or could not complete. Read app state before repeating a write.'})+'\n')
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
