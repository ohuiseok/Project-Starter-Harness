#!/usr/bin/env python3
"""Pure rendering and exact validation for the HTTP API contract apply pipeline."""
from __future__ import annotations
import hashlib
from pathlib import Path

from existing_http_api_contract import compare_openapi
from http_api_contract import derived_traceability, encoded, operations, validate_openapi
from prepare_http_api_contract_handoff import reference
from validate_feature_specs import load_object


def current_handoff(root: Path, handoff_path: Path, view_path: Path, derived_paths: list[Path] | None = None) -> dict:
    from validate_http_api_contract_handoff import validate_saved
    return validate_saved(root, handoff_path, view_path, derived_paths)


def render_artifacts(root: Path, handoff: dict, source_path: Path | None) -> tuple[dict[str, bytes], dict]:
    disposition = handoff["disposition"]; outputs = handoff["expectedOutputs"]
    feature = load_object(root / handoff["inputs"]["feature"]["path"])
    profile = load_object(root / handoff["inputs"]["technologyProfile"]["path"])
    route_ref = handoff["inputs"]["approvedRoute"]
    blockers: list[str] = []
    source = None; source_ref = None; baseline = None
    selected_ids = set((handoff.get("operationSelection") or {}).get("selectedOperationIds", []))
    if disposition == "CREATE":
        if source_path is None: raise ValueError("CREATE requires --openapi-source")
        source = load_object(source_path); source_ref = reference(source_path, root)
    else:
        baseline_path = root / handoff["baseline"]["path"]
        baseline = load_object(baseline_path)
        if disposition == "EXTEND":
            if source_path is None: raise ValueError("EXTEND requires --openapi-source")
            source = load_object(source_path); source_ref = reference(source_path, root)
        else:
            if source_path is not None: raise ValueError("REUSE does not accept --openapi-source")
            source = baseline
    traceability = [item for item in derived_traceability(source) if not selected_ids or item["subjectRef"] in selected_ids]
    blockers += validate_openapi(source, feature, profile, {"traceability": traceability}, selected_ids if selected_ids else None)
    artifact_path = outputs["openApi"] if disposition != "REUSE" else handoff["baseline"]["path"]
    route = load_object(root / route_ref["path"])
    selected_route = next(item for item in route["routes"] if item.get("contractId") == handoff["contractId"])
    metadata = {
        "contractVersion": 1, "contractId": handoff["contractId"], "kind": "HTTP_API",
        "featureId": route["featureId"], "route": route_ref,
        "disposition": disposition, "target": handoff["target"],
        "artifact": {"format": "OPENAPI", "path": artifact_path},
        "traceability": traceability, "evidencePaths": selected_route.get("evidencePaths", []),
        "approval": {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None},
    }
    writes: dict[str, bytes] = {}
    if disposition in {"EXTEND", "REUSE"}:
        baseline_path = root / handoff["baseline"]["path"]
        report = compare_openapi(baseline, source, handoff["contractId"], selected_ids if disposition == "REUSE" else None)
        report_bytes = encoded(report); writes[outputs["comparison"]] = report_bytes
        metadata["baselineArtifact"] = {"format": "OPENAPI", **handoff["baseline"]}
        metadata["comparison"] = {"path": outputs["comparison"], "sha256": hashlib.sha256(report_bytes).hexdigest()}
        metadata["selectedOperations"] = sorted(selected_ids)
        reviews = [item for item in report["changes"] if item["level"] == "REVIEW"]
        metadata["compatibilityReviews"] = [{"reviewId": f"{i['code']}:{i['location']}", "status": "PENDING", "reason": "UNKNOWN", "source": "UNKNOWN", "confirmedByUser": False} for i in reviews]
        blockers += [f"compatibility {item['level']}: {item['code']} at {item['location']}" for item in report["changes"] if item["level"] in {"BREAKING", "SECURITY", "UNKNOWN", "REVIEW"}]
    if disposition in {"CREATE", "EXTEND"}: writes[outputs["openApi"]] = encoded(source)
    writes[outputs["metadata"]] = encoded(metadata)
    return writes, {"source": source_ref, "blockers": sorted(set(blockers))}
