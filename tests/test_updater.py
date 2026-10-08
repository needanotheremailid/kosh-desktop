"""Explicit fixed-source updates with invented releases and temporary installations."""
import copy
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

import updater
import updater_worker
from tests.test_upgrade import installed, synthetic_data


PACKAGE = b'MZ invented installer bytes'


def release(version='0.5.0'):
    prefix = 'https://github.com/needanotheremailid/kosh-desktop/releases/'
    name = 'Kosh-' + version + '-Setup.exe'
    return {'id': 42, 'draft': False, 'prerelease': True, 'tag_name': 'v' + version,
            'html_url': prefix + 'tag/v' + version,
            'assets': [{'name': name, 'size': len(PACKAGE), 'state': 'uploaded',
                        'browser_download_url': prefix + 'download/v' + version + '/' + name,
                        'digest': 'sha256:' + hashlib.sha256(PACKAGE).hexdigest()},
                       {'name': 'SHA256SUMS.txt', 'size': 90, 'state': 'uploaded',
                        'browser_download_url': prefix + 'download/v' + version + '/SHA256SUMS.txt'}]}


class Transport:
    def __init__(self):
        self.urls = []
        self.broken = False

    def open(self, url):
        self.urls.append(url)
        if url == updater.RELEASES_URL:
            return io.BytesIO(json.dumps([release()]).encode())
        if url.endswith('/SHA256SUMS.txt'):
            return io.BytesIO((hashlib.sha256(PACKAGE).hexdigest() + '  Kosh-0.5.0-Setup.exe\n').encode())
        if self.broken:
            class Broken(io.BytesIO):
                def read(self, *_):
                    raise OSError('interrupted download')
            return Broken(PACKAGE)
        return io.BytesIO(PACKAGE)


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old = self.root / 'Kosh-old'
        installed(self.old, 'a' * 64)
        synthetic_data(self.old)
        self.transport = Transport()
        self.manager = updater.Updater(self.old, cache_dir=self.root / 'cache', transport=self.transport, current_version='0.4.0')

    def tearDown(self):
        self.temp.cleanup()

    def test_no_check_or_download_without_explicit_consent(self):
        self.assertEqual(self.manager.status()['phase'], 'idle')
        with self.assertRaises(updater.UpdateError):
            self.manager.check()
        self.assertEqual(self.transport.urls, [])
        self.assertFalse((self.root / 'cache').exists())

    def test_check_only_fetches_fixed_release_metadata(self):
        result = self.manager.check(consent=True)
        self.assertEqual(result['phase'], 'available')
        self.assertEqual(result['candidate']['version'], '0.5.0')
        self.assertTrue(result['candidate']['prerelease'])
        self.assertEqual(result['signature'], 'not_verified')
        self.assertEqual(self.transport.urls, [updater.RELEASES_URL])

    def test_rejects_release_repository_or_url_change(self):
        for key, value in [('html_url', 'https://github.com/other/kosh/releases/tag/v0.5.0'),
                           ('tag_name', 'v0.5.0/../shell'), ('draft', True)]:
            item = release(); item[key] = value
            with self.subTest(key=key), self.assertRaises(updater.UpdateError):
                updater.parse_release(item)
        for url in ('https://evil.example/installer.exe', 'https://github.com/other/kosh/releases/download/v0.5.0/Kosh-0.5.0-Setup.exe'):
            item = release(); item['assets'][0]['browser_download_url'] = url
            with self.assertRaises(updater.UpdateError): updater.parse_release(item)

    def test_rejects_duplicate_and_oversized_assets(self):
        item = release(); item['assets'].append(copy.deepcopy(item['assets'][0]))
        with self.assertRaises(updater.UpdateError): updater.parse_release(item)
        item = release(); item['assets'][0]['size'] = updater.MAX_INSTALLER + 1
        with self.assertRaises(updater.UpdateError): updater.parse_release(item)

    def test_checksums_exact_filename_and_no_duplicates(self):
        value = hashlib.sha256(PACKAGE).hexdigest()
        self.assertEqual(updater.parse_checksum((value+'  Kosh-0.5.0-Setup.exe\n').encode(), 'Kosh-0.5.0-Setup.exe'), value)
        for text in (value+'  ../Kosh-0.5.0-Setup.exe\n', value+'  Kosh-0.5.0-Setup.exe\n'+value+'  Kosh-0.5.0-Setup.exe\n', 'garbage'):
            with self.assertRaises(updater.UpdateError): updater.parse_checksum(text.encode(), 'Kosh-0.5.0-Setup.exe')

    def test_versions_compared_numerically(self):
        self.assertGreater(updater.version_tuple('0.10.0'), updater.version_tuple('0.9.9'))
        for version in ('0.1', '01.2.3', '0.4.0-beta', '0.4.0;calc'):
            with self.assertRaises(updater.UpdateError): updater.version_tuple(version)

    def test_verified_download_does_not_install_or_touch_old_data(self):
        before = updater_worker.upgrade._inventory(self.old / 'data')
        self.manager.check(consent=True)
        with self.assertRaises(updater.UpdateError): self.manager.download()
        result = self.manager.download(consent=True)
        self.assertEqual(result['phase'], 'downloaded')
        self.assertEqual(updater_worker.upgrade._inventory(self.old / 'data'), before)
        path = self.root / 'cache' / result['job_id'] / 'Kosh-0.5.0-Setup.exe'
        self.assertEqual(path.read_bytes(), PACKAGE)
        self.assertEqual(result['sha256'], hashlib.sha256(PACKAGE).hexdigest())
        self.assertFalse(list(self.root.glob('Kosh-0.5.0-*')))

    def test_interrupted_download_is_retained_without_executable_promotion(self):
        self.manager.check(consent=True); self.transport.broken = True
        with self.assertRaises(updater.UpdateError): self.manager.download(consent=True)
        result = self.manager.status()
        self.assertEqual(result['phase'], 'download_failed')
        self.assertFalse(list((self.root / 'cache').rglob('*.exe')))
        self.assertTrue(list((self.root / 'cache').rglob('*.part')))

    def test_checksum_mismatch_refuses_promotion(self):
        self.manager.check(consent=True)
        candidate = self.manager.candidate
        self.manager.candidate = updater.Candidate(candidate.version, candidate.prerelease, candidate.size, 'f'*64)
        with self.assertRaises(updater.UpdateError): self.manager.download(consent=True)
        self.assertFalse(list((self.root / 'cache').rglob('*.exe')))

    def test_install_requires_download_and_explicit_unsigned_approval(self):
        self.manager.check(consent=True)
        with self.assertRaises(updater.UpdateError): self.manager.install(approve=True, accept_unsigned=True)
        self.manager.download(consent=True)
        with self.assertRaises(updater.UpdateError): self.manager.install(approve=True)

    def test_redirect_policy_rejects_non_release_assets(self):
        handler = updater.ReleaseRedirects()
        from urllib.request import Request
        request = Request(updater.Candidate('0.5.0', True, 1, None).installer_url)
        for url in ('http://release-assets.githubusercontent.com/github-production-release-asset/1/abc',
                    'https://evil.example/anything', 'https://github.com/other/file'):
            with self.assertRaises(updater.UpdateError): handler.redirect_request(request, None, 302, 'Found', {}, url)

    def test_same_and_older_releases_never_become_candidates(self):
        for version in ('0.4.0','0.3.9'):
            with patch.object(self.transport,'open',return_value=io.BytesIO(json.dumps([release(version)]).encode())):
                self.assertEqual(self.manager.check(consent=True)['phase'],'up_to_date')

    def test_invalid_release_list_is_failure_not_false_up_to_date(self):
        with patch.object(self.transport,'open',return_value=io.BytesIO(b'[null]')):
            with self.assertRaises(updater.UpdateError): self.manager.check(consent=True)
        self.assertEqual(self.manager.status()['phase'],'check_failed')

    def test_old_and_nonnumeric_releases_do_not_block_newest_eligible(self):
        old=release('0.3.0');old['assets']=[]
        beta=release('0.6.0');beta['tag_name']='v0.6.0-beta'
        with patch.object(self.transport,'open',return_value=io.BytesIO(json.dumps([release(),old,beta]).encode())):
            self.assertEqual(self.manager.check(consent=True)['candidate']['version'],'0.5.0')
        newest=release('0.6.0');newest['assets']=[]
        with patch.object(self.transport,'open',return_value=io.BytesIO(json.dumps([release(),newest]).encode())):
            with self.assertRaises(updater.UpdateError):self.manager.check(consent=True)

    def test_unsigned_qualifier_is_visible_and_never_omitted(self):
        source=(Path(updater.__file__).parent/'ui/updater.js').read_text(encoding='utf-8')
        self.assertIn('This does not verify the publisher; installers are unsigned.',source)

    def test_status_previous_receipt_is_read_only_and_warns_about_divergence(self):
        previous=self.root/'Kosh-previous';installed(previous,'b'*64);synthetic_data(previous)
        receipt={'app':'Kosh','action':'offline-copy-only-upgrade','new_install':str(self.old),'old_install':str(previous),'old_build':'b'*64}
        (self.old/'UPGRADE_RECEIPT.json').write_text(json.dumps(receipt))
        before=updater_worker.upgrade._inventory(previous/'data')
        value=self.manager.status()['previous_installation']
        self.assertEqual(value['data_path'],str(previous/'data'))
        self.assertIn('not copied back',value['warning'])
        self.assertEqual(updater_worker.upgrade._inventory(previous/'data'),before)

    def test_ui_mount_and_explicit_approvals_with_actual_javascript(self):
        import shutil,subprocess
        node=shutil.which('node')
        if not node:self.skipTest('Installed Node unavailable for isolated UI helper check.')
        script="""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let calls=[];const root={innerHTML:'',querySelectorAll(){return [];},querySelector(){return null;}};
const context={console};vm.createContext(context);
vm.runInContext(fs.readFileSync('ui/updater.js','utf8')+';globalThis.updates=KoshUpdater;',context);
(async()=>{await context.updates.mount(root,{request:async route=>{calls.push(route);return {phase:'available',current_version:'0.4.0',install_supported:true,candidate:{version:'0.5.0',size:10,prerelease:true,release_url:'https://github.com/needanotheremailid/kosh-desktop/releases/tag/v0.5.0'}};}});
assert.deepStrictEqual(calls,['/updates/status']);assert(root.innerHTML.includes('Check for updates'));assert(root.innerHTML.includes('Download installer and checksum'));assert(root.innerHTML.includes('installers are unsigned.'));assert(!root.innerHTML.includes('data-update-action="install"'));console.log('UI initial/status controls passed');})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        result=subprocess.run([node,'-e',script],cwd=Path(updater.__file__).parent,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_ui_unsigned_approval_is_bound_to_transfer_and_keeps_focus(self):
        import shutil,subprocess
        node=shutil.which('node')
        if not node:self.skipTest('Installed Node unavailable for isolated UI helper check.')
        script="""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let calls=[],renders=0,document={activeElement:null};
