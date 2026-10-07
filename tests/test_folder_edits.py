"""Synthetic chosen-folder receipts, path boundaries and recovery."""
from pathlib import Path
import os
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from folder_edits import FolderEditor, FolderError


class FolderAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='synthetic-folder-',dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.target=self.base/'chosen'
        self.target.mkdir()
        self.editor=FolderEditor(self.base/'appdata')
        (self.target/'draft.md').write_bytes(b'Original paragraph.\n')

    def proposal(self, files=None):
        return self.editor.preview(str(self.target),files or [{'path':'draft.md','content':'Revised paragraph.\n'}])

    def test_preview_diff_exact_bytes_without_target_write(self):
        result=self.proposal()
        self.assertEqual((self.target/'draft.md').read_bytes(),b'Original paragraph.\n')
        self.assertIn('-Original paragraph.',result['files'][0]['diff'])
        self.assertIn('+Revised paragraph.',result['files'][0]['diff'])
        self.assertEqual(result['target_path'],str(self.target.resolve()))

    def test_approval_one_use_and_recovery_retained(self):
        preview=self.proposal()
        with self.assertRaises(FolderError): self.editor.apply(preview['preview_id'],False)
        result=self.editor.apply(preview['preview_id'],True)
        self.assertEqual(result['status'],'applied')
        self.assertEqual((self.target/'draft.md').read_bytes(),b'Revised paragraph.\n')
        self.assertEqual(Path(result['files'][0]['recovery_path']).read_bytes(),b'Original paragraph.\n')
        self.assertEqual(self.editor.history()[0]['receipt_id'],result['receipt_id'])
        with self.assertRaises(FolderError): self.editor.apply(preview['preview_id'],True)

    def test_stale_bytes_refuse_entire_batch(self):
        preview=self.proposal([{'path':'draft.md','content':'New'},{'path':'fresh.txt','content':'New file'}])
        (self.target/'draft.md').write_text('Changed elsewhere',encoding='utf-8')
        with self.assertRaises(FolderError): self.editor.apply(preview['preview_id'],True)
        self.assertEqual((self.target/'draft.md').read_text(),'Changed elsewhere')
        self.assertFalse((self.target/'fresh.txt').exists())

    def test_path_and_file_type_boundaries(self):
        for path in ('../escape.md','/escape.md','C:\\escape.md','C:escape.md','.git/config.md','.env.md','credentials.txt','draft.json','run.ps1','NUL.txt','draft.md:stream','folder/../../escape.txt','draft.md '):
            with self.subTest(path=path),self.assertRaises(FolderError): self.proposal([{'path':path,'content':'x'}])
        with self.assertRaises(FolderError): self.proposal([{'path':'draft.md','content':'\x00binary'}])
        with self.assertRaises(FolderError): self.proposal([{'path':'missing/fresh.md','content':'x'}])

    def test_folder_identity_changed_refuses(self):
        preview=self.proposal()
        self.target.rename(self.base/'previous')
        self.target.mkdir()
        (self.target/'draft.md').write_bytes(b'Original paragraph.\n')
        with self.assertRaises(FolderError): self.editor.apply(preview['preview_id'],True)
        self.assertEqual((self.target/'draft.md').read_bytes(),b'Original paragraph.\n')

    def test_partial_failure_receipt_and_recovery_after_restart(self):
        preview=self.proposal([{'path':'draft.md','content':'New'},{'path':'fresh.txt','content':'Second'}])
        from folder_edits import publish_bytes
        def fail_second(path,data,**kwargs):
            if path.name=='fresh.txt': raise OSError('Synthetic write failure')
            return publish_bytes(path,data,**kwargs)
        with patch('folder_edits.publish_bytes',side_effect=fail_second):
            result=self.editor.apply(preview['preview_id'],True)
        self.assertEqual(result['status'],'partial')
        self.assertEqual([f['status'] for f in result['files']],['applied','failed'])
        self.assertEqual((self.target/'draft.md').read_text(),'New')
        self.assertFalse((self.target/'fresh.txt').exists())
        restarted=FolderEditor(self.base/'appdata')
        recovery=restarted.recovery_preview(result['receipt_id'])
        restored=restarted.apply(recovery['preview_id'],True)
        self.assertEqual(restored['status'],'applied')
        self.assertEqual((self.target/'draft.md').read_bytes(),b'Original paragraph.\n')

    def test_create_does_not_clobber_new_file(self):
        preview=self.proposal([{'path':'new.md','content':'Proposed'}])
        (self.target/'new.md').write_text('Other writer',encoding='utf-8')
        with self.assertRaises(FolderError): self.editor.apply(preview['preview_id'],True)
        self.assertEqual((self.target/'new.md').read_text(),'Other writer')

    def test_binary_existing_and_size_limits(self):
        (self.target/'draft.md').write_bytes(b'\xff\x00')
        with self.assertRaises(FolderError): self.proposal()
        with self.assertRaises(FolderError): self.proposal([{'path':'large.md','content':'x'*(256*1024+1)}])

    def test_reparse_and_hard_link_refused(self):
        original=Path.lstat
        def reparse(path,*args,**kwargs):
            if path==self.target/'draft.md': return SimpleNamespace(st_mode=stat.S_IFREG,st_file_attributes=0x400)
            return original(path,*args,**kwargs)
        with patch.object(Path,'lstat',reparse),self.assertRaises(FolderError): self.proposal()
        os.link(self.target/'draft.md',self.target/'second.md')
        with self.assertRaises(FolderError): self.proposal()

    def test_no_newline_diff_and_exact_created_bytes(self):
        preview=self.proposal([{'path':'new.txt','content':'Exact text without final newline'}])
        self.assertIn('No newline at end of file',preview['files'][0]['diff'])
        receipt=self.editor.apply(preview['preview_id'],True)
        self.assertEqual(receipt['status'],'applied')
        self.assertEqual((self.target/'new.txt').read_bytes(),b'Exact text without final newline')
        with self.assertRaises(FolderError): self.editor.recovery_preview(receipt['receipt_id'])

    def test_backend_routes_preserve_explicit_target_and_approval(self):
        from backend import Store,AppError
        store=Store(self.base/'service-data')
        self.addCleanup(store.close)
        # This adapter grants only the synthetic fixture root for route tests.
        store.folder_editor=self.editor
        preview=store.dispatch('POST','/api/folder-edits/preview',{'target_path':str(self.target),'files':[{'path':'draft.md','content':'Scoped route edit'}]})
        with self.assertRaises(AppError): store.dispatch('POST','/api/folder-edits/apply',{'preview_id':preview['preview_id'],'approve':False,'approval_version':1})
        receipt=store.dispatch('POST','/api/folder-edits/apply',{'preview_id':preview['preview_id'],'approve':True,'approval_version':1})
        self.assertEqual(receipt['status'],'applied')
        self.assertEqual(store.dispatch('GET','/api/folder-edits/history')['receipts'][0]['receipt_id'],receipt['receipt_id'])

    def test_review_hidden_appdata_ancestor_mock(self):
        storage=self.base/'HiddenAppData'/'Local'/'Kosh'
        storage.mkdir(parents=True)
        editor=FolderEditor(storage)
        original=Path.lstat
        def hidden(path,*args,**kwargs):
            if path==self.base/'HiddenAppData': return SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=0x2)
            return original(path,*args,**kwargs)
        with patch.object(Path,'lstat',hidden):
            preview=editor.preview(str(self.target),[{'path':'draft.md','content':'Changed'}])
            receipt=editor.apply(preview['preview_id'],True)
            self.assertEqual(receipt['status'],'applied')
            self.assertEqual(editor.history()[0]['receipt_id'],receipt['receipt_id'])
            recovery=editor.recovery_preview(receipt['receipt_id'])
            editor.apply(recovery['preview_id'],True)
            self.assertEqual((self.target/'draft.md').read_bytes(),b'Original paragraph.\n')

    @unittest.skipUnless(os.name=='nt','Windows hidden attributes')
    def test_review_real_hidden_storage_and_hidden_target_rejected(self):
        import ctypes
        storage=self.base/'hidden-storage';storage.mkdir()
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.SetFileAttributesW.argtypes=(ctypes.c_wchar_p,ctypes.c_uint32)
        old=storage.stat().st_file_attributes
        self.assertTrue(kernel.SetFileAttributesW(str(storage),old|0x2))
        self.addCleanup(lambda: kernel.SetFileAttributesW(str(storage),old))
        self.assertTrue(storage.stat().st_file_attributes&0x2)
        editor=FolderEditor(storage)
        preview=editor.preview(str(self.target),[{'path':'draft.md','content':'Hidden storage works'}])
        self.assertEqual(editor.apply(preview['preview_id'],True)['status'],'applied')
        self.assertEqual(len(editor.history()),1)
        # Internal permission must not weaken hidden-target exclusion.
        target_old=self.target.stat().st_file_attributes
        self.assertTrue(kernel.SetFileAttributesW(str(self.target),target_old|0x2))
        self.addCleanup(lambda: kernel.SetFileAttributesW(str(self.target),target_old))
        with self.assertRaises(FolderError): editor.preview(str(self.target),[{'path':'draft.md','content':'Blocked'}])

    def test_review_failed_recovery_preparation_keeps_preview(self):
        preview=self.proposal()
        with patch.object(self.editor,'_journal',side_effect=OSError('Synthetic unavailable recovery storage')):
            with self.assertRaises(OSError): self.editor.apply(preview['preview_id'],True)
        self.assertEqual((self.target/'draft.md').read_bytes(),b'Original paragraph.\n')
        self.assertEqual(self.editor.apply(preview['preview_id'],True)['status'],'applied')

    def test_review_explicit_line_endings_and_bom_flags_and_recovery(self):
        original=b'\xef\xbb\xbfFirst\r\nSecond\r\n'
        (self.target/'draft.md').write_bytes(original)
        preview=self.proposal([{'path':'draft.md','content':'First\nSecond\n'}])
        self.assertTrue(preview['files'][0]['line_endings_changed'])
        self.assertTrue(preview['files'][0]['bom_removed'])
        receipt=self.editor.apply(preview['preview_id'],True)
        self.assertEqual(Path(receipt['files'][0]['recovery_path']).read_bytes(),original)
        recovery=self.editor.recovery_preview(receipt['receipt_id'])
        self.editor.apply(recovery['preview_id'],True)
        self.assertEqual((self.target/'draft.md').read_bytes(),original)

    def test_review_key_points_allowed_credentials_blocked(self):
        self.assertEqual(self.proposal([{'path':'key-points.md','content':'Ordinary writing'}])['files'][0]['path'],'key-points.md')
        for path in ('api-key.txt','private-key.txt','api-key-backup.txt','private-key-copy.md','keys.txt','credentials.md','token.txt'):
            with self.subTest(path=path),self.assertRaises(FolderError): self.proposal([{'path':path,'content':'x'}])

    def test_review_internal_reparse_storage_still_blocked(self):
        storage=self.base/'hidden-storage';storage.mkdir()
        editor=FolderEditor(storage)
        preview=editor.preview(str(self.target),[{'path':'draft.md','content':'Must not apply'}])
        original=Path.lstat
        def reparse(path,*args,**kwargs):
            if path==storage: return SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=0x402)
            return original(path,*args,**kwargs)
        with patch.object(Path,'lstat',reparse),self.assertRaises(FolderError):
            editor.apply(preview['preview_id'],True)
        self.assertEqual((self.target/'draft.md').read_bytes(),b'Original paragraph.\n')
        self.assertEqual(editor.apply(preview['preview_id'],True)['status'],'applied')


if __name__=='__main__': unittest.main()
