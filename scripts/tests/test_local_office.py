import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('local_office', Path(__file__).parents[1] / 'local_office.py')
office = importlib.util.module_from_spec(spec)
spec.loader.exec_module(office)

class LocalOfficeTests(unittest.TestCase):
    def test_two_periods_and_same_period_resume(self):
        state = {}
        start = 1792544400  # 2026-10-21 morning KST
        first = office.attendance(state, start)
        self.assertEqual(office.attendance(state, start + 60), first)
        office.attendance(state, first['end'])
        with self.assertRaises(RuntimeError):
            office.attendance(state, state['shifts'][-1]['end'])
        office.attendance(state, start + 86400)
        self.assertEqual(len(state['shifts']), 1)

    def test_success_requires_completed_event_and_readonly(self):
        def fake(args, **kwargs):
            self.assertIn('read-only', args)
            self.assertIn('--ignore-user-config', args)
            self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
            Path(args[args.index('-o') + 1]).write_text('검토할 초안', encoding='utf-8')
            return subprocess.CompletedProcess(args, 0, '{"type":"turn.completed","usage":{}}', '')
        with patch.object(office.subprocess, 'run', side_effect=fake):
            result = office.execute({'role': 'dev', 'prompt': '새 기능을 설계해줘'}, 50)
        self.assertEqual(result['status'], 'review')

    def test_nonzero_and_incomplete_never_success(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(office, 'STATE', Path(directory)):
            with patch.object(office.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'usage limit')):
                self.assertEqual(office.execute({'role': 'dev', 'prompt': 'test task'}, 50)['status'], 'failed')
            with patch.object(office.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')):
                self.assertEqual(office.execute({'role': 'dev', 'prompt': 'test task'}, 50)['status'], 'failed')

    def test_failed_publish_retains_result_checkpoint(self):
        state = {'active': '1', 'result': {'id': '1', 'status': 'review', 'output': 'draft'}}
        with patch.object(office, 'update_remote', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                office.publish_result(state)
        self.assertIn('result', state)

    def test_cas_retry_keeps_new_tasks(self):
        records = [({'tasks': [{'id': '1'}]}, 'old'), ({'tasks': [{'id': '2'}, {'id': '1'}]}, 'new')]
        with patch.object(office, 'read_remote', side_effect=records), patch.object(office, 'command', side_effect=[subprocess.CalledProcessError(1, [], stderr='409'), None]):
            result = office.update_remote(lambda d: d.update(marker=True))
        self.assertEqual(result['tasks'][0]['id'], '2')
