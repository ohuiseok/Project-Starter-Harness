#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tests.spring_gradle_acceptance as acceptance


class SpringGradleAcceptanceTests(unittest.TestCase):
    def test_outcome_has_one_user_action_and_explicit_stage(self):
        value = acceptance.outcome("UNKNOWN", "ENVIRONMENT", "TOOL_MISSING", "도구 설치", missing=["bwrap"])
        self.assertEqual("UNKNOWN", value["acceptanceState"])
        self.assertEqual("ENVIRONMENT", value["stage"])
        self.assertEqual("도구 설치", value["nextAction"])
        self.assertIn("FULL_UNMOCKED_CONTRACT_CHAIN", value["doesNotProve"])

    def test_missing_tool_is_unknown_not_product_failure(self):
        with mock.patch.object(acceptance.shutil, "which", side_effect=lambda name: None if name == "bwrap" else "/usr/bin/java"):
            value = acceptance.prerequisites()
        self.assertEqual("UNKNOWN", value["acceptanceState"])
        self.assertEqual("TOOL_MISSING", value["category"])

    def test_diagnostic_messages_are_redacted(self):
        self.assertNotIn("secret-value", acceptance.safe_message("password='secret-value' dev@example.com"))
        self.assertIn("[REDACTED_PII]", acceptance.safe_message("password='secret-value' dev@example.com"))

    def test_invalid_fixture_or_sandbox_is_blocked(self):
        runnable = acceptance.outcome("RUNNABLE", "ENVIRONMENT", "READY", "run", cache={"kind": "GRADLE"}, gradleExecutable="/bin/true")
        with mock.patch.object(acceptance, "prerequisites", return_value=runnable), mock.patch.object(acceptance, "copy_cache", side_effect=ValueError("unsafe cache")):
            value = acceptance.run()
        self.assertEqual("BLOCKED", value["acceptanceState"])
        self.assertEqual("EVIDENCE", value["stage"])

    def test_seed_excludes_feature_and_candidates_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            scenario = acceptance.load_scenario(acceptance.DEFAULT_SCENARIO)
            acceptance.write_seed_files(target, scenario)
            self.assertIn("org.springframework.boot", (target / "build.gradle").read_text())
            self.assertFalse((target / "src/main/java/com/example/OrdersController.java").exists())
            generated = acceptance.write_feature_candidates(target)
            self.assertEqual(2, len(generated))
            self.assertTrue((target / "src/test/java/com/example/OrdersControllerTest.java").is_file())
            self.assertFalse((acceptance.ROOT / "src/main/java/com/example/AcceptanceApplication.java").exists())

    def test_scenario_is_pinned_and_command_cannot_expand(self):
        scenario = acceptance.load_scenario(acceptance.DEFAULT_SCENARIO)
        self.assertEqual("3.2.0", scenario["springBootVersion"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            changed = dict(scenario, command=["./gradlew", "clean", "test"])
            path.write_text(__import__("json").dumps(changed))
            with self.assertRaisesRegex(ValueError, "command"): acceptance.load_scenario(path)

    def test_atomic_output_rejects_occupied_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json";path.write_text("owned")
            with self.assertRaisesRegex(ValueError, "occupied"): acceptance.atomic_output(path, "new")

    def test_atomic_output_materializes_new_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested/result.json"
            acceptance.atomic_output(path, "evidence\n")
            self.assertEqual("evidence\n", path.read_text())


if __name__ == "__main__":
    unittest.main()
