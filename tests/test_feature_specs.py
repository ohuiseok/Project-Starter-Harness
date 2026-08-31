#!/usr/bin/env python3
"""Focused regression tests for project briefs and feature specifications."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
sys.path.insert(0, str(SCRIPTS))

from render_spec_markdown import render_feature, render_project  # noqa: E402
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
        self.assertIn("## 추천 첫 번째 기능", render_project(project))
        self.assertIn("## 이 기능으로 사용자가 할 수 있는 일", render_feature(feature, project))
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

    def test_templates_are_valid_drafts(self) -> None:
        project = json.loads((ROOT / "templates/project-brief.json").read_text(encoding="utf-8"))
        feature = json.loads((ROOT / "templates/feature-spec.json").read_text(encoding="utf-8"))
        self.assertEqual((False, []), validate_project(project))
        approved, blockers = validate_feature(feature, project)
        self.assertFalse(approved)
        self.assertIn("feature is absent from project brief: F001", blockers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
