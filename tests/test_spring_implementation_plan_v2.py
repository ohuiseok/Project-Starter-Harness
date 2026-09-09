#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
from http_api_spring_mapping import build as build_mapping,reference
from spring_implementation_plan_v2 import build,validate
from render_spring_implementation_plan_v2 import render
from tests.test_http_api_spring_mapping import feature,profile,api
class PlanV2Tests(unittest.TestCase):
 def fixture(self,root,document=None,choices=None):
  subprocess.run(["git","init","-q"],cwd=root,check=True);docs=root/"docs";docs.mkdir();document=document or api();sources={"featureSpec":feature(),"technologyProfile":profile(),"designRoute":{},"httpApiContract":{"contractId":"orders-api","target":{"projectId":"orders"}},"openApi":document};refs={}
  for name,value in sources.items():path=docs/f"{name}.json";path.write_text(json.dumps(value));refs[name]=reference(path,root)
  mapping=build_mapping(feature(),profile(),document,root,".","com.example",choices or {},"USER_CONFIRMED",refs);mapping_path=docs/"mapping.json";mapping_path.write_text(json.dumps(mapping));approval=docs/"mapping-approval.json";approval.write_text("{}")
  plan=build(mapping,reference(mapping_path,root),reference(approval,root),root);return plan,mapping_path,approval
 def test_java_mvc_api_only_plan_is_reviewable_but_not_code_ready(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,_,_=self.fixture(root);self.assertEqual("REVIEW_READY",plan["status"]);self.assertEqual("JAVA_MVC_API_ONLY_V1",plan["capability"]["adapterId"]);self.assertFalse(plan["advancement"]["codeDryRun"]);self.assertEqual([],validate(plan,root,False));self.assertIn("코드 dry-run: 불가",render(plan,[]))
 def test_multiple_operations_have_symbol_and_test_links(self):
  with tempfile.TemporaryDirectory() as d:
   plan,_,_=self.fixture(Path(d));self.assertEqual(2,len(plan["operationLinks"]));self.assertTrue(all(i["componentRefs"] and i["testRefs"] for i in plan["operationLinks"]));self.assertTrue(all(c["symbols"] for c in plan["components"]))
 def test_request_and_response_components_follow_mapping(self):
  with tempfile.TemporaryDirectory() as d:
   document=api();op=document["paths"]["/orders"]["post"];op["requestBody"]={"content":{"application/json":{"schema":{"type":"object"}}}};op["responses"]["201"]={"description":"ok","content":{"application/json":{"schema":{"type":"object"}}}};plan,_,_=self.fixture(Path(d),document);roles={i["role"] for i in plan["components"]};self.assertTrue({"REQUEST_DTO","RESPONSE_DTO"}<=roles)
 def test_mapping_conflicts_propagate(self):
  with tempfile.TemporaryDirectory() as d:
   plan,_,_=self.fixture(Path(d),choices={"webStack":"WEBFLUX"});self.assertEqual("BLOCKED",plan["status"]);self.assertTrue(any(i["source"]=="SPRING_MAPPING" for i in plan["conflicts"]))
 def test_plan_tampering_and_cycles_are_detected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,_,_=self.fixture(root);plan["components"][0]["target"]["typeName"]="Injected";plan["components"][0]["dependsOn"]=[plan["components"][0]["componentId"]];blockers=validate(plan,root,False);self.assertIn("plan does not match deterministic reconstruction",blockers);self.assertIn("component dependency cycle exists",blockers)
 def test_capability_catalog_prevents_false_renderer_claim(self):
  with tempfile.TemporaryDirectory() as d:
   plan,_,_=self.fixture(Path(d));self.assertEqual("NOT_IMPLEMENTED",plan["capability"]["codeDryRunRenderer"]);self.assertEqual("NONE_PLANNED",plan["scope"]["buildChanges"])
 def test_shared_controller_is_deduplicated_with_multiple_symbols(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,mapping_path,approval=self.fixture(root);mapping=json.loads(mapping_path.read_text());controllers=[]
   for op in mapping["operationMappings"]:
    controller=next(i for i in op["components"] if i["role"]=="CONTROLLER");controller.update({"plannedPath":"src/main/java/com/example/api/OrdersController.java","typeName":"OrdersController","disposition":"REUSE"});controllers.append(controller)
   shared=build(mapping,reference(mapping_path,root),reference(approval,root),root);items=[i for i in shared["components"] if i["role"]=="CONTROLLER"];self.assertEqual(1,len(items));self.assertEqual(2,len(items[0]["symbols"]));self.assertEqual(2,len(items[0]["operationRefs"]))
 def test_distinct_components_cannot_silently_own_one_path(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);_,mapping_path,approval=self.fixture(root);mapping=json.loads(mapping_path.read_text());components=[op["components"][1] for op in mapping["operationMappings"]]
   components[1]["plannedPath"]=components[0]["plannedPath"]
   plan=build(mapping,reference(mapping_path,root),reference(approval,root),root);self.assertEqual("BLOCKED",plan["status"]);self.assertTrue(any(i["code"]=="TARGET_PATH_OWNERSHIP_COLLISION" for i in plan["conflicts"]))
if __name__=="__main__":unittest.main()
