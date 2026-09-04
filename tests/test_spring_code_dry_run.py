#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import render_spring_code_dry_run  # noqa: E402
import run_spring_code_verification  # noqa: E402
from render_spring_code_dry_run_markdown import render  # noqa: E402
from render_spring_code_verification_report import render as render_verification  # noqa: E402
from spring_code_dry_run import validate_candidate, validate_report  # noqa: E402
import tests.test_spring_implementation_plan as implementation_tests  # noqa: E402
from validate_feature_specs import approval_content_hash  # noqa: E402


def approve(plan: dict) -> dict:
    approved = copy.deepcopy(plan)
    approved["status"] = "APPROVED"
    approved["approval"] = {"status": "APPROVED", "approvedBy": "test-user", "approvedAt": "2026-09-02T00:00:00Z", "approvedContentSha256": None}
    approved["approval"]["approvedContentSha256"] = approval_content_hash(approved)
    return approved


class SpringCodeDryRunTests(unittest.TestCase):
    def fixture(self, parent: Path) -> tuple[Path, Path, Path, dict]:
        target = parent / "target"
        target.mkdir()
        plan = approve(implementation_tests.SpringImplementationPlanTests().fixture(target))
        plan_path = target / "docs/features/F001/implementation-plan.json"
        plan_path.parent.mkdir(parents=True)
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        rendered = parent / "rendered"
        rendered.mkdir()
        for component in plan["components"]:
            kind = component["kind"]
            package = component["target"]["packageName"]
            name = component["target"]["typeName"]
            declaration = "interface" if kind == "REPOSITORY" else "record" if kind in {"REQUEST_DTO", "RESPONSE_DTO"} else "class"
            markers = {
                "JPA_ENTITY": "@Entity\n",
                "REPOSITORY": "",
                "APPLICATION_SERVICE": "@Service\n@Transactional\n",
                "CONTROLLER": "@RestController\n@PostMapping\n",
                "EXCEPTION_HANDLER": "@RestControllerAdvice\n@ExceptionHandler\n",
                "UNIT_TEST": "@Test\n",
                "REPOSITORY_INTEGRATION_TEST": "@DataJpaTest\n@Test\n",
                "API_INTEGRATION_TEST": "@SpringBootTest\n@Test\n// AC-F001-01 BR-F001-01\n",
            }.get(kind, "")
            suffix = " extends JpaRepository<CreateLeaveRequestEntity, Object>" if kind == "REPOSITORY" else ""
            body = {
                "REQUEST_DTO": "(java.time.LocalDate leaveStartDate, java.time.LocalDate leaveEndDate)",
                "RESPONSE_DTO": "(java.util.UUID leaveRequestId, java.time.LocalDate leaveStartDate, java.time.LocalDate leaveEndDate)",
                "JPA_ENTITY": '{ @Id java.util.UUID id; @Column(name = "leave_request_id") java.util.UUID leaveRequestId; @Column(name = "start_date") java.time.LocalDate leaveStartDate; @Column(name = "end_date") java.time.LocalDate leaveEndDate; }',
                "REPOSITORY": "",
                "APPLICATION_SERVICE": "{ CreateLeaveRequestRepository repository; CreateLeaveRequestResponse create(CreateLeaveRequestRequest request) { repository.save(null); return null; } }",
                "CONTROLLER": '{ ResponseEntity<CreateLeaveRequestResponse> create(CreateLeaveRequestRequest request) { String path = "/leave-requests"; return null; } }',
                "EXCEPTION_HANDLER": "{ ResponseEntity<Object> handle() { return null; } }",
                "UNIT_TEST": "{ void verifies() { assertTrue(true); } }",
                "REPOSITORY_INTEGRATION_TEST": "{ void verifies() { assertThat(true); } }",
                "API_INTEGRATION_TEST": "{ // AC-F001-01 BR-F001-01\n void verifies() { andExpect(null); } }",
            }.get(kind, "{}")
            if kind == "JPA_ENTITY":
                markers += '@Table(name = "leave_requests")\n'
            content = f"package {package};\n\n{markers}public {declaration} {name}{suffix} {body}\n" if kind not in {"REQUEST_DTO", "RESPONSE_DTO"} else f"package {package};\n\npublic record {name}{body} {{}}\n"
            path = rendered / component["target"]["plannedPath"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return target, rendered, plan_path, plan

    def run_dry_run(self, target: Path, rendered: Path, plan: Path, output: Path) -> tuple[int, str]:
        argv = ["render", "--plan", str(plan), "--rendered-source", str(rendered), "--target", str(target), "--output", str(output)]
        stream = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            return render_spring_code_dry_run.main(), stream.getvalue()

    def test_clear_candidate_produces_reviewable_report_without_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, rendered, plan, _ = self.fixture(Path(directory))
            output = target / "docs/features/F001/code-dry-run.json"
            before = list(target.glob("src/**/*.java"))
            code, _ = self.run_dry_run(target, rendered, plan, output)
            self.assertEqual(0, code)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(report["readyForApproval"])
            self.assertFalse(report["targetSourceChanged"])
            self.assertEqual(10, len(report["plannedChanges"]["creates"]))
            self.assertEqual("NOT_RUN", report["verification"]["automatedTests"])
            self.assertEqual(before, list(target.glob("src/**/*.java")))

    def test_missing_and_extra_files_are_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, rendered, plan_path, plan = self.fixture(Path(directory))
            missing = rendered / plan["components"][0]["target"]["plannedPath"]
            missing.unlink()
            extra = rendered / "src/main/java/com/example/Extra.java"
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_text("package com.example; public class Extra {}", encoding="utf-8")
            _, conflicts = validate_candidate(plan, rendered)
            reasons = {item["reason"] for item in conflicts}
            self.assertIn("planned-component-is-missing", reasons)
            self.assertIn("file-is-not-in-approved-plan", reasons)

    def test_identity_role_and_entity_boundary_failures_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, rendered, _, plan = self.fixture(Path(directory))
            controller = next(item for item in plan["components"] if item["kind"] == "CONTROLLER")
            path = rendered / controller["target"]["plannedPath"]
            path.write_text("package wrong.name;\npublic class Wrong { CreateLeaveRequestEntity value; }", encoding="utf-8")
            checks, conflicts = validate_candidate(plan, rendered)
            reasons = {item["reason"] for item in conflicts}
            self.assertIn("package-or-public-type-does-not-match-plan", reasons)
            self.assertTrue(any(item.startswith("missing-required-marker") for item in reasons))
            self.assertIn("jpa-entity-crosses-api-boundary", reasons)
            self.assertTrue(any(item["state"] == "FAILED" for item in checks))

    def test_existing_unowned_source_is_a_conflict_and_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, rendered, plan, document = self.fixture(Path(directory))
            relative = document["components"][0]["target"]["plannedPath"]
            existing = target / relative
            existing.parent.mkdir(parents=True)
            existing.write_text("user-owned", encoding="utf-8")
            output = target / "docs/features/F001/code-dry-run.json"
            code, _ = self.run_dry_run(target, rendered, plan, output)
            self.assertEqual(0, code)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(report["readyForApproval"])
            self.assertEqual("user-owned", existing.read_text(encoding="utf-8"))

    def test_stale_approved_plan_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, rendered, plan, document = self.fixture(Path(directory))
            evidence = target / document["inputs"]["openApi"]["path"]
            evidence.write_text("changed", encoding="utf-8")
            output = target / "docs/features/F001/code-dry-run.json"
            code, message = self.run_dry_run(target, rendered, plan, output)
            self.assertEqual(1, code)
            self.assertIn("not approved and current", message)
            self.assertFalse(output.exists())

    def test_markdown_prioritizes_flow_and_discloses_non_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, rendered, plan, _ = self.fixture(Path(directory))
            output = target / "docs/features/F001/code-dry-run.json"
            self.assertEqual(0, self.run_dry_run(target, rendered, plan, output)[0])
            markdown = render(json.loads(output.read_text(encoding="utf-8")))
            self.assertLess(markdown.index("## 사용자 기능 흐름"), markdown.index("## 생성될 코드"))
            self.assertIn("컴파일·테스트: 아직 실행하지 않음", markdown)
            self.assertIn("다음 격리 컴파일·테스트 실행만 허용", markdown)
            self.assertIn("<details>", markdown)

    def test_report_tampering_and_hardcoded_secret_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, rendered, plan, document = self.fixture(Path(directory))
            service = next(item for item in document["components"] if item["kind"] == "APPLICATION_SERVICE")
            service_path = rendered / service["target"]["plannedPath"]
            service_path.write_text(service_path.read_text(encoding="utf-8").replace("public class", 'String password = "real-value";\npublic class'), encoding="utf-8")
            _, conflicts = validate_candidate(document, rendered)
            self.assertIn("hardcoded-secret-like-literal", {item["reason"] for item in conflicts})
            service_path.write_text(service_path.read_text(encoding="utf-8").replace('String password = "real-value";\n', ""), encoding="utf-8")
            output = target / "docs/features/F001/code-dry-run.json"
            self.assertEqual(0, self.run_dry_run(target, rendered, plan, output)[0])
            report = json.loads(output.read_text(encoding="utf-8"))
            validate_report(report, target)
            report["generatedFiles"][0]["content"] += "// changed"
            with self.assertRaisesRegex(ValueError, "content hash"):
                validate_report(report, target)

    def verification_fixture(self, parent: Path):
        target, rendered, plan, _ = self.fixture(parent)
        wrapper = target / "gradlew"
        wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        wrapper.chmod(0o755)
        dry_run = target / "docs/features/F001/code-dry-run.json"
        self.assertEqual(0, self.run_dry_run(target, rendered, plan, dry_run)[0])
        approval = target / "docs/features/F001/code-verification-approval.json"
        approval.write_text(json.dumps({"springCodeVerificationApprovalVersion": 1, "approved": True, "dryRunReportSha256": run_spring_code_verification.sha(dry_run), "target": str(target), "approvedBy": "test-user", "approvedAt": "2026-09-04T00:00:00Z"}), encoding="utf-8")
        output = target / "docs/features/F001/code-verification-report.json"
        return target, dry_run, approval, output

    def run_verification(self, target: Path, report: Path, approval: Path, output: Path, returncode: int):
        argv = ["verify", "--report", str(report), "--approval", str(approval), "--target", str(target), "--output", str(output)]
        completed = __import__("subprocess").CompletedProcess([], returncode, "verification output", "")
        stream = io.StringIO()
        with mock.patch.object(sys, "argv", argv), mock.patch.object(run_spring_code_verification, "isolation_preflight"), mock.patch.object(run_spring_code_verification.subprocess, "run", return_value=completed), mock.patch.object(run_spring_code_verification.shutil, "which", return_value="/usr/bin/bwrap"), contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            return run_spring_code_verification.main(), stream.getvalue()

    def test_exact_approval_runs_isolated_verification_without_target_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, report, approval, output = self.verification_fixture(Path(directory))
            before = list(target.glob("src/**/*.java"))
            code, _ = self.run_verification(target, report, approval, output, 0)
            self.assertEqual(0, code)
            result = json.loads(output.read_text(encoding="utf-8"))
            run_spring_code_verification.validate_verification_report(result, output, target)
            self.assertEqual("PASSED", result["result"]["state"])
            self.assertEqual("DISABLED", result["isolation"]["network"])
            self.assertTrue(result["readyForApplyApproval"])
            self.assertEqual(before, list(target.glob("src/**/*.java")))
            view = render_verification(result)
            self.assertIn("네트워크: DISABLED", view)
            self.assertIn("실제 target 적용이나 commit·push를 승인하지 않음", view)

    def test_failed_tests_do_not_prepare_apply_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, report, approval, output = self.verification_fixture(Path(directory))
            self.assertEqual(0, self.run_verification(target, report, approval, output, 1)[0])
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("FAILED", result["result"]["state"])
            self.assertFalse(result["readyForApplyApproval"])

    def test_changed_report_invalidates_verification_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, report, approval, output = self.verification_fixture(Path(directory))
            report.write_text(report.read_text(encoding="utf-8") + " ", encoding="utf-8")
            code, message = self.run_verification(target, report, approval, output, 0)
            self.assertEqual(1, code)
            self.assertIn("does not match", message)
            self.assertFalse(output.exists())

    def test_offline_dependency_failure_is_unknown_not_code_failure(self) -> None:
        self.assertEqual("UNKNOWN", run_spring_code_verification.result_state(1, "Could not resolve dependency while offline"))
        self.assertEqual("FAILED", run_spring_code_verification.result_state(1, "There were failing tests"))


if __name__ == "__main__":
    unittest.main()
