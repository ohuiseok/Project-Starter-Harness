#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(SCRIPTS))

import apply_approved_relational_artifacts as relational_apply  # noqa: E402
import tests.test_relational_artifact_dry_run as dry_tests  # noqa: E402
from render_generation_dry_run import load_baseline  # noqa: E402


class RelationalArtifactApplyTests(unittest.TestCase):
    def fixture(self, root: Path):
        dry = dry_tests.RelationalArtifactDryRunTests(); _, _, plan_path, report_path, dry_args = dry.fixture(root)
        self.assertEqual(0, dry.run_dry(dry_args)[0])
        approval = {"relationalArtifactApprovalVersion": 1, "approved": True, "dryRunReportSha256": hashlib.sha256(report_path.read_bytes()).hexdigest(), "target": str(root.resolve()), "approvedBy": "test-user", "approvedAt": "2026-09-01T00:00:00Z"}
        approval_path = root / "approval.json"; approval_path.write_text(json.dumps(approval))
        values = {dry_args[index][2:].replace("-", "_"): Path(dry_args[index + 1]) for index in range(1, len(dry_args), 2)}
        arguments = ["apply_approved_relational_artifacts.py", "--report", str(report_path), "--approval", str(approval_path), "--physical-contract", str(values["physical_contract"]), "--physical-model", str(values["physical_model"]), "--logical-contract", str(values["logical_contract"]), "--route", str(values["route"]), "--feature", str(values["feature"]), "--profile", str(values["profile"]), "--artifact-plan", str(plan_path), "--target", str(root)]
        return report_path, approval_path, arguments

    def run_apply(self, arguments: list[str]) -> tuple[int, str]:
        stream = io.StringIO()
        with mock.patch.object(sys, "argv", arguments), contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream): return relational_apply.main(), stream.getvalue()

    def test_exact_approved_report_is_atomically_applied_with_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); report, _, arguments = self.fixture(root); code, output = self.run_apply(arguments)
            self.assertEqual(0, code, output); self.assertTrue((root / "compose.yaml").is_file()); self.assertTrue((root / "src/main/resources/db/migration/V1__create_leave_requests.sql").is_file())
            baseline = json.loads((root / ".starter-harness-relational.json").read_text()); self.assertEqual("RELATIONAL", baseline["artifactKind"]); self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(), baseline["appliedFromDryRunSha256"])
            files, modes = load_baseline(root / ".starter-harness-relational.json"); self.assertEqual(baseline["files"], files); self.assertEqual(baseline["modes"], modes)
            self.assertIn("DATABASE_OR_CONTAINER_CHANGED: no", output)

    def test_target_drift_before_apply_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, arguments = self.fixture(root); (root / "compose.yaml").write_text("appeared after review\n")
            code, output = self.run_apply(arguments); self.assertEqual(1, code); self.assertIn("CREATE target changed after dry run", output); self.assertFalse((root / ".starter-harness-relational.json").exists())

    def test_altered_report_invalidates_exact_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); report, _, arguments = self.fixture(root); report.write_text(report.read_text() + "\n")
            code, output = self.run_apply(arguments); self.assertEqual(1, code); self.assertIn("exact dry-run report SHA-256", output); self.assertFalse((root / "compose.yaml").exists())

    def test_changed_physical_model_is_rejected_during_rerender(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, arguments = self.fixture(root); model_index = arguments.index("--physical-model") + 1; model = Path(arguments[model_index]); model.write_text(model.read_text() + "\n")
            code, output = self.run_apply(arguments); self.assertEqual(1, code); self.assertIn("physical model changed after dry run", output); self.assertFalse((root / "compose.yaml").exists())

    def test_partial_failure_rolls_back_files_and_records_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, arguments = self.fixture(root); real_replace = os.replace; commits = 0
            def fail_second(source, destination):
                nonlocal commits
                if "/commit/" in str(source):
                    commits += 1
                    if commits == 2: raise OSError("injected commit failure")
                return real_replace(source, destination)
            with mock.patch.object(relational_apply.os, "replace", side_effect=fail_second): code, output = self.run_apply(arguments)
            self.assertEqual(1, code); self.assertIn("was rolled back", output); self.assertFalse((root / "compose.yaml").exists()); self.assertFalse((root / "src").exists()); self.assertFalse((root / ".starter-harness-relational.json").exists())
            records = list((root / ".starter-harness/transactions").glob("*/transaction.json")); self.assertEqual(1, len(records)); self.assertEqual("ROLLED_BACK", json.loads(records[0].read_text())["state"])

    def test_malformed_existing_relational_baseline_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, arguments = self.fixture(root); baseline = root / ".starter-harness-relational.json"; baseline.write_text('{"manifestVersion": 1, "artifactKind": "OTHER"}')
            before = baseline.read_bytes(); code, output = self.run_apply(arguments); self.assertEqual(1, code); self.assertIn("unsupported identity", output); self.assertEqual(before, baseline.read_bytes()); self.assertFalse((root / "compose.yaml").exists())


if __name__ == "__main__": unittest.main(verbosity=2)
