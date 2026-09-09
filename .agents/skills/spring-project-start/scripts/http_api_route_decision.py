#!/usr/bin/env python3
"""Prepare, approve, and atomically apply an HTTP API route decision."""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import advance_design_route_draft as advance
from continuation_route import markdown, sanitize
from discover_http_api_evidence import atomic_create, discover, encoded, render as render_discovery
from spring_milestone_completion import sha, target_path
from validate_feature_specs import load_object


SOURCES = {"RECOMMENDATION_ACCEPTED", "CANDIDATE_SELECTED", "DIRECT_INPUT"}
DISPOSITIONS = {"CREATE", "EXTEND", "REUSE"}
CREATE_REASONS = {"NO_EVIDENCE_FOUND", "USER_REJECTED_CANDIDATES", "USER_REQUESTED_NEW_CONTRACT"}


def argument_path(root: Path, value: Path, label: str) -> Path:
    try:
        relative = value.absolute().relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError(f"{label} must be inside the target") from error
    return target_path(root, relative, label)


def reference(path: Path, root: Path) -> dict:
    return {"path": path.relative_to(root).as_posix(), "sha256": sha(path)}


def revalidate_discovery(root: Path, report_path: Path, view_path: Path, derived_paths: list[Path] | None = None) -> dict:
    saved = load_object(report_path)
    if saved.get("httpApiEvidenceDiscoveryVersion") != 1 or saved.get("target") != str(root):
        raise ValueError("discovery report identity is invalid")
    scope = saved["scope"]
    feature = target_path(root, saved["inputs"]["feature"]["path"], "feature")
    profile = target_path(root, saved["inputs"]["technologyProfile"]["path"], "technology profile")
    original_exclusions = scope["excludedPaths"]
    exclusions = list(original_exclusions)
    for path in derived_paths or []:
        relative = path.relative_to(root).as_posix()
        if relative not in exclusions: exclusions.append(relative)
    expected = discover(root, feature, profile, scope["modules"], scope["maxFiles"], scope["maxFileBytes"], scope["maxTotalBytes"], exclusions)
    expected["scope"]["excludedPaths"] = original_exclusions
    if saved != expected or not view_path.is_file() or view_path.read_text() != render_discovery(saved):
        raise ValueError("discovery report, evidence, or user view is stale")
    return saved


def selected_candidate(report: dict, candidate_id: str | None) -> dict | None:
    if candidate_id is None:
        return None
    matches = [item for item in report["candidates"] if item["candidateId"] == candidate_id]
    if len(matches) != 1:
        raise ValueError("selected candidate does not exist uniquely")
    return matches[0]


def decision(report: dict, disposition: str, source: str, reason_code: str, reason: str, candidate_id: str | None) -> tuple[dict | None, str]:
    if disposition not in DISPOSITIONS or source not in SOURCES:
        raise ValueError("disposition or selection source is unsupported")
    clean_reason = sanitize(reason)
    if clean_reason != reason.strip():
        raise ValueError("selection reason must already be PII-minimized")
    candidate = selected_candidate(report, candidate_id)
    if source == "CANDIDATE_SELECTED" and candidate is None:
        raise ValueError("CANDIDATE_SELECTED requires a candidate")
    if source != "CANDIDATE_SELECTED" and candidate is not None and source != "RECOMMENDATION_ACCEPTED":
        raise ValueError("an explicit candidate must use CANDIDATE_SELECTED")
    if source == "RECOMMENDATION_ACCEPTED":
        if report["summary"]["recommendedDisposition"] == "UNKNOWN" or disposition != report["summary"]["recommendedDisposition"]:
            raise ValueError("an ambiguous or different recommendation cannot be accepted automatically")
        if disposition in {"EXTEND", "REUSE"} and (candidate is None or candidate["recommendedDisposition"] != disposition):
            raise ValueError("recommendation acceptance requires its exact candidate")
    if disposition == "CREATE":
        if candidate is not None or reason_code not in CREATE_REASONS:
            raise ValueError("CREATE requires no candidate and an explicit creation reason")
        if reason_code == "NO_EVIDENCE_FOUND" and report["candidates"]:
            raise ValueError("NO_EVIDENCE_FOUND is false while candidates exist")
        if source == "RECOMMENDATION_ACCEPTED" and reason_code != "NO_EVIDENCE_FOUND":
            raise ValueError("recommended CREATE must be based on no discovered evidence")
    else:
        if reason_code != "EXISTING_CONTRACT_SELECTED" or candidate is None:
            raise ValueError("EXTEND or REUSE requires an explicit existing candidate")
        if candidate["kind"] != "OPENAPI_JSON" or candidate["evidence"]["stability"] != "STABLE" or candidate["discovery"]["parseState"] != "PARSED":
            raise ValueError("selected candidate is not a stable validated OpenAPI JSON contract")
        if disposition == "REUSE" and candidate["recommendedDisposition"] != "REUSE":
            raise ValueError("candidate does not prove complete REUSE eligibility")
        if disposition == "EXTEND" and candidate["recommendedDisposition"] not in {"EXTEND", "REUSE"}:
            raise ValueError("candidate is not eligible for extension")
    return candidate, clean_reason


