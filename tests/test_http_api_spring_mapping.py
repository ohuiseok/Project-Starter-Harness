#!/usr/bin/env python3
from __future__ import annotations
import contextlib,io,json,subprocess,sys,tempfile,unittest
from unittest import mock
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
from http_api_spring_mapping import build,reference,validate
from render_http_api_spring_mapping import render
import record_http_api_spring_mapping_approval as approve

def feature():return {"feature":{"id":"F001"},"acceptanceCriteria":[{"id":"AC-1"}],"businessRules":[{"id":"BR-1"}]}
def profile(language="language.java",security="security.none"):return {"decisions":{"language":{"option":language},"security":{"option":security}}}
def api():return {"openapi":"3.1.0","paths":{"/orders":{"post":{"operationId":"createOrder","x-harness-requirement-refs":["AC-1"],"responses":{"201":{"description":"ok"}}}},"/orders/{id}":{"get":{"operationId":"getOrder","x-harness-requirement-refs":["BR-1"],"responses":{"200":{"description":"ok"}}}}}}
class MappingTests(unittest.TestCase):
 def fixture(self,root,source=None,language="language.java",choices=None):
  subprocess.run(["git","init","-q"],cwd=root,check=True); docs=root/"docs";docs.mkdir(); documents={"featureSpec":feature(),"technologyProfile":profile(language),"httpApiContract":{"approval":"approved"},"openApi":api()};refs={}
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
   root=Path(d);value=self.fixture(root,'@RestController\nclass ExistingController {}');(root/value["inputs"]["featureSpec"]["path"]).write_text("drift");(root/value["sourceEvidence"][0]["path"]).write_text("drift");blockers=validate(value,root);self.assertTrue(any("input changed" in i for i in blockers));self.assertTrue(any("source evidence changed" in i for i in blockers))
 def test_exact_current_view_can_authorize_plan_but_not_code_dry_run(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);value=self.fixture(root);mapping=root/"docs/mapping.json";view=mapping.with_suffix(".md");mapping.write_text(json.dumps(value));view.write_text(render(value,[]));receipt=root/"docs/mapping-approval.json";args=["approve","--mapping",str(mapping),"--view",str(view),"--target",str(root),"--output",str(receipt),"--approved-by","user","--approved-at","2026-09-10T00:00:00+09:00"]
   stream=io.StringIO()
   with mock.patch.object(sys,"argv",args),contextlib.redirect_stdout(stream):code=approve.main()
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
   root=Path(d);subprocess.run(["git","init","-q"],cwd=root,check=True);docs=root/"docs";docs.mkdir();documents={"featureSpec":feature(),"technologyProfile":profile(),"httpApiContract":{},"openApi":api()};refs={}
   for name,doc in documents.items():path=docs/f"{name}.json";path.write_text(json.dumps(doc));refs[name]=reference(path,root)
   value=build(feature(),profile(),api(),root,".","com.example",{"architecture":"CUSTOM"},"USER_CONFIRMED",refs,{"architecture":"기능별 모듈과 포트-어댑터 혼합"});self.assertEqual("기능별 모듈과 포트-어댑터 혼합",value["decisions"]["architecture"]["detail"])
if __name__=="__main__":unittest.main()
