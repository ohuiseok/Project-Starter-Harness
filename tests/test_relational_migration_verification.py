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
import recover_relational_migration_verification as recovery  # noqa: E402
from migrate_relational_migration_verification_plan_v2 import migrate as migrate_plan_v2  # noqa: E402
from render_relational_migration_verification_plan import render  # noqa: E402
from render_relational_migration_verification_report import render as render_report, validate as validate_report  # noqa: E402
import tests.test_relational_artifact_apply as apply_tests  # noqa: E402


class RelationalMigrationVerificationTests(unittest.TestCase):
    def fixture(self, root: Path):
        applying = apply_tests.RelationalArtifactApplyTests(); _, _, apply_arguments = applying.fixture(root); self.assertEqual(0, applying.run_apply(apply_arguments)[0])
        migration = root / "src/main/resources/db/migration/V1__create_leave_requests.sql"; baseline = root / ".starter-harness-relational.json"
        plan = {"migrationVerificationPlanVersion": 2, "planId": "leave-migration-check", "target": str(root.resolve()), "relationalBaseline": {"path": ".starter-harness-relational.json", "sha256": hashlib.sha256(baseline.read_bytes()).hexdigest()}, "migrations": [{"version": "1", "description": "create leave requests", "path": migration.relative_to(root).as_posix(), "sha256": hashlib.sha256(migration.read_bytes()).hexdigest()}], "database": {"name": "harness_verify", "schema": "public"}, "images": {"postgres": "postgres:17.6", "flyway": "flyway/flyway:13.4.0"}, "limits": {"startupTimeoutSeconds": 10, "commandTimeoutSeconds": 30, "tmpfsBytes": 67108864}, "isolation": {"publishPorts": False, "persistentVolumes": False, "targetDatabaseAccess": False, "cleanupRequired": True}}
        plan_path = root / "verification-plan.json"; plan_path.write_text(json.dumps(plan)); approval = {"migrationVerificationApprovalVersion": 1, "approved": True, "planSha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(), "target": str(root.resolve()), "approvedBy": "test-user", "approvedAt": "2026-09-01T00:00:00Z"}; approval_path = root / "verification-approval.json"; approval_path.write_text(json.dumps(approval)); output = root / "verification-report.json"
        arguments = ["run_relational_migration_verification.py", "--plan", str(plan_path), "--approval", str(approval_path), "--target", str(root), "--output", str(output)]
        return plan_path, approval_path, output, arguments

    @staticmethod
    def completed(command, returncode=0, output="ok"):
        if command[:3] == ["docker", "image", "inspect"]:
            output = json.dumps([{"Id": "sha256:" + "a" * 64, "RepoDigests": [f"{command[-1].split(':')[0]}@sha256:" + "b" * 64]}])
        if "info" in command:
            output = json.dumps({"migrations": [{"category": "Versioned", "version": "1", "description": "create leave requests", "state": "Success"}]})
        return subprocess.CompletedProcess(command, returncode, output, "" if returncode == 0 else output)

    def run_main(self, arguments, side_effect):
        stream = io.StringIO()
        with mock.patch.object(sys, "argv", arguments), mock.patch.object(verification.subprocess, "run", side_effect=side_effect) as runner, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream): return verification.main(), stream.getvalue(), runner

    def test_approved_plan_uses_private_tmpfs_resources_and_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, output, arguments = self.fixture(root)
            code, text, runner = self.run_main(arguments, lambda command, **_: self.completed(command)); self.assertEqual(0, code, text); report = json.loads(output.read_text()); self.assertEqual("PASSED", report["result"]["state"]); self.assertTrue(all(report["result"]["cleanup"].values()))
            commands = [item.args[0] for item in runner.call_args_list]; database_run = next(item for item in commands if item[:3] == ["docker", "run", "--detach"]); self.assertNotIn("--publish", database_run); self.assertTrue(any("type=tmpfs" in item for item in database_run)); self.assertNotIn("--volume", database_run); self.assertEqual("sha256:" + "a" * 64, database_run[-1])
            network_create = next(item for item in commands if item[:3] == ["docker", "network", "create"]); self.assertIn("--internal", network_create)
            self.assertEqual({"postgres", "flyway"}, set(report["result"]["images"])); self.assertEqual("sha256:" + "a" * 64, report["result"]["images"]["postgres"]["imageId"])

    def test_two_version_chain_is_staged_and_history_is_matched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan_path, approval_path, output, arguments = self.fixture(root); baseline_path = root / ".starter-harness-relational.json"
            second = root / "src/main/resources/db/migration/V2__add_status.sql"; second.write_text("ALTER TABLE leave_requests ADD COLUMN status varchar(20);\n")
            baseline = json.loads(baseline_path.read_text()); relative = second.relative_to(root).as_posix(); baseline["files"][relative] = hashlib.sha256(second.read_bytes()).hexdigest(); baseline["modes"][relative] = 0o644; baseline_path.write_text(json.dumps(baseline))
            plan = json.loads(plan_path.read_text()); plan["relationalBaseline"]["sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest(); plan["migrations"].append({"version": "2", "description": "add status", "path": relative, "sha256": hashlib.sha256(second.read_bytes()).hexdigest()}); plan_path.write_text(json.dumps(plan))
            approval = json.loads(approval_path.read_text()); approval["planSha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest(); approval_path.write_text(json.dumps(approval))
            history = {"migrations": [{"category": "Versioned", "version": "1", "description": "create leave requests", "state": "Success"}, {"category": "Versioned", "version": "2", "description": "add status", "state": "Success"}]}
            def result(command, **_): return subprocess.CompletedProcess(command, 0, json.dumps(history), "") if "info" in command else self.completed(command)
            code, text, _ = self.run_main(arguments, result); self.assertEqual(0, code, text); report = json.loads(output.read_text()); self.assertEqual(["1", "2"], [item["version"] for item in report["result"]["appliedMigrations"]])

    def test_flyway_history_mismatch_fails_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, output, arguments = self.fixture(root); history = {"migrations": [{"category": "Versioned", "version": "1", "description": "unexpected", "state": "Success"}]}
            def result(command, **_): return subprocess.CompletedProcess(command, 0, json.dumps(history), "") if "info" in command else self.completed(command)
            code, _, _ = self.run_main(arguments, result); self.assertEqual(1, code); report = json.loads(output.read_text()); self.assertEqual("FAILED", report["result"]["state"]); self.assertIn("does not match approved migration 1", report["result"]["failure"]); self.assertTrue(all(report["result"]["cleanup"].values()))

    def test_duplicate_version_is_blocked_before_docker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan_path, approval_path, _, arguments = self.fixture(root); plan = json.loads(plan_path.read_text()); duplicate = dict(plan["migrations"][0]); duplicate["version"] = "1.0"; plan["migrations"].append(duplicate); plan_path.write_text(json.dumps(plan)); approval = json.loads(approval_path.read_text()); approval["planSha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest(); approval_path.write_text(json.dumps(approval))
            code, text, runner = self.run_main(arguments, lambda command, **_: self.completed(command)); self.assertEqual(1, code); self.assertIn("duplicate Flyway migration version", text); runner.assert_not_called()

    def test_omitted_baseline_owned_migration_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan_path, approval_path, _, arguments = self.fixture(root); second = root / "src/main/resources/db/migration/V2__required.sql"; second.write_text("SELECT 1;\n"); baseline_path = root / ".starter-harness-relational.json"; baseline = json.loads(baseline_path.read_text()); relative = second.relative_to(root).as_posix(); baseline["files"][relative] = hashlib.sha256(second.read_bytes()).hexdigest(); baseline["modes"][relative] = 0o644; baseline_path.write_text(json.dumps(baseline))
            plan = json.loads(plan_path.read_text()); plan["relationalBaseline"]["sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest(); plan["migrations"][0]["version"] = "3"; migration = root / plan["migrations"][0]["path"]; renamed = migration.with_name("V3__create_leave_requests.sql"); migration.rename(renamed); plan["migrations"][0]["path"] = renamed.relative_to(root).as_posix(); plan["migrations"][0]["sha256"] = hashlib.sha256(renamed.read_bytes()).hexdigest(); del baseline["files"][migration.relative_to(root).as_posix()]; del baseline["modes"][migration.relative_to(root).as_posix()]; baseline["files"][plan["migrations"][0]["path"]] = plan["migrations"][0]["sha256"]; baseline["modes"][plan["migrations"][0]["path"]] = 0o644; baseline_path.write_text(json.dumps(baseline)); plan["relationalBaseline"]["sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest(); plan_path.write_text(json.dumps(plan)); approval = json.loads(approval_path.read_text()); approval["planSha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest(); approval_path.write_text(json.dumps(approval))
            code, text, runner = self.run_main(arguments, lambda command, **_: self.completed(command)); self.assertEqual(1, code); self.assertIn("omits baseline-owned", text); runner.assert_not_called()

    def test_legacy_plan_migrates_to_unapproved_single_item_chain(self) -> None:
        legacy = {"migrationVerificationPlanVersion": 1, "planId": "legacy", "target": "/tmp/example", "relationalBaseline": {"path": ".starter-harness-relational.json", "sha256": "a" * 64}, "migration": {"path": "db/V01_2__add_user_status.sql", "sha256": "b" * 64}, "database": {}, "images": {}, "limits": {}, "isolation": {}}
        migrated = migrate_plan_v2(legacy); self.assertEqual(2, migrated["migrationVerificationPlanVersion"]); self.assertEqual("1.2", migrated["migrations"][0]["version"]); self.assertEqual("add user status", migrated["migrations"][0]["description"]); self.assertNotIn("migration", migrated)

    def test_flyway_failure_is_reported_and_resources_are_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, output, arguments = self.fixture(root)
            def result(command, **_): return self.completed(command, 1, "migration failed") if command[-1] == "migrate" else self.completed(command)
            code, _, _ = self.run_main(arguments, result); self.assertEqual(1, code); report = json.loads(output.read_text()); self.assertEqual("FAILED", report["result"]["state"]); self.assertTrue(all(report["result"]["cleanup"].values()))

    def test_cleanup_failure_keeps_recoverable_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, output, arguments = self.fixture(root)
            def result(command, **_):
                if command[:3] == ["docker", "network", "rm"]: return self.completed(command, 1, "network still attached")
                return self.completed(command)
            code, _, _ = self.run_main(arguments, result); self.assertEqual(1, code)
            report = json.loads(output.read_text()); self.assertEqual("CLEANUP_FAILED", report["result"]["state"])
            journal = json.loads((root / verification.JOURNAL_PATH).read_text()); self.assertEqual("CLEANUP_REQUIRED", journal["state"])

    def test_pending_journal_blocks_retry_before_docker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, _, arguments = self.fixture(root); pending = root / verification.JOURNAL_PATH; pending.parent.mkdir(parents=True); pending.write_text("{}")
            code, text, runner = self.run_main(arguments, lambda command, **_: self.completed(command)); self.assertEqual(1, code); self.assertIn("recover it before retrying", text); runner.assert_not_called()

    def test_symlinked_evidence_directory_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory); _, _, _, arguments = self.fixture(root); (root / ".starter-harness/verification").symlink_to(outside, target_is_directory=True)
            code, text, runner = self.run_main(arguments, lambda command, **_: self.completed(command)); self.assertEqual(1, code); self.assertIn("evidence directory is unsafe", text); runner.assert_not_called()

    def test_recovery_removes_only_labeled_recorded_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan_path, _, _, _ = self.fixture(root)
            plan = json.loads(plan_path.read_text())
            with mock.patch.object(verification.secrets, "token_hex", return_value="abcdef123456"):
                journal = verification.execution_resources(plan, root.resolve(), plan_path)
            pending = root / verification.JOURNAL_PATH; verification.atomic_json(journal, pending)
            def result(command, *_, **__):
                if "inspect" in command: return self.completed(command, output="true\n")
                return self.completed(command)
            with mock.patch.object(recovery, "run", side_effect=result) as runner: recovered = recovery.recover(root)
            self.assertEqual("RECOVERED", recovered["state"]); self.assertFalse(pending.exists())
            self.assertTrue((root / ".starter-harness/verification/recovered/abcdef123456.json").is_file())
            remove_commands = [item.args[0] for item in runner.call_args_list if "rm" in item.args[0]]; self.assertEqual(5, len(remove_commands))

    def test_recovery_refuses_unlabeled_resource(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan_path, _, _, _ = self.fixture(root); plan = json.loads(plan_path.read_text())
            with mock.patch.object(verification.secrets, "token_hex", return_value="abcdef123456"): journal = verification.execution_resources(plan, root.resolve(), plan_path)
            pending = root / verification.JOURNAL_PATH; verification.atomic_json(journal, pending)
            with mock.patch.object(recovery, "run", return_value=self.completed([], output="false\n")) as runner:
                with self.assertRaisesRegex(ValueError, "refusing to remove unlabeled"): recovery.recover(root)
            self.assertTrue(pending.is_file()); self.assertFalse(any("rm" in item.args[0] for item in runner.call_args_list))

    def test_ephemeral_credential_is_redacted_from_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, output, arguments = self.fixture(root); secret = "ephemeral-verification-secret"
            def result(command, **_):
                if command[:2] == ["docker", "version"]: return self.completed(command, output="29.1.3")
                if command[:2] == ["docker", "pull"]: return self.completed(command, output="pull ok")
                return self.completed(command, output=secret)
            with mock.patch.object(verification.secrets, "token_urlsafe", return_value=secret): code, _, _ = self.run_main(arguments, result)
            self.assertEqual(0, code); self.assertNotIn(secret, output.read_text()); self.assertIn("[REDACTED]", output.read_text())

    def test_long_output_is_marked_as_truncated(self) -> None:
        value = "x" * (verification.MAX_OUTPUT + 25); result = verification.bounded(value, "not-present")
        self.assertIn("앞부분 25자 생략됨", result); self.assertTrue(result.endswith("x" * verification.MAX_OUTPUT))

    def test_approved_digest_mismatch_is_blocked(self) -> None:
        reference = "flyway/flyway@sha256:" + "b" * 64; inspected = json.dumps([{"Id": "sha256:" + "a" * 64, "RepoDigests": ["flyway/flyway@sha256:" + "c" * 64]}])
        def result(command, _timeout): return subprocess.CompletedProcess(command, 0, inspected if "inspect" in command else "pulled", "")
        with mock.patch.object(verification, "run", side_effect=result):
            with self.assertRaisesRegex(ValueError, "does not match the approved reference"): verification.prepare_image(reference, 30, [])

    def test_changed_plan_is_blocked_before_docker_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan, _, output, arguments = self.fixture(root); plan.write_text(plan.read_text() + "\n")
            code, text, runner = self.run_main(arguments, lambda command, **_: self.completed(command)); self.assertEqual(1, code); self.assertIn("exact verification plan", text); runner.assert_not_called(); self.assertFalse(output.exists())

    def test_user_view_discloses_real_effects_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan_path, _, _, _ = self.fixture(root); plan = json.loads(plan_path.read_text()); view = render(plan, hashlib.sha256(plan_path.read_bytes()).hexdigest()); self.assertIn("Docker 이미지가 없으면 내려받음", view); self.assertIn("Docker cache에 남음", view); self.assertIn("실행 흐름", view); self.assertIn("production DB 접속 안 함", view); self.assertIn("별도 승인", view); self.assertIn("rollback은 검증하지 않음", view)

    def test_result_view_preserves_cleanup_and_scope_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, output, arguments = self.fixture(root); code, _, _ = self.run_main(arguments, lambda command, **_: self.completed(command)); self.assertEqual(0, code); report = json.loads(output.read_text()); validate_report(report, output, root); view = render_report(report); self.assertIn("상태: PASSED", view); self.assertIn("내부 Docker 네트워크: 정리 완료", view); self.assertIn("production 데이터·권한", view); self.assertIn("실제 실행 이미지", view)


if __name__ == "__main__": unittest.main(verbosity=2)