const root={ownerDocument:document,html:'',buttons:{},checkbox:null,live:null,
 set innerHTML(value){this.html=value;renders++;this.buttons={};for(const match of value.matchAll(/<button[^>]*data-update-action="([^"]+)"[^>]*>/g)){const action=match[1];this.buttons[action]={dataset:{updateAction:action},disabled:match[0].includes('disabled'),events:{},addEventListener(name,cb){this.events[name]=cb;},hasAttribute(){return false;},focus(){document.activeElement=this;}};}this.checkbox=value.includes('data-update-unsigned')?{checked:false,events:{},dataset:{},addEventListener(name,cb){this.events[name]=cb;},hasAttribute(name){return name==='data-update-unsigned';},focus(){document.activeElement=this;}}:null;this.live={textContent:'',replaceWith(node){root.live=node;}};},
 get innerHTML(){return this.html;},querySelectorAll(){return Object.values(this.buttons);},querySelector(selector){if(selector==='.update-status')return this.live;if(selector==='[data-update-unsigned]')return this.checkbox;const match=selector.match(/data-update-action="([^"]+)"/);return match?this.buttons[match[1]]||null:null;},contains(node){return node===this.checkbox||Object.values(this.buttons).includes(node);}};
const candidate={version:'0.5.0',size:10,prerelease:true,release_url:'https://github.com/needanotheremailid/kosh-desktop/releases/tag/v0.5.0'};
const oldTransfer={phase:'downloaded',current_version:'0.4.0',install_supported:true,candidate,version:'0.5.0',job_id:'a'.repeat(32),sha256:'b'.repeat(64)};
const newTransfer={...oldTransfer,job_id:'c'.repeat(32),sha256:'d'.repeat(64)};
const context={console};vm.createContext(context);vm.runInContext(fs.readFileSync('ui/updater.js','utf8')+';globalThis.updates=KoshUpdater;',context);
(async()=>{
 await context.updates.mount(root,{request:async(route,body)=>{calls.push(route);if(route==='/updates/status')return oldTransfer;if(route==='/updates/check')return {phase:'available',current_version:'0.4.0',install_supported:true,candidate};if(route==='/updates/download')return newTransfer;throw Error('Unexpected install request');},beforeInstall:async()=>true});
 const checkbox=root.checkbox;checkbox.checked=true;document.activeElement=checkbox;const before=renders;const live=root.live;checkbox.events.change();assert.strictEqual(renders,before);assert.strictEqual(document.activeElement,checkbox);assert.strictEqual(root.live,live);assert.strictEqual(root.buttons.install.disabled,false);
 await root.buttons.check.events.click();assert(!root.innerHTML.includes(context.updates.qualifier));assert(root.innerHTML.includes(context.updates.pendingQualifier));
 await root.buttons.download.events.click();assert.strictEqual(root.checkbox.checked,false);assert.strictEqual(root.buttons.install.disabled,true);assert.strictEqual(root.live,live);
 checkbox.checked=true;checkbox.events.change();await root.buttons.install.events.click();assert(!calls.includes('/updates/install'));assert(root.live.textContent.includes('this checked installer'));console.log('Transfer approval/focus/live status passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        result=subprocess.run([node,'-e',script],cwd=Path(updater.__file__).parent,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)


class WorkerTests(UpdaterTests):
    def prepared(self):
        self.manager.check(consent=True); result = self.manager.download(consent=True)
        directory = self.root / 'cache' / result['job_id']
        return self.manager.prepare_install(approve=True, accept_unsigned=True), directory

    def create_candidate(self, request):
        new = Path(request['new_install'])
        installed(new, 'b'*64)
        identity = "CURRENT_VERSION = '0.5.0'\nREPOSITORY = 'needanotheremailid/kosh-desktop'\n"
        (new / 'updater.py').write_bytes(identity.encode())
        manifest_path = new / 'package-manifest.json'
        manifest = json.loads(manifest_path.read_text()); manifest['files'].append({'path':'updater.py','size':len(identity.encode()),'sha256':hashlib.sha256(identity.encode()).hexdigest()})
        manifest_path.write_text(json.dumps(manifest))
        receipt_path = new / 'INSTALL_RECEIPT.json'; receipt = json.loads(receipt_path.read_text()); receipt['files_verified'] += 1; receipt['payload_bytes'] += len(identity.encode()); receipt_path.write_text(json.dumps(receipt))
        return new

    def test_worker_copies_and_verifies_before_shortcuts(self):
        request, directory = self.prepared(); before = updater_worker.upgrade._inventory(self.old / 'data'); events=[]
        def install(candidate, target): self.create_candidate(request); events.append('install')
        def retarget(old,new,stage): self.assertTrue((new/'data/research.sqlite3').exists());events.append('links');return {'status':'complete'}
        def launch(new,build): events.append('launch');return {'app':'pg-research-desktop','build':build,'ready':True}
        with patch('upgrade._stopped'), patch('upgrade._retarget_shortcuts',side_effect=retarget), patch.object(updater_worker,'run_installer',side_effect=install), patch.object(updater_worker,'launch_and_verify',side_effect=launch),patch.object(updater_worker,'open_candidate'),patch.object(updater_worker,'activate_candidate'):
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'installed_verified');self.assertEqual(events,['install','launch','links'])
        self.assertEqual(updater_worker.upgrade._inventory(self.old/'data'), before)

    def test_failed_startup_preserves_shortcuts_and_both_data(self):
        request,directory=self.prepared();before=updater_worker.upgrade._inventory(self.old/'data')
        def install(candidate,target): self.create_candidate(request)
        with patch('upgrade._stopped'), patch('upgrade._retarget_shortcuts',return_value={'status':'complete'}), patch.object(updater_worker,'run_installer',side_effect=install), patch.object(updater_worker,'launch_and_verify',side_effect=updater.UpdateError('startup failed')), patch.object(updater_worker,'restore_shortcuts',return_value={'status':'restored_verified'}) as restore:
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'failed');restore.assert_not_called()
        self.assertTrue((Path(request['new_install'])/'data/research.sqlite3').exists())
        self.assertEqual(updater_worker.upgrade._inventory(self.old/'data'), before)

    def test_failed_shortcut_retarget_restores_old_links_before_user_window(self):
        request,directory=self.prepared()
        with patch('upgrade._stopped'),patch.object(updater_worker,'run_installer',side_effect=lambda *_: self.create_candidate(request)),patch.object(updater_worker,'launch_and_verify',return_value={'app':'pg-research-desktop','ready':True,'build':'b'*64}),patch('upgrade._retarget_shortcuts',side_effect=updater.UpdateError('partial links')),patch.object(updater_worker,'restore_shortcuts',return_value={'status':'restored_verified'}) as restore,patch.object(updater_worker,'open_candidate') as window:
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'rolled_back');restore.assert_called_once();window.assert_not_called()

    def test_candidate_user_write_refuses_automatic_rollback(self):
        request,directory=self.prepared()
        def retarget(*_):
            import sqlite3
            with closing(sqlite3.connect(Path(request['new_install'])/'data/research.sqlite3')) as db:
                db.execute("INSERT INTO notes VALUES('newer', 'user work')");db.commit()
            raise updater.UpdateError('partial links')
        with patch('upgrade._stopped'),patch.object(updater_worker,'run_installer',side_effect=lambda *_: self.create_candidate(request)),patch.object(updater_worker,'launch_and_verify',return_value={'app':'pg-research-desktop','ready':True,'build':'b'*64}),patch('upgrade._retarget_shortcuts',side_effect=retarget),patch.object(updater_worker,'restore_shortcuts') as restore:
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'rollback_failed');restore.assert_not_called()

    def test_completed_update_never_automatically_repeats_or_rolls_back(self):
        request,directory=self.prepared();updater.write_receipt(directory,{'phase':'installed_verified','job_id':directory.name})
        with patch.object(updater_worker,'run_installer') as install,patch.object(updater_worker,'restore_shortcuts') as restore:
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'installed_verified');install.assert_not_called();restore.assert_not_called()

    def test_completed_receipt_is_unchanged_when_installer_is_gone(self):
        request,directory=self.prepared();receipt=updater.write_receipt(directory,{'phase':'installed_verified','job_id':directory.name})
        (directory/'Kosh-0.5.0-Setup.exe').unlink()
        self.assertEqual(updater_worker.run_job(directory),receipt)

    def test_second_manager_cannot_prepare_concurrent_install(self):
        request,directory=self.prepared()
        second=updater.Updater(self.old,cache_dir=self.root/'cache',transport=self.transport,current_version='0.4.0')
        with self.assertRaises(updater.UpdateError):second.check(consent=True)
        second.candidate=self.manager.candidate;second.job_dir=self.manager.job_dir;second.phase='downloaded'
        with self.assertRaises(updater.UpdateError):second.prepare_install(approve=True,accept_unsigned=True)

    def test_live_worker_marker_preserves_nonterminal_receipt(self):
        import os
        request,directory=self.prepared();receipt=updater.write_receipt(directory,{'phase':'retargeting','job_id':directory.name})
        (directory/'worker.json').write_text(json.dumps({'pid':os.getpid()}))
        with patch.object(updater_worker,'restore_shortcuts') as restore:
            self.assertEqual(updater_worker.run_job(directory),receipt)
        restore.assert_not_called()

    def test_interrupted_retarget_recovers_without_installer(self):
        request,directory=self.prepared();new=self.create_candidate(request)
        with patch('upgrade._stopped'):updater_worker.upgrade.upgrade(self.old,new,apply=True)
        updater.write_receipt(directory,{'phase':'retargeting','job_id':directory.name});(directory/'Kosh-0.5.0-Setup.exe').unlink()
        with patch.object(updater_worker,'stop_verification_candidate'),patch.object(updater_worker,'restore_shortcuts',return_value={'status':'restored_verified'}):
            self.assertEqual(updater_worker.run_job(directory)['phase'],'rolled_back')

    def test_close_timeout_resume_uses_retained_installer_without_network(self):
        request,directory=self.prepared()
        with patch.object(updater_worker,'wait_stopped',side_effect=updater_worker.CloseTimeout('close window')):
            self.assertEqual(updater_worker.run_job(directory)['phase'],'close_timeout')
        second=updater.Updater(self.old,cache_dir=self.root/'cache',transport=self.transport,current_version='0.4.0')
        before=list(self.transport.urls)
        (directory/'worker.json').write_text(json.dumps({'pid':2147483647}))
        with patch.object(second,'_spawn_worker') as spawn:
            result=second.resume(approve=True,accept_unsigned=True)
        self.assertEqual(result['phase'],'awaiting_close');spawn.assert_called_once();self.assertEqual(self.transport.urls,before)

    def test_changed_old_data_after_copy_refuses_shortcuts_and_completion(self):
        request,directory=self.prepared()
        def launch(*_):
            (self.old/'data/originals/source.txt').write_bytes(b'user changed original')
            return {'app':'pg-research-desktop','ready':True,'build':'b'*64}
        with patch('upgrade._stopped'),patch.object(updater_worker,'run_installer',side_effect=lambda *_:self.create_candidate(request)),patch.object(updater_worker,'launch_and_verify',side_effect=launch),patch('upgrade._retarget_shortcuts') as links,patch.object(updater_worker,'open_candidate') as window:
            self.assertEqual(updater_worker.run_job(directory)['phase'],'failed')
        links.assert_not_called();window.assert_not_called()

    def test_shortcut_pointing_other_install_refuses_candidate_window(self):
        request,directory=self.prepared()
        with patch('upgrade._stopped'),patch.object(updater_worker,'run_installer',side_effect=lambda *_:self.create_candidate(request)),patch.object(updater_worker,'launch_and_verify',return_value={'app':'pg-research-desktop','ready':True,'build':'b'*64}),patch('upgrade._retarget_shortcuts',return_value={'status':'complete','locations':[{'name':'Desktop','status':'preserved_unrelated'}]}),patch.object(updater_worker,'restore_shortcuts',return_value={'status':'restored_verified'}),patch.object(updater_worker,'open_candidate') as window:
            self.assertEqual(updater_worker.run_job(directory)['phase'],'rolled_back')
        window.assert_not_called()

    def test_stale_readiness_waits_for_owned_candidate_child(self):
        from unittest.mock import MagicMock
        request,directory=self.prepared();new=self.create_candidate(request)
        with patch('upgrade._stopped'):updater_worker.upgrade.upgrade(self.old,new,apply=True)
        child=MagicMock();child.pid=314;child.poll.return_value=None
        old_session={'pid':313,'build':'a'*64,'port':3000,'token':'never-output'}
        new_session={'pid':314,'build':'b'*64,'port':3000,'token':'never-output'}
        client=MagicMock();client.verify.return_value={'app':'pg-research-desktop','build':'b'*64,'ready':True};client.request.return_value={}
        with patch.object(updater_worker.subprocess,'Popen',return_value=child),patch('agent.read_session',side_effect=[old_session,new_session]),patch('agent.Client',return_value=client),patch.object(updater_worker.time,'sleep') as sleep:
            result=updater_worker.launch_and_verify(new,'b'*64)
        self.assertTrue(result['ready']);sleep.assert_called_once_with(0.25);child.terminate.assert_not_called()

    def test_activation_failure_is_terminal_and_never_automatically_rolls_back(self):
        request,directory=self.prepared()
        with patch('upgrade._stopped'),patch.object(updater_worker,'run_installer',side_effect=lambda *_: self.create_candidate(request)),patch.object(updater_worker,'launch_and_verify',return_value={'app':'pg-research-desktop','ready':True,'build':'b'*64}),patch('upgrade._retarget_shortcuts',return_value={'status':'complete'}),patch.object(updater_worker,'activate_candidate',side_effect=updater.UpdateError('activation offline')),patch.object(updater_worker,'open_candidate'),patch.object(updater_worker,'restore_shortcuts') as restore:
            result=updater_worker.run_job(directory)
            again=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'activation_failed');self.assertEqual(again['phase'],'activation_failed');restore.assert_not_called()

    def test_activation_requires_marker_and_durable_matching_startup_receipt(self):
        request,directory=self.prepared();new=self.create_candidate(request)
        marker={'format':1,'app':'Kosh','repository':updater.REPOSITORY,'job_id':directory.name,'version':'0.5.0','build':'b'*64,'new_install':str(new),'phase':'installed_verified'}
        (new/'UPDATE_READY.json').write_text(json.dumps(marker))
        self.assertFalse(updater.activation_ready(new,'b'*64,cache_dir=self.root/'cache'))
        updater.write_receipt(directory,{'phase':'installed_verified','job_id':directory.name,'version':'0.5.0','build':'b'*64,'startup':{'app':'pg-research-desktop','build':'b'*64,'ready':True}})
        self.assertTrue(updater.activation_ready(new,'b'*64,cache_dir=self.root/'cache'))
        self.assertFalse(updater.activation_ready(new,'c'*64,cache_dir=self.root/'cache'))
        marker['new_install']=str(self.old);(new/'UPDATE_READY.json').write_text(json.dumps(marker))
        self.assertFalse(updater.activation_ready(new,'b'*64,cache_dir=self.root/'cache'))

    def test_normal_relaunch_with_pending_update_stays_read_only_until_proof(self):
        request,directory=self.prepared();new=self.create_candidate(request)
        (new/'UPDATE_PENDING.json').write_text(json.dumps({'job_id':directory.name,'new_install':str(new)}))
        with patch.object(updater,'cache_root',return_value=self.root/'cache'):
            self.assertTrue(updater.verification_required(new,'b'*64))
            marker={'format':1,'app':'Kosh','repository':updater.REPOSITORY,'job_id':directory.name,'version':'0.5.0','build':'b'*64,'new_install':str(new),'phase':'installed_verified'}
            (new/'UPDATE_READY.json').write_text(json.dumps(marker))
            self.assertTrue(updater.verification_required(new,'b'*64))
            updater.write_receipt(directory,{'phase':'installed_verified','job_id':directory.name,'version':'0.5.0','build':'b'*64,'startup':{'app':'pg-research-desktop','build':'b'*64,'ready':True}})
            self.assertFalse(updater.verification_required(new,'b'*64))
            self.assertTrue(updater.verification_required(new,'b'*64,explicit=True))

    def test_offline_copy_without_pending_marker_is_normal_startup(self):
        self.assertFalse(updater.verification_required(self.old,'a'*64))
        self.assertTrue(updater.verification_required(self.old,'a'*64,explicit=True))

    def test_pending_marker_creation_is_idempotent_and_preserves_mismatch(self):
        request,directory=self.prepared();new=self.create_candidate(request)
        updater_worker.write_pending(new,directory.name)
        before=(new/'UPDATE_PENDING.json').read_bytes()
        updater_worker.write_pending(new,directory.name)
        self.assertEqual((new/'UPDATE_PENDING.json').read_bytes(),before)
        with self.assertRaises(updater.UpdateError):updater_worker.write_pending(new,'f'*32)
        self.assertEqual((new/'UPDATE_PENDING.json').read_bytes(),before)

    def test_normal_server_main_relaunch_of_pending_candidate_blocks_writes(self):
        import subprocess,time
        from agent import Client,read_session,AgentError
        request,directory=self.prepared();new=self.create_candidate(request)
        (new/'UPDATE_PENDING.json').write_text(json.dumps({'job_id':directory.name,'new_install':str(new)}))
        data=self.root/'http-data';ready=data/'server.json';cache=self.root/'http-cache'
        script="import sys;from pathlib import Path;import server,updater;server.ROOT=Path(sys.argv[1]);server.source_hash=lambda:'b'*64;updater.cache_root=lambda:Path(sys.argv[4]);sys.argv=['server','--data-dir',sys.argv[2],'--ready-file',sys.argv[3],'--idle-minutes','1'];server.main()"
        process=subprocess.Popen([sys.executable,'-c',script,str(new),str(data),str(ready),str(cache)],cwd=Path(updater.__file__).parent,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        client=None
        try:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if process.poll() is not None:self.fail('Synthetic verification server exited before ready.')
                if ready.exists():
                    try:client=Client(read_session(data),timeout=3);client.verify();break
                    except AgentError:pass
                time.sleep(.05)
            self.assertIsNotNone(client,'Synthetic server never became ready.')
            self.assertTrue(client.request('/api/updates/status')['activation_required'])
            for route in ('/api/notes','/api/updates/activate'):
                with self.subTest(route=route),self.assertRaises(AgentError) as captured:client.request(route,{})
                self.assertEqual(captured.exception.status,409)
            self.assertTrue(client.request('/api/updates/status')['activation_required'])
            client.request('/api/shutdown',{});process.wait(timeout=10)
            self.assertEqual(process.returncode,0)
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=5)

    def test_invalid_pending_marker_is_fail_closed(self):
        (self.old/'UPDATE_PENDING.json').write_text('{invalid')
        self.assertTrue(updater.verification_required(self.old,'a'*64))

    def test_interrupted_verification_is_stopped_before_old_shortcut_recovery(self):
        request,directory=self.prepared();new=self.create_candidate(request)
        with patch('upgrade._stopped'):updater_worker.upgrade.upgrade(self.old,new,apply=True)
        updater.write_receipt(directory,{'phase':'retargeting','job_id':directory.name})
        events=[]
        with patch.object(updater_worker,'stop_verification_candidate',side_effect=lambda *_:events.append('stop')),patch.object(updater_worker,'restore_shortcuts',side_effect=lambda *_:events.append('restore') or {'status':'restored_verified'}),patch.object(updater_worker,'run_installer') as install:
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'rolled_back');self.assertEqual(events,['stop','restore']);install.assert_not_called()

    def test_stop_gate_failure_never_installs_or_copies(self):
        request,directory=self.prepared()
        with patch.object(updater_worker,'wait_stopped',side_effect=updater.UpdateError('still running')),patch.object(updater_worker,'run_installer') as install:
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'failed'); install.assert_not_called()
        self.assertFalse(Path(request['new_install']).exists())

    def test_tampered_download_never_executes(self):
        request,directory=self.prepared();(directory/'Kosh-0.5.0-Setup.exe').write_bytes(b'tampered')
        with patch.object(updater_worker,'run_installer') as install:
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'failed');install.assert_not_called()

    def test_candidate_wrong_version_refused_before_copy(self):
        request,directory=self.prepared()
        def install(candidate,target):
            new=self.create_candidate(request)
            (new/'updater.py').write_text("CURRENT_VERSION = '0.8.0'\nREPOSITORY = 'needanotheremailid/kosh-desktop'\n")
        with patch('upgrade._stopped'),patch.object(updater_worker,'run_installer',side_effect=install),patch.object(updater_worker,'launch_and_verify') as launch:
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'failed');self.assertFalse((Path(request['new_install'])/'data').exists());launch.assert_not_called()

    def test_interrupted_worker_is_not_silently_repeated(self):
        request,directory=self.prepared()
        updater.write_receipt(directory, {'phase':'copying','job_id':directory.name})
        with patch.object(updater_worker,'run_installer') as install:
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'interrupted');install.assert_not_called()


if __name__ == '__main__': unittest.main()
