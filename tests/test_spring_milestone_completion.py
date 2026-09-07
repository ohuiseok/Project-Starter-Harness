#!/usr/bin/env python3
from __future__ import annotations
import contextlib,copy,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parent.parent; SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts"; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(SCRIPTS))
import complete_spring_milestone as completion_cli  # noqa: E402
import tests.test_spring_code_apply as apply_tests  # noqa: E402
from spring_milestone_completion import candidate_assessment,target_path  # noqa: E402
from tests.test_feature_specs import project_brief,refresh_approval  # noqa: E402

class SpringMilestoneCompletionTests(unittest.TestCase):
    def fixture(self,parent:Path):
        helper=apply_tests.SpringCodeApplyTests(); target,dry,verification,_,apply_args=helper.fixture(parent); self.assertEqual(0,helper.run_apply(apply_args)[0])
        brief=project_brief(); brief["featureCandidates"].append({"id":"F002","name":"List leave requests","userValue":"An employee sees submitted requests.","recommendationReason":"It completes the next read flow.","dependsOn":["F001"],"blockingUnknownIds":[],"recommendedOrder":2,"status":"APPROVED"}); brief["featureCandidates"].append({"id":"F003","name":"Approve leave","userValue":"A manager decides requests.","recommendationReason":"It follows request visibility.","dependsOn":["F002"],"blockingUnknownIds":[],"recommendedOrder":3,"status":"APPROVED"}); refresh_approval(brief)
        brief_path=target/"docs/project-brief.json"; brief_path.write_text(json.dumps(brief)); feature=target/"docs/evidence/featureSpec.json"; transaction=next((target/".starter-harness/implementation-transactions").iterdir()).name; output=target/"docs/features/F001/completion.json"
        args=["complete","--project-brief",str(brief_path),"--feature",str(feature),"--dry-run",str(dry),"--verification-report",str(verification),"--transaction-id",transaction,"--completed-at","2026-09-07T00:00:00Z","--target",str(target),"--output",str(output)]
        return target,dry,output,args
    def run_completion(self,args):
        stream=io.StringIO()
        with mock.patch.object(sys,"argv",args),contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream): return completion_cli.main(),stream.getvalue()
    def test_applied_feature_closes_with_requirement_evidence_and_next_recommendation(self):
        with tempfile.TemporaryDirectory() as d:
            target,_,output,args=self.fixture(Path(d)); before={p:p.read_bytes() for p in target.glob("src/**/*.java")}; code,text=self.run_completion(args); self.assertEqual(0,code,text)
            report=json.loads(output.read_text()); self.assertEqual("APPLIED_PREVERIFIED",report["state"]); self.assertEqual(2,report["summary"]["requirementsPassed"])
            progress=json.loads((target/"docs/progress.json").read_text()); self.assertEqual("F002",progress["current"]["recommendedFeatureId"]); self.assertEqual(["F002"],[item["featureId"] for item in progress["nextCandidates"]]); markdown=(target/"docs/progress.md").read_text(); self.assertIn("원하는 기능을 자연어로 직접 입력",markdown); self.assertIn(f"사용자 가치: {report['userValue']}",markdown); self.assertIn("적용 후 런타임 검증 미실행",markdown); self.assertEqual(before,{p:p.read_bytes() for p in target.glob("src/**/*.java")})
    def test_applied_file_drift_blocks_false_completion(self):
        with tempfile.TemporaryDirectory() as d:
            target,dry,output,args=self.fixture(Path(d)); relative=json.loads(dry.read_text())["generatedFiles"][0]["path"]; (target/relative).write_text("changed"); code,text=self.run_completion(args); self.assertEqual(1,code); self.assertIn("materialization changed",text); self.assertFalse(output.exists()); self.assertFalse((target/"docs/progress.json").exists())
    def test_duplicate_feature_completion_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            target,_,_,args=self.fixture(Path(d)); self.assertEqual(0,self.run_completion(args)[0]); before=(target/"docs/progress.json").read_bytes(); second=target/"docs/features/F001/completion-2.json"; args[args.index("--output")+1]=str(second); code,text=self.run_completion(args); self.assertEqual(1,code); self.assertIn("already completed",text); self.assertEqual(before,(target/"docs/progress.json").read_bytes()); self.assertFalse(second.exists())
    def test_stale_verification_evidence_blocks_completion(self):
        with tempfile.TemporaryDirectory() as d:
            target,_,output,args=self.fixture(Path(d)); verification=Path(args[args.index("--verification-report")+1]); verification.write_text(verification.read_text()+" "); code,text=self.run_completion(args); self.assertEqual(1,code); self.assertIn("evidence changed",text); self.assertFalse(output.exists())
    def test_partial_progress_write_failure_rolls_back_all_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            target,_,output,args=self.fixture(Path(d)); real=completion_cli.atomic_write_bytes; calls=0
            def fail(data,path):
                nonlocal calls; calls+=1
                if calls==2: raise OSError("injected")
                return real(data,path)
            with mock.patch.object(completion_cli,"atomic_write_bytes",side_effect=fail): code,text=self.run_completion(args)
            self.assertEqual(1,code); self.assertFalse(output.exists()); self.assertFalse((target/"docs/progress.json").exists()); self.assertFalse((target/"docs/progress.md").exists())
    def test_symlinked_progress_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            root=Path(d); (root/"docs").symlink_to(outside,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"symbolic link"): target_path(root,"docs/progress.json","progress ledger")
    def test_candidate_policy_ignores_finished_and_implementing_and_accepts_resolved_unknown(self):
        project={"unknowns":[{"id":"U1","status":"RESOLVED"}],"featureCandidates":[
            {"id":"F001","name":"done","userValue":"done","recommendationReason":"done","dependsOn":[],"blockingUnknownIds":[],"recommendedOrder":1,"status":"VERIFIED"},
            {"id":"F002","name":"work","userValue":"work","recommendationReason":"work","dependsOn":[],"blockingUnknownIds":[],"recommendedOrder":2,"status":"IMPLEMENTING"},
            {"id":"F003","name":"next","userValue":"next","recommendationReason":"next","dependsOn":[],"blockingUnknownIds":["U1"],"recommendedOrder":3,"status":"DRAFT"}]}
        eligible,blocked=candidate_assessment(project,set()); self.assertEqual(["F003"],[item["featureId"] for item in eligible]); self.assertEqual(["F002"],[item["featureId"] for item in blocked])
    def test_interrupted_completion_can_be_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            target,_,output,args=self.fixture(Path(d)); real=completion_cli.atomic_write_bytes
            def interrupt(data,path):
                if Path(path)==target/"docs/progress.json": raise KeyboardInterrupt()
                return real(data,path)
            with mock.patch.object(completion_cli,"atomic_write_bytes",side_effect=interrupt),self.assertRaises(KeyboardInterrupt): self.run_completion(args)
            record=next((target/".starter-harness/milestone-completion-transactions").glob("*/transaction.json")); result=completion_cli.recover(target,record.parent.name)
            self.assertEqual("RECOVERED",result["state"]); self.assertFalse(output.exists()); self.assertFalse((target/"docs/progress.json").exists())

if __name__=="__main__": unittest.main()
