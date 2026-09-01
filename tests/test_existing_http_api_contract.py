#!/usr/bin/env python3

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

from existing_http_api_contract import compare_openapi, validate_existing_contract  # noqa: E402
import record_existing_http_api_contract_approval  # noqa: E402
from render_existing_http_api_contract import render  # noqa: E402
from http_api_contract import derived_traceability, encoded  # noqa: E402
from tests.test_design_route import refresh, route  # noqa: E402
from tests.test_feature_specs import feature_spec  # noqa: E402
from tests.test_http_api_contract import openapi, profile  # noqa: E402
from validate_feature_specs import approval_content_hash  # noqa: E402


class ExistingHttpApiContractTests(unittest.TestCase):
    def fixture(self, root: Path, disposition: str = "REUSE", controller: str | None = None):
        baseline_path = root / "api/openapi.json"
        baseline_path.parent.mkdir(parents=True)
        baseline_path.write_bytes(encoded(openapi()))
        design_route = route()
        selected = design_route["routes"][0]
        selected["disposition"] = disposition
        selected["artifactPath"] = "docs/features/F001/contracts/http-api/metadata.json"
        selected["evidencePaths"] = ["api/openapi.json"]
        design_route["inputs"]["codeEvidence"] = [{
            "path": "api/openapi.json", "sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(), "kind": "OPENAPI",
        }]
        if controller is not None:
            controller_path = root / "src/LeaveController.java"
            controller_path.parent.mkdir(parents=True)
            controller_path.write_text(controller, encoding="utf-8")
            selected["evidencePaths"].append("src/LeaveController.java")
            design_route["inputs"]["codeEvidence"].append({
                "path": "src/LeaveController.java", "sha256": hashlib.sha256(controller_path.read_bytes()).hexdigest(),
                "kind": "SPRING_CONTROLLER",
            })
        refresh(design_route)
        route_path = root / "docs/features/F001/design-route.json"
        route_path.parent.mkdir(parents=True, exist_ok=True)
        route_path.write_bytes(encoded(design_route))
        proposed = openapi()
        if disposition == "EXTEND":
            extra = copy.deepcopy(proposed["paths"]["/api/leave-requests"]["post"])
            extra["operationId"] = "listLeaveRequests"
            extra["summary"] = "List leave requests"
            proposed["paths"]["/api/leave-requests"]["get"] = extra
            artifact_path = root / "docs/features/F001/contracts/http-api/proposed-openapi.json"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(encoded(proposed))
        else:
            artifact_path = baseline_path
        report = compare_openapi(openapi(), proposed, "http-api")
        comparison_path = root / "docs/features/F001/contracts/http-api/comparison.json"
        comparison_path.parent.mkdir(parents=True, exist_ok=True)
        comparison_path.write_bytes(encoded(report))
        contract_path = root / selected["artifactPath"]
        metadata = {
            "contractVersion": 1, "contractId": "http-api", "kind": "HTTP_API", "featureId": "F001",
            "route": {"path": route_path.relative_to(root).as_posix(), "sha256": hashlib.sha256(route_path.read_bytes()).hexdigest()},
            "disposition": disposition, "target": copy.deepcopy(selected["target"]),
            "artifact": {"format": "OPENAPI", "path": artifact_path.relative_to(root).as_posix()},
            "baselineArtifact": {"format": "OPENAPI", "path": baseline_path.relative_to(root).as_posix(), "sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest()},
            "comparison": {"path": comparison_path.relative_to(root).as_posix(), "sha256": hashlib.sha256(comparison_path.read_bytes()).hexdigest()},
            "acceptedCompatibilityReviews": [],
            "traceability": derived_traceability(proposed), "evidencePaths": copy.deepcopy(selected["evidencePaths"]),
            "approval": {"status": "APPROVED", "approvedBy": "test-user", "approvedAt": "2026-09-01T00:00:00Z", "approvedContentSha256": None},
        }
        metadata["approval"]["approvedContentSha256"] = approval_content_hash(metadata)
        contract_path.write_bytes(encoded(metadata))
        return metadata, design_route, route_path, contract_path

    def test_reuse_references_existing_openapi_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root)
            approved, blockers, _, report = validate_existing_contract(
                metadata, design_route, route_path, root, contract_path, feature_spec(), profile()
            )
            self.assertTrue(approved)
            self.assertEqual([], blockers)
            self.assertEqual([], report["changes"])

    def test_extend_allows_additive_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root, "EXTEND")
            _, blockers, _, report = validate_existing_contract(
                metadata, design_route, route_path, root, contract_path, feature_spec(), profile()
            )
            self.assertEqual([], blockers)
            self.assertEqual("OPERATION_ADDED", report["changes"][0]["code"])

    def test_removed_operation_is_breaking(self) -> None:
        baseline = openapi()
        proposed = copy.deepcopy(baseline)
        proposed["paths"] = {"/health": {"get": copy.deepcopy(baseline["paths"]["/api/leave-requests"]["post"])}}
        proposed["paths"]["/health"]["get"]["operationId"] = "health"
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(item["code"] == "OPERATION_REMOVED" for item in report["changes"]))
        self.assertGreater(report["summary"]["breaking"], 0)

    def test_required_request_field_is_breaking(self) -> None:
        baseline = openapi()
        proposed = copy.deepcopy(baseline)
        schema = proposed["paths"]["/api/leave-requests"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        schema["properties"] = {"reason": {"type": "string"}}
        schema["required"] = ["reason"]
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(
            item["code"] == "REQUEST_SCHEMA_CHANGED" and item["level"] == "BREAKING"
            for item in report["changes"]
        ))

    def test_controller_evidence_can_prove_mapping(self) -> None:
        source = '@RestController\nclass LeaveController {\n@PostMapping("/api/leave-requests") void request() {}\n}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root, controller=source)
            self.assertEqual([], validate_existing_contract(
                metadata, design_route, route_path, root, contract_path, feature_spec(), profile()
            )[1])

    def test_controller_mismatch_blocks_reuse(self) -> None:
        source = '@RestController\nclass OtherController {\n@GetMapping("/other") void other() {}\n}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root, controller=source)
            self.assertTrue(any("controller evidence does not prove operation" in item for item in validate_existing_contract(
                metadata, design_route, route_path, root, contract_path, feature_spec(), profile()
            )[1]))

    def test_controller_evidence_drift_is_detected_independently(self) -> None:
        source = '@RestController\nclass LeaveController {\n@PostMapping("/api/leave-requests") void request() {}\n}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root, controller=source)
            (root / "src/LeaveController.java").write_text(source + "\n// changed", encoding="utf-8")
            self.assertTrue(any("route evidence changed after assessment" in item for item in validate_existing_contract(
                metadata, design_route, route_path, root, contract_path, feature_spec(), profile()
            )[1]))

    def test_baseline_drift_blocks_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root)
            (root / metadata["baselineArtifact"]["path"]).write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_existing_contract(metadata, design_route, route_path, root, contract_path, feature_spec(), profile())

    def test_reuse_approval_does_not_modify_existing_openapi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root)
            metadata["approval"] = {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None}
            contract_path.write_bytes(encoded(metadata))
            api_path = root / metadata["artifact"]["path"]
            comparison_path = root / metadata["comparison"]["path"]
            api_before = api_path.read_bytes()
            report = json.loads(comparison_path.read_text(encoding="utf-8"))
            contract_path.with_suffix(".md").write_text(render(metadata, openapi(), report, []), encoding="utf-8")
            feature_path, project_path, profile_path = root / "feature.json", root / "project.json", root / "profile.json"
            feature_path.write_text(json.dumps(feature_spec()), encoding="utf-8")
            project_path.write_text("{}", encoding="utf-8")
            profile_path.write_text(json.dumps(profile()), encoding="utf-8")
            arguments = [
                "record_existing_http_api_contract_approval.py", "--contract", str(contract_path),
                "--route", str(route_path), "--feature", str(feature_path), "--project-brief", str(project_path),
                "--profile", str(profile_path), "--target", str(root),
                "--expected-contract-hash", approval_content_hash(metadata),
                "--expected-artifact-hash", hashlib.sha256(api_before).hexdigest(),
                "--expected-comparison-hash", hashlib.sha256(comparison_path.read_bytes()).hexdigest(),
                "--approved-by", "test-user", "--approved-at", "2026-09-01T00:00:00Z",
            ]
            with mock.patch.object(sys, "argv", arguments), mock.patch.object(
                record_existing_http_api_contract_approval, "assess", return_value=(True, True, [])
            ), mock.patch.object(
                record_existing_http_api_contract_approval, "verify_inputs", return_value=[]
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, record_existing_http_api_contract_approval.main())
            self.assertEqual("APPROVED", json.loads(contract_path.read_text(encoding="utf-8"))["approval"]["status"])
            self.assertEqual(api_before, api_path.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
