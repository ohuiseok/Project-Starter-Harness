#!/usr/bin/env python3
from __future__ import annotations
import json,shutil,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
import tests.spring_v2_production_apply_acceptance as acceptance

class ProductionApplyAcceptanceContractTests(unittest.TestCase):
 def test_result_contract_exposes_phase_scope_and_next_action(self):
  value=acceptance.outcome("BLOCKED","APPLY","BLOCKED_STALE","변경 내용을 다시 검토")
  self.assertEqual(["PREPARE","CANDIDATE_VERIFICATION"],value["completedPhases"]);self.assertEqual("NOT_RUN",value["scope"]["databaseRuntime"]);self.assertEqual("변경 내용을 다시 검토",value["nextAction"])
 def test_main_acceptance_has_no_mocking_dependency(self):
  source=Path(acceptance.__file__).read_text();self.assertNotIn("unittest.mock",source);self.assertNotIn("mock.patch",source)
 def test_failure_classification_separates_stale_code_and_environment(self):
  self.assertEqual(("BLOCKED","BLOCKED_STALE"),acceptance.failure_state("APPLY","target context changed"))
  self.assertEqual(("FAILED","FAILED_CODE"),acceptance.failure_state("APPLY","",fields={"VERIFICATION_RESULT":"FAILED"}))
  self.assertEqual(("UNKNOWN","UNKNOWN_ENVIRONMENT"),acceptance.failure_state("CANDIDATE_VERIFICATION","tool unavailable"))
 def test_unsafe_or_occupied_output_is_rejected(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/"result.json";path.write_text("owned")
   with self.assertRaisesRegex(ValueError,"occupied"):acceptance.atomic_output(path,"{}")
 def test_user_view_shows_five_phases_exclusions_and_next_action(self):
  value=acceptance.outcome("PASSED","COMPLETION","DONE","다음 기능 입력");value["completedPhases"]=acceptance.PHASES
  rendered=acceptance.render_result(value)
  self.assertIn("후보 검증: 완료",rendered);self.assertIn("DB runtime: `NOT_RUN`",rendered);self.assertIn("다음 기능 입력",rendered)
 def test_evidence_bundle_survives_temporary_target_removal(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);target=root/"target";target.mkdir();(target/"docs").mkdir();(target/"docs/evidence.json").write_text("{}")
   destination=root/"bundle";saved=acceptance.persist_bundle(target,destination,{"acceptanceState":"PASSED"});shutil.rmtree(target)
   manifest=json.loads((destination/"manifest.json").read_text());self.assertEqual(saved["manifestSha256"],acceptance.sha(destination/"manifest.json"));self.assertTrue(manifest["files"])
if __name__=="__main__":unittest.main()
