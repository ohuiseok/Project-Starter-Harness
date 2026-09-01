#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(SCRIPTS))

import run_relational_migration_verification as verification  # noqa: E402
from render_relational_migration_verification_plan import render  # noqa: E402
from render_relational_migration_verification_report import render as render_report, validate as validate_report  # noqa: E402
import tests.test_relational_artifact_apply as apply_tests  # noqa: E402


class RelationalMigrationVerificationTests(unittest.TestCase):
    def fixture(self, root: Path):
        applying = apply_tests.RelationalArtifactApplyTests(); _, _, apply_arguments = applying.fixture(root); self.assertEqual(0, applying.run_apply(apply_arguments)[0])
        migration = root / "src/main/resources/db/migration/V1__create_leave_requests.sql"; baseline = root / ".starter-harness-relational.json"
        plan = {"migrationVerificationPlanVersion": 1, "planId": "leave-migration-check", "target": str(root.resolve()), "relationalBaseline": {"path": ".starter-harness-relational.json", "sha256": hashlib.sha256(baseline.read_bytes()).hexdigest()}, "migration": {"path": migration.relative_to(root).as_posix(), "sha256": hashlib.sha256(migration.read_bytes()).hexdigest()}, "database": {"name": "harness_verify", "schema": "public"}, "images": {"postgres": "postgres:17.6", "flyway": "redgate/flyway:13.4.0"}, "limits": {"startupTimeoutSeconds": 10, "commandTimeoutSeconds": 30, "tmpfsBytes": 67108864}, "isolation": {"publishPorts": False, "persistentVolumes": False, "targetDatabaseAccess": False, "cleanupRequired": True}}
        plan_path = root / "verification-plan.json"; plan_path.write_text(json.dumps(plan)); approval = {"migrationVerificationApprovalVersion": 1, "approved": True, "planSha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(), "target": str(root.resolve()), "approvedBy": "test-user", "approvedAt": "2026-09-01T00:00:00Z"}; approval_path = root / "verification-approval.json"; approval_path.write_text(json.dumps(approval)); output = root / "verification-report.json"
        arguments = ["run_relational_migration_verification.py", "--plan", str(plan_path), "--approval", str(approval_path), "--target", str(root), "--output", str(output)]
        return plan_path, approval_path, output, arguments

    @staticmethod
    def completed(command, returncode=0, output="ok"):
        return subprocess.CompletedProcess(command, returncode, output, "" if returncode == 0 else output)

    def run_main(self, arguments, side_effect):
        stream = io.StringIO()
        with mock.patch.object(sys, "argv", arguments), mock.patch.object(verification.subprocess, "run", side_effect=side_effect) as runner, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream): return verification.main(), stream.getvalue(), runner

    def test_approved_plan_uses_private_tmpfs_resources_and_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, output, arguments = self.fixture(root)
            code, text, runner = self.run_main(arguments, lambda command, **_: self.completed(command)); self.assertEqual(0, code, text); report = json.loads(output.read_text()); self.assertEqual("PASSED", report["result"]["state"]); self.assertTrue(all(report["result"]["cleanup"].values()))
            commands = [item.args[0] for item in runner.call_args_list]; database_run = next(item for item in commands if item[:2] == ["docker", "run"] and "postgres:17.6" in item); self.assertNotIn("--publish", database_run); self.assertTrue(any("type=tmpfs" in item for item in database_run)); self.assertNotIn("--volume", database_run)
            network_create = next(item for item in commands if item[:3] == ["docker", "network", "create"]); self.assertIn("--internal", network_create)

    def test_flyway_failure_is_reported_and_resources_are_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, output, arguments = self.fixture(root)
            def result(command, **_): return self.completed(command, 1, "migration failed") if command[-1] == "migrate" else self.completed(command)
            code, _, _ = self.run_main(arguments, result); self.assertEqual(1, code); report = json.loads(output.read_text()); self.assertEqual("FAILED", report["result"]["state"]); self.assertTrue(all(report["result"]["cleanup"].values()))

    def test_ephemeral_credential_is_redacted_from_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, output, arguments = self.fixture(root); secret = "ephemeral-verification-secret"
            with mock.patch.object(verification.secrets, "token_urlsafe", return_value=secret): code, _, _ = self.run_main(arguments, lambda command, **_: self.completed(command, output=secret))
            self.assertEqual(0, code); self.assertNotIn(secret, output.read_text()); self.assertIn("[REDACTED]", output.read_text())

    def test_changed_plan_is_blocked_before_docker_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan, _, output, arguments = self.fixture(root); plan.write_text(plan.read_text() + "\n")
            code, text, runner = self.run_main(arguments, lambda command, **_: self.completed(command)); self.assertEqual(1, code); self.assertIn("exact verification plan", text); runner.assert_not_called(); self.assertFalse(output.exists())

    def test_user_view_discloses_real_effects_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan_path, _, _, _ = self.fixture(root); plan = json.loads(plan_path.read_text()); view = render(plan, hashlib.sha256(plan_path.read_bytes()).hexdigest()); self.assertIn("Docker 이미지가 없으면 내려받음", view); self.assertIn("production DB 접속 안 함", view); self.assertIn("별도 승인", view); self.assertIn("rollback은 검증하지 않음", view)

    def test_result_view_preserves_cleanup_and_scope_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, output, arguments = self.fixture(root); code, _, _ = self.run_main(arguments, lambda command, **_: self.completed(command)); self.assertEqual(0, code); report = json.loads(output.read_text()); validate_report(report, output, root); view = render_report(report); self.assertIn("상태: PASSED", view); self.assertIn("networkRemoved: 완료", view); self.assertIn("production 데이터·권한", view)


if __name__ == "__main__": unittest.main(verbosity=2)