def build_proposal(route: dict, root: Path, discovery_path: Path, contract_id: str, disposition: str, reason: str, candidate: dict | None) -> dict:
    proposed = copy.deepcopy(route)
    if route.get("approval", {}).get("status") == "APPROVED":
        raise ValueError("an approved route cannot be revised")
    http_routes = [item for item in proposed["routes"] if item.get("kind") == "HTTP_API" and item.get("contractId") == contract_id]
    if len(http_routes) != 1:
        raise ValueError("HTTP API contract identity is missing or ambiguous")
    candidate_path = candidate["evidence"]["path"] if candidate else None
    evidence = [item for item in proposed["inputs"]["codeEvidence"] if not str(item.get("kind", "")).startswith("HTTP_API_DISCOVERY:") and item.get("path") != candidate_path]
    discovery_kind = f"HTTP_API_DISCOVERY:{candidate['candidateId'] if candidate else 'CREATE'}"
    evidence.append({"path": discovery_path.relative_to(root).as_posix(), "sha256": sha(discovery_path), "kind": discovery_kind})
    evidence_paths = []
    if candidate:
        evidence.append({"path": candidate_path, "sha256": candidate["evidence"]["sha256"], "kind": "OPENAPI_JSON"})
        evidence_paths = [candidate_path]
    proposed["inputs"]["codeEvidence"] = sorted(evidence, key=lambda item: item["path"])
    http = http_routes[0]
    http.update({"disposition": disposition, "evidencePaths": evidence_paths, "reason": reason, "source": "USER_STATED", "confirmedByUser": True})
    if not http.get("artifactPath"):
        raise ValueError("HTTP API metadata artifact path is missing")
    proposed["approval"] = {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None}
    return proposed


def render(value: dict) -> str:
    selection = value["selection"]
    lines = ["# HTTP API 설계 경로 결정 미리보기", "", f"- 선택: {selection['selectedDisposition']}", f"- 선택 출처: {selection['selectionSource']}", f"- 사유: {markdown(selection['reason'])}"]
    if selection["candidateId"]:
        lines.extend([f"- 후보: {selection['candidateId']}", f"- 기존 계약: `{markdown(selection['candidatePath'])}`"])
    lines.extend(["", "## 승인 후 변경", "", f"- 새 설계 경로 revision: `{markdown(value['output']['routePath'])}`", "- 선택한 후보와 탐색 보고서의 SHA-256을 route evidence에 고정", "- 기존 route, OpenAPI, 애플리케이션 소스는 수정하지 않음", "- revision 생성 중 실패하면 기존 저널 복구 절차로 롤백 가능", "", "## 선택", "", "- 이 결정 승인", "- 다른 후보 선택", "- 다시 탐색", "- 기타 내용을 자연어로 입력", "- 취소", ""])
    return "\n".join(lines)


