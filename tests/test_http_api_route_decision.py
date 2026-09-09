#!/usr/bin/env python3
from __future__ import annotations
import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parent.parent; SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts"; sys.path[:0]=[str(SCRIPTS),str(ROOT)]
import discover_http_api_evidence as discovery
import http_api_route_decision as route_decision
import prepare_design_route_from_completion as prepare_route
from spring_milestone_completion import sha
import tests.test_design_route_preparation as design_route_fixtures

class HttpApiRouteDecisionTests(unittest.TestCase):
 def invoke(self,module,arguments):
  stream=io.StringIO()
  with mock.patch.object(sys,"argv",arguments),contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream): code=module.main()
  return code,stream.getvalue()
 def fixture(self,parent):
  helper=design_route_fixtures.DesignRoutePreparationTests(methodName="test_prepares_recommended_route_and_user_choices")
  root,completion,project,profile=helper.fixture(parent); current=root/"docs/features/F001/design-route.draft.v001.json"
  code,text=self.invoke(prepare_route,["prepare","--completion",str(completion),"--project-brief",str(project),"--profile",str(profile),"--target",str(root),"--output",str(current),"--view",str(current.with_suffix('.md'))]); self.assertEqual(0,code,text)
  feature=root/"docs/features/F001/spec.json"; report=root/"docs/features/F001/http-api-evidence.json"
  code,text=self.invoke(discovery,["discover","--feature",str(feature),"--profile",str(profile),"--target",str(root),"--output",str(report),"--view",str(report.with_suffix('.md'))]); self.assertEqual(0,code,text)
  return root,current,report
 def decision_paths(self,root):
  base=root/"docs/features/F001"; return base/"http-api-route-proposal.json",base/"http-api-route-decision.json",base/"design-route.draft.v002.json",base/"http-api-route-decision-approval.json"
 def prepare_decision(self,root,current,report,extra=None):
  proposal,decision,next_route,_=self.decision_paths(root); args=["decision","prepare","--current",str(current),"--discovery",str(report),"--discovery-view",str(report.with_suffix('.md')),"--proposal",str(proposal),"--output",str(decision),"--view",str(decision.with_suffix('.md')),"--route-output",str(next_route),"--target",str(root),"--contract-id","http-api","--disposition","CREATE","--selection-source","RECOMMENDATION_ACCEPTED","--reason-code","NO_EVIDENCE_FOUND","--reason","기존 API 근거가 없어 새 계약을 생성"]+(extra or [])
  return self.invoke(route_decision,args)
 def test_selection_preview_does_not_change_route(self):
  with tempfile.TemporaryDirectory() as d:
   root,current,report=self.fixture(Path(d)); before=current.read_bytes(); code,text=self.prepare_decision(root,current,report); self.assertEqual(0,code,text); proposal,decision,next_route,_=self.decision_paths(root); self.assertEqual(before,current.read_bytes()); self.assertFalse(next_route.exists()); self.assertEqual("READY_FOR_APPROVAL",json.loads(decision.read_text())["state"]); self.assertTrue(proposal.exists())
 def test_exact_approval_then_atomic_apply_creates_revision(self):
  with tempfile.TemporaryDirectory() as d:
   root,current,report=self.fixture(Path(d)); self.assertEqual(0,self.prepare_decision(root,current,report)[0]); proposal,decision,next_route,approval=self.decision_paths(root)
   code,text=self.invoke(route_decision,["decision","approve","--report",str(decision),"--view",str(decision.with_suffix('.md')),"--output",str(approval),"--target",str(root),"--expected-report-hash",sha(decision)]); self.assertEqual(0,code,text); self.assertFalse(next_route.exists())
   code,text=self.invoke(route_decision,["decision","apply","--report",str(decision),"--approval",str(approval),"--target",str(root)]); self.assertEqual(0,code,text); revised=json.loads(next_route.read_text()); http=next(item for item in revised["routes"] if item["contractId"]=="http-api"); self.assertEqual("CREATE",http["disposition"]); self.assertTrue(http["confirmedByUser"]); self.assertTrue(any(item["kind"]=="HTTP_API_DISCOVERY:CREATE" for item in revised["inputs"]["codeEvidence"])); journal=root/".starter-harness/design-route-draft-updates"/f"{sha(current)}.json"; self.assertEqual("COMMITTED",json.loads(journal.read_text())["state"])
 def test_ambiguous_recommendation_cannot_be_accepted(self):
  with tempfile.TemporaryDirectory() as d:
   root,current,old_report=self.fixture(Path(d)); old_report.unlink(); old_report.with_suffix('.md').unlink(); (root/"legacy.yaml").write_text("openapi: 3.0.3\npaths: {}\n"); feature=root/"docs/features/F001/spec.json"; profile=root/"docs/project-profile.json"; code,text=self.invoke(discovery,["discover","--feature",str(feature),"--profile",str(profile),"--target",str(root),"--output",str(old_report),"--view",str(old_report.with_suffix('.md'))]); self.assertEqual(0,code,text); code,text=self.prepare_decision(root,current,old_report); self.assertEqual(1,code); self.assertIn("ambiguous",text)
 def test_changed_decision_cannot_be_approved(self):
  with tempfile.TemporaryDirectory() as d:
   root,current,report=self.fixture(Path(d)); self.assertEqual(0,self.prepare_decision(root,current,report)[0]); _,decision,_,approval=self.decision_paths(root); expected=sha(decision); decision.write_text(decision.read_text()+" "); code,text=self.invoke(route_decision,["decision","approve","--report",str(decision),"--view",str(decision.with_suffix('.md')),"--output",str(approval),"--target",str(root),"--expected-report-hash",expected]); self.assertEqual(1,code); self.assertFalse(approval.exists())
 def test_changed_evidence_blocks_approved_apply(self):
  with tempfile.TemporaryDirectory() as d:
   root,current,report=self.fixture(Path(d)); self.assertEqual(0,self.prepare_decision(root,current,report)[0]); _,decision,next_route,approval=self.decision_paths(root); code,text=self.invoke(route_decision,["decision","approve","--report",str(decision),"--view",str(decision.with_suffix('.md')),"--output",str(approval),"--target",str(root),"--expected-report-hash",sha(decision)]); self.assertEqual(0,code,text); report.write_text(report.read_text()+" "); code,text=self.invoke(route_decision,["decision","apply","--report",str(decision),"--approval",str(approval),"--target",str(root)]); self.assertEqual(1,code); self.assertFalse(next_route.exists())
 def test_unrelated_route_change_hidden_in_proposal_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root,current,report=self.fixture(Path(d)); self.assertEqual(0,self.prepare_decision(root,current,report)[0]); proposal,decision,next_route,approval=self.decision_paths(root); proposed=json.loads(proposal.read_text()); proposed["routes"][1]["reason"]="unapproved unrelated change"; proposal.write_text(json.dumps(proposed)); value=json.loads(decision.read_text()); value["proposal"]["sha256"]=sha(proposal); decision.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n"); decision.with_suffix('.md').write_text(route_decision.render(value)); code,text=self.invoke(route_decision,["decision","approve","--report",str(decision),"--view",str(decision.with_suffix('.md')),"--output",str(approval),"--target",str(root),"--expected-report-hash",sha(decision)]); self.assertEqual(0,code,text); code,text=self.invoke(route_decision,["decision","apply","--report",str(decision),"--approval",str(approval),"--target",str(root)]); self.assertEqual(1,code); self.assertIn("outside",text); self.assertFalse(next_route.exists())

if __name__=="__main__": unittest.main()
