#!/usr/bin/env python3
"""Focused tests for completion-to-design-route preparation."""
from __future__ import annotations

import contextlib
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
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

import prepare_design_route_from_completion as prepare  # noqa: E402
from tests.test_feature_specs import feature_spec, project_brief  # noqa: E402
from spring_milestone_completion import sha  # noqa: E402
from validate_design_route import validate, verify_inputs  # noqa: E402


def ready_profile() -> dict:
    return {
        "profileVersion": 1,
        "project": {"groupId": "com.example", "artifactId": "sample", "name": "sample", "description": "test profile", "packageName": "com.example.sample"},
        "decisions": {
            "language": {"status": "NOW", "option": "language.java"},
            "java-version": {"status": "NOW", "option": "java-version.21"},
            "spring-boot-version": {"status": "NOW", "option": "spring-boot-version.current-stable", "resolvedValue": "4.0.0"},
            "build": {"status": "NOW", "option": "build.gradle-kotlin"},
            "application": {"status": "NOW", "option": "application.rest-api"},
            "view": {"status": "NOW", "option": "view.none"},
            "security": {"status": "NOW", "option": "security.none"},
            "authorization": {"status": "NOW", "option": "authorization.none"},
            "database": {"status": "NOW", "option": "database.h2"},
            "persistence": {"status": "NOW", "option": "persistence.jpa"},
            "database-topology": {"status": "NOW", "option": "database-topology.single"},
            "architecture": {"status": "NOW", "option": "architecture.single-module"},
            "packaging": {"status": "NOW", "option": "packaging.jar"},
            "verification": {"status": "NOW", "option": "verification.spring-integration"},
        },
        "dataStores": [], "projects": [],
        "confirmedBy": {"user": True, "confirmedAt": "2026-09-01T00:00:00+09:00"},
    }


