#!/usr/bin/env python3
from __future__ import annotations
import contextlib,io,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parent.parent; SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts"; sys.path[:0]=[str(SCRIPTS),str(ROOT)]
import discover_http_api_evidence as discovery
import validate_http_api_evidence_discovery as validate_discovery
from http_api_contract import encoded
from tests.test_design_route_preparation import ready_profile
from tests.test_feature_specs import feature_spec
from tests.test_http_api_contract import openapi

class HttpApiEvidenceDiscoveryTests(unittest.TestCase):
 def fixture(self,parent:Path):
  root=parent/"target"; feature=root/"docs/features/F001/spec.json"; profile=root/"docs/project-profile.json"; feature.parent.mkdir(parents=True); feature.write_text(json.dumps(feature_spec())); technology=ready_profile(); technology["decisions"]["security"]={"status":"NOW","option":"security.token"}; technology["decisions"]["authorization"]={"status":"NOW","option":"authorization.roles"}; profile.write_text(json.dumps(technology)); subprocess.run(["git","init","-q"],cwd=root,check=True); return root,feature,profile
 def invoke(self,root,feature,profile,extra=None):
  output=root/"docs/features/F001/http-api-evidence.json"; args=["discover","--feature",str(feature),"--profile",str(profile),"--target",str(root),"--output",str(output),"--view",str(output.with_suffix('.md'))]+(extra or []); stream=io.StringIO()
  with mock.patch.object(sys,"argv",args),contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream): code=discovery.main()
  return code,stream.getvalue(),output
 def test_no_existing_api_recommends_create_without_source_change(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}; code,text,output=self.invoke(root,feature,profile); self.assertEqual(0,code,text); report=json.loads(output.read_text()); self.assertEqual("CREATE",report["summary"]["recommendedDisposition"]); self.assertFalse(report["effects"]["routeChanged"]); self.assertEqual(before,{p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file() and p not in {output,output.with_suffix('.md')}})
 def test_current_openapi_with_requirement_traceability_recommends_reuse(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); api=root/"api/openapi.json"; api.parent.mkdir(); api.write_bytes(encoded(openapi())); code,text,output=self.invoke(root,feature,profile); self.assertEqual(0,code,text); candidate=json.loads(output.read_text())["candidates"][0]; self.assertEqual("OPENAPI_JSON",candidate["kind"]); self.assertEqual("REUSE",candidate["recommendedDisposition"]); self.assertEqual("HIGH",candidate["confidence"])
 def test_controller_is_only_supporting_unknown_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); source=root/"src/main/java/LeaveController.java"; source.parent.mkdir(parents=True); source.write_text('@RestController\n@RequestMapping("/leave")\nclass LeaveController { @GetMapping("/requests") Object list(){return null;} }'); code,text,output=self.invoke(root,feature,profile); self.assertEqual(0,code,text); candidate=json.loads(output.read_text())["candidates"][0]; self.assertEqual("SPRING_CONTROLLER",candidate["kind"]); self.assertEqual("UNKNOWN",candidate["recommendedDisposition"]); self.assertTrue(candidate["ambiguities"])
 def test_yaml_is_reported_but_never_treated_as_validated_contract(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); api=root/"openapi.yaml"; api.write_text("openapi: 3.1.0\npaths: {}\n"); code,text,output=self.invoke(root,feature,profile); self.assertEqual(0,code,text); candidate=json.loads(output.read_text())["candidates"][0]; self.assertEqual("UNSUPPORTED",candidate["discovery"]["parseState"]); self.assertEqual("UNKNOWN",candidate["recommendedDisposition"])
 def test_dirty_evidence_is_unstable_and_not_auto_selected(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); api=root/"openapi.json"; api.write_bytes(encoded(openapi())); subprocess.run(["git","add","openapi.json"],cwd=root,check=True); api.write_bytes(api.read_bytes()+b" "); code,text,output=self.invoke(root,feature,profile); self.assertEqual(0,code,text); report=json.loads(output.read_text()); self.assertEqual("UNSTABLE",report["candidates"][0]["evidence"]["stability"]); self.assertEqual("UNKNOWN",report["summary"]["recommendedDisposition"])
 def test_scan_limit_yields_unknown_instead_of_partial_guess(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); (root/"a.java").write_text("class A {}"); (root/"b.java").write_text("class B {}"); code,text,output=self.invoke(root,feature,profile,["--max-files","1"]); self.assertEqual(0,code,text); report=json.loads(output.read_text()); self.assertTrue(report["summary"]["truncated"]); self.assertEqual("UNKNOWN",report["summary"]["recommendedDisposition"])
 def test_exact_report_revalidation_detects_evidence_drift(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); api=root/"openapi.json"; api.write_bytes(encoded(openapi())); code,text,output=self.invoke(root,feature,profile); self.assertEqual(0,code,text); args=["validate","--report",str(output),"--view",str(output.with_suffix('.md')),"--target",str(root)]; stream=io.StringIO()
   with mock.patch.object(sys,"argv",args),contextlib.redirect_stdout(stream): self.assertEqual(0,validate_discovery.main(),stream.getvalue())
   api.write_bytes(api.read_bytes()+b" ")
   with mock.patch.object(sys,"argv",args),contextlib.redirect_stdout(io.StringIO()): self.assertEqual(1,validate_discovery.main())
 def test_unrelated_operation_cannot_claim_reuse_from_traceability_alone(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); document=openapi(); operation=document["paths"].pop("/api/leave-requests")["post"]; operation["operationId"]="adminSystemStatus"; operation["summary"]="Administrative system status"; operation["description"]="Infrastructure status"; document["paths"]["/admin/system"]={"get":operation}; api=root/"openapi.json"; api.write_bytes(encoded(document)); code,text,output=self.invoke(root,feature,profile); self.assertEqual(0,code,text); candidate=json.loads(output.read_text())["candidates"][0]; self.assertEqual("UNKNOWN",candidate["recommendedDisposition"])
 def test_competing_contract_candidate_blocks_automatic_reuse(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); (root/"openapi.json").write_bytes(encoded(openapi())); (root/"legacy.yaml").write_text("openapi: 3.0.3\npaths: {}\n"); code,text,output=self.invoke(root,feature,profile); self.assertEqual(0,code,text); report=json.loads(output.read_text()); self.assertEqual(2,len(report["candidates"])); self.assertEqual("UNKNOWN",report["summary"]["recommendedDisposition"])
 def test_malformed_possible_openapi_is_visible_and_blocks_create(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); (root/"openapi.json").write_text('{"openapi":'); code,text,output=self.invoke(root,feature,profile); self.assertEqual(0,code,text); report=json.loads(output.read_text()); self.assertEqual("MALFORMED",report["candidates"][0]["discovery"]["parseState"]); self.assertEqual("UNKNOWN",report["summary"]["recommendedDisposition"])
 def test_file_changed_during_snapshot_is_unstable_and_not_selected(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); api=root/"openapi.json"; api.write_bytes(encoded(openapi())); original=discovery.snapshot
   def changing(path):
    content,unchanged=original(path); return (content,False) if path==api else (content,unchanged)
   with mock.patch.object(discovery,"snapshot",side_effect=changing): code,text,output=self.invoke(root,feature,profile)
   self.assertEqual(0,code,text); report=json.loads(output.read_text()); self.assertEqual("UNSTABLE",report["candidates"][0]["evidence"]["stability"]); self.assertEqual("UNKNOWN",report["summary"]["recommendedDisposition"])
 def test_user_view_identifies_candidate_path_matches_coverage_and_reason(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); api=root/"api/openapi.json"; api.parent.mkdir(); api.write_bytes(encoded(openapi())); code,text,output=self.invoke(root,feature,profile); self.assertEqual(0,code,text); report=json.loads(output.read_text()); view=output.with_suffix('.md').read_text(); self.assertIn(report["candidates"][0]["candidateId"],view); self.assertIn("api/openapi.json",view); self.assertIn("기능과 연결된 API",view); self.assertIn("요구사항: 충족",view); self.assertIn("판단 이유",view)
 def test_controller_parser_consumes_the_same_snapshot_text(self):
  with tempfile.TemporaryDirectory() as d:
   root,feature,profile=self.fixture(Path(d)); source=root/"Controller.java"; source.write_text('@RestController class Controller { @GetMapping("/leave") Object get(){return null;} }'); original=discovery.controller_mappings; observed=[]
   def parse(path,text=None):
    observed.append(text); return original(path,text)
   with mock.patch.object(discovery,"controller_mappings",side_effect=parse): code,message,_=self.invoke(root,feature,profile)
   self.assertEqual(0,code,message); self.assertEqual([source.read_text()],observed)

if __name__=="__main__": unittest.main()
