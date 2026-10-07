"""Dependency-free MCP JSON-RPC stdio adapter over Kosh's fixed local CLI.

No configuration edits, arbitrary routes, SQL or shell executor. Start Kosh
first, then launch this script with the matching --data-dir if non-default.
"""
import argparse
import json
from pathlib import Path
import re
import sys

import agent


MAX_LINE = 1024 * 1024
PROTOCOLS = ('2024-11-05', '2025-03-26', '2025-06-18')


def string(maximum=4000, choices=None, minimum=1):
    schema = {'type': 'string', 'minLength': minimum, 'maxLength': maximum}
    if choices is not None:
        schema['enum'] = list(choices)
    return schema


def integer(minimum=0):
    return {'type': 'integer', 'minimum': minimum}


def array(maximum=1000, items=None):
    return {'type': 'array', 'items': items or string(240), 'minItems': 1, 'maxItems': maximum}


def manifest():
    """One fixed registry generates public schemas and CLI arguments."""
    tools = {}
    workspace = string(32)
    identifier = string(32)
    path = string(1024)
    model = string(200)
    consent = {'type': 'boolean', 'const': True}
    boolean = {'type': 'boolean'}
    citation_style = {**string(68), 'pattern': agent.CITATION_STYLE_PATTERN}
    def add(name, command, description, properties=None, required=(), aliases=None, positional=()):
        tools['kosh_' + name] = {'command': command, 'description': description,
                                'inputSchema': {'type': 'object', 'properties': properties or {}, 'required': list(required), 'additionalProperties': False},
                                'aliases': aliases or {}, 'positional': positional}
    add('health', 'health', 'Verify the current local app identity and build; no research content.')
    add('workspaces', 'workspaces', 'List workspace metadata only; no note or source contents.')
    add('workspace_state', 'state', 'Read only the explicitly selected workspace snapshot.', {'workspace': workspace}, ('workspace',))
    add('reading_state', 'reading-state', 'Read annotations, organisation, resume and user claim-review records for the selected workspace.', {'workspace':workspace}, ('workspace',))
    add('reading_duplicates', 'reading-duplicates', 'List possible duplicate references for review; does not merge or delete originals.', {'workspace':workspace}, ('workspace',))
    add('reading_geometry', 'reading-geometry', 'Read normalized word positions from one actual PDF page in the selected workspace.', {'workspace':workspace, 'document':identifier, 'page':integer(1)}, ('workspace','document','page'))
    for suffix in ('source', 'resume', 'annotation', 'claim'):
        add('reading_'+suffix+'_save', 'reading-'+suffix+'-save', 'Save reviewed '+suffix+' fields from a selected local JSON file using the expected reading-state version. Claim checked status is caller-attested human review, not machine verification.', {'workspace':workspace, 'version':integer(), 'file':path}, ('workspace','version','file'))
    add('models', 'models', 'Read installed local Ollama inventory; no model generation or download.')
    add('installed_agents', 'installed-agent-list', 'Detect supported installed agents; detection does not prove provider sign-in.')
    add('citation_styles', 'citation-styles', 'Read installed bundled and imported CSL style IDs; no document contents or network.')
    add('citation_style_import', 'citation-style-import', 'Import one explicitly selected local UTF-8 CSL file, at most 1 MiB. Supports in-text, note and dependent styles; missing dependencies require separate approved retrieval. No implicit download.', {'file': path}, ('file',))
    add('export_options','export-options','Read manuscript profiles, local compiler status, Word styles and CSL languages.')
    add('citation_locale_import','citation-locale-import','Import one selected CSL locale XML locally.',{'file':path},('file',))
    add('citation_retrieve','citation-retrieve','Explicitly approved official pinned style or locale retrieval; sends no research contents.',{'style_id':string(200),'style':citation_style,'locale':string(35),'approve':boolean},('approve',))
    add('create_workspace', 'create-workspace', 'Create an empty local workspace.', {'title': string(200)}, ('title',))
    for name in ('notes', 'evidence'):
        add(name, name, 'Read saved ' + name + ' only in the selected workspace.', {'workspace': workspace}, ('workspace',))
    add('document', 'document', 'Read extracted text for one explicit source ID.', {'id': identifier}, ('id',))
    add('search', 'search', 'Read matching extracted source passages in one workspace.', {'workspace': workspace, 'query': string(), 'documents': array()}, ('workspace', 'query'), {'documents': 'document'})
    add('import_files', 'import', 'Import only explicitly named local files; no directory discovery.', {'workspace': workspace, 'files': array(30, path)}, ('workspace', 'files'), positional=('files',))
    add('import_asset', 'asset-import', 'Import one explicitly selected image through local image validation; no folder discovery.', {'workspace': workspace, 'file': path}, ('workspace', 'file'))
    add('save_note', 'save-note', 'Create a saved note or update with its expected version. No automatic model overwrite.', {'workspace': workspace, 'id': identifier, 'version': integer(1), 'title': string(400), 'body': string(200_000, minimum=0)}, ('workspace', 'title', 'body'))
    add('save_metadata', 'save-metadata', 'Save this selected UTF-8 metadata JSON file with an explicit expected version.', {'document': identifier, 'version': integer(), 'file': path}, ('document', 'version', 'file'))
    add('save_evidence', 'save-evidence', 'Save a manually reviewed evidence row; no formal screening.', {'workspace': workspace, 'document': identifier, 'id': identifier, 'version': integer(1), 'question': string(minimum=0), 'design': string(minimum=0), 'findings': string(minimum=0), 'limitations': string(minimum=0)}, ('workspace', 'document'))
    add('writing_check', 'writing-check', 'Read mechanical diagnostics for the exact saved note version; no scientific verdict.', {'workspace': workspace, 'note': identifier, 'version': integer(1)}, ('workspace', 'note', 'version'))
    add('note_history', 'note-history', 'Read exact current and prior bodies of one saved note.', {'note': identifier}, ('note',))
    for name in ('archive', 'unarchive'):
        add(name, name, 'Change archive state only; originals and saved drafts remain.', {'document': identifier}, ('document',))
    for suffix in ('preview', 'import'):
        add('bibliography_' + suffix, 'bibliography-' + suffix, 'Read only this selected UTF-8 bibliography file; preview is read-only and import saves unverified metadata.', {'workspace': workspace, 'format': string(10, ('bib', 'ris', 'csljson')), 'file': path}, ('workspace', 'format', 'file'))
    add('catalogue_attach', 'catalogue-attach', 'Link explicitly reviewed metadata to an imported source with expected metadata version; originals stay intact.', {'workspace': workspace, 'catalogue': identifier, 'document': identifier, 'version': integer()}, ('workspace', 'catalogue', 'document', 'version'))
    add('literature_search', 'literature-search', 'Send only this explicit public query to selected index or all four indexes; metadata only, no full-text download.', {'workspace': workspace, 'provider': string(20, ('pubmed', 'crossref', 'europepmc', 'openalex', 'all')), 'query': string(500)}, ('workspace', 'provider', 'query'))
    add('literature_lookup', 'literature-lookup', 'Look up an explicitly supplied DOI in Crossref or PMID in PubMed; metadata only.', {'workspace': workspace, 'provider': string(20, ('pubmed', 'crossref')), 'identifier_type': string(10, ('doi', 'pmid')), 'identifier': string(500)}, ('workspace', 'provider', 'identifier_type', 'identifier'))
    add('assist_apply', 'assist-apply', 'Apply a reviewed replacement to its exact unique original selection; saved version and citation markers must match.', {'result': identifier, 'version': integer(1), 'selected_text_file': path}, ('result', 'version', 'selected_text_file'))
    add('literature_save', 'literature-save', 'Save selected cached catalogue metadata in its original workspace.', {'workspace': workspace, 'result': identifier}, ('workspace', 'result'))
    add('ask', 'ask', 'Retrieve scoped excerpts; an explicit installed local model may generate an unverified answer.', {'workspace': workspace, 'question': string(), 'documents': array(), 'model': model}, ('workspace', 'question'), {'documents': 'document'})
    add('assist_preview', 'assist-preview', 'Prepare exact outbound selected content without sending. Writing requires note/version/selected-text-file; source selection can be explicit JSON.', {'workspace': workspace, 'provider': string(20, ('codex', 'claude', 'ollama')), 'model': model, 'task': string(20, tuple(agent.TASKS)), 'question': string(minimum=0), 'custom_instructions': string(2000, minimum=0), 'documents': array(), 'note': identifier, 'version': integer(1), 'selected_text_file': path, 'selected_source_file': path}, ('workspace', 'provider'), {'documents': 'document'})
    add('assist_send', 'assist-send', 'Send one reviewed preview. Caller attests user consent; adapter cannot verify human approval. Installed providers may send selected content outside this computer and incur usage.', {'preview': identifier, 'consent': consent}, ('preview', 'consent'), {'consent': 'consent-to-provider-send'})
    add('assist_save_alternative', 'assist-save-alternative', 'Save a reviewed proposal as a separate note; never overwrite the original.', {'result': identifier, 'version': integer(1)}, ('result',))
    add('assist_history', 'assist-history', 'Read retained assistance jobs/results only in the selected workspace.', {'workspace': workspace}, ('workspace',))
    add('assist_result', 'assist-result', 'Read one retained proposal only in the selected workspace.', {'workspace': workspace, 'result': identifier}, ('workspace', 'result'))
    add('retrieval_capabilities', 'retrieval-capabilities', 'Read installed local OCR/semantic capability limits; no generation.')
    add('retrieval_index', 'retrieval-index', 'Explicit local embedding request on selected workspace paper text; cache only, no cloud fallback.', {'workspace': workspace, 'model': model, 'documents': array()}, ('workspace', 'model'), {'documents': 'document'})
    add('retrieval_search', 'retrieval-search', 'Explicit local semantic query over current source hashes; similarity is not verified evidence.', {'workspace': workspace, 'model': model, 'query': string(), 'documents': array()}, ('workspace', 'model', 'query'), {'documents': 'document'})
    add('ocr', 'ocr', 'Create a separate OCR PDF derivative from explicitly selected actual file pages; original bytes/citations remain.', {'workspace': workspace, 'document': identifier, 'language': string(3, ('eng', 'hin', 'pan')), 'pages': array(20, integer(1))}, ('workspace', 'document'), {'pages': 'page'})
    add('folder_preview', 'folder-preview', 'Read only explicit UTF-8 paths from a selected changes JSON file; create exact diffs without writing.', {'target': path, 'changes_file': path}, ('target', 'changes_file'))
    add('folder_apply', 'folder-apply', 'Apply only the exact reviewed one-use diff. Caller attests user approval; adapter cannot verify human approval. Recovery originals remain.', {'preview': identifier, 'approve': consent}, ('preview', 'approve'))
    add('folder_history', 'folder-history', 'Read retained folder publication/recovery receipts; no target changes.')
    add('folder_recovery_preview', 'folder-recovery-preview', 'Preview retained originals for recovery; another explicit apply is required.', {'receipt': identifier}, ('receipt',))
    add('folder_assist_preview', 'folder-assist-preview', 'Read only explicit relative chosen-file paths into an outbound preview; no provider send or target write.', {'workspace': workspace, 'target': path, 'paths': array(10), 'provider': string(20, ('codex', 'claude', 'ollama')), 'model': model, 'instruction': string()}, ('workspace', 'target', 'paths', 'provider', 'instruction'), {'paths': 'path'})
    add('folder_assist_run', 'folder-assist-run', 'Caller attests consent to one reviewed prompt. Provider result becomes an exact diff only; separate approval is required before writes.', {'preview': identifier, 'consent': consent}, ('preview', 'consent'), {'consent': 'consent-to-provider-send'})
    add('export', 'export', 'Export explicitly scoped saved work to a named local output; default never clobbers an existing file.', {'workspace': workspace, 'note': identifier, 'format': string(10, ('md', 'docx', 'docxlive', 'pdf', 'texpdf', 'bib', 'csv', 'tex', 'ris', 'csljson', 'html', 'share', 'texzip')), 'citation_style': citation_style,'citation_language':string(35),'note_placement':string(10,('footnote','endnote')),'word_style':string(20,('ieee','apa6','iso690-numeric')),'template_file':path, 'audit': boolean, 'output': path, 'overwrite': boolean}, ('workspace', 'format', 'output'))
    add('backup', 'backup', 'Save this workspace snapshot to an explicit no-clobber output; history is opt-in and retained locally.', {'workspace': workspace, 'include_history': boolean, 'output': path, 'overwrite': boolean}, ('workspace', 'output'))
    add('restore', 'restore', 'Restore one explicitly selected validated ZIP to a fresh workspace; existing records remain.', {'file': path}, ('file',))
    return tools


