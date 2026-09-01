#!/usr/bin/env python3
"""Focused tests for feature design routing."""

from __future__ import annotations

import copy
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from render_design_route import render  # noqa: E402
import record_design_route_approval  # noqa: E402
from validate_design_route import validate, verify_inputs  # noqa: E402
from migrate_design_route_v2 import migrate  # noqa: E402
from validate_feature_specs import approval_content_hash  # noqa: E402
from tests.test_feature_specs import feature_spec, project_brief  # noqa: E402


def profile() -> dict:
    return {"project": {"artifactId": "leave-service"}, "projects": [], "dataStores": []}


def route() -> dict:
    dispositions = {
        "HTTP_API": ("httpApi", "CREATE"),
        "PERSISTENCE": ("persistentState", "CREATE"),
        "MESSAGING": ("messaging", "NOT_NEEDED"),
        "SCHEDULED_JOB": ("scheduledJob", "NOT_NEEDED"),
        "SERVER_UI": ("serverRenderedUi", "NOT_NEEDED"),
        "CLIENT_INTEGRATION": ("separateClient", "CREATE"),
        "EXTERNAL_INTEGRATION": ("externalIntegration", "NOT_NEEDED"),
        "SECURITY": ("authorization", "CREATE"),
        "VERIFICATION": ("acceptanceCriteria", "CREATE"),
    }
    document = {
        "routeVersion": 2,
        "featureId": "F001",
        "inputs": {
            "feature": {"path": "docs/features/F001/spec.json", "sha256": "a" * 64},
            "projectBrief": {"path": "docs/project-brief.json", "sha256": "c" * 64},
            "technologyProfile": {"path": "docs/project-profile.json", "sha256": "b" * 64},
            "codeEvidence": [],
        },
        "routes": [],
        "approval": {
            "status": "APPROVED", "approvedBy": "test-user",
            "approvedAt": "2026-09-01T00:00:00Z", "approvedContentSha256": None,
        },
    }
    for kind, (requirement, disposition) in dispositions.items():
        document["routes"].append({
            "contractId": kind.lower().replace("_", "-"),
            "kind": kind, "requirementRef": requirement, "disposition": disposition,
            "target": {"projectId": "leave-service", "modulePath": ".", "dataStoreIds": []},
            "evidencePaths": [],
            "artifactPath": f"docs/features/F001/contracts/{kind.lower().replace('_', '-')}/metadata.json" if disposition == "CREATE" else None,
            "reason": "Matches the approved feature and current project.",
            "source": "USER_STATED", "confirmedByUser": True,
        })
    document["approval"]["approvedContentSha256"] = approval_content_hash(document)
    return document


def refresh(document: dict) -> None:
    document["approval"]["approvedContentSha256"] = approval_content_hash(document)


