#!/usr/bin/env python3
from __future__ import annotations
import contextlib, hashlib, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parent.parent; SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts"
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(SCRIPTS))
import apply_approved_spring_code as code_apply  # noqa: E402
import record_spring_code_apply_approval as record_approval  # noqa: E402
from render_spring_code_apply_review import render as render_review  # noqa: E402
import tests.test_spring_code_dry_run as dry_tests  # noqa: E402

class SpringCodeApplyTests(unittest.TestCase):
    def fixture(self,parent:Path):
        helper=dry_tests.SpringCodeDryRunTests(); target,dry_run,verification_approval,verification_report=helper.verification_fixture(parent)
        self.assertEqual(0,helper.run_verification(target,dry_run,verification_approval,verification_report,0)[0])
        subprocess.run(["git","config","user.email","test@example.com"],cwd=target,check=True); subprocess.run(["git","config","user.name","Test"],cwd=target,check=True)
        subprocess.run(["git","add","-A"],cwd=target,check=True); subprocess.run(["git","commit","-qm","evidence"],cwd=target,check=True)
        dry=json.loads(dry_run.read_text()); verification=json.loads(verification_report.read_text())
        approval={"springCodeApplyApprovalVersion":1,"approved":True,"verificationReportSha256":code_apply.sha(verification_report),"dryRunReportSha256":code_apply.sha(dry_run),"target":str(target),"targetContextSha256":verification["targetContextSha256"],"baselineSha256":None,"files":sorted(dry["plannedChanges"]["desiredManifest"]["files"]),"approvedBy":"test-user","approvedAt":"2026-09-04T00:00:00Z"}
        approval_path=target/"docs/features/F001/code-apply-approval.json"; approval_path.write_text(json.dumps(approval))
        args=["apply","--dry-run",str(dry_run),"--verification-report",str(verification_report),"--approval",str(approval_path),"--target",str(target)]
        return target,dry_run,verification_report,approval_path,args
    def run_apply(self,args):
        stream=io.StringIO()
        with mock.patch.object(sys,"argv",args),contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream): return code_apply.main(),stream.getvalue()
    def test_verified_code_is_applied_with_cumulative_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            target,dry,_,_,args=self.fixture(Path(d)); code,out=self.run_apply(args); self.assertEqual(0,code,out)
            report=json.loads(dry.read_text()); self.assertTrue(all((target/item["path"]).is_file() for item in report["generatedFiles"]))
            baseline=json.loads((target/code_apply.BASELINE).read_text()); self.assertEqual("SPRING_IMPLEMENTATION",baseline["artifactKind"]); self.assertEqual(1,len(baseline["appliedSlices"])); self.assertIn("POST_APPLY_VERIFICATION: NOT_RUN",out)
    def test_exact_approval_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            target,_,_,approval,args=self.fixture(Path(d)); value=json.loads(approval.read_text()); value["files"]=[]; approval.write_text(json.dumps(value)); code,out=self.run_apply(args); self.assertEqual(1,code); self.assertIn("does not match",out); self.assertFalse((target/code_apply.BASELINE).exists())
    def test_relevant_dirty_change_blocks_but_unrelated_document_warns(self):
        with tempfile.TemporaryDirectory() as d:
            target,dry,_,_,args=self.fixture(Path(d)); generated=json.loads(dry.read_text())["generatedFiles"][0]["path"]; path=target/generated; path.parent.mkdir(parents=True); path.write_text("dirty"); code,out=self.run_apply(args); self.assertEqual(1,code); self.assertIn("changed after verification",out)
        with tempfile.TemporaryDirectory() as d:
            target,_,_,_,args=self.fixture(Path(d)); (target/"notes.txt").write_text("unrelated"); code,out=self.run_apply(args); self.assertEqual(0,code,out); self.assertIn("notes.txt",out)
    def test_partial_failure_rolls_back_and_records_recovered_state(self):
        with tempfile.TemporaryDirectory() as d:
            target,_,_,_,args=self.fixture(Path(d)); real=os.replace; count=0
            def fail(source,destination):
                nonlocal count
                if "/commit/" in str(source):
                    count+=1
                    if count==2: raise OSError("injected")
                return real(source,destination)
            with mock.patch.object(code_apply.os,"replace",side_effect=fail): code,out=self.run_apply(args)
            self.assertEqual(1,code); self.assertIn("rolled back",out); self.assertFalse((target/code_apply.BASELINE).exists()); records=list((target/".starter-harness/implementation-transactions").glob("*/transaction.json")); self.assertEqual("RECOVERED",json.loads(records[0].read_text())["state"])
    def test_pending_transaction_blocks_new_apply(self):
        with tempfile.TemporaryDirectory() as d:
            target,_,_,_,args=self.fixture(Path(d)); record=target/".starter-harness/implementation-transactions/pending/transaction.json"; record.parent.mkdir(parents=True); record.write_text('{"state":"PREPARED"}'); code,out=self.run_apply(args); self.assertEqual(1,code); self.assertIn("requires recovery",out)
    def test_baseline_merge_preserves_previous_feature_files(self):
        existing={"files":{"src/main/java/Old.java":"a"*64},"modes":{"src/main/java/Old.java":420},"appliedSlices":[{"files":["src/main/java/Old.java"]}]}
        manifest={"files":{"src/main/java/New.java":"b"*64},"modes":{"src/main/java/New.java":420}}
        merged=code_apply.merged_baseline(existing,manifest,"c"*64,"d"*64); self.assertEqual({"src/main/java/Old.java","src/main/java/New.java"},set(merged["files"])); self.assertEqual(2,len(merged["appliedSlices"]))
    def test_apply_review_prioritizes_scope_safety_and_exclusions(self):
        with tempfile.TemporaryDirectory() as d:
            target,dry,verification,_,_=self.fixture(Path(d)); document=json.loads(dry.read_text()); verified=json.loads(verification.read_text()); view=render_review(document,verified,{"notes.txt"}); self.assertIn("## 적용 준비",view); self.assertIn("격리 컴파일·자동 테스트: 통과",view); self.assertIn("경고(적용 범위 밖): `notes.txt`",view); self.assertIn("Git commit·push 실행 안 함",view)
    def test_user_approval_is_recorded_without_manual_json_editing(self):
        with tempfile.TemporaryDirectory() as d:
            target,dry,verification,manual,_=self.fixture(Path(d)); manual.unlink(); output=target/"docs/features/F001/recorded-apply-approval.json"; argv=["record","--dry-run",str(dry),"--verification-report",str(verification),"--target",str(target),"--output",str(output),"--expected-verification-hash",code_apply.sha(verification),"--approved-by","test-user","--approved-at","2026-09-04T00:00:00Z"]
            with mock.patch.object(sys,"argv",argv),contextlib.redirect_stdout(io.StringIO()): self.assertEqual(0,record_approval.main())
            value=json.loads(output.read_text()); self.assertTrue(value["approved"]); self.assertEqual(sorted(json.loads(dry.read_text())["plannedChanges"]["desiredManifest"]["files"]),value["files"])

if __name__=="__main__": unittest.main()