TOOLS = manifest()


def validate(value, schema):
    kind = schema['type']
    correct = {'object': isinstance(value, dict), 'array': isinstance(value, list), 'string': isinstance(value, str), 'boolean': type(value) is bool, 'integer': type(value) is int}[kind]
    if not correct:
        raise agent.AgentError('Tool arguments do not match the explicit input schema.')
    if 'const' in schema and value != schema['const']:
        raise agent.AgentError('Explicit caller-attested approval must be true for this action.')
    if 'enum' in schema and value not in schema['enum']:
        raise agent.AgentError('Choose a supported value from the tool schema.')
    if kind == 'string' and 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
        raise agent.AgentError('Choose a bundled or imported content-addressed citation style ID.')
    if kind == 'object':
        properties = schema['properties']
        if set(value) - set(properties) or set(schema['required']) - set(value):
            raise agent.AgentError('Unknown or missing tool arguments; arbitrary routes and commands are not accepted.')
        for key, item in value.items():
            validate(item, properties[key])
    elif kind == 'array':
        if not schema['minItems'] <= len(value) <= schema['maxItems']:
            raise agent.AgentError('Selected list exceeds this tool limit.')
        for item in value:
            validate(item, schema['items'])
    elif kind == 'string' and (not schema['minLength'] <= len(value) <= schema['maxLength'] or '\x00' in value):
        raise agent.AgentError('Tool text exceeds its bounds or contains unsupported NUL content.')
    elif kind == 'integer' and value < schema['minimum']:
        raise agent.AgentError('Expected version or page is outside this tool limit.')


