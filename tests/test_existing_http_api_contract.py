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

from existing_http_api_contract import compare_openapi, controller_mappings, validate_existing_contract  # noqa: E402
from migrate_existing_http_api_contract_v2 import migrate  # noqa: E402
import record_existing_http_api_contract_approval  # noqa: E402
from render_existing_http_api_contract import render, render_recovery  # noqa: E402
from http_api_contract import derived_traceability, encoded, validate_openapi  # noqa: E402
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
            "selectedOperations": [item["subjectRef"] for item in derived_traceability(proposed)],
            "compatibilityReviews": [
                {"reviewId": f"{item['code']}:{item['location']}", "status": "PENDING", "reason": "UNKNOWN", "source": "UNKNOWN", "confirmedByUser": False}
                for item in report["changes"] if item["level"] == "REVIEW"
            ],
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

    def test_existing_parameter_type_change_is_breaking(self) -> None:
        baseline = openapi()
        operation = baseline["paths"]["/api/leave-requests"]["post"]
        operation["parameters"] = [{"in": "query", "name": "year", "required": False, "schema": {"type": "integer"}}]
        proposed = copy.deepcopy(baseline)
        proposed["paths"]["/api/leave-requests"]["post"]["parameters"][0]["schema"]["type"] = "string"
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(item["code"] == "PARAMETER_CHANGED" and item["level"] == "BREAKING" for item in report["changes"]))

    def test_request_content_type_removal_is_breaking(self) -> None:
        baseline = openapi()
        content = baseline["paths"]["/api/leave-requests"]["post"]["requestBody"]["content"]
        content["application/xml"] = copy.deepcopy(content["application/json"])
        proposed = copy.deepcopy(baseline)
        del proposed["paths"]["/api/leave-requests"]["post"]["requestBody"]["content"]["application/xml"]
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(item["code"] == "REQUEST_CONTENT_TYPE_REMOVED" for item in report["changes"]))

    def test_response_header_removal_is_breaking(self) -> None:
        baseline = openapi()
        baseline["paths"]["/api/leave-requests"]["post"]["responses"]["201"]["headers"] = {
            "Location": {"schema": {"type": "string"}}
        }
        proposed = copy.deepcopy(baseline)
        del proposed["paths"]["/api/leave-requests"]["post"]["responses"]["201"]["headers"]
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(item["code"] == "RESPONSE_HEADER_REMOVED" for item in report["changes"]))

    def test_local_ref_component_change_is_compared_by_meaning(self) -> None:
        baseline = openapi()
        operation = baseline["paths"]["/api/leave-requests"]["post"]
        operation["requestBody"]["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/LeaveRequest"}
        baseline["components"]["schemas"] = {"LeaveRequest": {"type": "object", "properties": {"reason": {"type": "string"}}}}
        proposed = copy.deepcopy(baseline)
        proposed["components"]["schemas"]["LeaveRequest"]["required"] = ["reason"]
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(item["code"] == "REQUEST_SCHEMA_CHANGED" and item["level"] == "BREAKING" for item in report["changes"]))

    def test_component_request_body_ref_change_is_compared_by_meaning(self) -> None:
        baseline = openapi()
        operation = baseline["paths"]["/api/leave-requests"]["post"]
        baseline["components"]["requestBodies"] = {"LeaveRequest": operation.pop("requestBody")}
        operation["requestBody"] = {"$ref": "#/components/requestBodies/LeaveRequest"}
        proposed = copy.deepcopy(baseline)
        schema = proposed["components"]["requestBodies"]["LeaveRequest"]["content"]["application/json"]["schema"]
        schema.update({"properties": {"reason": {"type": "string"}}, "required": ["reason"]})
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(item["code"] == "REQUEST_SCHEMA_CHANGED" and item["level"] == "BREAKING" for item in report["changes"]))

    def test_component_response_and_header_refs_are_compared(self) -> None:
        baseline = openapi()
        operation = baseline["paths"]["/api/leave-requests"]["post"]
        response = operation["responses"]["201"]
        response["headers"] = {"Location": {"$ref": "#/components/headers/Location"}}
        response["content"] = {"application/json": {"schema": {"type": "object", "properties": {"id": {"type": "string"}}}}}
        baseline["components"]["headers"] = {"Location": {"schema": {"type": "string"}}}
        baseline["components"]["responses"] = {"Created": response}
        operation["responses"]["201"] = {"$ref": "#/components/responses/Created"}
        proposed = copy.deepcopy(baseline)
        del proposed["components"]["responses"]["Created"]["headers"]["Location"]
        del proposed["components"]["responses"]["Created"]["content"]["application/json"]["schema"]["properties"]["id"]
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(item["code"] == "RESPONSE_HEADER_REMOVED" for item in report["changes"]))
        self.assertTrue(any(item["code"] == "RESPONSE_SCHEMA_CHANGED" and item["level"] == "BREAKING" for item in report["changes"]))

    def test_component_header_ref_definition_change_is_compared(self) -> None:
        baseline = openapi()
        response = baseline["paths"]["/api/leave-requests"]["post"]["responses"]["201"]
        response["headers"] = {"Location": {"$ref": "#/components/headers/Location"}}
        baseline["components"]["headers"] = {"Location": {"schema": {"type": "string"}}}
        proposed = copy.deepcopy(baseline)
        proposed["components"]["headers"]["Location"]["schema"]["type"] = "integer"
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(
            item["code"] == "RESPONSE_HEADER_CHANGED" and item["level"] == "BREAKING"
            for item in report["changes"]
        ))

    def test_partial_reuse_ignores_unselected_operation_traceability(self) -> None:
        api = openapi()
        extra = copy.deepcopy(api["paths"]["/api/leave-requests"]["post"])
        extra["operationId"] = "unrelatedAdminOperation"
        extra["summary"] = "Unrelated admin operation"
        extra.pop("x-harness-requirement-refs")
        api["paths"]["/admin"] = {"post": extra}
        metadata = {"traceability": derived_traceability(openapi())}
        self.assertEqual([], validate_openapi(api, feature_spec(), profile(), metadata, {"requestLeave"}))

    def test_security_removal_is_a_non_waivable_security_change(self) -> None:
        baseline = openapi()
        proposed = copy.deepcopy(baseline)
        proposed["paths"]["/api/leave-requests"]["post"]["security"] = []
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(item["code"] == "SECURITY_REMOVED" and item["level"] == "SECURITY" for item in report["changes"]))

    def test_referenced_security_scheme_definition_change_is_detected(self) -> None:
        baseline = openapi()
        proposed = copy.deepcopy(baseline)
        proposed["components"]["securitySchemes"]["bearerAuth"]["bearerFormat"] = "opaque"
        report = compare_openapi(baseline, proposed, "http-api")
        self.assertTrue(any(item["code"] == "SECURITY_CHANGED" and item["level"] == "SECURITY" for item in report["changes"]))

    def test_external_ref_remains_unknown(self) -> None:
        baseline = openapi()
        baseline["paths"]["/api/leave-requests"]["post"]["requestBody"]["content"]["application/json"]["schema"] = {
            "$ref": "https://schemas.example.test/leave.json"
        }
        report = compare_openapi(baseline, copy.deepcopy(baseline), "http-api")
        self.assertTrue(any(item["code"] == "EXTERNAL_REF_UNRESOLVED" and item["level"] == "UNKNOWN" for item in report["changes"]))

    def test_partial_reuse_ignores_external_ref_from_unselected_operation(self) -> None:
        baseline = openapi()
        unrelated = copy.deepcopy(baseline["paths"]["/api/leave-requests"]["post"])
        unrelated["operationId"] = "unrelated"
        unrelated["requestBody"]["content"]["application/json"]["schema"] = {"$ref": "https://example.test/unrelated.json"}
        baseline["paths"]["/unrelated"] = {"post": unrelated}
        report = compare_openapi(baseline, copy.deepcopy(baseline), "http-api", {"requestLeave"})
        self.assertFalse(any(item["code"] == "EXTERNAL_REF_UNRESOLVED" for item in report["changes"]))

    def test_partial_reuse_follows_selected_local_refs_to_external_refs(self) -> None:
        baseline = openapi()
        baseline["paths"]["/api/leave-requests"]["post"]["requestBody"]["content"]["application/json"]["schema"] = {
            "$ref": "#/components/schemas/LeaveRequest"
        }
        baseline["components"]["schemas"] = {"LeaveRequest": {"$ref": "https://example.test/leave.json"}}
        report = compare_openapi(baseline, copy.deepcopy(baseline), "http-api", {"requestLeave"})
        self.assertTrue(any(item["code"] == "EXTERNAL_REF_UNRESOLVED" for item in report["changes"]))

    def test_review_acceptance_requires_reason_source_and_user_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root, "EXTEND")
            baseline = openapi()
            artifact_path = root / metadata["artifact"]["path"]
            proposed = json.loads(artifact_path.read_text(encoding="utf-8"))
            schema = proposed["paths"]["/api/leave-requests"]["post"]["requestBody"]["content"]["application/json"]["schema"]
            schema["properties"] = {"optionalNote": {"type": "string"}}
            artifact_path.write_bytes(encoded(proposed))
            report = compare_openapi(baseline, proposed, "http-api")
            comparison_path = root / metadata["comparison"]["path"]
            comparison_path.write_bytes(encoded(report))
            metadata["comparison"]["sha256"] = hashlib.sha256(comparison_path.read_bytes()).hexdigest()
            metadata["traceability"] = derived_traceability(proposed)
            metadata["selectedOperations"] = [item["subjectRef"] for item in metadata["traceability"]]
            review_id = next(f"{item['code']}:{item['location']}" for item in report["changes"] if item["level"] == "REVIEW")
            metadata["compatibilityReviews"] = [{
                "reviewId": review_id, "status": "ACCEPTED", "reason": "UNKNOWN",
                "source": "USER_STATED", "confirmedByUser": False,
            }]
            metadata["approval"]["approvedContentSha256"] = approval_content_hash(metadata)
            blockers = validate_existing_contract(metadata, design_route, route_path, root, contract_path, feature_spec(), profile())[1]
            self.assertTrue(any("lacks user-confirmed reason" in item for item in blockers))
            metadata["compatibilityReviews"][0].update({
                "reason": "No client has consumed the optional field yet.", "confirmedByUser": True,
            })
            metadata["approval"]["approvedContentSha256"] = approval_content_hash(metadata)
            self.assertEqual([], validate_existing_contract(
                metadata, design_route, route_path, root, contract_path, feature_spec(), profile()
            )[1])

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

    def test_controller_class_and_method_paths_are_joined_exactly(self) -> None:
        source = '@RestController\n@RequestMapping("/api")\nclass LeaveController {\n@PostMapping("/leave-requests") void request() {}\n}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root, controller=source)
            self.assertEqual([], validate_existing_contract(
                metadata, design_route, route_path, root, contract_path, feature_spec(), profile()
            )[1])

    def test_controller_ignores_non_path_annotation_strings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "LeaveController.java"
            path.write_text(
                '@RestController\n@RequestMapping(path="/api", produces="application/json")\n'
                'class LeaveController {\n@PostMapping(value="/leave-requests", consumes="application/json") void request() {}\n}',
                encoding="utf-8",
            )
            result = controller_mappings(path)
            self.assertEqual({("post", "/api/leave-requests")}, result.mappings)
            self.assertEqual((), result.unknowns)

    def test_request_mapping_with_method_only_uses_class_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "LeaveController.java"
            path.write_text(
                '@RestController\n@RequestMapping("/api/leave-requests")\nclass LeaveController {\n'
                '@RequestMapping(method=RequestMethod.POST) void request() {}\n}', encoding="utf-8",
            )
            result = controller_mappings(path)
            self.assertEqual({("post", "/api/leave-requests")}, result.mappings)
            self.assertEqual((), result.unknowns)

    def test_controller_positional_path_array_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "LeaveController.java"
            path.write_text(
                '@RestController\nclass LeaveController {\n@GetMapping({"/one", "/two"}) void list() {}\n}',
                encoding="utf-8",
            )
            self.assertEqual({("get", "/one"), ("get", "/two")}, controller_mappings(path).mappings)

    def test_controller_substring_path_is_not_false_evidence(self) -> None:
        source = '@RestController\nclass LeaveController {\n@PostMapping("/leave") void request() {}\n}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root, controller=source)
            self.assertTrue(any("does not prove operation" in item for item in validate_existing_contract(
                metadata, design_route, route_path, root, contract_path, feature_spec(), profile()
            )[1]))

    def test_controller_constant_path_is_unknown_not_confirmed(self) -> None:
        source = '@RestController\nclass LeaveController {\n@PostMapping(LEAVE_PATH) void request() {}\n}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root, controller=source)
            self.assertTrue(any("controller mapping is UNKNOWN" in item for item in validate_existing_contract(
                metadata, design_route, route_path, root, contract_path, feature_spec(), profile()
            )[1]))

    def test_controller_constant_class_base_cannot_accidentally_confirm(self) -> None:
        source = '@RestController\n@RequestMapping(API_BASE)\nclass LeaveController {\n@PostMapping("/api/leave-requests") void request() {}\n}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root, controller=source)
            self.assertTrue(any("controller mapping is UNKNOWN" in item for item in validate_existing_contract(
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

    def test_broken_evidence_still_has_a_safe_recovery_view(self) -> None:
        markdown = render_recovery({"contractId": "member-api"}, ValueError("/secret/path: cannot load JSON"))
        self.assertIn("재분석 필요", markdown)
        self.assertIn("현재 OpenAPI와 Controller evidence로 다시 분석", markdown)
        self.assertNotIn("/secret/path", markdown)

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
            contract_path.with_suffix(".md").write_text(render(metadata, openapi(), report, [], feature_spec()), encoding="utf-8")
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

    def test_user_view_shows_change_impact_and_actions(self) -> None:
        baseline = openapi()
        proposed = copy.deepcopy(baseline)
        proposed["paths"]["/api/leave-requests"]["post"]["security"] = []
        report = compare_openapi(baseline, proposed, "http-api")
        metadata = {
            "disposition": "EXTEND", "selectedOperations": ["requestLeave"],
            "traceability": derived_traceability(proposed), "compatibilityReviews": [],
            "approval": {"status": "DRAFT"},
        }
        markdown = render(metadata, proposed, report, ["EXTEND contains a security regression or unresolved security change"], feature_spec())
        self.assertIn("차이:", markdown)
        self.assertIn("영향:", markdown)
        self.assertIn("추천:", markdown)
        self.assertIn("## 다음 행동", markdown)

    def test_legacy_review_migration_does_not_inherit_approval(self) -> None:
        legacy = {
            "disposition": "EXTEND", "traceability": [{"subjectRef": "requestLeave", "requirementRefs": ["AC-F001-01"]}],
            "acceptedCompatibilityReviews": ["REQUEST_SCHEMA_CHANGED:requestLeave"],
            "approval": {"status": "APPROVED"},
        }
        report = {"changes": [{"level": "REVIEW", "code": "REQUEST_SCHEMA_CHANGED", "location": "requestLeave"}]}
        migrated = migrate(legacy, report)
        self.assertEqual("REVIEW_REQUIRED", migrated["approval"]["status"])
        self.assertEqual("PENDING", migrated["compatibilityReviews"][0]["status"])
        self.assertNotIn("acceptedCompatibilityReviews", migrated)


if __name__ == "__main__":
    unittest.main(verbosity=2)
