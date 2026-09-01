#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from validate_design_contract import validate  # noqa: E402
from validate_feature_specs import approval_content_hash  # noqa: E402
from tests.test_design_route import route  # noqa: E402


class DesignContractTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[dict, dict, Path]:
        design_route = route()
        route_path = root / "docs/features/F001/design-route.json"
        route_path.parent.mkdir(parents=True)
        route_path.write_text(json.dumps(design_route), encoding="utf-8")
        selected = design_route["routes"][0]
        contract = {
            "contractVersion": 1,
            "contractId": selected["contractId"], "kind": selected["kind"], "featureId": "F001",
            "route": {"path": "docs/features/F001/design-route.json", "sha256": hashlib.sha256(route_path.read_bytes()).hexdigest()},
            "disposition": selected["disposition"], "target": copy.deepcopy(selected["target"]),
            "artifact": {"format": "OPENAPI", "path": "docs/features/F001/contracts/http-api/openapi.yaml"},
            "traceability": [{"subjectRef": "registerMember", "requirementRefs": ["AC-001"]}],
            "evidencePaths": [],
            "approval": {"status": "APPROVED", "approvedBy": "test-user", "approvedAt": "2026-09-01T00:00:00Z", "approvedContentSha256": None},
        }
        contract["approval"]["approvedContentSha256"] = approval_content_hash(contract)
        return contract, design_route, route_path

    def test_contract_is_ready_when_it_matches_approved_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, design_route, route_path = self.fixture(root)
            contract_path = root / design_route["routes"][0]["artifactPath"]
            self.assertEqual((True, []), validate(contract, design_route, route_path, root, contract_path))

    def test_route_drift_blocks_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, design_route, route_path = self.fixture(root)
            route_path.write_text("changed", encoding="utf-8")
            self.assertIn("design route changed after contract drafting", validate(
                contract, design_route, route_path, root
            )[1])

    def test_artifact_cannot_escape_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, design_route, route_path = self.fixture(root)
            contract["artifact"]["path"] = "../outside.yaml"
            with self.assertRaisesRegex(ValueError, "artifact.path escapes target"):
                validate(contract, design_route, route_path, root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