def arguments(tool, values):
    argv = [tool['command']]
    for key, value in values.items():
        if key in tool['positional']:
            continue
        flag = '--' + tool['aliases'].get(key, key.replace('_', '-'))
        if type(value) is bool:
            if value:
                argv.append(flag)
        else:
            for item in value if isinstance(value, list) else [value]:
                argv.append(flag + '=' + str(item))
    for key in tool['positional']:
        if key in values:
            argv.append('--')
            argv.extend(str(item) for item in values[key])
    return argv


def error(id, code, message):
    return {'jsonrpc': '2.0', 'id': id, 'error': {'code': code, 'message': message}}


class Server:
    def __init__(self, client=None, data_dir=None, timeout=150):
        self.client = client
        self.injected_client = client is not None
        self.data_dir = Path(data_dir) if data_dir is not None else agent.ROOT / 'data'
        self.timeout = timeout
        self.protocol = PROTOCOLS[0]

    def _client(self):
        # Reopen the private capability for every operation. App restarts rotate
        # it; do not replay an operation whose write outcome may be unknown.
        if not self.injected_client:
            self.client = agent.Client(agent.read_session(self.data_dir), self.timeout)
        return self.client

    def call(self, name, values):
        try:
            tool = TOOLS.get(name)
            if tool is None:
                raise agent.AgentError('Unknown local tool; no operation was performed.')
            validate(values, tool['inputSchema'])
            args = agent.build_parser().parse_args(arguments(tool, values))
            client = self._client()
            result = agent.execute(args, client)
            result = json.loads(client.redacted(json.dumps(result, ensure_ascii=False)))
            partial_failure = tool['command'] in {'import', 'asset-import', 'bibliography-import', 'ocr'} and any(row.get('status') == 'error' for row in result.get('results', []))
            response = {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}], 'isError': partial_failure}
            if self.protocol == '2025-06-18':
                response['structuredContent'] = result
            return response
        except agent.AgentError as failure:
            message = self.client.redacted(failure) if self.client else str(failure)
            return {'content': [{'type': 'text', 'text': json.dumps({'error': message, **({'status': failure.status} if failure.status is not None else {})})}], 'isError': True}
        except Exception:
            return {'content': [{'type': 'text', 'text': 'Local tool did not complete. Read saved state before repeating a write; no credentials or traceback are exposed.'}], 'isError': True}

    def handle(self, message):
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
            return error(None, -32600, 'Invalid JSON-RPC request.')
        if 'id' not in message:
            # Notifications never execute mutating tools or emit responses.
            return None
        id = message['id']
        if type(id) not in {str, int} and id is not None:
            return error(None, -32600, 'Invalid JSON-RPC request identifier.')
        method, params = message['method'], message.get('params', {})
        if not isinstance(params, dict):
            return error(id, -32602, 'Method parameters must be an object.')
        if method == 'initialize':
            requested = params.get('protocolVersion')
            self.protocol = requested if requested in PROTOCOLS else PROTOCOLS[-1]
            result = {'protocolVersion': self.protocol, 'capabilities': {'tools': {'listChanged': False}}, 'serverInfo': {'name': 'kosh-local', 'version': '1'},
                      'instructions': 'Use explicit workspace/source/file selections. Tool sends and file applies require caller-attested user consent; this adapter cannot verify human approval. No generic routes, SQL, shell or automatic configuration changes.'}
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools': [{'name': name, 'description': tool['description'], 'inputSchema': tool['inputSchema']} for name, tool in TOOLS.items()]}
        elif method == 'tools/call':
            if set(params) - {'name', 'arguments', '_meta'} or not isinstance(params.get('name'), str):
                return error(id, -32602, 'Select a named local tool and explicit arguments.')
            result = self.call(params['name'], params.get('arguments', {}))
        else:
            return error(id, -32601, 'Method not found.')
        return {'jsonrpc': '2.0', 'id': id, 'result': result}


def serve(server, source, output, max_line=MAX_LINE):
    while True:
        line = source.readline(max_line + 1)
        if not line:
            return
        if len(line) > max_line or len(line.encode('utf-8')) > max_line:
            while line and not line.endswith('\n'):
                line = source.readline(max_line + 1)
            response = error(None, -32600, 'Request exceeds the bounded stdio message limit.')
        elif not line.strip():
            continue
        else:
            try:
                response = server.handle(json.loads(line))
            except (ValueError, UnicodeError):
                response = error(None, -32700, 'Invalid JSON message.')
        if response is not None:
            serialized = json.dumps(response, ensure_ascii=False)
            if server.client is not None:
                serialized = server.client.redacted(serialized)
            output.write(serialized + '\n')
            output.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run Kosh local MCP stdio tools. No automatic client configuration changes.')
    parser.add_argument('--data-dir', type=Path, default=agent.ROOT / 'data')
    parser.add_argument('--timeout', type=int, default=150)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 180:
        parser.error('--timeout must be between 1 and 180 seconds.')
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    serve(Server(data_dir=args.data_dir, timeout=args.timeout), sys.stdin, sys.stdout)


if __name__ == '__main__':
    main()
