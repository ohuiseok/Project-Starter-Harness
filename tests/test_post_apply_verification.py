#!/usr/bin/env python3
from __future__ import annotations
import contextlib,io,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parent.parent; SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts"; sys.path.insert(0,str(SCRIPTS)); sys.path.insert(0,str(ROOT))
import create_post_apply_verification_plan as create_plan
import finalize_post_apply_verification as finalize
import record_post_apply_verification_approval as approve
import run_post_apply_verification as run_verify
import tests.test_spring_milestone_completion as milestone_tests
from spring_milestone_completion import sha
class PostApplyVerificationTests(unittest.TestCase):
 def call(self,module,args):
  stream=io.StringIO()
  with mock.patch.object(sys,"argv",args),contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream): return module.main(),stream.getvalue()
 def fixture(self,parent:Path):
  helper=milestone_tests.SpringMilestoneCompletionTests(); target,_,completion,args=helper.fixture(parent); self.assertEqual(0,helper.run_completion(args)[0]); feature=target/"docs/features/F001"; plan=feature/"post-apply-plan.json"; view=feature/"post-apply-plan.md"; approval=feature/"post-apply-approval.json"; report=feature/"post-apply-report.json"
  self.assertEqual(0,self.call(create_plan,["create","--completion",str(completion),"--target",str(target),"--output",str(plan),"--view",str(view)])[0]); self.assertEqual(0,self.call(approve,["approve","--plan",str(plan),"--target",str(target),"--output",str(approval),"--expected-plan-hash",sha(plan),"--approved-by","user","--approved-at","2026-09-08T00:00:00Z"])[0]); return target,completion,plan,approval,report
 def test_passing_actual_target_verification_finalizes_milestone(self):
  with tempfile.TemporaryDirectory() as d:
   target,completion,plan,approval,report=self.fixture(Path(d)); completed=subprocess.CompletedProcess([],0,"tests ok","")
   with mock.patch.object(run_verify.shutil,"which",return_value="/usr/bin/bwrap"),mock.patch.object(run_verify.subprocess,"run",return_value=completed): code,text=self.call(run_verify,["run","--plan",str(plan),"--approval",str(approval),"--target",str(target),"--output",str(report)])
   self.assertEqual(0,code,text); self.assertEqual(0,self.call(finalize,["finalize","--completion",str(completion),"--verification-report",str(report),"--target",str(target)])[0]); self.assertEqual("APPLIED_AND_VERIFIED",json.loads(completion.read_text())["state"]); self.assertIn("적용 후 실제 검증 완료",(target/"docs/progress.md").read_text())
 def test_changed_target_blocks_execution(self):
  with tempfile.TemporaryDirectory() as d:
   target,_,plan,approval,report=self.fixture(Path(d)); (target/"src/extra.txt").parent.mkdir(exist_ok=True); (target/"src/extra.txt").write_text("drift")
   code,text=self.call(run_verify,["run","--plan",str(plan),"--approval",str(approval),"--target",str(target),"--output",str(report)]); self.assertEqual(1,code); self.assertIn("no longer matches",text); self.assertFalse(report.exists())
 def test_failed_verification_cannot_finalize(self):
  with tempfile.TemporaryDirectory() as d:
   target,completion,plan,approval,report=self.fixture(Path(d)); completed=subprocess.CompletedProcess([],1,"", "tests failed")
   with mock.patch.object(run_verify.shutil,"which",return_value="/usr/bin/bwrap"),mock.patch.object(run_verify.subprocess,"run",return_value=completed): self.assertEqual(0,self.call(run_verify,["run","--plan",str(plan),"--approval",str(approval),"--target",str(target),"--output",str(report)])[0])
   code,text=self.call(finalize,["finalize","--completion",str(completion),"--verification-report",str(report),"--target",str(target)]); self.assertEqual(1,code); self.assertIn("passing current",text)
if __name__=="__main__": unittest.main()
