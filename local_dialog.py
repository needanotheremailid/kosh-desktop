"""Explicit, session-routed Windows file selection; no file writes or shell."""
from pathlib import Path
import json
import os
import subprocess
import threading

_active = threading.Lock()
KINDS = {'folder', 'backup-open', 'backup-save'}


def choose(root, body):
    from backend import AppError
    if (not isinstance(body, dict) or set(body) != {'kind'}
            or not isinstance(body['kind'], str) or body['kind'] not in KINDS):
        raise AppError('Choose a backup folder, ZIP to open, or new ZIP destination.')
    if os.name != 'nt':
        raise AppError('Native file selection requires the Windows desktop app.', 409)
    executable = Path(root) / 'bin' / 'ResearchDesktop.exe'
    if not executable.is_file():
        raise AppError('The desktop launcher is missing. Reinstall Kosh to enable file selection.', 409)
    if not _active.acquire(blocking=False):
        raise AppError('A file selection window is already open. Finish or cancel it first.', 409)
    try:
        try:
            result = subprocess.run([str(executable), '--dialog', body['kind']],
                                    capture_output=True, timeout=180, check=False,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired:
            raise AppError('File selection timed out. Nothing changed; choose again.', 408) from None
        except OSError:
            raise AppError('The file selection window could not open. Nothing changed.', 409) from None
        try:
            selected = json.loads(result.stdout.decode('utf-8-sig'))
            if result.returncode or set(selected) != {'cancelled', 'path'}:
                raise ValueError()
            if type(selected['cancelled']) is not bool or not isinstance(selected['path'], str):
                raise ValueError()
            if selected['cancelled']:
                return {'cancelled': True, 'path': ''}
            path = Path(selected['path'])
            if not path.is_absolute() or '\x00' in str(path):
                raise ValueError()
        except (ValueError, TypeError, UnicodeError):
            raise AppError('File selection did not return a usable path. Nothing changed.', 409) from None
        return {'cancelled': False, 'path': str(path)}
    finally:
        _active.release()
