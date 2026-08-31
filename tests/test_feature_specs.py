#!/usr/bin/env python3
"""Focused regression tests for project briefs and feature specifications."""

from __future__ import annotations

import copy
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
sys.path.insert(0, str(SCRIPTS))

from render_spec_markdown import render_feature, render_project  # noqa: E402
import record_spec_approval  # noqa: E402
from next_feature_id import next_feature_id  # noqa: E402
from validate_feature_specs import approval_content_hash, validate_feature, validate_project  # noqa: E402


def project_brief() -> dict:
    document = {
        "schemaVersion": 1,
        "project": {
            "name": "Leave service",
            "goal": "Employees request leave and managers decide it.",
            "targetUsers": ["Employee", "Manager"],
            "successCriteria": ["A leave request reaches a decision."],
            "nonFunctionalRequirements": ["Do not expose private leave reasons."],
        },
        "scope": {"included": ["Leave request"], "excluded": ["Payroll"]},
        "featureCandidates": [
            {
                "id": "F001",
                "name": "Request leave",
                "userValue": "An employee can submit a leave request.",
                "recommendationReason": "It is the first independently testable user flow.",
                "dependsOn": [],
                "blockingUnknownIds": [],
                "recommendedOrder": 1,
                "status": "APPROVED",
            }
        ],
        "unknowns": [],
        "sources": [
            {"id": "S001", "type": "USER_STATED", "reference": "Conversation goal"}
        ],
        "approval": {
            "status": "APPROVED",
            "approvedBy": "test-user",
            "approvedAt": "2026-09-01T00:00:00Z",
            "approvedContentSha256": None,
        },
    }
    document["approval"]["approvedContentSha256"] = approval_content_hash(document)
    return document


def feature_spec() -> dict:
    document = {
        "schemaVersion": 1,
        "feature": {
            "id": "F001",
            "name": "Request leave",
            "goal": "Accept a valid leave request.",
            "userValue": "An employee can submit a leave request.",
            "status": "APPROVED",
        },
        "actors": ["Employee"],
        "scenario": {
            "preconditions": ["The employee is authenticated."],
            "trigger": "The employee submits leave dates.",
            "mainFlow": ["Validate the dates.", "Store the pending request."],
            "alternateFlows": ["Reject an invalid date range."],
            "postconditions": ["A pending request exists."],
        },
        "businessRules": [
            {
                "id": "BR-F001-01",
                "description": "The end date cannot precede the start date.",
                "source": "RECOMMENDED",
                "status": "APPROVED",
                "confirmedByUser": True,
            }
        ],
        "authorization": ["An authenticated employee can request their own leave."],
        "dataAndState": ["Create a leave request in PENDING state."],
        "failureCases": ["Reject an invalid date range."],
        "acceptanceCriteria": [
            {
                "id": "AC-F001-01",
                "given": "an authenticated employee",
                "when": "valid dates are submitted",
                "then": "a pending request is stored",
            }
        ],
        "designNeeds": {
            "httpApi": True,
            "relationalData": True,
            "messaging": False,
            "scheduledJob": False,
            "serverRenderedUi": False,
            "separateClient": False,
            "externalIntegration": False,
        },
        "dependencies": [],
        "unknowns": [],
        "sources": [
            {"id": "S001", "type": "USER_STATED", "reference": "Approved summary"}
        ],
        "approval": {
            "status": "APPROVED",
            "approvedBy": "test-user",
            "approvedAt": "2026-09-01T00:00:00Z",
            "approvedContentSha256": None,
        },
    }
    document["approval"]["approvedContentSha256"] = approval_content_hash(document)
    return document


def refresh_approval(document: dict) -> None:
    document["approval"]["approvedContentSha256"] = approval_content_hash(document)


