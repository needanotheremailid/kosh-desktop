"""A failed startup activation keeps the real HTTP service read-only."""
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from agent import AgentError, Client, read_session


class StartupActivation(unittest.TestCase):
    def test_package_verification_failure_keeps_server_available_and_locked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'UPDATE_PENDING.json').write_text('{}')
            data = root / 'data'
            ready = data / 'server.json'
            script = (
                "import sys;from pathlib import Path;from types import SimpleNamespace;import server,updater,upgrade;"
                "server.ROOT=Path(sys.argv[1]);server.source_hash=lambda:'b'*64;"
                "updater.cache_root=lambda:Path(sys.argv[1])/'cache';"
                "updater.Updater=lambda root:SimpleNamespace(status=lambda:{});"
                "updater.verification_required=lambda *args:False;"
                "updater.confirm_activation=lambda *args:(_ for _ in ()).throw(upgrade.UpgradeError('Fixture package failure'));"
                "sys.argv=['server','--data-dir',sys.argv[2],'--ready-file',sys.argv[3],'--idle-minutes','1'];server.main()"
            )
            process = subprocess.Popen([sys.executable, '-c', script, str(root), str(data), str(ready)],
                                       cwd=Path(__file__).resolve().parents[1],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                client = None
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    self.assertIsNone(process.poll(), 'Candidate exited instead of remaining locked.')
                    if ready.exists():
                        try:
                            client = Client(read_session(data), timeout=2)
                            client.verify()
                            break
                        except AgentError:
                            pass
                    time.sleep(.05)
                self.assertIsNotNone(client)
                self.assertTrue(client.request('/api/updates/status')['activation_required'])
                with self.assertRaises(AgentError) as refused:
                    client.request('/api/notes', {})
                self.assertEqual(refused.exception.status, 409)
                client.request('/api/shutdown', {})
                process.wait(timeout=10)
                self.assertEqual(process.returncode, 0)
                self.assertFalse(ready.exists())
                self.assertFalse((data / 'agent-session.json').exists())
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
