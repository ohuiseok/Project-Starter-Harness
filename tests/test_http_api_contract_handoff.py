#!/usr/bin/env python3
from __future__ import annotations
import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parent.parent; SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts"; sys.path[:0]=[str(SCRIPTS),str(ROOT)]
import http_api_route_decision as decision
import prepare_http_api_contract_handoff as handoff
import validate_http_api_contract_handoff as validate_handoff
import record_design_route_approval as approve_route
from spring_milestone_completion import sha
from validate_feature_specs import approval_content_hash
import tests.test_http_api_route_decision as decision_fixtures

class HttpApiContractHandoffTests(unittest.TestCase):
 def invoke(self,module,args):
  stream=io.StringIO()
  with mock.patch.object(sys,"argv",args),contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream): code=module.main()
  return code,stream.getvalue()
 def fixture(self,parent,approve=True):
  helper=decision_fixtures.HttpApiRouteDecisionTests(methodName="test_selection_preview_does_not_change_route"); root,current,report,candidate=helper.existing_api_fixture(parent,"REUSE"); route=json.loads(current.read_text()); profile=root/"docs/project-profile.json"; technology=json.loads(profile.read_text()); technology["decisions"]["view"]={"status":"NOW","option":"view.separate-client"}; profile.write_text(json.dumps(technology)); route["inputs"]["technologyProfile"]["sha256"]=sha(profile)
  for item in route["routes"]:
   if item["disposition"]=="UNKNOWN": item.update({"disposition":"CREATE","artifactPath":f"docs/features/F001/contracts/{item['contractId']}/metadata.json"})
   if item["disposition"] in {"CREATE","EXTEND","REUSE"}: item.update({"source":"USER_STATED","confirmedByUser":True,"reason":"사용자가 현재 설계 경로를 확인함"})
  current.write_text(json.dumps(route,ensure_ascii=False,indent=2)+"\n"); report.unlink(); report.with_suffix('.md').unlink(); feature=root/"docs/features/F001/spec.json"; code,text=self.invoke(decision_fixtures.discovery,["discover","--feature",str(feature),"--profile",str(profile),"--target",str(root),"--output",str(report),"--view",str(report.with_suffix('.md'))]); self.assertEqual(0,code,text); candidate=json.loads(report.read_text())["candidates"][0]; extra=["--disposition","REUSE","--selection-source","CANDIDATE_SELECTED","--reason-code","EXISTING_CONTRACT_SELECTED","--reason","검증된 기존 계약을 재사용","--candidate-id",candidate["candidateId"]]; code,text=helper.prepare_decision(root,current,report,extra); self.assertEqual(0,code,text); _,decision_report,next_route,approval=helper.decision_paths(root); code,text=self.invoke(decision,["decision","approve","--report",str(decision_report),"--view",str(decision_report.with_suffix('.md')),"--output",str(approval),"--target",str(root),"--expected-report-hash",sha(decision_report)]); self.assertEqual(0,code,text); code,text=self.invoke(decision,["decision","apply","--report",str(decision_report),"--approval",str(approval),"--target",str(root)]); self.assertEqual(0,code,text)
  feature=root/"docs/features/F001/spec.json"; project=root/"docs/project-brief.json"; profile=root/"docs/project-profile.json"
  if approve:
   route_value=json.loads(next_route.read_text()); code,text=self.invoke(approve_route,["approve","--route",str(next_route),"--feature",str(feature),"--project-brief",str(project),"--profile",str(profile),"--target",str(root),"--expected-route-hash",approval_content_hash(route_value),"--approved-by","user","--approved-at","2026-09-09T12:00:00+09:00"]); self.assertEqual(0,code,text)
  application=root/".starter-harness/http-api-route-decisions/F001-http-api.json"; return root,next_route,feature,project,profile,application
 def args(self,root,route,feature,project,profile,application):
  output=root/"docs/features/F001/http-api-contract-handoff.json"; return ["handoff","--application",str(application),"--route",str(route),"--feature",str(feature),"--project-brief",str(project),"--profile",str(profile),"--target",str(root),"--contract-id","http-api","--output",str(output),"--view",str(output.with_suffix('.md'))],output
 def test_approved_reuse_route_creates_ready_immutable_handoff(self):
  with tempfile.TemporaryDirectory() as d:
   values=self.fixture(Path(d)); args,output=self.args(*values); code,text=self.invoke(handoff,args); self.assertEqual(0,code,text); value=json.loads(output.read_text()); self.assertEqual(("READY","REUSE_EXISTING_HTTP_API_CONTRACT"),(value["status"],value["expectedOutputs"]["adapter"])); self.assertTrue(value["operationScope"]["operations"]); self.assertFalse(value["effects"]["adapterExecuted"]); self.assertIn("기존 OpenAPI는 변경하지 않음",output.with_suffix('.md').read_text())
 def test_unapproved_route_cannot_create_handoff(self):
  with tempfile.TemporaryDirectory() as d:
   values=self.fixture(Path(d),approve=False); args,output=self.args(*values); code,text=self.invoke(handoff,args); self.assertEqual(1,code); self.assertIn("approved",text); self.assertFalse(output.exists())
 def test_existing_expected_output_creates_visible_blocked_handoff(self):
  with tempfile.TemporaryDirectory() as d:
   values=self.fixture(Path(d)); root,route=values[:2]; route_value=json.loads(route.read_text()); artifact=next(item["artifactPath"] for item in route_value["routes"] if item["contractId"]=="http-api"); metadata=root/artifact; metadata.parent.mkdir(parents=True,exist_ok=True); metadata.write_text("occupied"); args,output=self.args(*values); code,text=self.invoke(handoff,args); self.assertEqual(0,code,text); value=json.loads(output.read_text()); self.assertEqual("BLOCKED",value["status"]); self.assertTrue(any("already exists" in item for item in value["blockers"])); self.assertIn("먼저 해결할 항목",output.with_suffix('.md').read_text())
 def test_selected_operation_scope_hash_changes_with_reachable_component(self):
  document={"openapi":"3.1.0","paths":{"/x":{"get":{"operationId":"getX","responses":{"200":{"description":"ok","content":{"application/json":{"schema":{"$ref":"#/components/schemas/X"}}}}}}}},"components":{"schemas":{"X":{"type":"object","properties":{"id":{"type":"string"}}}}}}; first=handoff.operation_scope(document,{"getX"}); document["components"]["schemas"]["X"]["properties"]["id"]["type"]="integer"; second=handoff.operation_scope(document,{"getX"}); self.assertNotEqual(first["snapshotSha256"],second["snapshotSha256"]); self.assertEqual(["#/components/schemas/X"],first["localRefs"])
 def test_exact_handoff_revalidation_detects_baseline_drift(self):
  with tempfile.TemporaryDirectory() as d:
   values=self.fixture(Path(d)); args,output=self.args(*values); self.assertEqual(0,self.invoke(handoff,args)[0]); validate_args=["validate","--handoff",str(output),"--view",str(output.with_suffix('.md')),"--target",str(values[0])]; code,text=self.invoke(validate_handoff,validate_args); self.assertEqual(0,code,text); baseline=values[0]/json.loads(output.read_text())["baseline"]["path"]; baseline.write_text(baseline.read_text()+" "); code,text=self.invoke(validate_handoff,validate_args); self.assertEqual(1,code); self.assertIn("stale",text)
 def test_final_route_may_be_a_verified_descendant_of_contract_decision(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); first=root/"route-v1.json"; first_view=root/"route-v1.md"; first.write_text('{}'); first_view.write_text("view"); application={"nextRoute":{"path":"route-v1.json","sha256":sha(first)},"nextView":{"path":"route-v1.md","sha256":sha(first_view)}}; second=root/"route-v2.json"; second.write_text(json.dumps({"revision":{"previous":{"path":"route-v1.json","sha256":sha(first)}}})); self.assertTrue(handoff.route_descends_from_application(root,second,application)); first.write_text('{"drift":true}'); self.assertFalse(handoff.route_descends_from_application(root,second,application))

if __name__=="__main__": unittest.main()