def prepare(args: argparse.Namespace) -> int:
    written: list[tuple[Path, bytes]] = []
    try:
        root = args.target.resolve(strict=True)
        current = argument_path(root, args.current, "current route"); discovery_path = argument_path(root, args.discovery, "discovery report"); discovery_view = argument_path(root, args.discovery_view, "discovery view")
        proposal = argument_path(root, args.proposal, "route proposal"); output = argument_path(root, args.output, "decision report"); view = argument_path(root, args.view, "decision view")
        future_route = argument_path(root, args.route_output, "future route revision")
        if args.target.is_symlink() or view != output.with_suffix(".md") or len({current, discovery_path, discovery_view, proposal, output, view, future_route}) != 7:
            raise ValueError("target or decision paths are unsafe or duplicated")
        if any(not path.is_file() for path in (current, discovery_path, discovery_view)) or any(path.exists() for path in (proposal, output, view, future_route, future_route.with_suffix('.md'))):
            raise ValueError("decision inputs are missing or an output already exists")
        report = revalidate_discovery(root, discovery_path, discovery_view)
        candidate, clean_reason = decision(report, args.disposition, args.selection_source, args.reason_code, args.reason, args.candidate_id)
        route = load_object(current); proposed = build_proposal(route, root, discovery_path, args.contract_id, args.disposition, clean_reason, candidate)
        proposal_bytes = encoded(proposed)
        value = {"httpApiRouteDecisionVersion": 1, "state": "READY_FOR_APPROVAL", "currentRoute": reference(current, root), "discovery": {**reference(discovery_path, root), "view": reference(discovery_view, root)}, "proposal": {"path": proposal.relative_to(root).as_posix(), "sha256": hashlib.sha256(proposal_bytes).hexdigest()}, "output": {"routePath": future_route.relative_to(root).as_posix()}, "selection": {"contractId": args.contract_id, "recommendedDisposition": report["summary"]["recommendedDisposition"], "selectedDisposition": args.disposition, "selectionSource": args.selection_source, "reasonCode": args.reason_code, "reason": clean_reason, "candidateId": candidate["candidateId"] if candidate else None, "candidatePath": candidate["evidence"]["path"] if candidate else None, "candidateSha256": candidate["evidence"]["sha256"] if candidate else None}, "effects": {"routeChanged": False, "sourceChanged": False, "openApiChanged": False, "gitCommitOrPush": "NOT_RUN"}}
        output_bytes = encoded(value); view_bytes = render(value).encode()
        output.parent.mkdir(parents=True, exist_ok=True)
        for path, payload in ((proposal, proposal_bytes), (output, output_bytes), (view, view_bytes)):
            atomic_create(payload, path); written.append((path, payload))
    except (OSError, ValueError, KeyError, TypeError) as error:
        for path, payload in reversed(written):
            if path.exists() and path.read_bytes() == payload: path.unlink()
        print(f"HTTP_API_ROUTE_DECISION_VALID: no\nERROR: {error}"); return 1
    print("HTTP_API_ROUTE_DECISION_VALID: yes\nROUTE_CHANGED: no\nREADY_FOR_APPROVAL: yes"); return 0


def approve(args: argparse.Namespace) -> int:
    try:
        root = args.target.resolve(strict=True); report_path = argument_path(root, args.report, "decision report"); view = argument_path(root, args.view, "decision view"); output = argument_path(root, args.output, "decision approval")
        value = load_object(report_path)
        if value.get("state") != "READY_FOR_APPROVAL" or sha(report_path) != args.expected_report_hash or view.read_text() != render(value) or output.exists(): raise ValueError("decision report or view changed after review")
        approval = {"httpApiRouteDecisionApprovalVersion": 1, "decision": reference(report_path, root), "view": reference(view, root), "approvedBy": "user", "approvedAt": datetime.now(timezone.utc).isoformat(), "state": "APPROVED"}
        output.parent.mkdir(parents=True, exist_ok=True); atomic_create(encoded(approval), output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"HTTP_API_ROUTE_DECISION_APPROVED: no\nERROR: {error}"); return 1
    print("HTTP_API_ROUTE_DECISION_APPROVED: yes\nROUTE_CHANGED: no"); return 0


