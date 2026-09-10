#!/usr/bin/env python3
from __future__ import annotations
import contextlib,io,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
from http_api_spring_mapping import reference
from spring_code_dry_run_v2 import build_report
from spring_code_renderability_v2 import assess
import tests.test_spring_implementation_plan_v2 as plan_tests
import record_spring_code_dry_run_v2_approval as approve
import validate_spring_code_dry_run_v2_approval as validate_approval

class CodeDryRunV2Tests(unittest.TestCase):
 def fixture(self,root:Path):
  plan,_,_=plan_tests.PlanV2Tests().fixture(root);(root/"build.gradle").write_text("implementation 'org.springframework.boot:spring-boot-starter-web'\nimplementation 'org.springframework.boot:spring-boot-starter-validation'\ntestImplementation 'org.springframework.boot:spring-boot-starter-test'")
  approval=root/"docs/plan-approval.json";approval.write_text("{}")
  gate_path=root/"docs/renderability.json";gate=assess(plan,root,reference(approval,root));gate_path.write_text(json.dumps(gate));candidate=root/"candidate";candidate.mkdir()
  for component in plan["components"]:
   path=candidate/component["target"]["path"];path.parent.mkdir(parents=True,exist_ok=True);package=path.as_posix().split("/java/",1)[1].rsplit("/",1)[0].replace("/",".");name=component["target"]["typeName"]
   if component["role"]=="CONTROLLER":
    symbols=[]
    for symbol in component["symbols"]:
     annotation={"GET":"GetMapping","POST":"PostMapping","PUT":"PutMapping","PATCH":"PatchMapping","DELETE":"DeleteMapping"}[symbol["httpMethod"]];status=" CREATED " if symbol["httpMethod"]=="POST" else ""
     symbols.append(f'@{annotation}("{symbol["httpPath"]}") public void {symbol["operationId"]}() {{ String status = "{status}"; }}')
    body="@RestController public class "+name+" {"+"".join(symbols)+"}"
   elif component["role"]=="APPLICATION_SERVICE":body="@Service public class "+name+" {"+"".join(f"public void {op}() {{}}" for op in component["operationRefs"])+"}"
   else:
    op=component["operationRefs"][0];link=next(i for i in plan["operationLinks"] if i["operationId"]==op);trace=" ".join(component["requirementRefs"]);body=f'public class {name} {{ @Test void verifies() {{ String contract = "{link["method"]} {link["path"]} {trace}"; assertTrue(true); }} }}'
   path.write_text(f"package {package};\n{body}\n")
  return plan,approval,gate_path,gate,candidate
 def report(self,root):
  plan,approval,gate_path,gate,candidate=self.fixture(root);return plan,candidate,build_report(plan,reference(approval,root),reference(gate_path,root),gate,candidate,root)
 def test_create_candidate_is_reviewable_without_effects(self):
  with tempfile.TemporaryDirectory() as d:
   plan,_,report=self.report(Path(d));self.assertTrue(report["readyForVerificationApproval"]);self.assertEqual(len(plan["components"]),report["summary"]["creates"]);self.assertEqual("NOT_PROVEN",report["verification"]["businessBehavior"]);self.assertFalse(report["effects"]["sourceChanged"])
 def test_extra_missing_occupied_and_semantic_tampering_block(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,approval,gate_path,gate,candidate=self.fixture(root);first=next(iter(candidate.rglob("*.java")));first.write_text(first.read_text().replace("@RestController",""));extra=candidate/"src/main/java/x/Extra.java";extra.parent.mkdir(parents=True,exist_ok=True);extra.write_text("class Extra {}")
   report=build_report(plan,reference(approval,root),reference(gate_path,root),gate,candidate,root);reasons={i["reason"] for i in report["blockers"]};self.assertIn("candidate-file-not-in-create-plan",reasons);self.assertIn("missing-role-marker",reasons);self.assertFalse(report["readyForVerificationApproval"])
 def test_update_file_stays_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,approval,gate_path,gate,candidate=self.fixture(root);plan["components"][0]["fileAction"]="UPDATE_FILE";report=build_report(plan,reference(approval,root),reference(gate_path,root),dict(gate,readyForCodeDryRun=True),candidate,root);self.assertTrue(any("UPDATE_FILE" in i["reason"] for i in report["blockers"]))
 def test_exact_dry_run_approval_authorizes_verification_not_apply(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);_,_,report=self.report(root);report_path=root/"docs/code.json";view=report_path.with_suffix(".md");report_path.write_text(json.dumps(report));view.write_text("review");output=root/"docs/code-approval.json";argv=["approve","--report",str(report_path),"--view",str(view),"--target",str(root),"--output",str(output),"--approved-by","user","--approved-at","2026-09-10T00:00:00+09:00"]
   with mock.patch.object(sys,"argv",argv),mock.patch.object(approve,"validate_report"),mock.patch.object(approve,"render",return_value="review"),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,approve.main())
   receipt=json.loads(output.read_text());self.assertTrue(receipt["effects"]["isolatedVerificationAuthorized"]);self.assertFalse(receipt["effects"]["applyAuthorized"])
   with mock.patch.object(validate_approval,"validate_report"),mock.patch.object(validate_approval,"render",return_value="review"):self.assertEqual(receipt,validate_approval.validate_approval(root,output))
if __name__=="__main__":unittest.main()
