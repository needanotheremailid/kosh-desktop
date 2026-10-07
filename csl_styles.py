"""Content-addressed CSL storage and explicitly approved official retrieval."""
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import json
import urllib.request
import urllib.error

NS = '{http://purl.org/net/xbiblio/csl}'
LIMIT = 1024 * 1024
BUILTINS = {'vancouver': 'Vancouver — NLM', 'apa': 'APA 7th edition', 'ieee': 'IEEE', 'chicago-note': 'Chicago notes and bibliography'}
ROOT = Path(__file__).resolve().parent


class StyleError(ValueError):
    pass


def describe(xml):
    if not isinstance(xml, str) or len(xml.encode('utf-8')) > LIMIT or '\x00' in xml:
        raise StyleError('Choose a UTF-8 CSL style under 1 MiB.')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', xml, re.I):
        raise StyleError('CSL styles cannot contain DTDs or entities.')
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise StyleError('The CSL style is not valid XML.') from error
    if root.tag != NS + 'style' or root.get('version') not in {'1.0', '1.0.1', '1.0.2'}:
        raise StyleError('Choose a CSL 1.0 independent style.')
    parents = [element.get('href', '') for element in root.iter() if element.tag == NS + 'link' and element.get('rel') == 'independent-parent']
    if len(parents) > 1 or (not parents and root.find(NS + 'citation') is None):
        raise StyleError('CSL requires citation rules or one independent parent.')
    if not parents and root.get('class') not in {'in-text', 'note'}:
        raise StyleError('CSL class must be in-text or note.')
    if any(not isinstance(element.tag, str) or not element.tag.startswith(NS) or element.tag[len(NS):] in {'script', 'iframe', 'object', 'include'} for element in root.iter()):
        raise StyleError('CSL contains unsupported or foreign XML elements.')
    title = root.findtext(NS + 'info/' + NS + 'title', '').strip()
    identifier = root.findtext(NS + 'info/' + NS + 'id', '').strip()
    if not title or len(title) > 300 or not identifier:
        raise StyleError('CSL requires an information title and identifier.')
    return {'title': title, 'upstream_id': identifier, 'parent': parents[0] if parents else '',
            'style_class': root.get('class', ''), 'default_locale': root.get('default-locale', '')}


def _language(language):
    if not isinstance(language, str) or not re.fullmatch(r'[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-[A-Z]{2})?', language):
        raise StyleError('Choose a CSL locale language code, such as fr-FR.')
    return language


def select_language(language, locales):
    language = _language(language)
    if language in locales:
        return language
    # Primary dialects match the pinned processor's CSL.LANG_BASES. This is
    # same-language resolution, never substitution of English for missing terms.
    primary = {'en': 'en-US', 'fr': 'fr-FR', 'de': 'de-DE', 'es': 'es-ES', 'pt': 'pt-PT', 'zh': 'zh-CN'}
    if language in primary and primary[language] in locales:
        return primary[language]
    if '-' not in language:
        matches = [key for key in locales if key.startswith(language + '-')]
        if len(matches) == 1:
            return matches[0]
    raise StyleError('CSL locale unavailable: ' + language + '; import or explicitly retrieve it.')


def describe_locale(xml):
    if not isinstance(xml, str) or len(xml.encode('utf-8')) > LIMIT or '\x00' in xml or re.search(r'<!\s*(?:DOCTYPE|ENTITY)', xml, re.I):
        raise StyleError('Choose a UTF-8 CSL locale under 1 MiB without entities.')
    try:
        tree = ET.fromstring(xml)
    except ET.ParseError as error:
        raise StyleError('CSL locale XML is invalid.') from error
    if tree.tag != NS + 'locale':
        raise StyleError('Choose a CSL locale XML file.')
    return _language(tree.get('{http://www.w3.org/XML/1998/namespace}lang', ''))


