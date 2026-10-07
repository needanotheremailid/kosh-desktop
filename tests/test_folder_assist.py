"""Explicit chosen-file assistance with mocked providers and synthetic targets."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import AppError, Store
from folder_assist import FolderAssist


class FolderAssistAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-folder-assist-', dir=Path(__file__).resolve().parents[2])
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'data')
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.workspace = self.store.dispatch('POST', '/api/workspaces', {'title': 'Synthetic folder assistance'})['id']
        self.target = self.root / 'chosen'
        self.target.mkdir()
        (self.target / 'widgets.md').write_bytes(b'Original synthetic widgets.\r\n')
        (self.target / 'unselected.txt').write_text('Unselected synthetic material.', encoding='utf-8')
        self.assist = FolderAssist(self.store)
        self.providers = patch('backend.installed_agents', return_value=[{'id': 'claude', 'available': True}])
        self.providers.start()
        self.addCleanup(self.providers.stop)

    def preview(self, **changes):
        return self.assist.dispatch('POST', '/api/folder-assist/preview', {'workspace_id': self.workspace, 'target_path': str(self.target), 'paths': ['widgets.md'], 'provider': 'claude', 'instruction': 'Improve the selected synthetic text.', **changes})

    def send(self, preview):
        return self.assist.dispatch('POST', '/api/folder-assist/run', {'preview_id': preview['preview_id'], 'consent': True, 'consent_version': 1})

    def test_only_explicit_files_reach_prompt_and_preview_changes_nothing(self):
        with patch('backend.run_installed_agent') as provider:
            preview = self.preview(paths=['widgets.md', 'new widgets.txt'])
        self.assertIn('Original synthetic widgets.', preview['prompt'])
        self.assertNotIn('Unselected synthetic material.', preview['prompt'])
        self.assertEqual(preview['files'][1]['before_sha256'], None)
        self.assertEqual((self.target / 'widgets.md').read_bytes(), b'Original synthetic widgets.\r\n')
        self.assertFalse((self.target / 'new widgets.txt').exists())
        provider.assert_not_called()

    def test_provider_result_becomes_diff_and_explicit_apply_remains_separate(self):
        preview = self.preview()
        with patch('backend.run_installed_agent', return_value=json.dumps({'files': [{'path': 'widgets.md', 'content': 'Reviewed synthetic widgets.\r\n'}]})) as provider:
            result = self.send(preview)
            repeated = self.send(preview)
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(repeated['result_id'], result['result_id'])
        self.assertIn('Reviewed synthetic widgets.', result['folder_preview']['files'][0]['diff'])
        self.assertEqual((self.target / 'widgets.md').read_bytes(), b'Original synthetic widgets.\r\n')
        self.assertEqual(len(self.store._state(self.workspace)['notes']), 0)
        receipt = self.store.folder_editor.apply(result['folder_preview']['preview_id'], True, 1)
        self.assertEqual(receipt['status'], 'applied')
        self.assertEqual((self.target / 'widgets.md').read_bytes(), b'Reviewed synthetic widgets.\r\n')

    def test_consent_and_changed_files_prevent_provider_send(self):
        preview = self.preview()
        with patch('backend.run_installed_agent') as provider:
            with self.assertRaises(AppError):
                self.assist.dispatch('POST', '/api/folder-assist/run', {'preview_id': preview['preview_id']})
            (self.target / 'widgets.md').write_text('Changed concurrently.', encoding='utf-8')
            with self.assertRaises(AppError) as changed:
                self.send(preview)
            self.assertEqual(changed.exception.status, 409)
            provider.assert_not_called()

    def test_changed_files_during_provider_refuse_diff_and_repeated_usage(self):
        preview = self.preview()
        def provider(provider, prompt):
            (self.target / 'widgets.md').write_text('Changed during request.', encoding='utf-8')
            return json.dumps({'files': [{'path': 'widgets.md', 'content': 'Proposed widgets.'}]})
        with patch('backend.run_installed_agent', side_effect=provider) as sent:
            with self.assertRaises(AppError):
                self.send(preview)
            with self.assertRaises(AppError):
                self.send(preview)
            self.assertEqual(sent.call_count, 1)
        self.assertEqual((self.target / 'widgets.md').read_text(), 'Changed during request.')

    def test_change_between_hash_check_and_diff_is_refused(self):
        preview = self.preview()
        make_diff = self.store.folder_editor.preview
        def race(target, files):
            (self.target / 'widgets.md').write_text('Changed just before diff.', encoding='utf-8')
            return make_diff(target, files)
        with patch('backend.run_installed_agent', return_value=json.dumps({'files': [{'path': 'widgets.md', 'content': 'Reviewed widgets.'}]})), patch.object(self.store.folder_editor, 'preview', side_effect=race):
            with self.assertRaises(AppError) as changed:
                self.send(preview)
            self.assertEqual(changed.exception.status, 409)
        self.assertEqual(self.store.folder_editor.previews, {})

    def test_local_model_uses_fixed_loopback_prompt_and_diff_only(self):
        with patch.object(self.store, 'models', return_value={'available': True, 'models': [{'name': 'synthetic:local'}]}):
            preview = self.preview(provider='ollama', model='synthetic:local')
        output = json.dumps({'files': [{'path': 'widgets.md', 'content': 'Local synthetic widgets.'}]})
        with patch('backend.ollama_request', return_value={'response': output}) as provider, patch('backend.run_installed_agent') as installed:
            result = self.send(preview)
        self.assertEqual(provider.call_args.args[0], '/api/generate')
        self.assertEqual(provider.call_args.args[1]['model'], 'synthetic:local')
        self.assertEqual(provider.call_args.args[1]['prompt'], preview['prompt'])
        self.assertEqual(provider.call_args.args[1]['format'], 'json')
        self.assertEqual(provider.call_args.args[1]['options'], {'num_ctx': 32768, 'num_predict': 8192})
        self.assertEqual(result['files'][0]['content'], 'Local synthetic widgets.')
        installed.assert_not_called()
        self.assertEqual((self.target / 'widgets.md').read_bytes(), b'Original synthetic widgets.\r\n')

    def test_single_whole_json_fence_becomes_a_diff_without_target_write(self):
        preview = self.preview()
        output = '```json\n{"files":[{"path":"widgets.md","content":"Fenced synthetic widgets."}]}\n```'
        with patch('backend.run_installed_agent', return_value=output):
            result = self.send(preview)
        self.assertEqual(result['files'][0]['content'], 'Fenced synthetic widgets.')
        self.assertEqual((self.target / 'widgets.md').read_bytes(), b'Original synthetic widgets.\r\n')

    def test_prose_or_multiple_json_fences_are_rejected(self):
        value = '{"files":[{"path":"widgets.md","content":"Widgets."}]}'
        for output in ('Here is the result:\n```json\n' + value + '\n```', '```json\n' + value + '\n```\nMore prose', '```json\n' + value + '\n```\n```json\n' + value + '\n```'):
            with self.subTest(output=output):
                preview = self.preview()
                with patch('backend.run_installed_agent', return_value=output), self.assertRaises(AppError):
                    self.send(preview)
        self.assertEqual(self.store.folder_editor.previews, {})

    def test_local_truncated_json_is_rejected_before_a_diff_and_not_resent(self):
        value = '{"files":[{"path":"widgets.md","content":"Valid-looking partial widgets."}]}'
        for counters in ({'done_reason': 'length'}, {'prompt_eval_count': 30000, 'eval_count': 2768}, {'prompt_eval_count': 32768, 'eval_count': 0}):
            with self.subTest(counters=counters):
                with patch.object(self.store, 'models', return_value={'available': True, 'models': [{'name': 'synthetic:local'}]}):
                    preview = self.preview(provider='ollama', model='synthetic:local')
                with patch('backend.ollama_request', return_value={'response': value, **counters}) as provider:
                    with self.assertRaises(AppError) as failure:
                        self.send(preview)
                    self.assertEqual(failure.exception.status, 502)
                    with self.assertRaises(AppError):
                        self.send(preview)
                    self.assertEqual(provider.call_count, 1)
                self.assertEqual(self.store.folder_editor.previews, {})
        self.assertEqual((self.target / 'widgets.md').read_bytes(), b'Original synthetic widgets.\r\n')

    def test_local_completion_below_context_bound_is_accepted(self):
        with patch.object(self.store, 'models', return_value={'available': True, 'models': [{'name': 'synthetic:local'}]}):
            preview = self.preview(provider='ollama', model='synthetic:local')
        value = '{"files":[{"path":"widgets.md","content":"Bounded complete widgets."}]}'
        with patch('backend.ollama_request', return_value={'response': value, 'done_reason': 'stop', 'prompt_eval_count': 24000, 'eval_count': 3000}):
            result = self.send(preview)
        self.assertEqual(result['files'][0]['content'], 'Bounded complete widgets.')

    def test_invalid_provider_token_counters_do_not_bypass_context_checks(self):
        value = '{"files":[{"path":"widgets.md","content":"Invalid-counter widgets."}]}'
        for counters in ({'prompt_eval_count': '30000'}, {'eval_count': -1}, {'eval_count': True}):
            with self.subTest(counters=counters):
                with patch.object(self.store, 'models', return_value={'available': True, 'models': [{'name': 'synthetic:local'}]}):
                    preview = self.preview(provider='ollama', model='synthetic:local')
                with patch('backend.ollama_request', return_value={'response': value, **counters}), self.assertRaises(AppError) as failure:
                    self.send(preview)
                self.assertEqual(failure.exception.status, 502)
        self.assertEqual(self.store.folder_editor.previews, {})

    def test_unselected_paths_commands_and_invalid_json_are_refused(self):
        for output in ('not JSON', json.dumps({'files': [{'path': 'unselected.txt', 'content': 'Forbidden widgets.'}]}), json.dumps({'files': [{'path': 'widgets.md', 'content': 'Widgets', 'command': 'anything'}]})):
            preview = self.preview()
            with patch('backend.run_installed_agent', return_value=output), self.assertRaises(AppError):
                self.send(preview)
        self.assertEqual((self.target / 'unselected.txt').read_text(), 'Unselected synthetic material.')
        self.assertEqual(self.store.folder_editor.previews, {})

    def test_restart_recovers_proposal_diff_without_new_provider_request(self):
        preview = self.preview()
        with patch('backend.run_installed_agent', return_value=json.dumps({'files': [{'path': 'widgets.md', 'content': 'Recovered widgets.'}]})):
            result = self.send(preview)
        self.store.close()
        self.store = Store(self.root / 'data')
        self.addCleanup(self.store.close)
        self.assist = FolderAssist(self.store)
        with patch('backend.run_installed_agent') as provider:
            recovered = self.send(preview)
            repeated = self.send(preview)
        self.assertEqual(recovered['result_id'], result['result_id'])
        self.assertIn('Recovered widgets.', recovered['folder_preview']['files'][0]['diff'])
        self.assertNotEqual(recovered['folder_preview']['preview_id'], result['folder_preview']['preview_id'])
        self.assertEqual(recovered['folder_preview']['preview_id'], repeated['folder_preview']['preview_id'])
        self.assertEqual(len(self.store.folder_editor.previews), 1)
        provider.assert_not_called()

    def test_original_folder_path_guards_and_prompt_size_are_preserved(self):
        for paths in (['../outside.txt'], ['secret.txt'], ['widgets.md', 'WIDGETS.md'], ['missing-parent/new.txt']):
            with self.assertRaises(AppError):
                self.preview(paths=paths)
        with self.assertRaises(AppError):
            self.preview(target_path=str(self.store.root))
        (self.target / 'widgets.md').write_text('x' * 24_000, encoding='utf-8')
        with self.assertRaises(AppError) as size:
            self.preview()
        self.assertEqual(size.exception.status, 413)


if __name__ == '__main__':
    unittest.main()
