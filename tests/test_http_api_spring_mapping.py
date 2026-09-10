#!/usr/bin/env python3
from __future__ import annotations
import contextlib,io,json,subprocess,sys,tempfile,unittest
from unittest import mock
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
from http_api_spring_mapping import build,reference,validate,child_mappings
from render_http_api_spring_mapping import render
import record_http_api_spring_mapping_approval as approve
import validate_http_api_spring_mapping_approval as validate_approval

def feature():return {"feature":{"id":"F001"},"acceptanceCriteria":[{"id":"AC-1"}],"businessRules":[{"id":"BR-1"}]}
def profile(language="language.java",security="security.none"):return {"decisions":{"language":{"option":language},"security":{"option":security}}}
def api():return {"openapi":"3.1.0","paths":{"/orders":{"post":{"operationId":"createOrder","x-harness-requirement-refs":["AC-1"],"responses":{"201":{"description":"ok"}}}},"/orders/{id}":{"get":{"operationId":"getOrder","x-harness-requirement-refs":["BR-1"],"responses":{"200":{"description":"ok"}}}}}}
class MappingTests(unittest.TestCase):
 def fixture(self,root,source=None,language="language.java",choices=None):
  subprocess.run(["git","init","-q"],cwd=root,check=True); docs=root/"docs";docs.mkdir(); documents={"featureSpec":feature(),"technologyProfile":profile(language),"designRoute":{"routes":[]},"httpApiContract":{"contractId":"orders-api","target":{"projectId":"orders"}},"openApi":api()};refs={}
  for name,value in documents.items():path=docs/f"{name}.json";path.write_text(json.dumps(value));refs[name]=reference(path,root)
  if source:
   path=root/"src/main/java/com/example/api/ExistingController.java";path.parent.mkdir(parents=True);path.write_text(source)
  return build(documents["featureSpec"],documents["technologyProfile"],documents["openApi"],root,".","com.example",choices or {},"USER_CONFIRMED",refs)
 def test_multiple_operations_get_traceable_components_security_and_tests(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);value=self.fixture(root);self.assertEqual("REVIEW_READY",value["status"]);self.assertEqual(2,value["summary"]["operations"]);self.assertEqual(4,value["summary"]["tests"]);self.assertEqual([],validate(value,root));self.assertIn("API별 구현과 검증",render(value,[]))
 def test_existing_exact_controller_mapping_is_reused(self):
  with tempfile.TemporaryDirectory() as d:
   value=self.fixture(Path(d),'@RestController\nclass ExistingController {\n@PostMapping("/orders") void create() {}\n}')
   operation=next(i for i in value["operationMappings"] if i["operationId"]=="createOrder");controller=next(i for i in operation["components"] if i["role"]=="CONTROLLER");self.assertEqual("REUSE",controller["disposition"]);self.assertTrue(controller["candidateEvidence"])
 def test_nonliteral_mapping_is_unknown_not_inferred(self):
  with tempfile.TemporaryDirectory() as d:
   value=self.fixture(Path(d),'@RestController\nclass ExistingController {\n@GetMapping(PATH) void get() {}\n}');self.assertEqual("BLOCKED",value["status"]);self.assertTrue(any(i["code"]=="CONTROLLER_MAPPING_UNKNOWN" for i in value["unknowns"]))
 def test_incompatible_web_test_selection_blocks(self):
  with tempfile.TemporaryDirectory() as d:
   value=self.fixture(Path(d),choices={"webStack":"WEBFLUX","testClient":"MOCKMVC"});self.assertEqual("BLOCKED",value["status"]);self.assertTrue(any(i["code"]=="TEST_STACK_MISMATCH" for i in value["conflicts"]))
 def test_input_and_source_drift_are_detected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);value=self.fixture(root,'@RestController\nclass ExistingController { @GetMapping(PATH) void x(){} }');(root/value["inputs"]["featureSpec"]["path"]).write_text("drift");(root/value["sourceEvidence"][0]["path"]).write_text("drift");blockers=validate(value,root);self.assertTrue(any("input changed" in i for i in blockers));self.assertTrue(any("source evidence changed" in i for i in blockers))
 def test_exact_current_view_can_authorize_plan_but_not_code_dry_run(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);value=self.fixture(root);mapping=root/"docs/mapping.json";view=mapping.with_suffix(".md");mapping.write_text(json.dumps(value));view.write_text(render(value,[]));receipt=root/"docs/mapping-approval.json";args=["approve","--mapping",str(mapping),"--view",str(view),"--target",str(root),"--output",str(receipt),"--approved-by","user","--approved-at","2026-09-10T00:00:00+09:00"]
   stream=io.StringIO()
   with mock.patch.object(sys,"argv",args),mock.patch.object(approve,"validate_contract_current"),contextlib.redirect_stdout(stream):code=approve.main()
   self.assertEqual(0,code,stream.getvalue());saved=json.loads(receipt.read_text());self.assertTrue(saved["effects"]["implementationPlanAuthorized"]);self.assertFalse(saved["effects"]["codeDryRunAuthorized"])
 def test_validator_rejects_unsafe_planned_path_and_missing_security_test(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);value=self.fixture(root);original=value["operationMappings"][0]["components"][0]["plannedPath"];value["operationMappings"][0]["components"][0]["plannedPath"]="../Escape.java"
   with self.assertRaisesRegex(ValueError,"unsafe"):validate(value,root)
   value["operationMappings"][0]["components"][0]["plannedPath"]=original;value["operationMappings"][0]["security"]["required"]=True;self.assertTrue(any("security test" in item for item in validate(value,root)))
 def test_custom_natural_language_choice_requires_preserved_detail(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   with self.assertRaisesRegex(ValueError,"concise detail"):self.fixture(root,choices={"architecture":"CUSTOM"})
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);subprocess.run(["git","init","-q"],cwd=root,check=True);docs=root/"docs";docs.mkdir();documents={"featureSpec":feature(),"technologyProfile":profile(),"designRoute":{},"httpApiContract":{"contractId":"orders-api","target":{"projectId":"orders"}},"openApi":api()};refs={}
   for name,doc in documents.items():path=docs/f"{name}.json";path.write_text(json.dumps(doc));refs[name]=reference(path,root)
   value=build(feature(),profile(),api(),root,".","com.example",{"architecture":"CUSTOM"},"USER_CONFIRMED",refs,{"architecture":"기능별 모듈과 포트-어댑터 혼합"});self.assertEqual("기능별 모듈과 포트-어댑터 혼합",value["decisions"]["architecture"]["detail"])
 def test_deterministic_reconstruction_rejects_internal_tampering(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);value=self.fixture(root);value["operationMappings"][0]["components"][0]["typeName"]="InjectedController";self.assertIn("mapping does not match deterministic reconstruction",validate(value,root))
 def test_unrelated_source_is_not_snapshot_evidence_or_drift(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);value=self.fixture(root,"class Utility {}");self.assertEqual([],value["sourceEvidence"]);path=root/"src/main/java/com/example/api/ExistingController.java";path.write_text("class UtilityChanged {}");self.assertEqual([],validate(value,root))
 def test_scan_limit_and_microservice_without_module_are_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);value=self.fixture(root,choices={"architecture":"MICROSERVICE"});self.assertTrue(any(i["code"]=="SERVICE_BOUNDARY_MISSING" for i in value["conflicts"]));path=root/"src/main/java/com/example/Utility.java";path.parent.mkdir(parents=True);path.write_text("class Utility {}");limited=build(feature(),profile(),api(),root,".","com.example",{},"USER_CONFIRMED",value["inputs"],max_files=1,max_bytes=1);self.assertTrue(any(i["code"]=="SOURCE_SCAN_LIMIT" for i in limited["unknowns"]))
 def test_openapi_shapes_control_dtos_and_security_cases(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);subprocess.run(["git","init","-q"],cwd=root,check=True);docs=root/"docs";docs.mkdir();document=api();op=document["paths"]["/orders"]["post"];op["requestBody"]={"content":{"application/json":{"schema":{"type":"object"}}}};op["responses"]["201"]={"description":"ok","content":{"application/json":{"schema":{"type":"object"}}}};op["security"]=[{"bearerAuth":["orders.write"]}];documents={"featureSpec":feature(),"technologyProfile":profile(security="security.token"),"designRoute":{},"httpApiContract":{"contractId":"orders-api","target":{"projectId":"orders"}},"openApi":document};refs={}
   for name,doc in documents.items():path=docs/f"{name}.json";path.write_text(json.dumps(doc));refs[name]=reference(path,root)
   value=build(feature(),documents["technologyProfile"],document,root,".","com.example",{},"USER_CONFIRMED",refs);mapping=value["operationMappings"][0];self.assertIn("REQUEST_DTO",[i["role"] for i in mapping["components"]]);self.assertIn("RESPONSE_DTO",[i["role"] for i in mapping["components"]]);security=next(i for i in mapping["tests"] if i["kind"]=="SECURITY");self.assertIn("orders.write",security["cases"])
 def test_implementation_semantics_preserve_structure_without_examples(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);document=api();operation=document["paths"]["/orders"]["post"];operation["parameters"]=[{"name":"limit","in":"query","schema":{"type":"integer","minimum":1,"example":10,"description":"ignored"}}];operation["requestBody"]={"required":True,"content":{"application/json":{"schema":{"type":"object","required":["name"],"properties":{"name":{"type":"string","minLength":2,"example":"private"}}}}}};value=self.fixture(root);refs=value["inputs"];mapped=build(feature(),profile(),document,root,".","com.example",{},"USER_CONFIRMED",refs);semantics=mapped["operationMappings"][0]["implementationSemantics"];self.assertEqual(1,semantics["parameters"][0]["schema"]["minimum"]);name=semantics["requestBody"]["content"]["application/json"]["properties"]["name"];self.assertEqual(2,name["minLength"]);self.assertNotIn("example",name)
 def test_local_component_refs_are_resolved_and_only_referenced_schemas_are_copied(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);document=api();document["components"]={"parameters":{"Limit":{"name":"limit","in":"query","schema":{"type":"integer"}}},"schemas":{"Order":{"type":"object","properties":{"id":{"type":"string"}}},"Unused":{"type":"string"}}};operation=document["paths"]["/orders"]["post"];operation["parameters"]=[{"$ref":"#/components/parameters/Limit"}];operation["responses"]["201"]={"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Order"}}}};base=self.fixture(root);mapped=build(feature(),profile(),document,root,".","com.example",{},"USER_CONFIRMED",base["inputs"]);self.assertEqual("limit",mapped["operationMappings"][0]["implementationSemantics"]["parameters"][0]["name"]);self.assertEqual({"Order"},set(mapped["schemaCatalog"]))
 def test_response_headers_media_types_and_unresolved_refs_are_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);document=api();response=document["paths"]["/orders"]["post"]["responses"]["201"];response.update({"headers":{"Location":{"required":True,"schema":{"type":"string","format":"uri"}}},"content":{"text/plain":{"schema":{"type":"string"}}}});document["paths"]["/orders/{id}"]["get"]["parameters"]=[{"$ref":"https://example.invalid/parameter.json"}];base=self.fixture(root);mapped=build(feature(),profile(),document,root,".","com.example",{},"USER_CONFIRMED",base["inputs"]);create=mapped["operationMappings"][0]["implementationSemantics"];self.assertIn("Location",create["responses"]["201"]["headers"]);self.assertIn("text/plain",create["responses"]["201"]["content"]);get=mapped["operationMappings"][1]["implementationSemantics"];self.assertEqual("https://example.invalid/parameter.json",get["parameters"][0]["unresolvedRef"])
 def test_latest_revision_invalidates_older_approval_consumption(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);value=self.fixture(root);mapping=root/"docs/mapping.json";view=mapping.with_suffix(".md");mapping.write_text(json.dumps(value));view.write_text(render(value,[]));receipt=root/"docs/approval.json";args=["approve","--mapping",str(mapping),"--view",str(view),"--target",str(root),"--output",str(receipt),"--approved-by","user","--approved-at","2026-09-10T00:00:00+09:00"]
   with mock.patch.object(sys,"argv",args),mock.patch.object(approve,"validate_contract_current"),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,approve.main())
   with mock.patch.object(validate_approval,"validate_contract_current"):self.assertEqual("APPROVED",validate_approval.validate_approval(root,receipt)["state"])
   child=root/"docs/mapping-v2.json";next_value=json.loads(json.dumps(value));next_value["revision"]={"previous":reference(mapping,root),"changeSummary":"changed"};child.write_text(json.dumps(next_value));self.assertEqual([child],child_mappings(root,mapping))
   with mock.patch.object(validate_approval,"validate_contract_current"),self.assertRaisesRegex(ValueError,"latest"):validate_approval.validate_approval(root,receipt)
 def test_custom_detail_rejects_secrets_and_pii(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);value=self.fixture(root)
   with self.assertRaisesRegex(ValueError,"secret-like"):build(feature(),profile(),api(),root,".","com.example",{"architecture":"CUSTOM"},"USER_CONFIRMED",value["inputs"],{"architecture":"password=abc"})
 def test_custom_architecture_paths_are_first_class(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);base=self.fixture(root);value=build(feature(),profile(),api(),root,".","com.example",{"architecture":"CUSTOM"},"USER_CONFIRMED",base["inputs"],{"architecture":"포트 어댑터 혼합"},custom_layout={"controller":"entry/web","service":"core/usecase","dto":"entry/model"});self.assertEqual("REVIEW_READY",value["status"]);paths=[c["plannedPath"] for c in value["operationMappings"][0]["components"]];self.assertTrue(any("entry/web" in p for p in paths));self.assertEqual([],validate(value,root))
if __name__=="__main__":unittest.main()
