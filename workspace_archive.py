"""Bounded file I/O for local ZIPs; validation/remapping remain in Store."""
from collections.abc import Mapping, MutableMapping
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import backend as b


CHUNK_SIZE = 1024 * 1024
TOTAL_LIMIT = b.FILE_LIMIT * (b.BACKUP_COLLECTION_LIMITS['documents'] + 1)
FILE_ARCHIVE_LIMIT = TOTAL_LIMIT + 1024 * 1024


class ArchiveCancelled(Exception):
    """Cooperative cancellation, separate from malformed input/storage errors."""


def checkpoint(control, phase, done=0, total=None):
    if control is not None:
        control.checkpoint(phase, done=done, total=total)


def stream_copy(source, output=None, *, limit=FILE_ARCHIVE_LIMIT, control=None, phase='reading', total=None):
    digest, size = hashlib.sha256(), 0
    checkpoint(control, phase, total=total)
    while block := source.read(CHUNK_SIZE):
        size += len(block)
        if size > limit:
            raise b.AppError('Archive or source exceeds its record-derived file limit.', 413)
        digest.update(block)
        if output is not None:
            output.write(block)
        checkpoint(control, phase, done=size, total=total)
    return size, digest.hexdigest()


def hash_file(path, *, limit=FILE_ARCHIVE_LIMIT, control=None):
    with Path(path).open('rb') as source:
        return stream_copy(source, limit=limit, control=control, phase='checking_archive', total=Path(path).stat().st_size)


def write_snapshot(store, snapshot, target, control=None):
    checkpoint(control, 'preparing_backup')
    manifest = json.dumps(snapshot, ensure_ascii=False, indent=2).encode('utf-8')
    if len(manifest) > b.FILE_LIMIT:
        raise b.AppError('Workspace manifest exceeds its 32 MiB limit. No completed backup was published.', 413)
    required = len(manifest) + sum(row['size'] for row in snapshot['documents']) + 1024 * 1024
    target = Path(target)
    if shutil.disk_usage(target.parent).free < required:
        raise b.AppError('The backup drive has insufficient free space. Earlier completed backups are retained.', 413)
    with target.open('xb') as output:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.writestr('manifest.json', manifest)
            for document in snapshot['documents']:
                checkpoint(control, 'writing_source', total=document['size'])
                path = store.root / document['path']
                if path.is_symlink() or path.resolve().parent != store.originals or not path.is_file():
                    raise b.AppError('Managed original is missing or outside the data folder. No completed backup was published.', 409)
                if path.stat().st_size != document['size'] or document['size'] > b.FILE_LIMIT:
                    raise b.AppError('Managed original size changed. No completed backup was published.', 409)
                with path.open('rb') as source, archive.open(document['path'], 'w', force_zip64=True) as member:
                    size, digest = stream_copy(source, member, limit=b.FILE_LIMIT, control=control,
                                               phase='writing_source', total=document['size'])
                if size != document['size'] or digest != document['sha256']:
                    raise b.AppError('Managed original hash changed. No completed backup was published.', 409)
        output.flush()
        os.fsync(output.fileno())
    size, digest = hash_file(target, control=control)
    return {'bytes': size, 'sha256': digest,
            'counts': {key: len(snapshot[key]) for key in b.BACKUP_COLLECTION_LIMITS}}


