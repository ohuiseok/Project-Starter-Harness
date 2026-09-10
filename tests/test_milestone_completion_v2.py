#!/usr/bin/env python3
from __future__ import annotations
import json,tempfile,unittest
from pathlib import Path
from unittest import mock
import sys
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
import apply_milestone_completion_v2 as apply_script
import milestone_completion_v2 as core
import recover_milestone_completion_v2 as recover_script
class CompletionV2Tests(unittest.TestCase):
 def fixture(self,root:Path,legacy=False):
  docs=root/"docs";docs.mkdir();project=docs/"project.json";feature=docs/"feature.json";post=docs/"post.json";project.write_text(json.dumps({"project":{"name":"Sample","goal":"Goal"},"featureCandidates":[],"unknowns":[]}));feature.write_text(json.dumps({"feature":{"id":"F001","name":"Create","userValue":"Value"}}));post.write_text("{}");
  if legacy:(docs/"progress.json").write_text("{}")
  chain={"feature":json.loads(feature.read_text()),"featureId":"F001","featureRef":core.reference(feature,root),"implementationPlan":core.reference(feature,root),"dryRun":core.reference(feature,root),"candidateVerification":core.reference(feature,root),"applyResult":core.reference(feature,root),"postApplyVerification":core.reference(post,root),"baseline":{"path":".starter-harness-implementation-v2.json","sha256":"a"*64},"times":{"implementedAt":"2026-09-10T00:00:00Z","verifiedAt":"2026-09-10T00:01:00Z"}}
  with mock.patch.object(core,"evidence_chain",return_value=chain):review=core.build_review(root,post,feature,project,"docs/completion.json","2026-09-10T00:02:00Z")
  review_path=docs/"review.json";review_path.write_text(json.dumps(review));approval=docs/"approval.json";approval.write_text("{}");return review,review_path,approval
 def test_completion_separates_state_from_verification_levels(self):
  with tempfile.TemporaryDirectory() as d:
   review,_,_=self.fixture(Path(d));completion=review["completion"]["document"];self.assertEqual("COMPLETED",completion["state"]);self.assertEqual("PASSED",completion["verificationLevels"]["appliedIsolated"]);self.assertEqual("NOT_RUN",completion["verificationLevels"]["deployment"])
 def test_legacy_progress_requires_separate_migration(self):
  with tempfile.TemporaryDirectory() as d:
   review,_,_=self.fixture(Path(d),True);self.assertEqual("PROGRESS_V1_MIGRATION_REQUIRED",review["blockers"][0]["code"]);self.assertFalse(review["readyForApproval"])
 def test_apply_commits_completion_progress_and_view(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);review,path,approval=self.fixture(root)
   with mock.patch.object(apply_script,"validate_approval"):record=apply_script.apply(root,path,approval)
   self.assertEqual("COMMITTED",record["state"]);self.assertTrue((root/"docs/completion.json").is_file());self.assertTrue((root/core.PROGRESS).is_file());self.assertTrue((root/core.VIEW).is_file())
 def test_view_failure_preserves_committed_json_for_recovery(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);review,path,approval=self.fixture(root);real=apply_script.atomic_file
   def fail_view(data,mode,destination):
    if destination==root/core.VIEW:raise OSError("view")
    return real(data,mode,destination)
   with mock.patch.object(apply_script,"validate_approval"),mock.patch.object(apply_script,"atomic_file",side_effect=fail_view):record=apply_script.apply(root,path,approval)
   self.assertEqual("COMMITTED_VIEW_PENDING",record["state"]);self.assertTrue((root/core.PROGRESS).is_file())
   with mock.patch.object(sys,"argv",["recover","--target",str(root),"--attempt-id",review["completionAttemptId"]]):self.assertEqual(0,recover_script.main())
   self.assertTrue((root/core.VIEW).is_file())
 def test_recommendation_is_versioned_derived_state(self):
  with tempfile.TemporaryDirectory() as d:
   review,_,_=self.fixture(Path(d));progress=review["progressAfter"]["document"];self.assertEqual(1,progress["recommendationPolicyVersion"]);self.assertEqual(1,progress["verificationLevelModelVersion"])
if __name__=="__main__":unittest.main()