class FeatureSpecTests(unittest.TestCase):
    def test_approved_project_brief_advances(self) -> None:
        approved, blockers = validate_project(project_brief())
        self.assertTrue(approved)
        self.assertEqual([], blockers)

    def test_rest_feature_advances(self) -> None:
        approved, blockers = validate_feature(feature_spec(), project_brief())
        self.assertTrue(approved)
        self.assertEqual([], blockers)

    def test_batch_feature_does_not_require_api(self) -> None:
        feature = feature_spec()
        feature["designNeeds"]["httpApi"] = False
        feature["designNeeds"]["relationalData"] = False
        feature["designNeeds"]["scheduledJob"] = True
        refresh_approval(feature)
        self.assertEqual((True, []), validate_feature(feature, project_brief()))

    def test_message_consumer_does_not_require_relational_data(self) -> None:
        feature = feature_spec()
        feature["designNeeds"]["httpApi"] = False
        feature["designNeeds"]["relationalData"] = False
        feature["designNeeds"]["messaging"] = True
        refresh_approval(feature)
        self.assertEqual((True, []), validate_feature(feature, project_brief()))

    def test_blocking_unknown_prevents_advancement(self) -> None:
        feature = feature_spec()
        feature["unknowns"] = [{
            "id": "U-F001-01", "question": "Who may cancel?",
            "impact": "Changes authorization.", "blocking": True, "status": "OPEN",
        }]
        refresh_approval(feature)
        self.assertIn("blocking unknown is unresolved: U-F001-01", validate_feature(feature, project_brief())[1])

    def test_duplicate_business_rule_id_is_invalid(self) -> None:
        feature = feature_spec()
        feature["businessRules"].append(copy.deepcopy(feature["businessRules"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate ID BR-F001-01"):
            validate_feature(feature, project_brief())

    def test_approved_feature_requires_acceptance_criterion(self) -> None:
        feature = feature_spec()
        feature["acceptanceCriteria"] = []
        refresh_approval(feature)
        self.assertIn("at least one acceptance criterion is required", validate_feature(feature, project_brief())[1])

    def test_approved_feature_may_have_no_separate_business_rule(self) -> None:
        feature = feature_spec()
        feature["businessRules"] = []
        refresh_approval(feature)
        self.assertEqual((True, []), validate_feature(feature, project_brief()))

    def test_unconfirmed_ai_rule_prevents_advancement(self) -> None:
        feature = feature_spec()
        feature["businessRules"][0]["source"] = "INFERRED"
        feature["businessRules"][0]["confirmedByUser"] = False
        refresh_approval(feature)
        self.assertIn("AI-proposed rule is not user-confirmed: BR-F001-01", validate_feature(feature, project_brief())[1])

    def test_incomplete_approval_is_invalid(self) -> None:
        feature = feature_spec()
        feature["approval"]["approvedBy"] = None
        with self.assertRaisesRegex(ValueError, "approval.approvedBy"):
            validate_feature(feature, project_brief())

    def test_content_change_invalidates_approval(self) -> None:
        feature = feature_spec()
        feature["feature"]["goal"] = "Changed after approval"
        with self.assertRaisesRegex(ValueError, "approved content has changed"):
            validate_feature(feature, project_brief())

    def test_feature_must_exist_in_project_brief(self) -> None:
        project = project_brief()
        project["featureCandidates"] = []
        refresh_approval(project)
        self.assertIn("feature is absent from project brief: F001", validate_feature(feature_spec(), project)[1])

    def test_unapproved_project_brief_blocks_feature(self) -> None:
        project = project_brief()
        project["approval"] = {
            "status": "DRAFT", "approvedBy": None, "approvedAt": None,
            "approvedContentSha256": None,
        }
        self.assertIn("project brief is not approved", validate_feature(feature_spec(), project)[1])

    def test_unknown_or_draft_rule_blocks_approved_feature(self) -> None:
        feature = feature_spec()
        feature["businessRules"][0]["source"] = "UNKNOWN"
        feature["businessRules"][0]["status"] = "DRAFT"
        refresh_approval(feature)
        blockers = validate_feature(feature, project_brief())[1]
        self.assertIn("business rule source is UNKNOWN: BR-F001-01", blockers)
        self.assertIn("business rule is not approved: BR-F001-01", blockers)

    def test_secret_bearing_field_is_invalid(self) -> None:
        feature = feature_spec()
        feature["databasePassword"] = "not-a-real-password"
        with self.assertRaisesRegex(ValueError, "secret-bearing fields"):
            validate_feature(feature, project_brief())

    def test_markdown_is_user_ordered_and_staleness_is_detected(self) -> None:
        project = project_brief()
        feature = feature_spec()
        self.assertIn("## 추천 다음 기능", render_project(project))
        self.assertIn("## 이 기능으로 사용자가 할 수 있는 일", render_feature(feature, project))
        self.assertNotIn("BR-F001-01", render_feature(feature, project))
        self.assertIn("하네스 추천 · 사용자 확인 완료", render_feature(feature, project))
        self.assertIn("BR-F001-01", render_feature(feature, project, "full"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            feature_path = root / "feature.json"
            markdown_path = root / "spec.md"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            feature_path.write_text(json.dumps(feature), encoding="utf-8")
            command = [
                sys.executable, str(SCRIPTS / "render_spec_markdown.py"),
                "--input", str(feature_path), "--project-brief", str(project_path),
                "--output", str(markdown_path),
            ]
            self.assertEqual(0, subprocess.run(command, check=False, capture_output=True).returncode)
            self.assertEqual(0, subprocess.run(command + ["--check"], check=False, capture_output=True).returncode)
            feature["feature"]["userValue"] = "Changed value"
            refresh_approval(feature)
            feature_path.write_text(json.dumps(feature), encoding="utf-8")
            checked = subprocess.run(command + ["--check"], check=False, capture_output=True, text=True)
            self.assertEqual(1, checked.returncode)
            self.assertIn("Markdown view is stale", checked.stdout)

    def test_confirmation_badge_is_only_for_ai_proposed_rules(self) -> None:
        project = project_brief()
        feature = feature_spec()
        feature["businessRules"][0].update({
            "source": "PROJECT_EVIDENCE", "confirmedByUser": False,
        })
        refresh_approval(feature)
        rule_line = next(
            line for line in render_feature(feature, project).splitlines()
            if "end date" in line
        )
        self.assertIn("프로젝트에서 확인한 내용", rule_line)
        self.assertNotIn("사용자 확인", rule_line)

    def test_blocking_deferred_unknown_is_shown_as_immediate(self) -> None:
        project = project_brief()
        project["unknowns"] = [{
            "id": "U-PROJECT-01", "question": "Which privacy policy applies?",
            "impact": "Changes data retention.", "blocking": True, "status": "DEFERRED",
        }]
        refresh_approval(project)
        markdown = render_project(project)
        immediate = markdown.split("## 지금 확인해야 할 사항", 1)[1].split("## 나중에 결정 가능한 사항", 1)[0]
        later = markdown.split("## 나중에 결정 가능한 사항", 1)[1]
        self.assertIn("Which privacy policy applies?", immediate)
        self.assertNotIn("Which privacy policy applies?", later)

    def test_deferred_feature_is_not_recommended_first(self) -> None:
        project = project_brief()
        project["featureCandidates"][0]["status"] = "DEFERRED"
        project["featureCandidates"].append({
            "id": "F002", "name": "View leave", "userValue": "See request status.",
            "recommendationReason": "It can be verified independently.",
            "dependsOn": [], "blockingUnknownIds": [],
            "recommendedOrder": 2, "status": "DRAFT",
        })
        refresh_approval(project)
        recommendation = render_project(project).split("## 추천 다음 기능", 1)[1].split("## 지금 확인해야 할 사항", 1)[0]
        self.assertIn("View leave", recommendation)
        self.assertNotIn("Request leave", recommendation)

    def test_completed_or_implementing_feature_is_not_recommended_next(self) -> None:
        project = project_brief()
        project["featureCandidates"][0]["status"] = "VERIFIED"
        project["featureCandidates"].append({
            "id": "F002", "name": "Decide leave", "userValue": "Decide a request.",
            "recommendationReason": "It is already underway.", "dependsOn": ["F001"],
            "blockingUnknownIds": [], "recommendedOrder": 2, "status": "IMPLEMENTING",
        })
        project["featureCandidates"].append({
            "id": "F003", "name": "View leave", "userValue": "See request status.",
            "recommendationReason": "It is the next independently testable value.",
            "dependsOn": ["F001"], "blockingUnknownIds": [],
            "recommendedOrder": 3, "status": "DRAFT",
        })
        refresh_approval(project)
        recommendation = render_project(project).split("## 추천 다음 기능", 1)[1].split("## 지금 확인해야 할 사항", 1)[0]
        self.assertIn("View leave", recommendation)
        self.assertNotIn("Request leave", recommendation)
        self.assertNotIn("Decide leave", recommendation)

    def test_feature_with_unresolved_link_is_not_recommended(self) -> None:
        project = project_brief()
        project["unknowns"] = [{
            "id": "U-PROJECT-01", "question": "Which calendar is authoritative?",
            "impact": "Changes validation.", "blocking": False, "status": "OPEN",
        }]
        project["featureCandidates"][0]["blockingUnknownIds"] = ["U-PROJECT-01"]
        refresh_approval(project)
        recommendation = render_project(project).split("## 추천 다음 기능", 1)[1].split("## 지금 확인해야 할 사항", 1)[0]
        self.assertIn("현재 추천할 다음 기능 없음", recommendation)

    def test_approval_tool_records_hashes_without_exposing_them(self) -> None:
        project = project_brief()
        feature = feature_spec()
        project["approval"] = {
            "status": "REVIEW_REQUIRED", "approvedBy": None, "approvedAt": None,
            "approvedContentSha256": None,
        }
        feature["feature"]["status"] = "REVIEW_REQUIRED"
        feature["approval"] = {
            "status": "REVIEW_REQUIRED", "approvedBy": None, "approvedAt": None,
            "approvedContentSha256": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            feature_path = root / "feature.json"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            feature_path.write_text(json.dumps(feature), encoding="utf-8")
            project_path.with_suffix(".md").write_text(render_project(project), encoding="utf-8")
            feature_path.with_suffix(".md").write_text(render_feature(feature, project), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPTS / "record_spec_approval.py"),
                "--project-brief", str(project_path), "--feature", str(feature_path),
                "--expected-project-hash", approval_content_hash(project),
                "--expected-feature-hash", approval_content_hash(feature),
                "--approved-by", "test-user", "--approved-at", "2026-09-01T00:00:00Z",
            ], check=False, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("CONTENT_HASH_VISIBLE_TO_USER: no", result.stdout)
            self.assertNotIn("sha256", result.stdout.lower())
            approved_project = json.loads(project_path.read_text(encoding="utf-8"))
            approved_feature = json.loads(feature_path.read_text(encoding="utf-8"))
            self.assertEqual("APPROVED", approved_project["featureCandidates"][0]["status"])
            self.assertEqual((True, []), validate_project(approved_project))
            self.assertEqual((True, []), validate_feature(approved_feature, approved_project))
            self.assertEqual(render_project(approved_project), project_path.with_suffix(".md").read_text(encoding="utf-8"))
            self.assertEqual(
                render_feature(approved_feature, approved_project),
                feature_path.with_suffix(".md").read_text(encoding="utf-8"),
            )

    def test_approval_rejects_independently_edited_markdown(self) -> None:
        project = project_brief()
        project["approval"] = {
            "status": "REVIEW_REQUIRED", "approvedBy": None, "approvedAt": None,
            "approvedContentSha256": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "project.json"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            project_path.with_suffix(".md").write_text("independent edit", encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPTS / "record_spec_approval.py"),
                "--project-brief", str(project_path),
                "--expected-project-hash", approval_content_hash(project),
                "--approved-by", "test-user", "--approved-at", "2026-09-01T00:00:00Z",
            ], check=False, capture_output=True, text=True)
            self.assertEqual(1, result.returncode)
            self.assertIn("project Markdown view changed", result.stdout)
            self.assertEqual("independent edit", project_path.with_suffix(".md").read_text(encoding="utf-8"))

    def test_approval_rollback_preserves_external_change(self) -> None:
        project = project_brief()
        project["approval"] = {
            "status": "REVIEW_REQUIRED", "approvedBy": None, "approvedAt": None,
            "approvedContentSha256": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "project.json"
            markdown_path = project_path.with_suffix(".md")
            project_path.write_text(json.dumps(project), encoding="utf-8")
            markdown_path.write_text(render_project(project), encoding="utf-8")
            real_write = record_spec_approval.atomic_write_bytes
            calls = 0

            def fail_after_external_change(content: bytes, destination: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    real_write(content, destination)
                    return
                project_path.write_text("external change", encoding="utf-8")
                raise OSError("injected failure")

            arguments = [
                "record_spec_approval.py", "--project-brief", str(project_path),
                "--expected-project-hash", approval_content_hash(project),
                "--approved-by", "test-user", "--approved-at", "2026-09-01T00:00:00Z",
            ]
            with mock.patch.object(sys, "argv", arguments), mock.patch.object(
                record_spec_approval, "atomic_write_bytes", side_effect=fail_after_external_change
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(1, record_spec_approval.main())
            self.assertEqual("external change", project_path.read_text(encoding="utf-8"))

    def test_next_feature_id_uses_brief_and_existing_directories(self) -> None:
        project = project_brief()
        project["featureCandidates"].append({
            "id": "F002", "name": "Decide leave", "userValue": "Decide a request.",
            "recommendationReason": "It follows submission.", "dependsOn": ["F001"],
            "blockingUnknownIds": [], "recommendedOrder": 2, "status": "DRAFT",
        })
        refresh_approval(project)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            features = root / "features"
            (features / "F004").mkdir(parents=True)
            project_path.write_text(json.dumps(project), encoding="utf-8")
            self.assertEqual("F005", next_feature_id(project_path, features))

    def test_approval_tool_rejects_content_changed_after_display(self) -> None:
        project = project_brief()
        project["approval"] = {
            "status": "REVIEW_REQUIRED", "approvedBy": None, "approvedAt": None,
            "approvedContentSha256": None,
        }
        shown_hash = approval_content_hash(project)
        project["project"]["goal"] = "Changed after display"
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "project.json"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPTS / "record_spec_approval.py"),
                "--project-brief", str(project_path),
                "--expected-project-hash", shown_hash,
                "--approved-by", "test-user", "--approved-at", "2026-09-01T00:00:00Z",
            ], check=False, capture_output=True, text=True)
            self.assertEqual(1, result.returncode)
            self.assertIn("changed after it was shown", result.stdout)
            unchanged = json.loads(project_path.read_text(encoding="utf-8"))
            self.assertEqual("REVIEW_REQUIRED", unchanged["approval"]["status"])

    def test_templates_are_valid_drafts(self) -> None:
        project = json.loads((ROOT / "templates/project-brief.json").read_text(encoding="utf-8"))
        feature = json.loads((ROOT / "templates/feature-spec.json").read_text(encoding="utf-8"))
        self.assertEqual((False, []), validate_project(project))
        approved, blockers = validate_feature(feature, project)
        self.assertFalse(approved)
        self.assertIn("feature is absent from project brief: F001", blockers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
