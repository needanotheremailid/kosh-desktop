"""Automatic backup tests use isolated, invented workspaces only."""
import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import AppError, Store
from auto_backup import AutoBackup


class AutomaticBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'data')
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Invented widgets'})['id']
        self.folder = self.root / 'backups'
        self.folder.mkdir()
        self.clock = 1000.0
        self.backups = AutoBackup(self.store, clock=lambda: self.clock)

    def tearDown(self):
        self.backups.stop()
        self.store.close()
        self.temp.cleanup()

    def enable(self):
        return self.backups.configure({'enabled': True, 'destination': str(self.folder), 'interval_minutes': 60})

    def test_disabled_by_default_and_catchup_once_with_history(self):
        self.assertFalse(self.backups.status()['enabled'])
        self.assertIsNone(self.backups.tick())
        note = self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'title': 'Draft', 'body': 'First'})
        self.store.dispatch('POST', '/api/notes', {'workspace_id': self.workspace, 'id': note['id'], 'version': note['version'], 'title': 'Draft', 'body': 'Second'})
        self.enable()
        result = self.backups.tick()
        self.assertTrue(result['ok'])
        self.assertEqual(self.backups.status()['last_success'], 1000.0)
        self.assertIsNone(self.backups.tick())
        sets = self.backups.list_sets()['sets']
        self.assertEqual(len(sets), 1)
        self.assertEqual(len(sets[0]['workspaces']), 1)
        archive = self.folder / sets[0]['set_id'] / sets[0]['workspaces'][0]['file']
        import zipfile
        with zipfile.ZipFile(archive) as zipped:
            manifest = json.loads(zipped.read('manifest.json'))
        self.assertTrue(manifest['history_included'])
        self.assertEqual(len(manifest['revisions']), 1)
        self.assertEqual(json.loads(manifest['revisions'][0]['payload'])['body'], 'First')
        self.assertEqual(manifest['notes'][0]['body'], 'Second')
        self.clock += 3600
        self.assertTrue(self.backups.tick()['ok'])
        self.assertEqual(len(self.backups.list_sets()['sets']), 2)

    def test_failed_export_preserves_previous_success_and_retry(self):
        self.enable()
        self.assertTrue(self.backups.tick()['ok'])
        self.clock += 3600
        with patch.object(self.store, 'file_response', side_effect=AppError('Invented source is missing.')):
            failed = self.backups.tick()
        self.assertFalse(failed['ok'])
        self.assertEqual(self.backups.status()['last_success'], 1000.0)
        self.assertEqual(self.backups.status()['last_failure'], 4600.0)
        self.assertIsNone(self.backups.tick())
        self.clock += 3600
        self.assertTrue(self.backups.tick()['ok'])
        self.assertEqual(len(self.backups.list_sets()['sets']), 2)

    def test_destination_rejects_data_runtime_relative_and_links(self):
        for destination in (str(self.store.root), str(Path(__file__).resolve().parents[1]), '.', '//server/share'):
            with self.subTest(destination=destination), self.assertRaises(AppError):
                self.backups.configure({'enabled': True, 'destination': destination, 'interval_minutes': 60})
        self.assertFalse(self.backups.status()['enabled'])

    def test_all_workspaces_no_partial_set_on_second_export_failure(self):
        self.store.dispatch('POST', '/api/workspaces', {'title': 'Second invented workspace'})
        self.enable()
        original = self.store.file_response
        calls = []
        def export(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise AppError('Second export refused.')
            return original(*args, **kwargs)
        with patch.object(self.store, 'file_response', side_effect=export):
            self.assertFalse(self.backups.tick()['ok'])
        self.assertIsNone(self.backups.status()['last_success'])
        self.assertEqual(self.backups.list_sets()['sets'], [])
        self.assertTrue(self.backups.run_now()['ok'])
        self.assertEqual(len(self.backups.list_sets()['sets'][0]['workspaces']), 2)

    def test_corruption_not_previewed_and_restore_requires_fresh_preview(self):
        self.enable()
        self.backups.run_now()
        saved = self.backups.list_sets()['sets'][0]
        entry = saved['workspaces'][0]
        before = self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0]
        preview = self.backups.preview_restore({'set_id': saved['set_id'], 'workspace_id': entry['workspace_id']})
        self.assertEqual(preview['title'], 'Invented widgets')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], before)
        with self.assertRaises(AppError):
            self.backups.restore({'preview_id': preview['preview_id'], 'approve': False})
        archive = self.folder / saved['set_id'] / entry['file']
        archive.write_bytes(b'corrupt')
        with self.assertRaises(AppError):
            self.backups.restore({'preview_id': preview['preview_id'], 'approve': True})
        with self.assertRaises(AppError):
            self.backups.preview_restore({'set_id': saved['set_id'], 'workspace_id': entry['workspace_id']})
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM workspaces').fetchone()[0], before)

    def test_valid_restore_is_separate_and_settings_persist(self):
        self.enable()
        self.backups.run_now()
        saved = self.backups.list_sets()['sets'][0]
        preview = self.backups.preview_restore({'set_id': saved['set_id'], 'workspace_id': self.workspace})
        result = self.backups.restore({'preview_id': preview['preview_id'], 'approve': True})
        self.assertNotEqual(result['workspace_id'], self.workspace)
        self.assertEqual(self.store._workspace(self.workspace)['title'], 'Invented widgets')
        with self.assertRaises(AppError):
            self.backups.restore({'preview_id': preview['preview_id'], 'approve': True})
        reloaded = AutoBackup(self.store, clock=lambda: self.clock)
        self.assertTrue(reloaded.status()['enabled'])
        self.assertEqual(reloaded.status()['last_success'], 1000.0)
        self.assertIsNone(reloaded.tick())

    def test_concurrent_guard_and_stop_waits_for_worker(self):
        self.enable()
        entered, release = threading.Event(), threading.Event()
        original = self.store.file_response
        def export(*args, **kwargs):
            entered.set()
            release.wait(5)
            return original(*args, **kwargs)
        with patch.object(self.store, 'file_response', side_effect=export):
            self.backups.start()
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.backups.run_now()['status'], 'busy')
            release.set()
            self.backups.stop()
        self.assertFalse(self.backups.status()['running'])
        self.assertEqual(len(self.backups.list_sets()['sets']), 1)

    def test_no_clobber_of_completed_set(self):
        self.enable()
        with patch('auto_backup.new_id', return_value='a' * 32):
            self.assertTrue(self.backups.run_now()['ok'])
            saved = {path.name: path.read_bytes() for path in (self.folder / ('kosh-backup-' + 'a' * 32)).iterdir()}
            self.assertFalse(self.backups.run_now()['ok'])
            self.assertEqual(saved, {path.name: path.read_bytes() for path in (self.folder / ('kosh-backup-' + 'a' * 32)).iterdir()})

    def test_clock_rollback_catches_up_once_and_closed_intervals_do_not_burst(self):
        self.enable()
        self.backups.run_now()
        self.clock -= 300
        self.assertIn('future', self.backups.status()['clock_warning'])
        self.assertTrue(self.backups.tick()['ok'])
        self.assertIsNone(self.backups.tick())

        self.clock += 3600 * 3
        reloaded = AutoBackup(self.store, clock=lambda: self.clock)
        self.assertTrue(reloaded.tick()['ok'])
        self.assertIsNone(reloaded.tick())
        self.assertEqual(len(reloaded.list_sets()['sets']), 3)

    def test_failed_partial_sets_use_interval_backoff_and_future_clock_does_not_bypass_it(self):
        self.store.dispatch('POST', '/api/workspaces', {'title': 'Second invented workspace'})
        self.enable()
        self.backups.run_now()
        self.clock -= 300
        original = self.store.file_response
        calls = []
        def export(*args, **kwargs):
            calls.append(1)
            if len(calls) % 2 == 0:
                raise AppError('Second export remains unavailable.')
            return original(*args, **kwargs)
        with patch.object(self.store, 'file_response', side_effect=export):
            self.assertFalse(self.backups.tick()['ok'])
            for _ in range(20):
                self.clock += 60
                self.assertIsNone(self.backups.tick())
        self.assertEqual(len(list(self.folder.glob('*.incomplete'))), 1)
        self.assertEqual(len(calls), 2)
        self.assertTrue(self.backups.status()['last_error'])
        self.assertTrue(self.backups.run_now()['ok'])
        self.clock += 3600
        self.assertTrue(self.backups.tick()['ok'])

    def test_enabled_empty_install_does_not_create_incomplete_folders(self):
        self.store.close()
        self.store = Store(self.root / 'empty-data')
        self.backups = AutoBackup(self.store, clock=lambda: self.clock)
        self.enable()
        for _ in range(10):
            self.backups.tick()
            self.clock += 60
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_scheduler_survives_status_persistence_failure_and_retries(self):
        import sqlite3
        self.enable()
        failed = threading.Event()
        def persist():
            failed.set()
            raise sqlite3.OperationalError('Synthetic database unavailable')
        with patch.object(self.backups, '_persist', side_effect=persist):
            self.backups.start()
            self.assertTrue(failed.wait(5))
            deadline = time.monotonic() + 5
            while self.backups.status()['running'] and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(self.backups._thread.is_alive())
            self.assertTrue(self.backups.status()['last_error'])
            self.assertIsNone(self.backups.status()['last_success'])
        self.clock += 3600
        self.backups._wake.set()
        deadline = time.monotonic() + 5
        while self.backups.status()['last_success'] is None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.backups.status()['last_success'], 4600.0)
        self.backups.stop()

    def test_pdf_restore_validation_is_serialized_with_page_rendering(self):
        import backend
        pdf = backend.pdf_lib.open()
        pdf.new_page().insert_text((40, 40), 'Invented PDF widgets')
        imported = self.store.dispatch('POST', '/api/import', {'workspace_id': self.workspace, 'files': [{'name': 'synthetic.pdf', 'data': base64.b64encode(pdf.tobytes()).decode('ascii')}]})
        document = imported['results'][0]['document']['id']
        pdf.close()
        self.enable()
        original = backend.pdf_lib.open
        guard = threading.Lock()
        concurrent, maximum = [0], [0]
        def opened(*args, **kwargs):
            with guard:
                concurrent[0] += 1
                maximum[0] = max(maximum[0], concurrent[0])
            try:
                time.sleep(0.02)
                return original(*args, **kwargs)
            finally:
                with guard:
                    concurrent[0] -= 1
        result = []
        with patch.object(backend.pdf_lib, 'open', side_effect=opened):
            worker = threading.Thread(target=lambda: result.append(self.backups.run_now()))
            worker.start()
            for _ in range(10):
                self.store.file_response('/api/page', {'id': document, 'page': '1'})
            worker.join(5)
            saved = self.backups.list_sets()['sets'][0]
            preview_worker = threading.Thread(target=lambda: result.append(self.backups.preview_restore({'set_id': saved['set_id'], 'workspace_id': self.workspace})))
            preview_worker.start()
            for _ in range(10):
                self.store.file_response('/api/page', {'id': document, 'page': '1'})
            preview_worker.join(5)
        self.assertEqual(maximum[0], 1)
        self.assertTrue(result[0]['ok'])
        self.assertTrue(result[1]['preview_id'])

    def test_full_disk_preserves_completed_sets_and_records_error(self):
        self.enable()
        self.backups.run_now()
        self.clock += 3600
        import shutil
        with patch('auto_backup.shutil.disk_usage', return_value=shutil._ntuple_diskusage(100, 100, 0)):
            result = self.backups.tick()
        self.assertFalse(result['ok'])
        self.assertIn('free space', result['error'])
        self.assertEqual(self.backups.status()['last_success'], 1000.0)
        self.assertEqual(len(self.backups.list_sets()['sets']), 1)

    def test_malformed_export_and_manifest_rejected_before_success(self):
        self.enable()
        with patch.object(self.store, 'file_response', return_value=(b'invalid zip', 'application/zip', 'backup.zip')):
            self.assertFalse(self.backups.run_now()['ok'])
        self.assertIsNone(self.backups.status()['last_success'])
        self.assertTrue(self.backups.run_now()['ok'])
        saved = self.backups.list_sets()['sets'][0]
        manifest = self.folder / saved['set_id'] / 'manifest.json'
        content = json.loads(manifest.read_text(encoding='utf-8'))
        content['workspaces'][0]['file'] = '../escape.zip'
        manifest.write_text(json.dumps(content), encoding='utf-8')
        listing = self.backups.list_sets()
        self.assertEqual(listing['sets'], [])
        self.assertEqual(len(listing['issues']), 1)
        with self.assertRaises(AppError):
            self.backups.preview_restore({'set_id': saved['set_id'], 'workspace_id': self.workspace})

    def test_success_status_write_failure_does_not_advance_success(self):
        self.enable()
        self.backups.run_now()
        self.clock += 3600
        original = self.backups._persist
        calls = []
        def persist():
            calls.append(1)
            if len(calls) == 2:
                raise OSError('Synthetic status-write failure')
            return original()
        with patch.object(self.backups, '_persist', side_effect=persist):
            self.assertFalse(self.backups.run_now()['ok'])
        self.assertEqual(self.backups.status()['last_success'], 1000.0)
        self.assertEqual(self.backups.status()['last_failure'], 4600.0)

    def test_stop_waits_for_manual_backup_and_refuses_new_runs(self):
        self.enable()
        entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
        original = self.store.file_response
        def export(*args, **kwargs):
            entered.set()
            release.wait(5)
            return original(*args, **kwargs)
        def stop():
            self.backups.stop()
            stopped.set()
        with patch.object(self.store, 'file_response', side_effect=export):
            worker = threading.Thread(target=self.backups.run_now)
            worker.start()
            self.assertTrue(entered.wait(5))
            shutdown = threading.Thread(target=stop)
            shutdown.start()
            self.assertFalse(stopped.wait(0.05))
            release.set()
            worker.join(5)
            shutdown.join(5)
        self.assertTrue(stopped.is_set())
        with self.assertRaises(AppError):
            self.backups.run_now()

    def test_unavailable_destination_can_be_disabled_without_touching_files(self):
        self.enable()
        self.folder.rename(self.root / 'unplugged')
        result = self.backups.configure({'enabled': False, 'destination': str(self.folder), 'interval_minutes': 60})
        self.assertFalse(result['enabled'])
        self.assertIsNone(self.backups.tick())

    def test_pending_work_notice_survives_refresh_and_successful_backup(self):
        root = Path(__file__).resolve().parents[1]
        bundled = root / 'tools' / 'node' / 'node.exe'
        node = str(bundled) if bundled.is_file() else shutil.which('node')
        if not node:
            self.skipTest('Node runtime is required for UI logic checks')
        script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map();
