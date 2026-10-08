"""RC ordering and interrupted-update recovery, using invented local packages."""
import copy
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import updater
import updater_worker
import upgrade
from tests.test_upgrade import installed, synthetic_data
from tests.test_updater import release, PACKAGE


class SemVerTests(unittest.TestCase):
    def test_standard_prerelease_precedence_and_final(self):
        ordered=['0.6.0','1.0.0-alpha','1.0.0-alpha.1','1.0.0-alpha.beta','1.0.0-beta','1.0.0-beta.2','1.0.0-beta.11','1.0.0-rc.1','1.0.0-rc.2','1.0.0-rc.10','1.0.0','1.0.1-alpha']
        self.assertEqual(sorted(reversed(ordered),key=updater.version_tuple),ordered)

    def test_build_metadata_does_not_change_precedence(self):
        self.assertEqual(updater.version_tuple('1.0.0-rc.1+001'),updater.version_tuple('1.0.0-rc.1+source.a'))

    def test_unsafe_or_noncanonical_versions_are_refused(self):
        for value in ('01.0.0','1.0.0-rc.01','1.0.0-','1.0.0-rc..1','1.0.0/rc','1.0.0%2Frc','1.0.0-rc;calc','1.0.0-rc.$x','1.0.0-rc.é','1.0.0+','1.0.0+meta/escape'):
            with self.subTest(version=value),self.assertRaises(updater.UpdateError):updater.version_tuple(value)

    def test_rc_asset_names_and_fixed_urls_pass_transport(self):
        item=release('1.0.0-rc.1');candidate=updater.parse_release(item)
        self.assertEqual(candidate.filename,'Kosh-1.0.0-rc.1-Setup.exe')
        self.assertEqual(candidate.installer_url,'https://github.com/needanotheremailid/kosh-desktop/releases/download/v1.0.0-rc.1/Kosh-1.0.0-rc.1-Setup.exe')
        transport=updater.GithubTransport();transport.opener=MagicMock()
        transport.open(candidate.installer_url)
        self.assertEqual(transport.opener.open.call_args.args[0].full_url,candidate.installer_url)
        for url in (candidate.installer_url+'?shell=1',candidate.installer_url.replace('rc.1-Setup','rc.2-Setup')):
            with self.assertRaises(updater.UpdateError):transport.open(url)

    def test_prerelease_label_and_encoded_build_asset_url_are_exact(self):
        item=release('1.0.0-rc.1');item['prerelease']=False
        with self.assertRaises(updater.UpdateError):updater.parse_release(item)
        item=release('1.0.0-rc.1+build.01');candidate=updater.parse_release(item)
        self.assertIn('%2Bbuild.01',candidate.installer_url)
        transport=updater.GithubTransport();transport.opener=MagicMock();transport.open(candidate.installer_url)
        digest=hashlib.sha256(PACKAGE).hexdigest()
        self.assertEqual(updater.parse_checksum((digest+'  '+candidate.filename+'\n').encode(),candidate.filename),digest)


class RCRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.old=self.root/'Kosh-old';installed(self.old,'a'*64);synthetic_data(self.old)
        self.cache=self.root/'cache';self.version='1.0.0-rc.1'

    def tearDown(self):self.temporary.cleanup()

    def manager(self,current='0.6.0',values=None):
        values=values if values is not None else [release(self.version)]
        class Transport:
            def open(inner,url):
                if url==updater.RELEASES_URL:return io.BytesIO(json.dumps(values).encode())
                if url.endswith('/SHA256SUMS.txt'):return io.BytesIO((hashlib.sha256(PACKAGE).hexdigest()+'  Kosh-'+self.version+'-Setup.exe\n').encode())
                return io.BytesIO(PACKAGE)
        return updater.Updater(self.old,cache_dir=self.cache,transport=Transport(),current_version=current)

    def prepared(self):
        manager=self.manager();manager.check(consent=True);manager.download(consent=True)
        request=manager.prepare_install(approve=True,accept_unsigned=True);directory=manager.job_dir
        new=self.create_candidate(request)
        with patch('upgrade._stopped'):upgrade.upgrade(self.old,new,apply=True)
        updater_worker.write_pending(new,directory.name)
        updater.write_receipt(directory,{'phase':'installed_verified','job_id':directory.name,'version':self.version,'build':'b'*64,'startup':{'app':'pg-research-desktop','build':'b'*64,'ready':True}})
        return directory,new

    def create_candidate(self,request):
        new=Path(request['new_install']);installed(new,'b'*64)
        identity=("CURRENT_VERSION = '"+self.version+"'\nREPOSITORY = 'needanotheremailid/kosh-desktop'\n").encode()
        (new/'updater.py').write_bytes(identity)
        manifest=upgrade._json(new/'package-manifest.json');manifest['files'].append({'path':'updater.py','size':len(identity),'sha256':hashlib.sha256(identity).hexdigest()})
        (new/'package-manifest.json').write_text(json.dumps(manifest))
        receipt=upgrade._json(new/'INSTALL_RECEIPT.json');receipt['files_verified']+=1;receipt['payload_bytes']+=len(identity);(new/'INSTALL_RECEIPT.json').write_text(json.dumps(receipt))
        return new

    def test_beta_and_rc_builds_discover_prereleases_but_final_builds_do_not(self):
        for current in ('0.6.0','1.0.0-rc.0'):
            self.assertEqual(self.manager(current).check(consent=True)['candidate']['version'],self.version)
        final=self.manager('1.0.0',[release('1.1.0-rc.1')])
        self.assertEqual(final.check(consent=True)['phase'],'up_to_date')

    def test_newer_final_beats_rc_and_same_rc_metadata_is_not_update(self):
        final=release('1.0.0');final['prerelease']=False
        self.assertEqual(self.manager('1.0.0-rc.0',[release(self.version),final]).check(consent=True)['candidate']['version'],'1.0.0')
        same=self.manager('1.0.0-rc.1',[release('1.0.0-rc.1+newbuild')])
        self.assertEqual(same.check(consent=True)['phase'],'up_to_date')

    def test_missing_ready_marker_recovers_from_exact_completed_proof(self):
        directory,new=self.prepared();before=upgrade._inventory(self.old/'data')
        self.assertFalse(updater.activation_ready(new,'b'*64,cache_dir=self.cache))
        self.assertTrue(updater.recover_ready(new,'b'*64,cache_dir=self.cache))
        self.assertTrue(updater.activation_ready(new,'b'*64,cache_dir=self.cache))
        self.assertEqual(upgrade._inventory(self.old/'data'),before)

    def test_local_activation_proof_survives_unavailable_cache(self):
        directory,new=self.prepared();updater.recover_ready(new,'b'*64,cache_dir=self.cache)
        self.assertTrue(updater.confirm_activation(new,'b'*64,cache_dir=self.cache))
        self.cache.rename(self.root/'unavailable-cache')
        with patch.object(updater,'cache_root',return_value=self.cache):
            self.assertFalse(updater.verification_required(new,'b'*64))
            self.assertTrue(updater.activation_ready(new,'b'*64))
            self.assertFalse(updater.activation_ready(new,'c'*64))

    def test_unproved_candidate_or_changed_package_stays_locked(self):
        directory,new=self.prepared();(directory/'receipts').rename(directory/'saved-receipts')
        self.assertFalse(updater.recover_ready(new,'b'*64,cache_dir=self.cache))
        with self.assertRaises(updater.UpdateError):updater.confirm_activation(new,'b'*64,cache_dir=self.cache)
        (directory/'saved-receipts').rename(directory/'receipts');(new/'server.py').write_bytes(b'changed candidate')
        self.assertFalse(updater.recover_ready(new,'b'*64,cache_dir=self.cache))
        self.assertFalse((new/'UPDATE_READY.json').exists())

    def test_local_proof_cannot_unlock_copied_install_or_different_build(self):
        import shutil
        directory,new=self.prepared();updater.recover_ready(new,'b'*64,cache_dir=self.cache);updater.confirm_activation(new,'b'*64,cache_dir=self.cache)
        copied=self.root/'Copied-Kosh';shutil.copytree(new,copied)
        self.assertFalse(updater.activation_ready(copied,'b'*64,cache_dir=self.cache))
        self.assertTrue(updater.verification_required(copied,'b'*64))
        manifest=upgrade._json(new/'package-manifest.json');manifest['build']='c'*64;(new/'package-manifest.json').write_text(json.dumps(manifest))
        self.assertFalse(updater.activation_ready(new,'b'*64,cache_dir=self.cache))

    def test_truncated_readiness_marker_is_preserved_then_explicitly_repaired(self):
        directory,new=self.prepared();broken=b'{"format":'
        (new/'UPDATE_READY.json').write_bytes(broken)
        self.assertTrue(updater.recover_ready(new,'b'*64,cache_dir=self.cache))
        copies=list(new.glob('UPDATE_READY.recovery-*.json'))
        self.assertEqual(len(copies),1);self.assertEqual(copies[0].read_bytes(),broken)
        self.assertTrue(updater.activation_ready(new,'b'*64,cache_dir=self.cache))

    def test_proof_storage_failure_does_not_lift_gate_or_touch_original_data(self):
        directory,new=self.prepared();before=upgrade._inventory(self.old/'data')
        original=upgrade._write_json_new
        def fail_ready(path,value):
            if 'UPDATE_READY' in path.name:raise OSError('Synthetic unavailable installation drive')
            return original(path,value)
        with patch.object(upgrade,'_write_json_new',side_effect=fail_ready),self.assertRaises(updater.UpdateError):
            updater.recover_ready(new,'b'*64,cache_dir=self.cache)
        self.assertFalse(updater.activation_ready(new,'b'*64,cache_dir=self.cache))
        updater.recover_ready(new,'b'*64,cache_dir=self.cache)
        def fail_activation(path,value):
            if 'UPDATE_ACTIVATED' in path.name:raise OSError('Synthetic unavailable installation drive')
            return original(path,value)
        with patch.object(upgrade,'_write_json_new',side_effect=fail_activation),self.assertRaises(updater.UpdateError):
            updater.confirm_activation(new,'b'*64,cache_dir=self.cache)
        self.assertFalse((new/'UPDATE_ACTIVATED.json').exists())
        self.assertEqual(upgrade._inventory(self.old/'data'),before)

    def test_well_formed_wrong_marker_is_never_replaced(self):
        directory,new=self.prepared();wrong={'new_install':'different root'}
        (new/'UPDATE_READY.json').write_text(json.dumps(wrong))
        self.assertFalse(updater.recover_ready(new,'b'*64,cache_dir=self.cache))
        self.assertEqual(json.loads((new/'UPDATE_READY.json').read_text()),wrong)

    def test_torn_local_proof_write_never_publishes_partial_authority(self):
        directory,new=self.prepared();updater.recover_ready(new,'b'*64,cache_dir=self.cache)
        original=upgrade._write_json_new
        def torn(path,value):
            if 'UPDATE_ACTIVATED' in path.name:
                path.write_bytes(b'{"phase":');raise OSError('Synthetic interrupted proof write')
            return original(path,value)
        with patch.object(upgrade,'_write_json_new',side_effect=torn),self.assertRaises(updater.UpdateError):
            updater.confirm_activation(new,'b'*64,cache_dir=self.cache)
        self.assertFalse((new/'UPDATE_ACTIVATED.json').exists())
        self.assertTrue(list(new.glob('UPDATE_ACTIVATED.pending-*.json')))
        self.assertTrue(updater.confirm_activation(new,'b'*64,cache_dir=self.cache))

    def test_candidate_cleanup_prefers_exact_owned_service_shutdown(self):
        directory,new=self.prepared();child=MagicMock();child.pid=314;child.poll.return_value=None
        session={'pid':314,'build':'b'*64,'port':3000,'token':'never-output'}
        client=MagicMock();client.verify.return_value={'app':'pg-research-desktop','build':'b'*64,'ready':True}
        with patch('agent.read_session',return_value=session),patch('agent.Client',return_value=client):
            updater_worker.stop_owned_service(child,new,'b'*64)
        client.request.assert_called_once_with('/api/shutdown',{})
        child.wait.assert_called_once_with(timeout=5);child.terminate.assert_not_called()

    def test_rolled_back_current_receipt_rejects_orphaned_completion_event(self):
        directory,new=self.prepared()
        updater.write_receipt(directory,{'phase':'rolled_back','job_id':directory.name})
        self.assertFalse(updater.recover_ready(new,'b'*64,cache_dir=self.cache))
        self.assertFalse(updater.activation_ready(new,'b'*64,cache_dir=self.cache))

    def test_activation_timeout_reads_durable_proof_and_service_state_without_replay(self):
        from agent import AgentError
        directory,new=self.prepared();session={'pid':314,'build':'b'*64,'port':3000,'token':'never-output'}
        client=MagicMock()
        def request(route,body=None):
            if route=='/api/updates/activate':
                updater.recover_ready(new,'b'*64,cache_dir=self.cache);updater.confirm_activation(new,'b'*64,cache_dir=self.cache)
                raise AgentError('Synthetic response lost after activation')
            if route=='/api/updates/status':return {'activation_required':False,'current_version':self.version}
            raise AssertionError('Unexpected request')
        client.request.side_effect=request
        with patch('agent.read_session',return_value=session),patch('agent.Client',return_value=client):
            updater_worker.activate_candidate(new,'b'*64)
        self.assertEqual(sum(call.args[0]=='/api/updates/activate' for call in client.request.call_args_list),1)
        self.assertTrue(any(call.args[0]=='/api/updates/status' for call in client.request.call_args_list))

    def test_worker_liveness_rejects_reused_pid_birth_identity(self):
        directory,new=self.prepared()
        (directory/'worker.json').write_text(json.dumps({'pid':314,'process_identity':'1234'}))
        with patch('upgrade._pid_alive',return_value=True),patch('upgrade._process_identity',return_value='5678'):
            self.assertFalse(updater.worker_alive(directory/'worker.json'))

    def test_receipt_pointer_failure_rolls_back_and_cannot_activate_orphan_event(self):
        manager=self.manager();manager.check(consent=True);manager.download(consent=True)
        request=manager.prepare_install(approve=True,accept_unsigned=True);directory=manager.job_dir;new=Path(request['new_install'])
        original=updater.os.replace;failed=[];before=upgrade._inventory(self.old/'data')
        def pointer_failure(source,target):
            if Path(target).name=='receipt.json' and not failed and json.loads(Path(source).read_text())['phase']=='installed_verified':
                failed.append(True);raise OSError('Synthetic receipt sharing violation')
            return original(source,target)
        with patch('upgrade._stopped'),patch.object(updater_worker,'run_installer',side_effect=lambda *_:self.create_candidate(request)),patch.object(updater_worker,'launch_and_verify',return_value={'app':'pg-research-desktop','build':'b'*64,'ready':True}),patch('upgrade._retarget_shortcuts',return_value={'status':'complete'}),patch.object(updater_worker,'restore_shortcuts',return_value={'status':'restored_verified'}),patch.object(updater.os,'replace',side_effect=pointer_failure),patch.object(updater_worker,'open_candidate') as window:
            result=updater_worker.run_job(directory)
        self.assertEqual(result['phase'],'rolled_back');self.assertTrue(failed);window.assert_not_called()
        self.assertTrue(any(json.loads(path.read_text())['phase']=='installed_verified' for path in (directory/'receipts').glob('*.json')))
        self.assertFalse(updater.recover_ready(new,'b'*64,cache_dir=self.cache));self.assertFalse(updater.activation_ready(new,'b'*64,cache_dir=self.cache))
        self.assertFalse((directory/'worker.json').exists());self.assertEqual(upgrade._inventory(self.old/'data'),before)

    def test_activation_readback_uses_new_target_version_not_old_worker_constant(self):
        from agent import AgentError
        self.version='1.0.0-rc.2';directory,new=self.prepared()
        client=MagicMock();session={'pid':314,'build':'b'*64,'port':3000,'token':'never-output'}
        def request(route,body=None):
            if route=='/api/updates/activate':
                with patch.object(updater,'CURRENT_VERSION',self.version):
                    updater.recover_ready(new,'b'*64,cache_dir=self.cache);updater.confirm_activation(new,'b'*64,cache_dir=self.cache)
                raise AgentError('Synthetic response lost after newer-version activation')
            return {'activation_required':False,'current_version':self.version}
        client.request.side_effect=request
        with patch('agent.read_session',return_value=session),patch('agent.Client',return_value=client):
            updater_worker.activate_candidate(new,'b'*64,self.version)
        self.assertNotEqual(updater_worker.CURRENT_VERSION,self.version)


if __name__=='__main__':unittest.main()
