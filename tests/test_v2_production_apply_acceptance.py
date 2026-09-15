#!/usr/bin/env python3
from __future__ import annotations
import sys,tempfile,unittest
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
  self.assertEqual(("FAILED","FAILED_CODE"),acceptance.failure_state("APPLY","VERIFICATION_RESULT: FAILED"))
  self.assertEqual(("UNKNOWN","UNKNOWN_ENVIRONMENT"),acceptance.failure_state("CANDIDATE_VERIFICATION","tool unavailable"))
 def test_unsafe_or_occupied_output_is_rejected(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/"result.json";path.write_text("owned")
   with self.assertRaisesRegex(ValueError,"occupied"):acceptance.atomic_output(path,"{}")
if __name__=="__main__":unittest.main()