class Element {
  constructor(tag){this.tag=tag;this.events={};this.children=[];this.open=false;this.checked=false;this.hidden=false;this.value='';this.textContent='';}
  set innerHTML(value){for(const match of value.matchAll(/id="([^"]+)"/g)){const node=new Element('field');node.id=match[1];nodes.set(node.id,node);}nodes.set('close',new Element('button'));}
  setAttribute(){}
  querySelector(selector){return nodes.get(selector === '[data-auto-close]' ? 'close' : selector.slice(1));}
  querySelectorAll(){return [];}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  addEventListener(name,callback){this.events[name]=callback;}
  showModal(){this.open=true;}
  close(){this.open=false;this.events.close?.();}
}
let poll, dialog;
const document={createElement:tag=>{const result=new Element(tag);if(tag==='dialog')dialog=result;return result;},querySelector:()=>null,body:{append(){}}};
const context={window:{},document,Date,setInterval:callback=>{poll=callback;return 1;},clearInterval(){},setTimeout,Number,String,Error};
vm.createContext(context);
vm.runInContext(fs.readFileSync('ui/auto_backup.js','utf8'),context);
let counts={conflicts:1,evidence:1,reviewer:2}, completed=false, runCount=0;
const status=()=>({enabled:true,scheduler_alive:true,running:false,destination:'Chosen local folder',interval_minutes:60,last_success:completed?1000:null,last_failure:null,last_set_path:'',last_error:'',clock_warning:'',notice:'Saved records only.',next_due:0});
context.window.KoshAutoBackup.mount({pendingSummary:()=>counts,flushEdits:async()=>true,onRestored:async()=>{},request:async(path,body)=>{
  if(path==='/auto-backup')return status();
  if(path==='/auto-backup/sets')return {sets:[],issues:[]};
  if(path==='/auto-backup/run'){runCount++;completed=true;return {ok:true};}
  throw new Error('Unexpected request: '+path);
}});
(async()=>{
  await context.window.KoshAutoBackup.open();
  assert.ok(nodes.has('auto-backup-pending'),'Dialog must disclose unsaved exclusions.');
  const notice=nodes.get('auto-backup-pending');
  assert.equal(notice.hidden,false);
  assert.match(notice.textContent,/1 conflicted draft/);
  assert.match(notice.textContent,/1 evidence row awaiting/);
  assert.match(notice.textContent,/2 unsaved reviewer comments/);
  const text=notice.textContent;
  poll();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(notice.textContent,text,'Status polling must retain the exclusion notice.');
  await nodes.get('auto-backup-run').events.click();
  assert.equal(runCount,1,'Pending exclusions must not block saved-record backup.');
  assert.equal(notice.textContent,text,'Successful saved backup must retain unsaved exclusions.');
  counts={conflicts:0,evidence:0,reviewer:0};
  await nodes.get('auto-backup-refresh-sets').events.click();
  assert.equal(notice.hidden,true);
  assert.equal(notice.textContent,'');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run([node, '-e', script], cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
