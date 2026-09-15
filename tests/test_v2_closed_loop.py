#!/usr/bin/env python3
"""Cross-stage contract test from implementation plan evidence to progress v2."""
from __future__ import annotations
import json,subprocess,tempfile,unittest
from pathlib import Path
from unittest import mock
import sys
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
from http_api_spring_mapping import reference
import milestone_completion_v2 as completion
import apply_milestone_completion_v2 as apply_completion
import tests.test_spring_implementation_plan_v2 as plan_tests
class ClosedLoopV2Tests(unittest.TestCase):
 def chain(self,root:Path):
  plan,mapping_path,_=plan_tests.PlanV2Tests().fixture(root);docs=root/"docs";plan_path=docs/"plan.json";plan_path.write_text(json.dumps(plan));plan_approval=docs/"plan-approval.json";plan_approval.write_text(json.dumps({"implementationPlan":reference(plan_path,root)}));dry=docs/"dry.json";dry.write_text(json.dumps({"planId":plan["planId"],"implementationPlanApproval":reference(plan_approval,root)}));candidate=docs/"candidate-verification.json";candidate.write_text(json.dumps({"dryRun":reference(dry,root),"result":{"state":"PASSED"}}));baseline=root/completion.BASELINE;baseline.write_text("{}\n");apply=docs/"apply.json";apply.write_text(json.dumps({"verification":reference(candidate,root),"baseline":{"path":completion.BASELINE,"sha256":completion.sha(baseline)},"committedAt":"2026-09-15T00:00:00Z"}));post_plan=docs/"post-plan.json";post_plan.write_text(json.dumps({"applyResult":reference(apply,root)}));post_approval=docs/"post-approval.json";post_approval.write_text("{}");post=docs/"post.json";post.write_text(json.dumps({"state":"VERIFIED","readyForMilestoneCompletion":True,"milestoneCompletionAuthorized":False,"plan":reference(post_plan,root),"approval":reference(post_approval,root),"applyResult":reference(apply,root),"finishedAt":"2026-09-15T00:01:00Z"}));feature=root/plan["inputs"]["springMapping"]["path"];mapping=json.loads(mapping_path.read_text());feature=root/mapping["inputs"]["featureSpec"]["path"];project=docs/"project.json";project.write_text(json.dumps({"project":{"name":"Orders","goal":"Manage orders"},"featureCandidates":[],"unknowns":[]}));return feature,project,post,dry
 def test_real_references_flow_to_atomic_progress(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);feature,project,post,_=self.chain(root)
   subprocess.run(["git","config","user.email","test@example.com"],cwd=root,check=True);subprocess.run(["git","config","user.name","Test"],cwd=root,check=True);subprocess.run(["git","add","."],cwd=root,check=True);subprocess.run(["git","commit","-qm","fixture"],cwd=root,check=True)
   with mock.patch.object(completion,"validate_post_result"),mock.patch.object(completion,"validate_post_plan"),mock.patch.object(completion,"validate_post_approval"):chain=completion.evidence_chain(root,post,feature)
   chain["feature"]["feature"].update(name="Create order",userValue="An order can be created")
   with mock.patch.object(completion,"evidence_chain",return_value=chain),mock.patch.object(completion,"validate_project",return_value=(True,[])),mock.patch.object(completion,"validate_feature",return_value=(True,[])):review=completion.build_review(root,post,feature,project,"docs/completion.json","2026-09-15T00:02:00Z")
   review_path=root/"docs/review.json";review_path.write_text(json.dumps(review));approval=root/"docs/approval.json";approval.write_text("{}")
   with mock.patch.object(apply_completion,"validate_approval"):record=apply_completion.apply(root,review_path,approval)
   self.assertEqual("COMMITTED",record["state"]);progress=json.loads((root/completion.PROGRESS).read_text());self.assertEqual([review["completion"]["document"]["featureId"]],[i["featureId"] for i in progress["completedMilestones"]])
 def test_mid_chain_hash_tampering_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);feature,_,post,dry=self.chain(root);dry.write_text(dry.read_text()+" ")
   with mock.patch.object(completion,"validate_post_result"),mock.patch.object(completion,"validate_post_plan"),mock.patch.object(completion,"validate_post_approval"),self.assertRaisesRegex(ValueError,"dry run evidence changed"):completion.evidence_chain(root,post,feature)
if __name__=="__main__":unittest.main()
