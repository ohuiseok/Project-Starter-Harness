#!/usr/bin/env python3
from __future__ import annotations
import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
from http_api_spring_mapping import reference
from spring_code_verification_v2 import build_plan,context_hash,render_plan,source_context
import spring_code_verification_v2 as core
import run_spring_code_verification_v2 as runner
import recover_spring_code_verification_v2 as recover

class VerificationV2Tests(unittest.TestCase):
 def cache_value(self,status="READY"):
  return {"kind":"GRADLE","status":status,"roots":["caches","wrapper"],"manifestSha256":"a"*64 if status=="READY" else None,"fileCount":2,"totalBytes":2,"limits":{"maxFiles":30000,"maxBytes":4294967296},"scanComplete":status=="READY","unsafeEntries":[],"credentialSettingsCopied":False}
 def git_value(self):return {"branch":"main","head":"a"*40,"relevantDirtyPaths":[]}
 def fixture(self,root:Path):
  (root/"docs").mkdir();launcher=root/"gradlew";launcher.write_text("#!/bin/sh\n");launcher.chmod(0o755);wrapper=root/"gradle/wrapper";wrapper.mkdir(parents=True);(wrapper/"gradle-wrapper.jar").write_bytes(b"jar");(wrapper/"gradle-wrapper.properties").write_text("distributionUrl=x")
  implementation=root/"docs/implementation.json";implementation.write_text(json.dumps({"target":{"modulePath":"."}}));plan_approval=root/"docs/implementation-approval.json";plan_approval.write_text(json.dumps({"implementationPlan":reference(implementation,root)}));dry=root/"docs/dry.json";dry.write_text(json.dumps({"implementationPlanApproval":reference(plan_approval,root),"generatedFiles":[]}));approval=root/"docs/dry-approval.json";approval.write_text("{}")
  receipt={"dryRun":reference(dry,root)};return dry,approval,receipt
 def test_ready_plan_is_explicit_and_source_free(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);_,approval,receipt=self.fixture(root)
   with mock.patch.object(core,"validate_dry_run_approval",return_value=receipt),mock.patch.object(core,"validate_dry_run"),mock.patch.object(core,"cache",return_value=self.cache_value()),mock.patch.object(core,"git_state",return_value=self.git_value()),mock.patch.object(core,"environment",return_value={"java":{"status":"READY","version":"Java 21"},"bubblewrap":{"status":"READY"}}):plan=build_plan(root,approval,90)
   self.assertTrue(plan["readyForApproval"]);self.assertEqual("DISABLED",plan["effects"]["network"]);self.assertFalse(plan["dependencyCache"]["credentialSettingsCopied"]);self.assertIn("비즈니스 행동 완료",render_plan(plan))
 def test_missing_offline_cache_is_visible_unknown_blocker(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);_,approval,receipt=self.fixture(root)
   with mock.patch.object(core,"validate_dry_run_approval",return_value=receipt),mock.patch.object(core,"validate_dry_run"),mock.patch.object(core,"cache",return_value=self.cache_value("MISSING")),mock.patch.object(core,"git_state",return_value=self.git_value()),mock.patch.object(core,"environment",return_value={"java":{"status":"READY","version":"Java 21"},"bubblewrap":{"status":"READY"}}):plan=build_plan(root,approval)
   self.assertFalse(plan["readyForApproval"]);self.assertTrue(any(i["code"]=="OFFLINE_CACHE_NOT_FIXED" for i in plan["blockers"]))
 def test_secret_like_gradle_property_blocks_copy(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);_,approval,receipt=self.fixture(root);(root/"gradle.properties").write_text("repositoryPassword=do-not-copy-this")
   with mock.patch.object(core,"validate_dry_run_approval",return_value=receipt),mock.patch.object(core,"validate_dry_run"),mock.patch.object(core,"cache",return_value=self.cache_value()),mock.patch.object(core,"git_state",return_value=self.git_value()),mock.patch.object(core,"environment",return_value={"java":{"status":"READY","version":"Java 21"},"bubblewrap":{"status":"READY"}}):plan=build_plan(root,approval)
   self.assertTrue(any(i["code"]=="SENSITIVE_BUILD_INPUT" for i in plan["blockers"]));self.assertFalse(plan["readyForApproval"])
 def test_cache_manifest_detects_content_change_and_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);(base/"caches").mkdir();(base/"wrapper").mkdir();item=base/"caches/a.jar";item.write_bytes(b"one");first=core.cache("GRADLE",base);item.write_bytes(b"two");second=core.cache("GRADLE",base);self.assertNotEqual(first["manifestSha256"],second["manifestSha256"]);(base/"caches/link").symlink_to(item);self.assertEqual("UNSAFE",core.cache("GRADLE",base)["status"])
 def test_resources_are_bound_and_dynamic_build_input_blocks(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);_,approval,receipt=self.fixture(root);resource=root/"src/main/resources/application.yml";resource.parent.mkdir(parents=True);resource.write_text("spring: {}\n");(root/"build.gradle").write_text("apply from: customScript\n")
   with mock.patch.object(core,"validate_dry_run_approval",return_value=receipt),mock.patch.object(core,"validate_dry_run"),mock.patch.object(core,"cache",return_value=self.cache_value()),mock.patch.object(core,"git_state",return_value=self.git_value()),mock.patch.object(core,"environment",return_value={"java":{"status":"READY","version":"Java 21"},"bubblewrap":{"status":"READY"}}):plan=build_plan(root,approval)
   self.assertIn("src/main/resources/application.yml",plan["targetContext"]["files"]);self.assertTrue(any(i["code"]=="DYNAMIC_BUILD_INPUT_UNSUPPORTED" for i in plan["blockers"]))
 def test_sandbox_does_not_mount_host_root(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);workspace=root/"workspace";home=root/"home";workspace.mkdir();home.mkdir()
   with mock.patch.object(runner.shutil,"which",side_effect=lambda name:"/usr/bin/java" if name=="java" else "/usr/bin/bwrap"):command=runner.sandbox(workspace,home,["./gradlew","test"])
   pairs=list(zip(command,command[1:]));self.assertNotIn(("/","/"),pairs);self.assertNotIn("--ro-bind / /"," ".join(command))
 def test_historical_plan_validation_does_not_recompute_environment(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);_,approval,receipt=self.fixture(root)
   with mock.patch.object(core,"validate_dry_run_approval",return_value=receipt),mock.patch.object(core,"validate_dry_run"),mock.patch.object(core,"cache",return_value=self.cache_value()),mock.patch.object(core,"git_state",return_value=self.git_value()),mock.patch.object(core,"environment",return_value={"java":{"status":"READY","version":"Java 21"},"bubblewrap":{"status":"READY"}}):plan=build_plan(root,approval)
   path=root/"docs/verification-plan.json";path.write_text(json.dumps(plan))
   with mock.patch.object(core,"build_plan",side_effect=AssertionError("must not run")):core.validate_plan(plan,path,root,False)
 def test_result_state_distinguishes_failure_and_unknown(self):
  self.assertEqual("PASSED",runner.state(0,""));self.assertEqual("FAILED",runner.state(1,"assertion failed"));self.assertEqual("UNKNOWN",runner.state(1,"Could not resolve dependency"))
 def test_runner_records_pass_without_target_mutation(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/"docs").mkdir();plan_path=root/"docs/plan.json";approval=root/"docs/approval.json";approval.write_text("{}");dry_path=root/"docs/dry.json";dry_path.write_text("{}");generated={"path":"src/test/java/X.java","content":"class X {}\n","mode":0o644};dry={"generatedFiles":[generated]};ctx=context_hash(source_context(root,{generated["path"]}));plan={"readyForApproval":True,"dryRun":reference(dry_path,root),"targetContext":{"files":{},"sha256":ctx},"git":self.git_value(),"dependencyCache":{"kind":"GRADLE"},"command":["./gradlew","test"],"limits":{"timeoutSeconds":30,"maxOutputCharacters":20000},"effects":{}};plan_path.write_text(json.dumps(plan));output=root/"docs/result.json"
   class Process:
    pid=123456;returncode=0
    def communicate(self,timeout=None):return (b"BUILD SUCCESS",None)
    def kill(self):pass
   argv=["run","--plan",str(plan_path),"--approval",str(approval),"--target",str(root),"--output",str(output)]
   with mock.patch.object(sys,"argv",argv),mock.patch.object(runner,"validate_plan",return_value=dry),mock.patch.object(runner,"validate_approval"),mock.patch.object(runner,"copy_cache"),mock.patch.object(runner,"git_state",return_value=self.git_value()),mock.patch.object(runner,"sandbox",return_value=["true"]),mock.patch.object(runner,"process_start_ticks",return_value="99"),mock.patch.object(runner.subprocess,"Popen",return_value=Process()),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,runner.main())
   report=json.loads(output.read_text());self.assertEqual("PASSED",report["result"]["state"]);self.assertFalse(report["targetSourceChanged"]);self.assertFalse((root/core.JOURNAL).exists());self.assertFalse((root/generated["path"]).exists())
 def test_secret_output_becomes_redacted_unknown(self):
  text="password=very-secret-value";self.assertTrue(core.SECRET.search(text));self.assertEqual("[REDACTED]",core.SECRET.sub("[REDACTED]",text));self.assertTrue(core.PII.search("dev@example.com"))
 def test_recovery_removes_only_exact_journal_temp_root(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);temporary=Path(tempfile.mkdtemp(prefix="spring-code-verification-v2-",dir="/var/tmp"));journal=root/core.JOURNAL;journal.parent.mkdir(parents=True);journal.write_text(json.dumps({"springCodeVerificationV2JournalVersion":2,"state":"PREPARED","plan":{},"approval":{},"temporaryRoot":str(temporary),"pid":None,"processStartTicks":None}));argv=["recover","--target",str(root)]
   with mock.patch.object(sys,"argv",argv),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,recover.main())
   self.assertFalse(temporary.exists());self.assertFalse(journal.exists())
if __name__=="__main__":unittest.main()