class DesignRouteTests(unittest.TestCase):
    def test_complete_route_is_ready(self) -> None:
        self.assertEqual((True, []), validate(route(), feature_spec(), project_brief(), profile()))

    def test_required_design_cannot_be_marked_not_needed(self) -> None:
        document = route()
        document["routes"][0]["disposition"] = "NOT_NEEDED"
        document["routes"][0]["artifactPath"] = None
        refresh(document)
        self.assertIn("required design needs an active contract instance: HTTP_API", validate(
            document, feature_spec(), project_brief(), profile()
        )[1])

    def test_reuse_requires_actual_code_evidence(self) -> None:
        document = route()
        document["routes"][0]["disposition"] = "REUSE"
        document["routes"][0]["artifactPath"] = None
        refresh(document)
        self.assertIn("REUSE requires code evidence: HTTP_API", validate(
            document, feature_spec(), project_brief(), profile()
        )[1])

    def test_multiple_stores_require_explicit_persistence_targets(self) -> None:
        technology = profile()
        technology["dataStores"] = [{"id": "primary"}, {"id": "audit"}]
        self.assertIn("active persistence route must select data stores", validate(
            route(), feature_spec(), project_brief(), technology
        )[1])

    def test_verification_route_cannot_be_skipped(self) -> None:
        document = route()
        verification = next(item for item in document["routes"] if item["kind"] == "VERIFICATION")
        verification.update({"disposition": "NOT_NEEDED", "artifactPath": None})
        refresh(document)
        self.assertIn("verification route must be CREATE, EXTEND, or REUSE", validate(
            document, feature_spec(), project_brief(), profile()
        )[1])

    def test_user_markdown_separates_actions_and_questions(self) -> None:
        document = route()
        document["routes"][2].update({
            "disposition": "UNKNOWN", "reason": "Event publication is undecided.",
            "source": "UNKNOWN", "confirmedByUser": False,
        })
        refresh(document)
        markdown = render(document, feature_spec(), project_brief(), profile())
        self.assertIn("## 이번에 만들거나 활용할 설계", markdown)
        self.assertIn("웹 API — 새로 설계", markdown)
        self.assertIn("메시징 — Event publication is undecided.", markdown)

    def test_basic_markdown_shows_real_gate_blocker_and_drift_status(self) -> None:
        document = route()
        blockers = ["code evidence is stale: src/Existing.java"]
        markdown = render(
            document, feature_spec(), project_brief(), profile(), runtime_blockers=blockers
        )
        immediate = markdown.split("## 지금 확인해야 할 사항", 1)[1].split("## 나중에 설계할 사항", 1)[0]
        self.assertIn("재사용 근거 파일이 변경되어 다시 확인해야 합니다.", immediate)
        self.assertIn("입력 변경으로 재검토 필요", markdown)

    def test_complete_unapproved_route_is_shown_as_waiting_for_approval(self) -> None:
        document = route()
        document["approval"] = {
            "status": "REVIEW_REQUIRED", "approvedBy": None,
            "approvedAt": None, "approvedContentSha256": None,
        }
        markdown = render(document, feature_spec(), project_brief(), profile())
        self.assertIn("## 현재 상태\n\n- 승인 대기", markdown)

    def test_input_and_code_evidence_drift_is_detected(self) -> None:
        document = route()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            feature_path = target / "spec.json"
            profile_path = target / "profile.json"
            project_path = target / "project.json"
            evidence_path = target / "src" / "Existing.java"
            evidence_path.parent.mkdir()
            feature_path.write_text("feature", encoding="utf-8")
            profile_path.write_text("profile", encoding="utf-8")
            project_path.write_text("project", encoding="utf-8")
            evidence_path.write_text("class Existing {}", encoding="utf-8")
            document["inputs"]["feature"]["sha256"] = hashlib.sha256(b"feature").hexdigest()
            document["inputs"]["technologyProfile"]["sha256"] = hashlib.sha256(b"profile").hexdigest()
            document["inputs"]["projectBrief"] = {
                "path": "project.json", "sha256": hashlib.sha256(b"project").hexdigest(),
            }
            document["inputs"]["feature"]["path"] = "spec.json"
            document["inputs"]["technologyProfile"]["path"] = "profile.json"
            document["inputs"]["codeEvidence"] = [{
                "path": "src/Existing.java", "kind": "SOURCE",
                "sha256": hashlib.sha256(b"old").hexdigest(),
            }]
            self.assertIn("code evidence is stale: src/Existing.java", verify_inputs(
                document, feature_path, project_path, profile_path, target
            ))

    def test_route_paths_cannot_escape_target(self) -> None:
        document = route()
        document["routes"][0]["artifactPath"] = "../outside.md"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            feature_path = target / "spec.json"
            profile_path = target / "profile.json"
            project_path = target / "project.json"
            feature_path.write_text("feature", encoding="utf-8")
            profile_path.write_text("profile", encoding="utf-8")
            project_path.write_text("project", encoding="utf-8")
            document["inputs"]["feature"] = {
                "path": "spec.json", "sha256": hashlib.sha256(b"feature").hexdigest(),
            }
            document["inputs"]["technologyProfile"] = {
                "path": "profile.json", "sha256": hashlib.sha256(b"profile").hexdigest(),
            }
            document["inputs"]["projectBrief"] = {
                "path": "project.json", "sha256": hashlib.sha256(b"project").hexdigest(),
            }
            self.assertIn("route artifactPath escapes target: http-api", verify_inputs(
                document, feature_path, project_path, profile_path, target
            ))

    def test_v2_supports_multiple_contracts_of_the_same_kind(self) -> None:
        document = route()
        second = copy.deepcopy(document["routes"][0])
        second["contractId"] = "internal-http-api"
        second["target"]["projectId"] = "internal-service"
        second["artifactPath"] = "docs/features/F001/contracts/internal-http-api/metadata.json"
        document["routes"].append(second)
        technology = profile()
        technology["projects"] = [{"id": "leave-service"}, {"id": "internal-service"}]
        refresh(document)
        self.assertEqual((True, []), validate(document, feature_spec(), project_brief(), technology))
        markdown = render(document, feature_spec(), project_brief(), technology)
        self.assertIn("웹 API (http-api)", markdown)
        self.assertIn("웹 API (internal-http-api)", markdown)

    def test_contract_ids_are_globally_unique(self) -> None:
        document = route()
        document["routes"][1]["contractId"] = document["routes"][0]["contractId"]
        with self.assertRaisesRegex(ValueError, "duplicate contractId"):
            validate(document, feature_spec(), project_brief(), profile())

    def test_v1_migration_preserves_source_and_requires_review(self) -> None:
        source = route()
        source["routeVersion"] = 1
        for item in source["routes"]:
            item.pop("contractId")
        original = copy.deepcopy(source)
        migrated = migrate(source)
        self.assertEqual(original, source)
        self.assertEqual(2, migrated["routeVersion"])
        self.assertTrue(all(item["contractId"] for item in migrated["routes"]))
        self.assertEqual("REVIEW_REQUIRED", migrated["approval"]["status"])

    def test_route_approval_updates_json_and_markdown_together(self) -> None:
        document = route()
        document["approval"] = {
            "status": "REVIEW_REQUIRED", "approvedBy": None,
            "approvedAt": None, "approvedContentSha256": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            route_path = root / "design-route.json"
            feature_path = root / "spec.json"
            project_path = root / "project-brief.json"
            profile_path = root / "project-profile.json"
            feature = feature_spec()
            project = project_brief()
            technology = profile()
            feature_path.write_text(json.dumps(feature), encoding="utf-8")
            project_path.write_text(json.dumps(project), encoding="utf-8")
            profile_path.write_text(json.dumps(technology), encoding="utf-8")
            document["inputs"]["feature"]["sha256"] = hashlib.sha256(feature_path.read_bytes()).hexdigest()
            document["inputs"]["technologyProfile"]["sha256"] = hashlib.sha256(profile_path.read_bytes()).hexdigest()
            document["inputs"]["projectBrief"]["sha256"] = hashlib.sha256(project_path.read_bytes()).hexdigest()
            route_path.write_text(json.dumps(document), encoding="utf-8")
            route_path.with_suffix(".md").write_text(
                render(document, feature, project, technology), encoding="utf-8"
            )
            arguments = [
                "record_design_route_approval.py", "--route", str(route_path),
                "--feature", str(feature_path), "--project-brief", str(project_path),
                "--profile", str(profile_path), "--target", str(root),
                "--expected-route-hash", approval_content_hash(document),
                "--approved-by", "test-user", "--approved-at", "2026-09-01T00:00:00Z",
            ]
            with mock.patch.object(sys, "argv", arguments), mock.patch.object(
                record_design_route_approval, "assess", return_value=(False, True, [])
            ), mock.patch.object(
                record_design_route_approval, "verify_inputs", return_value=[]
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, record_design_route_approval.main())
            approved = json.loads(route_path.read_text(encoding="utf-8"))
            self.assertEqual("APPROVED", approved["approval"]["status"])
            self.assertEqual(
                render(approved, feature, project, technology),
                route_path.with_suffix(".md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