class ZipOriginals(Mapping):
    """Keep member identities only; materialize at most one bounded original."""
    def __init__(self, archive, control=None):
        self.archive = archive
        self.members = {}
        self.control = control

    def __getitem__(self, key):
        if self.control is None:
            return self.archive.read(self.members[key])
        with self.archive.open(self.members[key]) as source, io.BytesIO() as output:
            stream_copy(source, output, limit=b.FILE_LIMIT, control=self.control,
                        phase='reading_source', total=self.archive.getinfo(self.members[key]).file_size)
            return output.getvalue()

    def __iter__(self):
        return iter(self.members)

    def __len__(self):
        return len(self.members)

    def add_verified(self, key, member, size, digest):
        with self.archive.open(member) as source:
            actual_size, actual_digest = stream_copy(source, limit=b.FILE_LIMIT, control=self.control,
                                                    phase='verifying_source', total=size)
        if size != actual_size or digest != actual_digest:
            raise b.AppError('Backup original failed its size or SHA256 check.')
        self.members[key] = member

    def publish(self, key, target, size, digest):
        target = Path(target)
        if target.exists() or target.is_symlink():
            raise b.AppError('A managed object already exists; it was preserved.', 409)
        pending = target.with_name(target.name + '.pending-' + b.new_id())
        with self.archive.open(self.members[key]) as source, pending.open('xb') as output:
            actual_size, actual_digest = stream_copy(source, output, limit=b.FILE_LIMIT)
            output.flush()
            os.fsync(output.fileno())
        if size != actual_size or digest != actual_digest:
            raise b.AppError('Backup original changed after validation. No workspace was created.')
        pending.rename(target)


class SpilledExtractions(MutableMapping):
    """Validated text lives on disk instead of accumulating across the library."""
    def __init__(self, directory, control=None):
        self.directory = Path(directory)
        self.files = {}
        self.control = control

    def __getitem__(self, key):
        checkpoint(self.control, 'validating_records')
        return json.loads(self.files[key].read_text(encoding='utf-8'))

    def __setitem__(self, key, value):
        checkpoint(self.control, 'saving_validation_text')
        path = self.directory / (key + '.json')
        with path.open('x', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False)
        self.files[key] = path
        checkpoint(self.control, 'validating_records')

    def __delitem__(self, key):
        raise TypeError('Validated extraction records are immutable.')

    def __iter__(self):
        return iter(self.files)

    def __len__(self):
        return len(self.files)


def restore_file(store, path, *, preview_only=False, expected_sha256=None, expected_size=None, control=None):
    if not preview_only:
        control = None  # Approved apply is never interrupted midway through publication.
    checkpoint(control, 'preparing_preview')
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > FILE_ARCHIVE_LIMIT:
        raise b.AppError('Selected backup file is missing, linked or exceeds the record-derived archive limit.')
    # Copy and hash once into a private immutable snapshot. All validation and
    # publication use this same handle, so a selected file cannot change between
    # the verdict and application. Cleanup removes only this owned scratch tree.
    with tempfile.TemporaryDirectory(prefix='kosh-archive-') as scratch:
        stage = Path(scratch) / 'selected.zip'
        required = path.stat().st_size
        if shutil.disk_usage(scratch).free < required:
            raise b.AppError('Temporary validation storage has insufficient free space for the selected ZIP. No workspace was created; the selected file was retained.', 413)
        with path.open('rb') as source, stage.open('xb') as output:
            size, digest = stream_copy(source, output, control=control, phase='staging_archive', total=path.stat().st_size)
        if expected_size is not None and size != expected_size or expected_sha256 is not None and digest != expected_sha256:
            raise b.AppError('Backup ZIP changed or failed its SHA-256 byte check. No restore was performed.')
        try:
            with stage.open('rb') as source, zipfile.ZipFile(source) as archive:
                if preview_only:
                    with store.lock:
                        store._ensure_open()
                    # Pure record validation and spill/file I/O use the immutable
                    # snapshot outside the DB lock. Store serializes only native
                    # PDF/image parser lifetimes; publication keeps the full lock.
                    return store._restore_archive(archive, preview_only=True, file_backed=True,
                                                  spill_directory=scratch, control=control)
                with store.lock:
                    store._ensure_open()
                    return store._restore_archive(archive, preview_only=preview_only, file_backed=True,
                                                  spill_directory=scratch)
        except b.AppError:
            raise
        except OSError:
            raise b.AppError('Backup storage failed. Check destination permissions and free space. Any newly written recovery originals or pending files were retained; no new workspace was created.') from None
        except (ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError, NotImplementedError):
            raise b.AppError('Backup archive or manifest is malformed. No workspace was created.') from None
