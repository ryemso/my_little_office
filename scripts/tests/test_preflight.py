from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from office.preflight import check_workspace


class PreflightTests(unittest.TestCase):
    def test_real_file_and_process_roundtrip_with_unicode_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'김렴소 작업실';root.mkdir()
            result=check_workspace(root)
            self.assertTrue(result['process'])
            self.assertFalse(result['codex_sandbox_verified'])
            self.assertEqual(list(root.iterdir()),[])

    def test_invalid_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):check_workspace(Path(directory)/'missing')

    def test_write_failure_does_not_start_process(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('office.preflight.Path.write_text',side_effect=PermissionError('denied')),patch('office.preflight.HostProcess') as run:
                with self.assertRaises(PermissionError):check_workspace(directory)
                run.assert_not_called()
