import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('runner',Path(__file__).resolve().parents[1]/'run_task.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RunnerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=m.DATA;m.DATA=Path(self.tmp.name)/'tasks.json'
  self.env={'TASK_ROLE':'dev','TASK_PROMPT':'로그인 기능 설계 작성','OPENAI_API_KEY':'test-secret','OPENAI_MODEL':'test-model','GITHUB_RUN_ID':'123','PUBLISH_CONSENT':'true'}
 def tearDown(self):m.DATA=self.old;self.tmp.cleanup()
 def test_blocks_missing_key_and_public_consent(self):
  for k in ['OPENAI_API_KEY','PUBLISH_CONSENT','OPENAI_MODEL']:
   with self.assertRaises(ValueError):m.begin({**self.env,k:''})
  self.assertFalse(m.DATA.exists())
 def test_execution_persists_review_and_bounded_request(self):
  m.begin(self.env)
  def transport(req):
   body=json.loads(req.data);self.assertEqual(body['max_output_tokens'],2400);self.assertFalse(body['store']);self.assertNotIn('tools',body)
   return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'실행하지 않은 코드 초안'}]}],'usage':{'total_tokens':10}}
  self.assertTrue(m.run(self.env,transport));t=m.load()['tasks'][0];self.assertEqual(t['status'],'review');self.assertEqual(t['usage']['total_tokens'],10)
 def test_failure_and_incomplete_not_success(self):
  m.begin(self.env);self.assertFalse(m.run(self.env,lambda req:(_ for _ in ()).throw(TimeoutError())))
  self.assertEqual(m.load()['tasks'][0]['status'],'failed')
  m.begin(self.env);m.run(self.env,lambda req:{'status':'incomplete','output':[{'type':'message','content':[{'type':'output_text','text':'부분 결과'}]}]});self.assertEqual(m.load()['tasks'][0]['status'],'incomplete')
 def test_secret_in_output_never_published(self):
  m.begin(self.env);m.run(self.env,lambda req:{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'test-secret'}]}]})
  self.assertNotIn('test-secret',m.DATA.read_text());self.assertEqual(m.load()['tasks'][0]['status'],'failed')
if __name__=='__main__':unittest.main()
