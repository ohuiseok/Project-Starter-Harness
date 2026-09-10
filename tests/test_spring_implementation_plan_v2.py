#!/usr/bin/env python3
from __future__ import annotations
import contextlib,io,json,subprocess,sys,tempfile,unittest
from unittest import mock
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
from http_api_spring_mapping import build as build_mapping,reference
from spring_implementation_plan_v2 import build,cid,validate
from render_spring_implementation_plan_v2 import render
import cancel_spring_implementation_plan_v2 as cancel_plan
import record_spring_implementation_plan_v2_approval as approve_plan
import spring_implementation_plan_v2 as plan_core
import validate_spring_implementation_plan_v2_approval as validate_plan_approval
from validate_spring_implementation_capabilities_v2 import load_and_validate
from spring_code_renderability_v2 import assess,schema_blockers
from render_spring_code_renderability_v2 import render as render_readiness
import prepare_spring_code_renderability_v2 as prepare_readiness
import validate_spring_code_renderability_v2 as validate_readiness
from tests.test_http_api_spring_mapping import feature,profile,api
class PlanV2Tests(unittest.TestCase):
 def fixture(self,root,document=None,choices=None,security="security.none"):
  subprocess.run(["git","init","-q"],cwd=root,check=True);docs=root/"docs";docs.mkdir();document=document or api();selected_profile=profile(security=security);sources={"featureSpec":feature(),"technologyProfile":selected_profile,"designRoute":{},"httpApiContract":{"contractId":"orders-api","target":{"projectId":"orders"}},"openApi":document};refs={}
  for name,value in sources.items():path=docs/f"{name}.json";path.write_text(json.dumps(value));refs[name]=reference(path,root)
  mapping=build_mapping(feature(),selected_profile,document,root,".","com.example",choices or {},"USER_CONFIRMED",refs);mapping_path=docs/"mapping.json";mapping_path.write_text(json.dumps(mapping));approval=docs/"mapping-approval.json";approval.write_text("{}")
  plan=build(mapping,reference(mapping_path,root),reference(approval,root),root);return plan,mapping_path,approval
 def test_java_mvc_api_only_plan_is_reviewable_and_has_scoped_renderer(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,_,_=self.fixture(root);self.assertEqual("REVIEW_READY",plan["status"]);self.assertEqual("JAVA_MVC_API_ONLY_V1",plan["capability"]["adapterId"]);self.assertTrue(plan["advancement"]["codeDryRun"]);self.assertEqual([],validate(plan,root,False));self.assertIn("코드 dry-run 준비: 가능",render(plan,[]))
 def test_multiple_operations_have_symbol_and_test_links(self):
  with tempfile.TemporaryDirectory() as d:
   plan,_,_=self.fixture(Path(d));self.assertEqual(2,len(plan["operationLinks"]));self.assertTrue(all(i["componentRefs"] and i["testRefs"] for i in plan["operationLinks"]));self.assertTrue(all(c["symbols"] for c in plan["components"]))
 def test_request_and_response_components_follow_mapping(self):
  with tempfile.TemporaryDirectory() as d:
   document=api();op=document["paths"]["/orders"]["post"];op["requestBody"]={"content":{"application/json":{"schema":{"type":"object"}}}};op["responses"]["201"]={"description":"ok","content":{"application/json":{"schema":{"type":"object"}}}};plan,_,_=self.fixture(Path(d),document);roles={i["role"] for i in plan["components"]};self.assertTrue({"REQUEST_DTO","RESPONSE_DTO"}<=roles);self.assertIsNotNone(plan["operationLinks"][0]["implementationSemantics"]["requestBody"])
 def test_mapping_conflicts_propagate(self):
  with tempfile.TemporaryDirectory() as d:
   plan,_,_=self.fixture(Path(d),choices={"webStack":"WEBFLUX"});self.assertEqual("BLOCKED",plan["status"]);self.assertTrue(any(i["source"]=="SPRING_MAPPING" for i in plan["conflicts"]))
 def test_plan_tampering_and_cycles_are_detected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,_,_=self.fixture(root);plan["components"][0]["target"]["typeName"]="Injected";plan["components"][0]["dependsOn"]=[plan["components"][0]["componentId"]];blockers=validate(plan,root,False);self.assertIn("plan does not match deterministic reconstruction",blockers);self.assertIn("component dependency cycle exists",blockers)
 def test_capability_catalog_registers_only_scoped_renderer(self):
  with tempfile.TemporaryDirectory() as d:
   plan,_,_=self.fixture(Path(d));self.assertEqual("JAVA_MVC_API_ONLY_V1",plan["capability"]["codeDryRunRenderer"]);self.assertEqual("NONE_PLANNED",plan["scope"]["buildChanges"])
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
 def test_shared_component_with_mixed_dispositions_is_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);_,mapping_path,approval=self.fixture(root);mapping=json.loads(mapping_path.read_text());controllers=[next(i for i in op["components"] if i["role"]=="CONTROLLER") for op in mapping["operationMappings"]]
   source=root/"src/main/java/com/example/api/OrdersController.java";source.parent.mkdir(parents=True);source.write_text("package com.example.api; public class OrdersController {}")
   for item in controllers:item.update({"plannedPath":"src/main/java/com/example/api/OrdersController.java","typeName":"OrdersController"})
   controllers[0].update({"disposition":"REUSE","candidateEvidence":[reference(source,root)]});controllers[1]["disposition"]="EXTEND";plan=build(mapping,reference(mapping_path,root),reference(approval,root),root);component=next(i for i in plan["components"] if i["role"]=="CONTROLLER");self.assertEqual("UPDATE_FILE",component["fileAction"]);self.assertEqual({"REUSE_METHOD","ADD_METHOD"},{i["action"] for i in component["symbols"]});self.assertFalse(any(i["code"]=="SHARED_COMPONENT_DISPOSITION_CONFLICT" for i in plan["conflicts"]))
 def test_security_profile_is_not_falsely_supported(self):
  with tempfile.TemporaryDirectory() as d:
   document=api();document["paths"]["/orders"]["post"]["security"]=[{"bearerAuth":[]}];plan,_,_=self.fixture(Path(d),document,security="security.token");self.assertEqual("BLOCKED",plan["status"]);self.assertEqual("UNSUPPORTED",plan["scope"]["security"]);self.assertTrue(any(i["code"]=="SECURITY_CAPABILITY_UNAVAILABLE" for i in plan["conflicts"]))
 def test_public_operation_in_secured_project_stays_api_only(self):
  with tempfile.TemporaryDirectory() as d:
   plan,_,_=self.fixture(Path(d),security="security.token");self.assertEqual("REVIEW_READY",plan["status"]);self.assertEqual("NOT_USED",plan["scope"]["security"])
 def test_test_paths_follow_controller_architecture_and_occupied_path_blocks(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,mapping_path,approval=self.fixture(root,choices={"architecture":"HEXAGONAL"});test=next(i for i in plan["components"] if i["role"]=="TEST");self.assertIn("adapter/in/web",test["target"]["path"]);path=root/test["target"]["path"];path.parent.mkdir(parents=True,exist_ok=True);path.write_text("existing");mapping=json.loads(mapping_path.read_text());blocked=build(mapping,reference(mapping_path,root),reference(approval,root),root);self.assertTrue(any(i["code"]=="TEST_PATH_OCCUPIED" for i in blocked["conflicts"]))
 def test_component_ids_keep_hash_identity_after_readable_normalization(self):
  self.assertNotEqual(cid("TEST","x/y","Z"),cid("TEST","x-y","Z"));self.assertRegex(cid("TEST","x/y","Z"),r"-[0-9a-f]{10}$")
 def test_file_actions_evidence_coverage_and_v2_baseline_are_explicit(self):
  with tempfile.TemporaryDirectory() as d:
   plan,_,_=self.fixture(Path(d));self.assertTrue(all(i["fileAction"]=="CREATE_FILE" for i in plan["components"]));self.assertTrue(all(i["verificationLevel"]=="API_CONTRACT_ONLY" for i in plan["coverage"]));self.assertEqual(".starter-harness-implementation-v2.json",plan["baseline"]["path"]);self.assertTrue(all("sourceEvidence" in i for i in plan["components"]))
 def test_renderability_checks_build_schema_update_and_limits_without_effects(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,_,_=self.fixture(root);report=assess(plan,root);self.assertTrue(any(i["code"]=="BUILD_CAPABILITY_MISSING" for i in report["blockers"]));self.assertFalse(report["readyForCodeDryRun"]);self.assertFalse(report["effects"]["sourceChanged"]);self.assertEqual(100,report["limits"]["maxFiles"]);self.assertIn("비즈니스 행동 완료를 의미하지 않음",render_readiness(report))
   (root/"build.gradle").write_text("implementation 'org.springframework.boot:spring-boot-starter-web'\nimplementation 'org.springframework.boot:spring-boot-starter-validation'\ntestImplementation 'org.springframework.boot:spring-boot-starter-test'");self.assertFalse(any(i["code"]=="BUILD_CAPABILITY_MISSING" for i in assess(plan,root)["blockers"]))
 def test_unsupported_schema_composition_is_blocked_before_rendering(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,_,_=self.fixture(root);plan["operationLinks"][0]["implementationSemantics"]["requestBody"]={"required":True,"content":{"application/json":{"oneOf":[{"type":"string"},{"type":"integer"}]}}};self.assertTrue(any(i["code"]=="SCHEMA_COMPOSITION_UNSUPPORTED" for i in schema_blockers(plan)))
 def test_approved_plan_prepares_and_revalidates_atomic_renderability_view(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,_,_=self.fixture(root);plan_path=root/"docs/plan.json";plan_path.write_text(json.dumps(plan));approval=root/"docs/plan-approval.json";approval.write_text("{}");receipt={"implementationPlan":reference(plan_path,root)};report=root/"docs/renderability.json";view=report.with_suffix(".md");argv=["prepare","--plan-approval",str(approval),"--target",str(root),"--output",str(report),"--view",str(view)]
   with mock.patch.object(sys,"argv",argv),mock.patch.object(prepare_readiness,"validate_approval",return_value=receipt),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,prepare_readiness.main())
   argv=["validate","--report",str(report),"--view",str(view),"--target",str(root)]
   with mock.patch.object(sys,"argv",argv),mock.patch.object(validate_readiness,"validate_approval",return_value=receipt),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,validate_readiness.main())
   self.assertIn("코드 dry-run 준비 점검",view.read_text());self.assertFalse(json.loads(report.read_text())["effects"]["sourceChanged"])
 def test_multimodule_dirty_paths_and_commented_dependencies_are_not_misread(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,_,_=self.fixture(root,choices={"architecture":"MICROSERVICE"});plan["target"]["modulePath"]="order-service";module=root/"order-service";source=module/"src/main/java/X.java";source.parent.mkdir(parents=True);source.write_text("class X {}")
   build_file=module/"build.gradle";build_file.write_text("// implementation 'org.springframework.boot:spring-boot-starter-web'")
   report=assess(plan,root);self.assertIn("order-service/src/main/java/X.java",report["git"]["dirtyPaths"]);self.assertFalse(report["buildCapability"]["checks"]["springMvc"])
 def test_baseline_content_or_mode_drift_is_blocking(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,_,_=self.fixture(root);managed=root/"src/main/java/Managed.java";managed.parent.mkdir(parents=True);managed.write_text("before");baseline_path=root/".starter-harness-implementation-v2.json";baseline_path.write_text(json.dumps({"manifestVersion":2,"artifactKind":"SPRING_IMPLEMENTATION_V2","files":{"src/main/java/Managed.java":"0"*64},"modes":{"src/main/java/Managed.java":420}}));report=assess(plan,root);self.assertEqual("DRIFTED",report["baseline"]["state"]);self.assertTrue(any(i["code"]=="BASELINE_DRIFT" for i in report["blockers"]))
 def test_capability_catalog_rejects_overlapping_selectors(self):
  with tempfile.TemporaryDirectory() as d:
   source=json.loads((ROOT/".agents/skills/spring-project-start/references/spring-implementation-capabilities-v2.json").read_text());source["adapters"].append(dict(source["adapters"][0],id="JAVA_MVC_DUPLICATE"));path=Path(d)/"catalog.json";path.write_text(json.dumps(source))
   with self.assertRaisesRegex(ValueError,"overlap"):load_and_validate(path)
 def test_exact_plan_approval_authorizes_preparation_only_and_cancel_invalidates_it(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);plan,mapping_path,_=self.fixture(root);plan_path=root/"docs/implementation-plan-v2.json";view=plan_path.with_suffix(".md");plan_path.write_text(json.dumps(plan));view.write_text(render(plan,[]));approval=root/"docs/implementation-plan-v2-approval.json";mapping_ref=reference(mapping_path,root)
   argv=["approve","--plan",str(plan_path),"--view",str(view),"--target",str(root),"--output",str(approval),"--approved-by","user","--approved-at","2026-09-10T00:00:00+09:00"]
   with mock.patch.object(sys,"argv",argv),mock.patch.object(plan_core,"validate_mapping_approval",return_value={"mapping":mapping_ref}),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,approve_plan.main())
   with mock.patch.object(plan_core,"validate_mapping_approval",return_value={"mapping":mapping_ref}):receipt=validate_plan_approval.validate_approval(root,approval)
   self.assertTrue(receipt["effects"]["codeDryRunPreparationAuthorized"]);self.assertFalse(receipt["effects"]["isolatedVerificationAuthorized"])
   cancellation=root/"docs/implementation-plan-v2-cancellation.json";argv=["cancel","--plan",str(plan_path),"--target",str(root),"--output",str(cancellation),"--reason","구현 방향 재검토"]
   with mock.patch.object(sys,"argv",argv),mock.patch.object(plan_core,"validate_mapping_approval",return_value={"mapping":mapping_ref}),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,cancel_plan.main())
   with mock.patch.object(plan_core,"validate_mapping_approval",return_value={"mapping":mapping_ref}),self.assertRaisesRegex(ValueError,"cancelled"):validate_plan_approval.validate_approval(root,approval)
if __name__=="__main__":unittest.main()
