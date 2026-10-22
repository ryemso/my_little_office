import json
from pathlib import Path
import tempfile
import unittest
from office.smoke import verify

class SmokeTests(unittest.TestCase):
    def test_requires_files_values_and_successful_analysis_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertFalse(verify(root,[])['passed'])
            folder=root/'acceptance';folder.mkdir()
            for name,body in [('input.csv','category,value\nA,10\nA,20\nB,5'),('analyze.py','# fixture'),('summary.json',json.dumps({'A':30,'B':5})),('chart.svg','<svg></svg>')]:
                (folder/name).write_text(body,encoding='utf-8')
            self.assertFalse(verify(root,[])['passed'])
            self.assertFalse(verify(root,[{'command':'python acceptance/analyze.py','exit_code':1}])['passed'])
            self.assertTrue(verify(root,[{'command':'python acceptance/analyze.py','exit_code':0}])['passed'])
            (folder/'summary.json').write_text('{}')
            self.assertFalse(verify(root,[{'command':'python acceptance/analyze.py','exit_code':0}])['passed'])
