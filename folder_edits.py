"""Explicit bounded text diffs and local publication; no model or command executor."""
from __future__ import annotations
import difflib
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import tempfile
import threading
import time
import uuid

FILE_LIMIT=256*1024
TOTAL_LIMIT=1024*1024
EXTENSIONS={'.md','.txt','.bib','.tex','.csv'}


class FolderError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def text_bytes(content):
    if not isinstance(content,str): raise FolderError('Replacement content must be UTF-8 text.')
    if any(ord(c)<32 and c not in '\t\r\n' for c in content):
        raise FolderError('Binary/control content is not supported.')
    try: data=content.encode('utf-8')
    except UnicodeError: raise FolderError('Replacement text contains invalid Unicode.') from None
    if len(data)>FILE_LIMIT: raise FolderError('Each text file is limited to 256 KB.')
    return data


def check_chain(path,allow_hidden=False):
    """Check before resolve, including junctions and other Windows reparse points."""
    for candidate in reversed((path,*path.parents)):
        try: info=candidate.lstat()
        except FileNotFoundError: continue
        attributes=getattr(info,'st_file_attributes',0)
        if stat.S_ISLNK(info.st_mode) or attributes & 0x400:
            raise FolderError('Symlinks, junctions and reparse points (including cloud placeholder files) are excluded; an ordinary cloud-synced folder is not automatically excluded.')
        if not allow_hidden and attributes & 0x2 and candidate != Path(candidate.anchor):
            raise FolderError('Hidden files or directories are excluded.')


def relative_path(value):
    if not isinstance(value,str) or not value or len(value)>240:
        raise FolderError('Enter a relative text-file path of at most 240 characters.')
    windows=PureWindowsPath(value)
    if windows.drive or windows.is_absolute() or value.startswith(('/','\\')):
        raise FolderError('Absolute, drive-relative and network file paths are excluded.')
    parts=value.replace('\\','/').split('/')
    for part in parts:
        if not part or part in {'.','..'} or part.startswith('.') or part.endswith((' ','.')):
            raise FolderError('Traversal, hidden paths and ambiguous Windows names are excluded.')
        if any(ord(c)<32 or c in '<>:"|?*' for c in part):
            raise FolderError('Unsupported path characters or alternate streams.')
        if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part,re.I):
            raise FolderError('Windows device names are excluded.')
        if re.search(r'(^|[-_.])(credentials?|secrets?|tokens?|passwords?|passwd|auth|cookies?)([-_.]|$)',part,re.I):
            raise FolderError('Credential and secret paths are excluded.')
        stem=part.rsplit('.',1)[0].casefold().replace('_','-')
        if stem in {'key','keys'} or re.search(r'(^|-)(api|private|secret|access|signing)-keys?(-|$)',stem):
            raise FolderError('Credential key paths are excluded.')
    if Path(parts[-1]).suffix.lower() not in EXTENSIONS:
        raise FolderError('Only Markdown, TXT, BIB, TEX and CSV text files are supported.')
    return '/'.join(parts)


def read_original(path,allow_hidden=False):
    check_chain(path,allow_hidden=allow_hidden)
    if not path.exists(): return None
    if not path.is_file() or path.stat().st_nlink>1:
        raise FolderError('Directories and hard-linked files are excluded.')
    if path.stat().st_size>FILE_LIMIT: raise FolderError('Existing file exceeds 256 KB.')
    data=path.read_bytes()
    if len(data)>FILE_LIMIT: raise FolderError('Existing file exceeds 256 KB.')
    try: text=data.decode('utf-8')
    except UnicodeError: raise FolderError('Existing file must be UTF-8 text, not binary.') from None
    text_bytes(text)
    return data


def publish_bytes(path,data,create=False):
    """Publish a prepared sibling atomically. Creation never replaces another file."""
    descriptor,temporary=tempfile.mkstemp(prefix='kosh-pending-',suffix='.tmp',dir=path.parent)
    temporary=Path(temporary)
    try:
        with os.fdopen(descriptor,'wb') as output:
            output.write(data);output.flush();os.fsync(output.fileno())
        if create:
            os.link(temporary,path)  # Atomic no-clobber name creation.
        else:
            os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)  # Only our generated staging file.