class DesignRoutePreparationTests(unittest.TestCase):
    def fixture(self, parent: Path) -> tuple[Path, Path, Path, Path]:
        root = parent / "target"
        feature_path = root / "docs/features/F001/spec.json"
        project_path = root / "docs/project-brief.json"
        profile_path = root / "docs/project-profile.json"
        plan_path = root / "docs/promotion.json"
        completion_path = root / ".starter-harness/continuation-completions/intake.json"
        feature_path.parent.mkdir(parents=True)
        completion_path.parent.mkdir(parents=True)
        feature_path.write_text(json.dumps(feature_spec()))
        project_path.write_text(json.dumps(project_brief()))
        profile_path.write_text(json.dumps(ready_profile()))
        plan = {"featureSpecPromotionVersion": 2, "projectBrief": {"path": "docs/project-brief.json", "sha256": "before"}, "officialFeaturePath": "docs/features/F001/spec.json", "proposedFeature": feature_spec()}
        plan_path.write_text(json.dumps(plan))
        completion = {"continuationCompletionVersion": 1, "intake": {"path": "docs/intake.json", "sha256": "a" * 64}, "promotionPlan": {"path": "docs/promotion.json", "sha256": sha(plan_path)}, "reservation": None, "featureId": "F001", "approvedBy": "user", "approvedAt": "2026-09-09T00:00:00Z", "state": "CONSUMED"}
        completion_path.write_text(json.dumps(completion))
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        return root, completion_path, project_path, profile_path

    def call(self, arguments: list[str]) -> tuple[int, str]:
        stream = io.StringIO()
        with mock.patch.object(sys, "argv", arguments), contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            return prepare.main(), stream.getvalue()

    def test_prepares_recommended_route_and_user_choices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, completion, project, profile = self.fixture(Path(directory))
            output = root / "docs/features/F001/design-route.json"
            view = output.with_suffix(".md")
            code, text = self.call(["prepare", "--completion", str(completion), "--project-brief", str(project), "--profile", str(profile), "--target", str(root), "--output", str(output), "--view", str(view)])
            self.assertEqual(0, code, text)
            route = json.loads(output.read_text())
            http = next(item for item in route["routes"] if item["kind"] == "HTTP_API")
            messaging = next(item for item in route["routes"] if item["kind"] == "MESSAGING")
            security = next(item for item in route["routes"] if item["kind"] == "SECURITY")
            self.assertEqual(("CREATE", "RECOMMENDED", False), (http["disposition"], http["source"], http["confirmedByUser"]))
            self.assertEqual("NOT_NEEDED", messaging["disposition"])
            self.assertEqual("UNKNOWN", security["disposition"])
            self.assertIn("인증 또는 인가", security["reason"])
            self.assertEqual(sha(completion), route["preparation"]["completion"]["sha256"])
            self.assertIn("기타 내용을 자연어로 입력", view.read_text())
            completion.write_text(completion.read_text() + " ")
            blockers = verify_inputs(route, root / route["inputs"]["feature"]["path"], project, profile, root)
            self.assertIn("continuation completion is stale", blockers)

    def test_multiple_projects_remain_an_explicit_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, completion, project, profile = self.fixture(Path(directory))
            value = json.loads(profile.read_text())
            value["projects"] = [{"id": "api", "profile": "profiles/api.json"}, {"id": "worker", "profile": "profiles/worker.json"}]
            profile.write_text(json.dumps(value))
            output = root / "docs/features/F001/design-route.json"
            with mock.patch.object(prepare, "git_overlap", return_value=[]):
                route, _, _, _, _ = prepare.build(root, completion, project, profile, output, output.with_suffix(".md"))
            required = [item for item in route["routes"] if item["kind"] in {"HTTP_API", "PERSISTENCE", "SECURITY", "VERIFICATION"}]
            self.assertTrue(all(item["disposition"] == "UNKNOWN" for item in required))

    def test_create_contract_collision_is_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, completion, project, profile = self.fixture(Path(directory))
            output = root / "docs/features/F001/design-route.json"
            with mock.patch.object(prepare, "git_overlap", return_value=[]):
                route, _, _, _, _ = prepare.build(root, completion, project, profile, output, output.with_suffix(".md"))
            http = next(item for item in route["routes"] if item["kind"] == "HTTP_API")
            occupied = root / http["artifactPath"]
            occupied.parent.mkdir(parents=True)
            occupied.write_text("existing")
            blockers = verify_inputs(route, root / route["inputs"]["feature"]["path"], project, profile, root)
            self.assertIn("CREATE artifact path is occupied: http-api", blockers)

    def test_unready_profile_produces_questions_instead_of_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, completion, project, profile = self.fixture(Path(directory))
            value = json.loads(profile.read_text())
            value["confirmedBy"] = {"user": False, "confirmedAt": None}
            profile.write_text(json.dumps(value))
            output = root / "docs/features/F001/design-route.json"
            code, text = self.call(["prepare", "--completion", str(completion), "--project-brief", str(project), "--profile", str(profile), "--target", str(root), "--output", str(output), "--view", str(output.with_suffix('.md'))])
            self.assertEqual(0, code, text)
            route = json.loads(output.read_text())
            self.assertEqual("UNKNOWN", next(item for item in route["routes"] if item["kind"] == "HTTP_API")["disposition"])
            self.assertIn("기술 구성을 먼저 확정", output.with_suffix(".md").read_text())

    def test_symbolic_link_output_parent_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, completion, project, profile = self.fixture(Path(directory))
            link = root / "linked-docs"
            link.symlink_to(root / "docs", target_is_directory=True)
            output = link / "design-route.json"
            code, text = self.call(["prepare", "--completion", str(completion), "--project-brief", str(project), "--profile", str(profile), "--target", str(root), "--output", str(output), "--view", str(output.with_suffix('.md'))])
            self.assertEqual(1, code)
            self.assertIn("symbolic link", text)

    def test_git_deleted_route_is_not_silently_recreated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, completion, project, profile = self.fixture(Path(directory))
            output = root / "docs/features/F001/design-route.json"
            output.write_text("tracked prior route")
            subprocess.run(["git", "add", str(output.relative_to(root))], cwd=root, check=True)
            output.unlink()
            code, text = self.call(["prepare", "--completion", str(completion), "--project-brief", str(project), "--profile", str(profile), "--target", str(root), "--output", str(output), "--view", str(output.with_suffix('.md'))])
            self.assertEqual(1, code)
            self.assertIn("overlap current Git changes", text)

    def test_manual_route_edit_cannot_bypass_feature_technology_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, completion, project, profile = self.fixture(Path(directory))
            output = root / "docs/features/F001/design-route.json"
            with mock.patch.object(prepare, "git_overlap", return_value=[]):
                route, feature, project_value, profile_value, _ = prepare.build(root, completion, project, profile, output, output.with_suffix(".md"))
            security = next(item for item in route["routes"] if item["kind"] == "SECURITY")
            security.update({"disposition": "CREATE", "artifactPath": "docs/features/F001/contracts/security/metadata.json", "reason": "manual override", "source": "USER_STATED", "confirmedByUser": True})
            self.assertIn("technology profile conflicts with required design: SECURITY", validate(route, feature, project_value, profile_value)[1])

    def test_revision_uses_the_promoted_official_feature_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, completion, project, profile = self.fixture(Path(directory))
            canonical = root / "docs/features/F001/spec.json"
            revised = root / "docs/evidence/featureSpec.json"
            revised.parent.mkdir(parents=True)
            canonical.rename(revised)
            plan_path = root / "docs/promotion.json"
            plan = json.loads(plan_path.read_text())
            plan["officialFeaturePath"] = "docs/evidence/featureSpec.json"
            plan_path.write_text(json.dumps(plan))
            receipt = json.loads(completion.read_text())
            receipt["promotionPlan"]["sha256"] = sha(plan_path)
            completion.write_text(json.dumps(receipt))
            output = root / "docs/features/F001/design-route.json"
            with mock.patch.object(prepare, "git_overlap", return_value=[]):
                route, _, _, _, _ = prepare.build(root, completion, project, profile, output, output.with_suffix(".md"))
            self.assertEqual("docs/evidence/featureSpec.json", route["inputs"]["feature"]["path"])


if __name__ == "__main__":
    unittest.main()
