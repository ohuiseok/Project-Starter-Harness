#!/usr/bin/env python3
from __future__ import annotations
import json,tempfile,unittest
from pathlib import Path
from unittest import mock
import sys
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
import post_apply_verification_v2 as core
import recover_post_apply_verification_v2 as recover
import run_post_apply_verification_v2 as runner
class PostApplyV2Tests(unittest.TestCase):
 def fixture(self,root:Path):
  (root/"docs").mkdir();(root/"gradlew").write_text("#!/bin/sh\n");(root/"gradlew").chmod(0o755);(root/"src/main").mkdir(parents=True);(root/"src/main/A.java").write_text("class A {}\n");result=root/"docs/apply.json";result.write_text(json.dumps({"transactionId":"spring-code-v2-test"}));return result
 def test_plan_uses_structured_networkless_single_command(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);result=self.fixture(root)
   with mock.patch.object(core,"validate_apply_result"),mock.patch.object(core,"reference",return_value={"path":"docs/apply.json","sha256":"a"*64}),mock.patch.object(core,"cache_evidence",return_value={"kind":"GRADLE","status":"READY"}),mock.patch.object(core,"git_state",return_value={"branch":"main","head":"b"*40,"relevantDirtyPaths":[]}):plan=core.build_plan(root,result)
   self.assertEqual("./gradlew",plan["command"]["executable"]);self.assertEqual(["--offline","--no-daemon","test"],plan["command"]["arguments"]);self.assertEqual("DISABLED",plan["effects"]["network"]);self.assertTrue(plan["readyForApproval"])
 def test_missing_cache_blocks_approval(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);result=self.fixture(root)
   with mock.patch.object(core,"validate_apply_result"),mock.patch.object(core,"reference",return_value={"path":"docs/apply.json","sha256":"a"*64}),mock.patch.object(core,"cache_evidence",return_value={"kind":"GRADLE","status":"MISSING"}),mock.patch.object(core,"git_state",return_value={}):plan=core.build_plan(root,result)
   self.assertFalse(plan["readyForApproval"]);self.assertEqual("DEPENDENCY_CACHE_MISSING",plan["blockers"][0]["code"])
 def test_non_executable_wrapper_is_visible_blocker(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);result=self.fixture(root);(root/"gradlew").chmod(0o644)
   with mock.patch.object(core,"validate_apply_result"),mock.patch.object(core,"reference",return_value={"path":"docs/apply.json","sha256":"a"*64}),mock.patch.object(core,"cache_evidence",return_value={"kind":"GRADLE","status":"READY"}),mock.patch.object(core,"git_state",return_value={}):plan=core.build_plan(root,result)
   self.assertEqual("WRAPPER_NOT_EXECUTABLE",plan["blockers"][0]["code"]);self.assertFalse(plan["readyForApproval"])
 def test_failure_categories_distinguish_test_environment_timeout_and_secret(self):
  self.assertEqual(("FAILED","TEST_OR_BUILD_FAILURE"),runner.classify(1,"tests failed",False,False));self.assertEqual(("UNKNOWN","OFFLINE_DEPENDENCY_OR_INFRASTRUCTURE"),runner.classify(1,"Could not resolve",False,False));self.assertEqual(("UNKNOWN","TIMEOUT"),runner.classify(124,"",True,False));self.assertEqual(("UNKNOWN","SENSITIVE_OUTPUT"),runner.classify(0,"",False,True))
 def test_result_view_keeps_completion_as_separate_approval(self):
  import render_post_apply_verification_result_v2 as render
  value={"state":"VERIFIED","category":"TESTS_PASSED","result":{"exitCode":0,"timedOut":False,"unexpectedMutation":False},"log":{"truncated":False,"redacted":False}}
  self.assertIn("아직 승인되지 않음",render.render(value));self.assertIn("별도 검토",render.render(value))
 def test_recovery_never_reexecutes_command(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);journal=root/core.JOURNAL;journal.parent.mkdir(parents=True);temp=Path(tempfile.mkdtemp(prefix="post-apply-v2-",dir="/var/tmp"));marker=temp/".starter-harness-post-apply-v2.json";marker.write_text("owned");journal.write_text(json.dumps({"postApplyVerificationV2JournalVersion":1,"temporaryRoot":str(temp),"temporaryMarkerSha256":__import__("hashlib").sha256(b"owned").hexdigest(),"pid":None,"processStartTicks":None}))
   with mock.patch.object(sys,"argv",["recover","--target",str(root)]),mock.patch.object(recover,"apply_lock",mock.MagicMock(return_value=__import__("contextlib").nullcontext())):self.assertEqual(0,recover.main())
   self.assertFalse(temp.exists());self.assertFalse(journal.exists())
 def test_recovery_rejects_unsafe_temporary_path(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);journal=root/core.JOURNAL;journal.parent.mkdir(parents=True);journal.write_text(json.dumps({"postApplyVerificationV2JournalVersion":1,"temporaryRoot":"/tmp/not-owned","pid":None,"processStartTicks":None}))
   with mock.patch.object(sys,"argv",["recover","--target",str(root)]),mock.patch.object(recover,"apply_lock",mock.MagicMock(return_value=__import__("contextlib").nullcontext())):self.assertEqual(1,recover.main())
if __name__=="__main__":unittest.main()