class StyleLibrary:
    def __init__(self, data_root):
        self.directory = Path(data_root) / 'citation-styles'

    def resolve(self, style):
        if style in BUILTINS:
            return (ROOT / 'vendor/csl/styles' / (style + '.csl')).read_text(encoding='utf-8')
        if not isinstance(style, str) or not re.fullmatch(r'csl-[a-f0-9]{64}', style):
            raise StyleError('Choose an installed citation style.')
        path = self.directory / (style + '.csl')
        if not path.is_file() or path.is_symlink() or path.stat().st_size > LIMIT:
            raise StyleError('This citation style is unavailable; import its original CSL file.')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != style[4:]:
            raise StyleError('Citation style hash changed; import a reviewed copy again.')
        try:
            xml = data.decode('utf-8')
        except UnicodeDecodeError as error:
            raise StyleError('CSL must be UTF-8 text.') from error
        describe(xml)
        return xml

    def list_styles(self):
        rows = [{'id': key, **describe(self.resolve(key)), 'title': title, 'builtin': True, 'resolved': True} for key, title in BUILTINS.items()]
        for path in sorted(self.directory.glob('csl-*.csl')):
            try:
                row = {'id': path.stem, **describe(self.resolve(path.stem)), 'builtin': False}
                try:
                    bundle = self.resolve_bundle(path.stem)
                    row.update(resolved=True, style_class=bundle['style_class'], language=bundle['language'])
                except StyleError as error:
                    row.update(resolved=False, dependency_error=str(error))
                rows.append(row)
            except (StyleError, OSError):
                rows.append({'id': path.stem, 'title': 'Unavailable style — import original again', 'builtin': False, 'unavailable': True})
        return rows

    def import_style(self, xml):
        details = describe(xml)
        data = xml.encode('utf-8')
        identifier = 'csl-' + hashlib.sha256(data).hexdigest()
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.directory.is_symlink():
            raise StyleError('Citation style storage cannot be a symbolic link.')
        path = self.directory / (identifier + '.csl')
        if path.exists():
            self.resolve(identifier)
        else:
            with path.open('xb') as output:
                output.write(data)
        return {'id': identifier, **details, 'builtin': False}

    def import_locale(self, xml):
        language = describe_locale(xml)
        data = xml.encode('utf-8')
        digest = hashlib.sha256(data).hexdigest()
        directory = self.directory / 'locales'
        directory.mkdir(parents=True, exist_ok=True)
        if self.directory.is_symlink() or directory.is_symlink():
            raise StyleError('CSL locale storage cannot be a symbolic link.')
        path = directory / ('locale-' + digest + '.xml')
        if path.exists():
            if path.is_symlink() or path.read_bytes() != data:
                raise StyleError('Locale cache integrity failed.')
        else:
            with path.open('xb') as output:
                output.write(data)
        return {'language': language, 'sha256': digest}

    def _locales(self):
        result = {}
        for path in sorted((ROOT / 'vendor/csl/locales').glob('locales-*.xml')):
            xml = path.read_text(encoding='utf-8-sig')
            result[describe_locale(xml)] = xml
        for path in sorted((self.directory / 'locales').glob('locale-*.xml')):
            if path.is_symlink() or path.stat().st_size > LIMIT:
                raise StyleError('Locale cache integrity failed.')
            data = path.read_bytes()
            if path.stem != 'locale-' + hashlib.sha256(data).hexdigest():
                raise StyleError('Locale cache hash changed; import original again.')
            xml = data.decode('utf-8')
            language = describe_locale(xml)
            if language in result and result[language] != xml:
                raise StyleError('Conflicting cached CSL locale: ' + language)
            result[language] = xml
        return result

    def list_locales(self):
        return sorted(self._locales())

    def resolve_bundle(self, style, language=None):
        xml = self.resolve(style)
        details = describe(xml)
        selected_language = language or details['default_locale']
        seen = set()
        for _ in range(8):
            details = describe(xml)
            if details['upstream_id'] in seen:
                raise StyleError('CSL parent dependency loop.')
            seen.add(details['upstream_id'])
            if not details['parent']:
                break
            candidates = [self.resolve(key) for key in BUILTINS]
            candidates += [self.resolve(path.stem) for path in sorted(self.directory.glob('csl-*.csl'))]
            matches = [candidate for candidate in candidates if describe(candidate)['upstream_id'] == details['parent']]
            if not matches:
                raise StyleError('CSL independent parent is missing; import it or explicitly retrieve official dependencies.')
            if len(set(matches)) != 1:
                raise StyleError('Conflicting CSL parent copies; review imported styles.')
            xml = matches[0]
        else:
            raise StyleError('CSL parent dependency depth exceeds eight.')
        selected_language = _language(selected_language or details['default_locale'] or 'en-US')
        locales = self._locales()
        selected_language = select_language(selected_language, locales)
        # Return all available exact locales: citeproc may request language variants
        # for terms and a style's embedded locale fallbacks. Never return English
        # XML while claiming that it is another language.
        return {'style_xml': xml, 'language': selected_language, 'locales': locales,
                'style_class': details['style_class']}

    def retrieve_official(self, *, style_id=None, locale=None, approved=False):
        if approved is not True:
            raise StyleError('Explicit approval is required to retrieve official CSL files.')
        if (style_id is None) == (locale is None):
            raise StyleError('Choose one official style identifier or locale.')
        if style_id is not None and (not isinstance(style_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,199}', style_id)):
            raise StyleError('Choose an official CSL style identifier, not a URL.')
        if locale is not None:
            _language(locale)
        pins = json.loads((ROOT / 'vendor/csl/components.json').read_text(encoding='utf-8'))['pins']
        if any(not re.fullmatch(r'[a-f0-9]{40}', pins.get(key, '')) for key in ('styles', 'locales')):
            raise StyleError('Official CSL repository pins are invalid.')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise StyleError('Official CSL retrieval refused a redirect.')
        opener = urllib.request.build_opener(NoRedirect)
        def fetch(repository, name):
            url = 'https://raw.githubusercontent.com/citation-style-language/' + repository + '/' + pins[repository] + '/' + name
            try:
                with opener.open(urllib.request.Request(url, headers={'User-Agent': 'Kosh-CSL'}), timeout=15) as response:
                    data = response.read(LIMIT + 1)
                if len(data) > LIMIT:
                    raise StyleError('Official CSL file exceeds 1 MiB.')
                return data.decode('utf-8-sig')
            except urllib.error.HTTPError:
                raise
            except (OSError, UnicodeDecodeError) as error:
                raise StyleError('Official CSL file unavailable; no fallback was used.') from error
        if locale is not None:
            try:
                return self.import_locale(fetch('locales', 'locales-' + locale + '.xml'))
            except urllib.error.HTTPError as error:
                raise StyleError('Official CSL locale unavailable.') from error
        seen = set()
        imported = None
        current = style_id
        for _ in range(8):
            if current in seen:
                raise StyleError('Official CSL dependency loop.')
            seen.add(current)
            try:
                xml = fetch('styles', current + '.csl')
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise StyleError('Official CSL style retrieval failed.') from error
                try:
                    xml = fetch('styles', 'dependent/' + current + '.csl')
                except urllib.error.HTTPError as parent_error:
                    raise StyleError('Official CSL style unavailable.') from parent_error
            details = describe(xml)
            expected_id = 'http://www.zotero.org/styles/' + current
            if details['upstream_id'] != expected_id:
                raise StyleError('Official CSL identifier does not match the requested style.')
            row = self.import_style(xml)
            imported = imported or row
            if not details['parent']:
                language = details['default_locale'] or 'en-US'
                if language not in self._locales():
                    self.retrieve_official(locale=language, approved=True)
                return imported
            match = re.fullmatch(r'https?://www\.zotero\.org/styles/([a-z0-9][a-z0-9-]{0,199})', details['parent'])
            if not match:
                raise StyleError('Dependent CSL parent is not an official style identifier.')
            if details['default_locale'] and details['default_locale'] not in self._locales():
                self.retrieve_official(locale=details['default_locale'], approved=True)
            current = match[1]
        raise StyleError('Official CSL dependency depth exceeds eight.')

    def retrieve_dependencies(self, style, *, language=None, approved=False):
        """Explicit action for an already imported style; XML links are never URLs."""
        if approved is not True:
            raise StyleError('Explicit approval is required to retrieve official CSL files.')
        details = describe(self.resolve(style))
        if details['parent']:
            match = re.fullmatch(r'https?://www\.zotero\.org/styles/([a-z0-9][a-z0-9-]{0,199})', details['parent'])
            if not match:
                raise StyleError('Dependent CSL parent is not an official style identifier.')
            self.retrieve_official(style_id=match[1], approved=True)
        selected = language or details['default_locale']
        if selected and selected not in self._locales():
            self.retrieve_official(locale=_language(selected), approved=True)
        return self.resolve_bundle(style, language=language)