def apply(args: argparse.Namespace) -> int:
    try:
        root = args.target.resolve(strict=True); report_path = argument_path(root, args.report, "decision report"); approval_path = argument_path(root, args.approval, "decision approval"); value = load_object(report_path); approval = load_object(approval_path)
        if approval.get("state") != "APPROVED" or approval.get("decision") != reference(report_path, root): raise ValueError("approval does not bind the exact decision report")
        view = target_path(root, approval["view"]["path"], "decision view")
        if reference(view, root) != approval["view"] or view.read_text() != render(value): raise ValueError("approved decision view is stale")
        current = target_path(root, value["currentRoute"]["path"], "current route"); proposal = target_path(root, value["proposal"]["path"], "route proposal"); discovery_path = target_path(root, value["discovery"]["path"], "discovery report"); discovery_view = target_path(root, value["discovery"]["view"]["path"], "discovery view")
        if reference(current, root) != value["currentRoute"] or reference(proposal, root) != value["proposal"] or reference(discovery_path, root) != {key: value["discovery"][key] for key in ("path", "sha256")} or reference(discovery_view, root) != value["discovery"]["view"]: raise ValueError("decision inputs changed before apply")
        derived = [report_path, view, approval_path, proposal]
        current_discovery = revalidate_discovery(root, discovery_path, discovery_view, derived)
        selection = value["selection"]; candidate, _ = decision(current_discovery, selection["selectedDisposition"], selection["selectionSource"], selection["reasonCode"], selection["reason"], selection["candidateId"])
        if selection["recommendedDisposition"] != current_discovery["summary"]["recommendedDisposition"] or (candidate["evidence"]["path"] if candidate else None) != selection["candidatePath"] or (candidate["evidence"]["sha256"] if candidate else None) != selection["candidateSha256"]: raise ValueError("selected candidate or recommendation changed before apply")
        expected_proposal = build_proposal(load_object(current), root, discovery_path, selection["contractId"], selection["selectedDisposition"], selection["reason"], candidate)
        if load_object(proposal) != expected_proposal: raise ValueError("route proposal contains changes outside the approved HTTP API decision")
        output = target_path(root, value["output"]["routePath"], "route revision"); feature = target_path(root, current_discovery["inputs"]["feature"]["path"], "feature"); profile = target_path(root, current_discovery["inputs"]["technologyProfile"]["path"], "profile")
        project = target_path(root, load_object(current)["inputs"]["projectBrief"]["path"], "project brief")
        argv = ["advance", "--current", str(current), "--proposal", str(proposal), "--answer", selection["reason"], "--feature", str(feature), "--project-brief", str(project), "--profile", str(profile), "--target", str(root), "--output", str(output), "--view", str(output.with_suffix('.md'))]
        stream = io.StringIO(); previous_argv = sys.argv
        try:
            sys.argv = argv
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream): code = advance.main()
        finally:
            sys.argv = previous_argv
        if code: raise ValueError("atomic route revision failed: " + stream.getvalue().strip())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"HTTP_API_ROUTE_DECISION_APPLIED: no\nERROR: {error}"); return 1
    print("HTTP_API_ROUTE_DECISION_APPLIED: yes\nROUTE_REVISION_STATE: COMMITTED\nSOURCE_CHANGED: no\nOPENAPI_CHANGED: no"); return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(); commands = value.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    for name in ("current", "discovery", "discovery-view", "proposal", "output", "view", "route-output"): prepare_parser.add_argument(f"--{name}", required=True, type=Path)
    prepare_parser.add_argument("--target", required=True, type=Path); prepare_parser.add_argument("--contract-id", required=True); prepare_parser.add_argument("--disposition", required=True); prepare_parser.add_argument("--selection-source", required=True); prepare_parser.add_argument("--reason-code", required=True); prepare_parser.add_argument("--reason", required=True); prepare_parser.add_argument("--candidate-id")
    approve_parser = commands.add_parser("approve")
    for name in ("report", "view", "output", "target"): approve_parser.add_argument(f"--{name}", required=True, type=Path)
    approve_parser.add_argument("--expected-report-hash", required=True)
    apply_parser = commands.add_parser("apply")
    for name in ("report", "approval", "target"): apply_parser.add_argument(f"--{name}", required=True, type=Path)
    return value


def main() -> int:
    args = parser().parse_args()
    return {"prepare": prepare, "approve": approve, "apply": apply}[args.command](args)


if __name__ == "__main__": sys.exit(main())
