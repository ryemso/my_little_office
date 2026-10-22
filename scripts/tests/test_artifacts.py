import json
from pathlib import Path
import tempfile
import unittest
from office.artifacts import inspect_artifacts
from office.planning import parse_plan
from office.store import Store

class ArtifactTests(unittest.TestCase):
    def test_contract_survives_delegation_and_detects_empty_file(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);store.clock_in();p=store.company_project()
            identifier=store.submit('lead','분석 파일을 만들어줘',delegate=True,project_id=p)
            store.claim();store.finish(identifier,{'status':'review','output':json.dumps({'tasks':[{'role':'data','prompt':'분석 파일을 만들어줘','artifacts':['summary.csv']}]})})
            child=store.children(identifier)[0]
            self.assertEqual(json.loads(child['expected_json']),['summary.csv'])
            path=Path(root)/'summary.csv';path.touch()
            self.assertFalse(inspect_artifacts(Path(root),['summary.csv'])[0]['present'])
            path.write_text('a,b\n1,2')
            result=inspect_artifacts(Path(root),['summary.csv'])[0]
            self.assertTrue(result['present']);self.assertEqual(len(result['sha256']),64)

    def test_contract_rejects_escape_and_non_list(self):
        for outputs in [['../secret'],['/secret'],['C:\\secret'],'file']:
            with self.assertRaises(ValueError):
                parse_plan(json.dumps({'tasks':[{'role':'data','prompt':'분석을 진행해줘','artifacts':outputs}]}))