class FolderEditor:
    def __init__(self,data_root,protected_roots=()):
        self.data_root=Path(data_root).absolute()
        self.recovery_root=self.data_root/'folder-edit-recovery'
        self.protected=[self.data_root,*[Path(p).absolute() for p in protected_roots]]
        self.lock=threading.RLock();self.previews={}

    def _target(self,value):
        if not isinstance(value,str) or not value.strip() or len(value)>1024:
            raise FolderError('Choose one explicit existing absolute folder.')
        path=Path(value)
        if not path.is_absolute(): raise FolderError('The selected folder must be an absolute path.')
        check_chain(path)
        if not path.is_dir(): raise FolderError('The selected folder does not exist.')
        target=path.resolve()
        if target==Path(target.anchor): raise FolderError('A filesystem or drive root cannot be selected.')
        blocked={os.environ.get(k,'') for k in ('WINDIR','ProgramFiles','ProgramFiles(x86)','ProgramData')}
        for value_ in blocked:
            if value_ and (target==Path(value_).resolve() or target.is_relative_to(Path(value_).resolve())):
                raise FolderError('System and program directories are excluded.')
        for protected in self.protected:
            resolved=protected.resolve()
            if target==resolved or target.is_relative_to(resolved) or resolved.is_relative_to(target):
                raise FolderError('App storage and its parent folders cannot be editing targets.')
        if any(part.startswith('.') or part.casefold() in {'appdata','windows','program files','program files (x86)','programdata'} for part in target.parts):
            raise FolderError('Hidden configuration and system directories are excluded.')
        info=target.stat()
        return target,(info.st_dev,info.st_ino)

    def _file(self,target,relative):
        path=target.joinpath(*relative.split('/'))
        check_chain(path)
        if not path.parent.is_dir(): raise FolderError('Parent directories must already exist; no folders are created.')
        if not path.resolve().is_relative_to(target): raise FolderError('File path escapes the selected folder.')
        return path

    def preview(self,target_path,files):
        with self.lock:
            target,identity=self._target(target_path)
            if not isinstance(files,list) or not 1<=len(files)<=10:
                raise FolderError('Propose between one and ten text files.')
            prepared=[];seen=set();total=0
            for item in files:
                if not isinstance(item,dict) or set(item)!={'path','content'}:
                    raise FolderError('Each proposal needs only path and replacement content; no delete/command operations.')
                relative=relative_path(item['path'])
                if relative.casefold() in seen: raise FolderError('Duplicate target paths are excluded.')
                seen.add(relative.casefold())
                path=self._file(target,relative)
                original=read_original(path);replacement=text_bytes(item['content'])
                total+=len(replacement)+(len(original) if original is not None else 0)
                if total>TOTAL_LIMIT: raise FolderError('Combined original and replacement text exceeds 1 MB.')
                lines=difflib.unified_diff((original or b'').decode('utf-8').splitlines(keepends=True),item['content'].splitlines(keepends=True),fromfile=relative+' (original)',tofile=relative+' (proposed)')
                diff=''.join(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n' for line in lines)
                ending_names={'\r\n':'CRLF','\n':'LF','\r':'CR'}
                before_endings=sorted({ending_names[v] for v in re.findall(r'\r\n|\r|\n',(original or b'').decode('utf-8'))})
                after_endings=sorted({ending_names[v] for v in re.findall(r'\r\n|\r|\n',item['content'])})
                prepared.append({'path':relative,'operation':'replace' if original is not None else 'create','before_sha256':digest(original) if original is not None else None,'after_sha256':digest(replacement),'bytes':len(replacement),'diff':diff,'line_endings_changed':original is not None and before_endings!=after_endings,'original_line_endings':before_endings,'proposed_line_endings':after_endings,'bom_removed':bool(original and original.startswith(b'\xef\xbb\xbf') and not replacement.startswith(b'\xef\xbb\xbf')),'original':original,'replacement':replacement})
            current=time.monotonic()
            self.previews={k:v for k,v in self.previews.items() if v['expires']>current}
            if len(self.previews)>=30: raise FolderError('Too many pending previews. Wait for unused previews to expire.')
            preview_id=uuid.uuid4().hex
            preview={'preview_id':preview_id,'target_path':str(target),'target_identity':identity,'files':prepared,'expires':current+900,'approval_version':1}
            self.previews[preview_id]=preview
            return {'preview_id':preview_id,'target_path':str(target),'files':[{k:v for k,v in item.items() if k not in {'original','replacement'}} for item in prepared],'approval_version':1,'notice':'Only these exact UTF-8 bytes will be applied after approval. No command execution or file deletion. Close other editors while applying; this is not OS-level isolation. Existing originals are retained in app recovery storage.'}

    def _journal(self,directory,receipt):
        data=json.dumps(receipt,ensure_ascii=False,indent=2).encode('utf-8')
        publish_bytes(directory/'receipt.json',data)

    def apply(self,preview_id,approved,approval_version=1):
        with self.lock:
            if approved is not True or type(approval_version) is not int or approval_version!=1:
                raise FolderError('Explicit approval of this exact preview is required.')
            preview=self.previews.get(preview_id) if isinstance(preview_id,str) else None
            if not preview or preview['expires']<=time.monotonic(): raise FolderError('Preview expired or was already applied. Create a new diff.')
            target,identity=self._target(preview['target_path'])
            if identity!=preview['target_identity']: raise FolderError('The selected folder identity changed; preview again.')
            for item in preview['files']:
                data=read_original(self._file(target,item['path']))
                if (digest(data) if data is not None else None)!=item['before_sha256']:
                    raise FolderError('Target changed after preview: '+item['path']+'. Nothing was applied.')
            check_chain(self.data_root,allow_hidden=True)
            self.recovery_root.mkdir(parents=True,exist_ok=True)
            check_chain(self.recovery_root,allow_hidden=True)
            receipt_id=uuid.uuid4().hex;directory=self.recovery_root/receipt_id
            directory.mkdir()
            rows=[]
            for index,item in enumerate(preview['files']):
                recovery_path=directory/(str(index)+'.original')
                if item['original'] is not None: publish_bytes(recovery_path,item['original'],create=True)
                rows.append({k:item[k] for k in ('path','operation','before_sha256','after_sha256','bytes')}|{'status':'pending','recovery_path':str(recovery_path) if item['original'] is not None else None})
            receipt={'receipt_id':receipt_id,'target_path':str(target),'created_at':time.time(),'status':'applying','files':rows,'notice':'Recovery copies and this journal are retained locally. Created files are never automatically deleted.'}
            self._journal(directory,receipt)
            self.previews.pop(preview_id)
            failed=False
            for item,row in zip(preview['files'],rows):
                if failed: row['status']='not_applied';continue
                try:
                    current_target,current_identity=self._target(preview['target_path'])
                    if current_identity!=identity: raise FolderError('Selected folder identity changed during application.')
                    path=self._file(current_target,item['path']);current=read_original(path)
                    if (digest(current) if current is not None else None)!=item['before_sha256']:
                        raise FolderError('File changed before publication.')
                    publish_bytes(path,item['replacement'],create=item['operation']=='create')
                    if read_original(path)!=item['replacement']: raise FolderError('Published bytes did not match the approved content.')
                    row['status']='applied'
                except (OSError,FolderError) as error:
                    row['status']='failed';row['error']=str(error);failed=True
                    try:
                        actual=read_original(self._file(target,item['path']))
                        if actual is not None and digest(actual)==item['after_sha256']:
                            row['status']='applied'
                            row['error']='Approved bytes are present, but a later operation reported: '+str(error)
                        elif (digest(actual) if actual is not None else None)!=item['before_sha256']:
                            row['status']='needs_review'
                    except (OSError,FolderError): row['status']='needs_review'
                try: self._journal(directory,receipt)
                except OSError:
                    row['journal_warning']='Receipt update could not be persisted; inspect history before retrying.'
                    failed=True
            receipt['status']='partial' if failed and any(r['status'] in {'applied','needs_review'} for r in rows) else 'failed' if failed else 'applied'
            try: self._journal(directory,receipt)
            except OSError: receipt['notice']+=' Final journal update failed; recovery copies remain. Inspect targets before retrying.'
            return receipt

    def _receipt(self,receipt_id):
        if not isinstance(receipt_id,str) or not re.fullmatch(r'[a-f0-9]{32}',receipt_id): raise FolderError('Invalid recovery receipt.')
        path=self.recovery_root/receipt_id/'receipt.json';check_chain(path,allow_hidden=True)
        if not path.is_file() or path.stat().st_size>128*1024: raise FolderError('Recovery receipt is absent or invalid.')
        try: value=json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,OSError): raise FolderError('Recovery receipt cannot be read.') from None
        if not isinstance(value,dict) or value.get('receipt_id')!=receipt_id or not isinstance(value.get('target_path'),str) or not isinstance(value.get('created_at'),(float,int)) or not isinstance(value.get('files'),list) or len(value['files'])>10 or any(not isinstance(row,dict) for row in value['files']):
            raise FolderError('Recovery receipt schema is invalid.')
        return value

    def history(self):
        with self.lock:
            if not self.recovery_root.exists(): return []
            check_chain(self.recovery_root,allow_hidden=True)
            receipts=[]
            for directory in self.recovery_root.iterdir():
                if re.fullmatch(r'[a-f0-9]{32}',directory.name):
                    try:
                        receipt=self._receipt(directory.name)
                        if receipt.get('status')=='applying': receipt['notice']='Interrupted application. Pending statuses are unverified; inspect targets before retrying. Recovery copies are retained.'
                        receipts.append(receipt)
                    except FolderError: continue
            return sorted(receipts,key=lambda r:r.get('created_at',0),reverse=True)

    def recovery_preview(self,receipt_id):
        with self.lock:
            receipt=self._receipt(receipt_id);files=[]
            for index,row in enumerate(receipt['files']):
                if row.get('operation')!='replace' or row.get('status') not in {'applied','pending','failed','needs_review'}: continue
                relative=relative_path(row.get('path'))
                original=self.recovery_root/receipt_id/(str(index)+'.original')
                data=read_original(original,allow_hidden=True)
                if data is None or digest(data)!=row.get('before_sha256'): raise FolderError('Recovery copy is absent or its hash changed.')
                files.append({'path':relative,'content':data.decode('utf-8')})
            if not files: raise FolderError('No replacement originals to recover. Created files are retained and never deleted.')
            preview=self.preview(receipt['target_path'],files)
            preview['notice']='Recovery preview: review the current differences before approving. This restores retained originals as text replacements; created files are retained.'
            return preview
