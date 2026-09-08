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
from spring_milestone_completion import sha,validate_progress
from validate_feature_specs import load_object
class PostApplyVerificationTests(unittest.TestCase):
 def call(self,module,args):
  stream=io.StringIO()
  with mock.patch.object(sys,"argv",args),contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream): return module.main(),stream.getvalue()
 def fixture(self,parent:Path):
  helper=milestone_tests.SpringMilestoneCompletionTests(); target,_,completion,args=helper.fixture(parent); self.assertEqual(0,helper.run_completion(args)[0]); feature=target/"docs/features/F001"; plan=feature/"post-apply-plan.json"; view=feature/"post-apply-plan.md"; approval=feature/"post-apply-approval.json"; report=feature/"post-apply-report.json"
  with mock.patch.object(create_plan,"cache_info",return_value={"kind":"GRADLE","status":"READY"}),mock.patch("post_apply_verification.cache_info",return_value={"kind":"GRADLE","status":"READY"}):
   self.assertEqual(0,self.call(create_plan,["create","--completion",str(completion),"--target",str(target),"--output",str(plan),"--view",str(view)])[0]); self.assertEqual(0,self.call(approve,["approve","--plan",str(plan),"--view",str(view),"--target",str(target),"--output",str(approval),"--expected-plan-hash",sha(plan),"--approved-by","user","--approved-at","2026-09-08T00:00:00Z"])[0])
  return target,completion,plan,approval,report
 def test_passing_actual_target_verification_finalizes_milestone(self):
  with tempfile.TemporaryDirectory() as d:
   target,completion,plan,approval,report=self.fixture(Path(d)); completed=subprocess.CompletedProcess([],0,"tests ok","")
   with mock.patch.object(run_verify.shutil,"which",return_value="/usr/bin/bwrap"),mock.patch.object(run_verify,"copy_dependency_cache"),mock.patch.object(run_verify.subprocess,"run",return_value=completed): code,text=self.call(run_verify,["run","--plan",str(plan),"--approval",str(approval),"--target",str(target),"--output",str(report)])
   self.assertEqual(0,code,text); self.assertEqual(0,self.call(finalize,["finalize","--completion",str(completion),"--verification-report",str(report),"--target",str(target)])[0]); self.assertEqual("APPLIED_AND_VERIFIED",json.loads(completion.read_text())["state"]); self.assertIn("적용 상태 기반 격리 테스트 완료",(target/"docs/progress.md").read_text()); report.write_text(report.read_text()+" ")
   with self.assertRaisesRegex(ValueError,"post-apply verification evidence changed"): validate_progress(load_object(target/"docs/progress.json"),target)
 def test_changed_target_blocks_execution(self):
  with tempfile.TemporaryDirectory() as d:
   target,_,plan,approval,report=self.fixture(Path(d)); (target/"src/extra.txt").parent.mkdir(exist_ok=True); (target/"src/extra.txt").write_text("drift")
   code,text=self.call(run_verify,["run","--plan",str(plan),"--approval",str(approval),"--target",str(target),"--output",str(report)]); self.assertEqual(1,code); self.assertIn("no longer matches",text); self.assertFalse(report.exists())
 def test_failed_verification_cannot_finalize(self):
  with tempfile.TemporaryDirectory() as d:
   target,completion,plan,approval,report=self.fixture(Path(d)); completed=subprocess.CompletedProcess([],1,"", "tests failed")
   with mock.patch.object(run_verify.shutil,"which",return_value="/usr/bin/bwrap"),mock.patch.object(run_verify,"copy_dependency_cache"),mock.patch.object(run_verify.subprocess,"run",return_value=completed): self.assertEqual(0,self.call(run_verify,["run","--plan",str(plan),"--approval",str(approval),"--target",str(target),"--output",str(report)])[0])
   code,text=self.call(finalize,["finalize","--completion",str(completion),"--verification-report",str(report),"--target",str(target)]); self.assertEqual(1,code); self.assertIn("passing current",text)
 def test_stale_review_view_blocks_approval(self):
  with tempfile.TemporaryDirectory() as d:
   helper=milestone_tests.SpringMilestoneCompletionTests(); target,_,completion,args=helper.fixture(Path(d)); self.assertEqual(0,helper.run_completion(args)[0]); feature=target/"docs/features/F001"; plan=feature/"plan.json"; view=feature/"plan.md"; approval=feature/"approval.json"; self.assertEqual(0,self.call(create_plan,["create","--completion",str(completion),"--target",str(target),"--output",str(plan),"--view",str(view)])[0]); view.write_text("stale")
   code,text=self.call(approve,["approve","--plan",str(plan),"--view",str(view),"--target",str(target),"--output",str(approval),"--expected-plan-hash",sha(plan),"--approved-by","user","--approved-at","2026-09-08T00:00:00Z"]); self.assertEqual(1,code); self.assertIn("stale",text)
 def test_secret_like_output_is_redacted_and_not_finalizable(self):
  with tempfile.TemporaryDirectory() as d:
   target,_,plan,approval,report=self.fixture(Path(d)); completed=subprocess.CompletedProcess([],0,"token=super-secret-value","")
   with mock.patch.object(run_verify.shutil,"which",return_value="/usr/bin/bwrap"),mock.patch.object(run_verify,"copy_dependency_cache"),mock.patch.object(run_verify.subprocess,"run",return_value=completed): self.assertEqual(0,self.call(run_verify,["run","--plan",str(plan),"--approval",str(approval),"--target",str(target),"--output",str(report)])[0])
   value=json.loads(report.read_text()); self.assertEqual("UNKNOWN",value["result"]["state"]); self.assertNotIn("super-secret",report.read_text())
 def test_bubblewrap_hides_environment_and_user_home(self):
  if not run_verify.shutil.which("bwrap"): self.skipTest("bubblewrap unavailable")
  with tempfile.TemporaryDirectory(prefix="bwrap-contract-",dir="/var/tmp") as d:
   root=Path(d); workspace=root/"workspace"; home=root/"home"; workspace.mkdir(); home.mkdir()
   cmd=["bwrap","--die-with-parent","--unshare-all","--ro-bind","/","/","--tmpfs","/root","--tmpfs","/home","--tmpfs","/etc","--tmpfs","/var/lib","--tmpfs","/var/tmp","--tmpfs","/tmp","--tmpfs","/run","--dir","/run/workspace","--dir","/run/workhome","--dev","/dev","--proc","/proc","--bind",str(workspace),"/run/workspace","--bind",str(home),"/run/workhome","--chdir","/run/workspace","--clearenv","--setenv","PATH","/usr/bin:/bin","--setenv","HOME","/run/workhome","--","/bin/sh","-c",'test -z "$HARNESS_TEST_SECRET" && test ! -e /root/.ssh && test ! -e /var/tmp/bwrap-contract-secret']
   completed=subprocess.run(cmd,env={**__import__("os").environ,"HARNESS_TEST_SECRET":"must-not-leak"},capture_output=True,text=True)
   if completed.returncode and "Operation not permitted" in completed.stderr: self.skipTest("bubblewrap namespaces unavailable")
   self.assertEqual(0,completed.returncode,completed.stderr)
 def test_missing_dependency_cache_is_reported_before_approval(self):
  with tempfile.TemporaryDirectory() as d:
   helper=milestone_tests.SpringMilestoneCompletionTests(); target,_,completion,args=helper.fixture(Path(d)); self.assertEqual(0,helper.run_completion(args)[0]); feature=target/"docs/features/F001"; plan=feature/"plan.json"; view=feature/"plan.md"
   with mock.patch.object(create_plan,"cache_info",return_value={"kind":"GRADLE","status":"MISSING"}): code,text=self.call(create_plan,["create","--completion",str(completion),"--target",str(target),"--output",str(plan),"--view",str(view)])
   self.assertEqual(0,code,text); self.assertIn("READY_FOR_APPROVAL: no",text); self.assertIn("현재 실행 불가",view.read_text())
 def test_plan_and_view_creation_rolls_back_partial_failure(self):
  with tempfile.TemporaryDirectory() as d:
   helper=milestone_tests.SpringMilestoneCompletionTests(); target,_,completion,args=helper.fixture(Path(d)); self.assertEqual(0,helper.run_completion(args)[0]); feature=target/"docs/features/F001"; plan=feature/"plan.json"; view=feature/"plan.md"; real=create_plan.atomic_write_bytes; calls=0
   def fail(data,path):
    nonlocal calls; calls+=1
    if calls==2: raise OSError("injected")
    return real(data,path)
   with mock.patch.object(create_plan,"cache_info",return_value={"kind":"GRADLE","status":"READY"}),mock.patch.object(create_plan,"atomic_write_bytes",side_effect=fail): code,_=self.call(create_plan,["create","--completion",str(completion),"--target",str(target),"--output",str(plan),"--view",str(view)])
   self.assertEqual(1,code); self.assertFalse(plan.exists()); self.assertFalse(view.exists())
if __name__=="__main__": unittest.main()
