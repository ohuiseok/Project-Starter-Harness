#!/usr/bin/env python3
from __future__ import annotations
import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parent.parent; SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts"; sys.path.insert(0,str(SCRIPTS)); sys.path.insert(0,str(ROOT))
import create_continuation_route as create_route
import record_continuation_route_approval as approve_route
import consume_continuation_handoff as consume_handoff
import create_feature_spec_from_intake as create_feature_draft
import recover_feature_spec_intake as recover_feature_draft
import tests.test_spring_milestone_completion as milestone_tests
from continuation_route import build_route,validate_handoff,validate_route
from spring_milestone_completion import sha
class ContinuationRouteTests(unittest.TestCase):
 def fixture(self,parent:Path):
  helper=milestone_tests.SpringMilestoneCompletionTests(); target,_,_,args=helper.fixture(parent); self.assertEqual(0,helper.run_completion(args)[0]); return target,target/"docs/project-brief.json",target/"docs/progress.json"
 def route(self,target,project,progress,request,feature=None): return build_route(target,request,project,progress,feature)
 def call(self,module,args):
  stream=io.StringIO()
  with mock.patch.object(sys,"argv",args),contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream): return module.main(),stream.getvalue()
 def test_generic_next_uses_current_recommendation(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); route=self.route(target,project,progress,"다음 추천 기능 진행해줘"); self.assertEqual("NEXT_FEATURE",route["route"]["type"]); self.assertEqual("F002",route["route"]["selectedFeature"]["featureId"]); self.assertTrue(route["route"]["requiresConfirmation"])
 def test_blocked_candidate_explains_dependency(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); route=self.route(target,project,progress,"F003 진행","F003"); self.assertEqual("BLOCKED",route["route"]["type"]); self.assertIn("dependencies:F002",route["route"]["blockers"]); self.assertIn("선행 기능 완료 필요: F002",__import__("continuation_route").render(route))
 def test_new_feature_reserves_next_id_without_mutation(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); before=project.read_bytes(); route=self.route(target,project,progress,"휴가 알림 이메일을 보내줘"); self.assertEqual("NEW_FEATURE",route["route"]["type"]); self.assertEqual("F004",route["route"]["proposedFeature"]["featureId"]); self.assertEqual(before,project.read_bytes())
 def test_completed_feature_routes_to_revision(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); route=self.route(target,project,progress,"F001 기능 변경","F001"); self.assertEqual("REVISE_FEATURE",route["route"]["type"])
 def test_technology_and_retry_requests_use_existing_workflows(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); self.assertEqual("TECHNOLOGY_SELECTION",self.route(target,project,progress,"DB 변경하고 싶어")["route"]["nextWorkflow"]); self.assertEqual("POST_APPLY_VERIFICATION",self.route(target,project,progress,"검증 재시도해줘")["route"]["nextWorkflow"])
 def test_unknown_or_multiple_feature_ids_require_clarification(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d))
   for request in ("F999 진행해줘","F002와 F003 같이 진행해줘"):
    route=self.route(target,project,progress,request); self.assertEqual("NEEDS_CLARIFICATION",route["route"]["type"]); self.assertIsNone(route["route"]["proposedFeature"])
 def test_specific_database_and_auth_changes_route_to_technology(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d))
   for request in ("PostgreSQL로 바꿔줘","세션 인증을 JWT로 바꿔줘"):
    self.assertEqual("TECHNOLOGY_CHANGE",self.route(target,project,progress,request)["route"]["type"])
 def test_request_is_redacted_and_markdown_escaped(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); route=self.route(target,project,progress,"홍길동님의 이메일 test@example.com으로 <script> 알림 추가")
   self.assertNotIn("test@example.com",json.dumps(route,ensure_ascii=False)); view=__import__("continuation_route").render(route); self.assertIn("[이메일]",view); self.assertNotIn("<script>",view)
 def test_changed_progress_invalidates_saved_route(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); path=target/"docs/continuation.json"; path.write_text(json.dumps(self.route(target,project,progress,"다음 기능"))); value=json.loads(path.read_text()); progress.write_text(progress.read_text()+" ")
   with self.assertRaisesRegex(ValueError,"evidence changed"): validate_route(value,path,target)
 def test_stale_view_blocks_approval(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); route=target/"docs/route.json"; view=target/"docs/route.md"; approval=target/"docs/route-approval.json"; handoff=target/"docs/handoff.json"; self.assertEqual(0,self.call(create_route,["create","--request","다음 기능","--project-brief",str(project),"--progress",str(progress),"--target",str(target),"--output",str(route),"--view",str(view)])[0]); view.write_text("stale"); code,text=self.call(approve_route,["approve","--route",str(route),"--view",str(view),"--target",str(target),"--approval-output",str(approval),"--handoff-output",str(handoff),"--expected-route-hash",sha(route),"--approved-by","user","--approved-at","2026-09-08T00:00:00Z"]); self.assertEqual(1,code); self.assertIn("stale",text)
 def test_approved_route_creates_handoff_without_source_change(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); route=target/"docs/route.json"; view=target/"docs/route.md"; approval=target/"docs/route-approval.json"; handoff=target/"docs/handoff.json"; before={p:p.read_bytes() for p in target.glob("src/**/*") if p.is_file()}; self.assertEqual(0,self.call(create_route,["create","--request","다음 기능","--project-brief",str(project),"--progress",str(progress),"--target",str(target),"--output",str(route),"--view",str(view)])[0]); code,text=self.call(approve_route,["approve","--route",str(route),"--view",str(view),"--target",str(target),"--approval-output",str(approval),"--handoff-output",str(handoff),"--expected-route-hash",sha(route),"--approved-by","user","--approved-at","2026-09-08T00:00:00Z"]); self.assertEqual(0,code,text); value=json.loads(handoff.read_text()); self.assertEqual("FEATURE_SPECIFICATION",value["nextWorkflow"]); validate_handoff(value,handoff,target); self.assertEqual(before,{p:p.read_bytes() for p in target.glob("src/**/*") if p.is_file()})
 def test_new_feature_reservations_are_unique_and_handoff_is_consumable(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); ids=[]
   for index in range(2):
    route=target/f"docs/new-{index}.json"; view=target/f"docs/new-{index}.md"; code,text=self.call(create_route,["create","--request",f"새 알림 기능 {index}","--project-brief",str(project),"--progress",str(progress),"--target",str(target),"--output",str(route),"--view",str(view)]); self.assertEqual(0,code,text); ids.append(json.loads(route.read_text())["route"]["proposedFeature"]["featureId"])
   self.assertEqual(2,len(set(ids)))
   route=target/"docs/new-0.json"; view=target/"docs/new-0.md"; approval=target/"docs/new-approval.json"; handoff=target/"docs/new-handoff.json"; intake=target/"docs/new-intake.json"; code,text=self.call(approve_route,["approve","--route",str(route),"--view",str(view),"--target",str(target),"--approval-output",str(approval),"--handoff-output",str(handoff),"--expected-route-hash",sha(route),"--approved-by","user","--approved-at","2026-09-08T00:00:00Z"]); self.assertEqual(0,code,text); code,text=self.call(consume_handoff,["consume","--handoff",str(handoff),"--target",str(target),"--output",str(intake)]); self.assertEqual(0,code,text); self.assertEqual("READY_FOR_WORKFLOW",json.loads(intake.read_text())["state"])
 def test_feature_intake_creates_reviewable_draft_once_without_changing_contracts(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); route=target/"docs/route.json"; view=target/"docs/route.md"; approval=target/"docs/approval.json"; handoff=target/"docs/handoff.json"; intake=target/"docs/intake.json"; draft=target/"docs/features/F002/spec.draft.json"; review=target/"docs/features/F002/spec.draft.md"; project_before=project.read_bytes()
   self.assertEqual(0,self.call(create_route,["create","--request","다음 기능 진행","--project-brief",str(project),"--progress",str(progress),"--target",str(target),"--output",str(route),"--view",str(view)])[0]); self.assertEqual(0,self.call(approve_route,["approve","--route",str(route),"--view",str(view),"--target",str(target),"--approval-output",str(approval),"--handoff-output",str(handoff),"--expected-route-hash",sha(route),"--approved-by","user","--approved-at","2026-09-08T00:00:00Z"])[0]); self.assertEqual(0,self.call(consume_handoff,["consume","--handoff",str(handoff),"--target",str(target),"--output",str(intake)])[0])
   args=["draft","--intake",str(intake),"--target",str(target),"--draft-output",str(draft),"--view-output",str(review)]; original=intake.read_bytes(); changed=json.loads(original); changed["requestSummary"]="tampered"; intake.write_text(json.dumps(changed)); code,text=self.call(create_feature_draft,args); self.assertEqual(1,code); self.assertIn("does not match route",text); intake.write_bytes(original); code,text=self.call(create_feature_draft,args); self.assertEqual(0,code,text); self.assertEqual("DRAFT",json.loads(draft.read_text())["feature"]["status"]); self.assertIn("지금 결정해야 할 내용",review.read_text()); self.assertEqual(project_before,project.read_bytes()); code,text=self.call(create_feature_draft,args); self.assertEqual(1,code); self.assertIn("already",text); review.unlink(); code,text=self.call(recover_feature_draft,["recover","--intake",str(intake),"--target",str(target)]); self.assertEqual(0,code,text); self.assertFalse(draft.exists())
 def test_revision_intake_requires_and_copies_current_feature_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   target,project,progress=self.fixture(Path(d)); existing=target/"docs/evidence/featureSpec.json"; route=target/"docs/revise-route.json"; view=target/"docs/revise-route.md"; approval=target/"docs/revise-approval.json"; handoff=target/"docs/revise-handoff.json"; intake=target/"docs/revise-intake.json"; draft=target/"docs/features/F001/spec.revision.draft.json"; review=target/"docs/features/F001/spec.revision.draft.md"
   self.assertEqual(0,self.call(create_route,["create","--request","F001 기능 변경","--feature-id","F001","--project-brief",str(project),"--progress",str(progress),"--target",str(target),"--output",str(route),"--view",str(view)])[0]); self.assertEqual(0,self.call(approve_route,["approve","--route",str(route),"--view",str(view),"--target",str(target),"--approval-output",str(approval),"--handoff-output",str(handoff),"--expected-route-hash",sha(route),"--approved-by","user","--approved-at","2026-09-08T00:00:00Z"])[0]); self.assertEqual(0,self.call(consume_handoff,["consume","--handoff",str(handoff),"--target",str(target),"--output",str(intake)])[0]); args=["draft","--intake",str(intake),"--target",str(target),"--draft-output",str(draft),"--view-output",str(review)]; code,text=self.call(create_feature_draft,args); self.assertEqual(1,code); self.assertIn("existing-feature",text); args.extend(["--existing-feature",str(existing)]); code,text=self.call(create_feature_draft,args); self.assertEqual(0,code,text); value=json.loads(draft.read_text()); self.assertEqual("REVIEW_REQUIRED",value["feature"]["status"]); self.assertEqual(json.loads(existing.read_text())["acceptanceCriteria"],value["acceptanceCriteria"])
if __name__=="__main__": unittest.main()
