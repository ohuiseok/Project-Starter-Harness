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

from http_api_contract import derived_traceability, validate_http_contract, validate_openapi  # noqa: E402
from render_http_api_contract import render  # noqa: E402
import create_http_api_contract  # noqa: E402
import record_http_api_contract_approval  # noqa: E402
from tests.test_design_route import route  # noqa: E402
from tests.test_feature_specs import feature_spec  # noqa: E402
from validate_feature_specs import approval_content_hash  # noqa: E402


def profile(option: str = "security.token") -> dict:
    return {"decisions": {"security": {"option": option, "status": "NOW"}}}


def openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Leave requests", "version": "0.1.0"},
        "paths": {
            "/api/leave-requests": {
                "post": {
                    "operationId": "requestLeave", "summary": "Request leave",
                    "x-harness-requirement-refs": ["AC-F001-01", "BR-F001-01"],
                    "security": [{"bearerAuth": []}],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                    "responses": {
                        "201": {"description": "Created"}, "400": {"description": "Invalid dates"},
                        "401": {"description": "Authentication required"}, "403": {"description": "Forbidden"},
                    },
                }
            }
        },
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
    }


class HttpApiContractTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[dict, dict, Path, Path]:
        design_route = route()
        selected = design_route["routes"][0]
        route_path = root / "docs/features/F001/design-route.json"
        route_path.parent.mkdir(parents=True)
        route_path.write_text(json.dumps(design_route), encoding="utf-8")
        contract_path = root / selected["artifactPath"]
        contract_path.parent.mkdir(parents=True)
        api_path = contract_path.parent / "openapi.json"
        api = openapi()
        api_path.write_text(json.dumps(api), encoding="utf-8")
        metadata = {
            "contractVersion": 1, "contractId": "http-api", "kind": "HTTP_API", "featureId": "F001",
            "route": {"path": "docs/features/F001/design-route.json", "sha256": hashlib.sha256(route_path.read_bytes()).hexdigest()},
            "disposition": "CREATE", "target": copy.deepcopy(selected["target"]),
            "artifact": {"format": "OPENAPI", "path": api_path.relative_to(root).as_posix()},
            "traceability": derived_traceability(api), "evidencePaths": [],
            "approval": {"status": "APPROVED", "approvedBy": "test-user", "approvedAt": "2026-09-01T00:00:00Z", "approvedContentSha256": None},
        }
        metadata["approval"]["approvedContentSha256"] = approval_content_hash(metadata)
        contract_path.write_text(json.dumps(metadata), encoding="utf-8")
        return metadata, design_route, route_path, contract_path

    def test_complete_token_api_contract_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root)
            self.assertEqual((True, [], openapi()), validate_http_contract(
                metadata, design_route, route_path, root, contract_path, feature_spec(), profile()
            ))

    def test_every_acceptance_criterion_must_be_covered(self) -> None:
        api = openapi()
        api["paths"]["/api/leave-requests"]["post"]["x-harness-requirement-refs"] = ["BR-F001-01"]
        metadata = {"traceability": derived_traceability(api)}
        self.assertTrue(any("acceptance criteria are not covered" in item for item in validate_openapi(
            api, feature_spec(), profile(), metadata
        )))

    def test_session_profile_requires_cookie_security(self) -> None:
        api = openapi()
        metadata = {"traceability": derived_traceability(api)}
        self.assertIn("session security requires a cookie apiKey security scheme", validate_openapi(
            api, feature_spec(), profile("security.session"), metadata
        ))

    def test_no_security_profile_rejects_bearer_api(self) -> None:
        api = openapi()
        metadata = {"traceability": derived_traceability(api)}
        self.assertIn("security.none profile cannot define secured API operations", validate_openapi(
            api, feature_spec(), profile("security.none"), metadata
        ))

    def test_secret_like_bearer_example_is_rejected(self) -> None:
        api = openapi()
        api["paths"]["/api/leave-requests"]["post"]["description"] = "Bearer abcdefghijklmnop"
        metadata = {"traceability": derived_traceability(api)}
        with self.assertRaisesRegex(ValueError, "secret-like value"):
            validate_openapi(api, feature_spec(), profile(), metadata)

    def test_authorized_api_requires_401_and_403(self) -> None:
        api = openapi()
        del api["paths"]["/api/leave-requests"]["post"]["responses"]["403"]
        metadata = {"traceability": derived_traceability(api)}
        self.assertTrue(any("authorized operation must describe both 401 and 403" in item for item in validate_openapi(
            api, feature_spec(), profile(), metadata
        )))

    def test_user_view_is_derived_from_openapi(self) -> None:
        api = openapi()
        metadata = {"approval": {"status": "DRAFT"}, "traceability": derived_traceability(api)}
        markdown = render(metadata, api, [])
        self.assertIn("POST /api/leave-requests", markdown)
        self.assertIn("인증 필요", markdown)
        self.assertIn("AC-F001-01", markdown)
        self.assertIn("승인 대기", markdown)

    def test_creator_refuses_to_overwrite_existing_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "metadata.json"
            existing.write_text("owned", encoding="utf-8")
            arguments = [
                "create_http_api_contract.py", "--route", str(root / "route.json"),
                "--feature", str(root / "feature.json"), "--project-brief", str(root / "project.json"),
                "--profile", str(root / "profile.json"), "--target", str(root),
                "--contract-id", "http-api", "--openapi-source", str(root / "draft.json"),
                "--contract-output", str(existing), "--openapi-output", str(root / "openapi.json"),
            ]
            with mock.patch.object(sys, "argv", arguments), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(1, create_http_api_contract.main())
            self.assertEqual("owned", existing.read_text(encoding="utf-8"))

    def test_creator_materializes_openapi_and_derived_metadata_without_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            design_route = route()
            selected = design_route["routes"][0]
            route_path = root / "docs/features/F001/design-route.json"
            route_path.parent.mkdir(parents=True)
            route_path.write_text(json.dumps(design_route), encoding="utf-8")
            feature_path = root / "feature.json"
            project_path = root / "project.json"
            profile_path = root / "profile.json"
            draft_path = root / "draft.json"
            feature_path.write_text(json.dumps(feature_spec()), encoding="utf-8")
            project_path.write_text("{}", encoding="utf-8")
            profile_path.write_text(json.dumps(profile()), encoding="utf-8")
            draft_path.write_text(json.dumps(openapi()), encoding="utf-8")
            contract_output = root / selected["artifactPath"]
            openapi_output = contract_output.parent / "openapi.json"
            arguments = [
                "create_http_api_contract.py", "--route", str(route_path),
                "--feature", str(feature_path), "--project-brief", str(project_path),
                "--profile", str(profile_path), "--target", str(root),
                "--contract-id", "http-api", "--openapi-source", str(draft_path),
                "--contract-output", str(contract_output), "--openapi-output", str(openapi_output),
            ]
            with mock.patch.object(sys, "argv", arguments), mock.patch.object(
                create_http_api_contract, "assess", return_value=(True, True, [])
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, create_http_api_contract.main())
            metadata = json.loads(contract_output.read_text(encoding="utf-8"))
            self.assertEqual(derived_traceability(openapi()), metadata["traceability"])
            self.assertEqual(openapi(), json.loads(openapi_output.read_text(encoding="utf-8")))
            self.assertFalse((root / "src").exists())

    def test_approval_updates_metadata_and_view_without_changing_openapi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata, design_route, route_path, contract_path = self.fixture(root)
            metadata["approval"] = {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None}
            contract_path.write_text(json.dumps(metadata), encoding="utf-8")
            api_path = root / metadata["artifact"]["path"]
            api_bytes = api_path.read_bytes()
            contract_path.with_suffix(".md").write_text(render(metadata, openapi(), []), encoding="utf-8")
            feature_path = root / "feature.json"
            project_path = root / "project.json"
            profile_path = root / "profile.json"
            feature_path.write_text(json.dumps(feature_spec()), encoding="utf-8")
            project_path.write_text("{}", encoding="utf-8")
            profile_path.write_text(json.dumps(profile()), encoding="utf-8")
            arguments = [
                "record_http_api_contract_approval.py", "--contract", str(contract_path),
                "--route", str(route_path), "--feature", str(feature_path),
                "--project-brief", str(project_path), "--profile", str(profile_path),
                "--target", str(root), "--expected-contract-hash", approval_content_hash(metadata),
                "--expected-openapi-hash", hashlib.sha256(api_bytes).hexdigest(),
                "--approved-by", "test-user", "--approved-at", "2026-09-01T00:00:00Z",
            ]
            with mock.patch.object(sys, "argv", arguments), mock.patch.object(
                record_http_api_contract_approval, "assess", return_value=(True, True, [])
            ), mock.patch.object(
                record_http_api_contract_approval, "verify_inputs", return_value=[]
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, record_http_api_contract_approval.main())
            self.assertEqual("APPROVED", json.loads(contract_path.read_text(encoding="utf-8"))["approval"]["status"])
            self.assertEqual(api_bytes, api_path.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
