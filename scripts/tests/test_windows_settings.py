from pathlib import Path
import tempfile
import unittest
from office.windows_settings import windows_settings


class WindowsSettingsTests(unittest.TestCase):
    def test_whitelist_preserves_backend_without_loading_permissions_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'config.toml'
            config.write_text('''model="custom-model"
approval_policy="never"
sandbox_mode="danger-full-access"
[windows]
sandbox="elevated"
[features]
prefer_mxc=true
[mcp_servers.private]
command="private-tool"
''')
            args,info=windows_settings(directory,windows=True)
            self.assertIn('windows.sandbox="elevated"',args)
            self.assertIn('features.prefer_mxc=true',args)
            self.assertNotIn('danger-full-access',str(args)+str(info))
            self.assertNotIn('private-tool',str(args)+str(info))
            self.assertNotIn('custom-model',str(args)+str(info))

    def test_missing_or_non_windows_config_keeps_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(windows_settings(directory,windows=True)[0],[])
            self.assertEqual(windows_settings(directory,windows=False)[0],[])

    def test_malformed_or_unknown_backend_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.toml'
            for contents in ('[windows','[windows]\nsandbox="disabled"'):
                path.write_text(contents)
                with self.assertRaises(RuntimeError):windows_settings(directory,windows=True)
