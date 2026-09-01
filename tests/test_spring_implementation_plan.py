#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import copy
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import record_spring_implementation_plan_approval  # noqa: E402
from render_spring_implementation_plan import render  # noqa: E402
from spring_implementation_plan import build, ref, validate  # noqa: E402
from tests.test_feature_specs import feature_spec  # noqa: E402
from validate_feature_specs import approval_content_hash  # noqa: E402


def profile() -> dict:
    return {
        "decisions": {
            "language": {"option": "language.java"},
            "build": {"option": "build.gradle-kotlin"},
            "application": {"option": "application.rest-api"},
            "persistence": {"option": "persistence.jpa"},
            "database": {"option": "database.postgresql"},
        }
    }


def route() -> dict:
    return {"routes": [{"target": {"projectId": "leave-service"}}]}


def openapi(requirements: bool = True) -> dict:
    operation = {
        "operationId": "createLeaveRequest",
        "responses": {"201": {}, "400": {}, "409": {}},
    }
    if requirements:
        operation["x-harness-requirement-refs"] = ["AC-F001-01", "BR-F001-01"]
    return {"paths": {"/leave-requests": {"post": operation}}}


class SpringImplementationPlanTests(unittest.TestCase):
    def fixture(self, root: Path, selected_profile: dict | None = None, api: dict | None = None) -> dict:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        documents = {
            "featureSpec": feature_spec(),
            "technologyProfile": selected_profile or profile(),
            "designRoute": route(),
            "httpApiContract": {"kind": "HTTP_API"},
            "openApi": api or openapi(),
            "physicalContract": {"kind": "PERSISTENCE"},
            "physicalModel": {"database": "POSTGRESQL"},
            "migrationVerification": {"result": {"state": "PASSED"}},
        }
        evidence = root / "docs/evidence"
        evidence.mkdir(parents=True)
        paths = {}
        for name, document in documents.items():
            path = evidence / f"{name}.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            paths[name] = path
        refs = {name: ref(path, root) for name, path in paths.items()}
        return build(
            documents["featureSpec"], documents["technologyProfile"], documents["designRoute"],
            documents["openApi"], documents["physicalModel"], documents["migrationVerification"],
            root, "com.example.leave", refs,
        )

    def test_ready_plan_separates_boundaries_and_covers_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(root)
            self.assertEqual([], validate(plan, root))
            self.assertEqual("REVIEW_READY", plan["status"])
            self.assertEqual(10, plan["summary"]["create"])
            self.assertEqual(3, plan["summary"]["automatedTests"])
            self.assertEqual(2, len(plan["coverage"]))
            entity = next(item for item in plan["components"] if item["kind"] == "JPA_ENTITY")
            response = next(item for item in plan["components"] if item["kind"] == "RESPONSE_DTO")
            self.assertNotEqual(entity["target"]["plannedPath"], response["target"]["plannedPath"])
            service = next(item for item in plan["components"] if item["kind"] == "APPLICATION_SERVICE")
            self.assertTrue(service["transaction"]["required"])

    def test_occupied_path_blocks_without_overwriting_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = root / "src/main/java/com/example/leave/feature/createleaverequest/api/CreateLeaveRequestController.java"
            expected.parent.mkdir(parents=True)
            expected.write_text("user-owned", encoding="utf-8")
            plan = self.fixture(root)
            self.assertEqual("BLOCKED", plan["status"])
            self.assertTrue(any(item["code"] == "DIRTY_OVERLAP" for item in plan["conflicts"]))
            self.assertEqual("user-owned", expected.read_text(encoding="utf-8"))

    def test_unsupported_stack_and_traceability_gap_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unsupported = profile()
            unsupported["decisions"]["language"]["option"] = "language.kotlin"
            plan = self.fixture(root, unsupported, openapi(False))
            codes = {item["code"] for item in plan["conflicts"]}
            self.assertEqual("BLOCKED", plan["status"])
            self.assertIn("UNSUPPORTED_STACK", codes)
            self.assertIn("TRACEABILITY_GAP", codes)

    def test_validator_detects_cycles_input_drift_and_summary_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(root)
            plan["components"][0]["dependsOn"] = [plan["components"][1]["componentId"]]
            plan["components"][1]["dependsOn"] = [plan["components"][0]["componentId"]]
            self.assertIn("component dependency cycle exists", validate(plan, root))
            evidence = root / plan["inputs"]["featureSpec"]["path"]
            evidence.write_text("changed", encoding="utf-8")
            self.assertIn("input changed: featureSpec", validate(plan, root))
            plan["summary"]["create"] = 99
            with self.assertRaisesRegex(ValueError, "summary"):
                validate(plan, root)

    def test_markdown_leads_with_user_flow_and_shows_approval_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(root)
            markdown = render(plan, [])
            self.assertLess(markdown.index("## 사용자 기능 흐름"), markdown.index("## 상세 component"))
            self.assertIn("다음 code dry-run 준비만 허용", markdown)
            self.assertIn("테스트 실행, commit, push 허용 안 함", markdown)

    def test_exact_plan_approval_changes_only_plan_and_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(root)
            plan_path = root / "docs/features/F001/implementation-plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            markdown_path = plan_path.with_suffix(".md")
            markdown_path.write_text(render(plan, []), encoding="utf-8")
            before_sources = list(root.glob("src/**/*.java"))
            argv = [
                "record", "--plan", str(plan_path), "--target", str(root),
                "--expected-plan-hash", approval_content_hash(plan),
                "--approved-by", "test-user", "--approved-at", "2026-09-01T00:00:00Z",
            ]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, record_spring_implementation_plan_approval.main())
            approved = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual("APPROVED", approved["status"])
            self.assertEqual([], validate(approved, root))
            self.assertEqual(before_sources, list(root.glob("src/**/*.java")))


if __name__ == "__main__":
    unittest.main()
