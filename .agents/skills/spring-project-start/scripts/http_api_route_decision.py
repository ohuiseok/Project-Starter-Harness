#!/usr/bin/env python3
"""Prepare, approve, and atomically apply an HTTP API route decision."""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import advance_design_route_draft as advance
from continuation_route import markdown, sanitize
from discover_http_api_evidence import atomic_create, discover, encoded, render as render_discovery
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha, target_path
from validate_feature_specs import load_object


SOURCES = {"RECOMMENDATION_ACCEPTED", "CANDIDATE_SELECTED", "DIRECT_INPUT"}
DISPOSITIONS = {"CREATE", "EXTEND", "REUSE"}
CREATE_REASONS = {"NO_EVIDENCE_FOUND", "USER_REJECTED_CANDIDATES", "USER_REQUESTED_NEW_CONTRACT"}
REPORT_FIELDS = {"httpApiRouteDecisionVersion", "state", "currentRoute", "discovery", "proposal", "output", "selection", "effects"}
APPROVAL_FIELDS = {"httpApiRouteDecisionApprovalVersion", "decision", "view", "approvedBy", "approvedAt", "state"}
APPLICATION_FIELDS = {"httpApiRouteDecisionApplicationVersion", "decision", "approval", "previousRoute", "nextRoute", "nextView", "routeJournal", "state"}


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
        if reason_code == "USER_REJECTED_CANDIDATES" and not report["candidates"]:
            raise ValueError("USER_REJECTED_CANDIDATES requires discovered candidates")
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


def within(path: str, directory: str) -> bool:
    child, parent = PurePosixPath(path), PurePosixPath(directory)
    return directory == "." or child == parent or parent in child.parents


def crosses_nested_git(root: Path, relative: str) -> bool:
    current = (root / PurePosixPath(relative)).parent
    while current != root:
        if (current / ".git").exists(): return True
        current = current.parent
    return False


def build_proposal(route: dict, report: dict, root: Path, discovery_path: Path, contract_id: str, disposition: str, reason: str, candidate: dict | None) -> dict:
    proposed = copy.deepcopy(route)
    if route.get("approval", {}).get("status") == "APPROVED":
        raise ValueError("an approved route cannot be revised")
    http_routes = [item for item in proposed["routes"] if item.get("kind") == "HTTP_API" and item.get("contractId") == contract_id]
    if len(http_routes) != 1:
        raise ValueError("HTTP API contract identity is missing or ambiguous")
    http = http_routes[0]
    module_path = http["target"]["modulePath"]
    if module_path == "UNKNOWN" or not any(within(module_path, scope) for scope in report["scope"]["modules"]):
        raise ValueError("discovery scope does not cover the selected route module")
    candidate_path = candidate["evidence"]["path"] if candidate else None
    if candidate_path and not within(candidate_path, module_path):
        raise ValueError("selected candidate is outside the route module")
    if candidate_path and crosses_nested_git(root, candidate_path):
        raise ValueError("selected candidate crosses a nested Git repository boundary")
    for item in proposed["routes"]:
        if item.get("kind") == "HTTP_API" and item.get("contractId") != contract_id and candidate_path in item.get("evidencePaths", []):
            raise ValueError("selected candidate is already owned by another HTTP API contract")
    evidence_prefix = f"HTTP_API_DISCOVERY:{contract_id}:"
    discovery_relative = discovery_path.relative_to(root).as_posix()
    evidence = [item for item in proposed["inputs"]["codeEvidence"] if not str(item.get("kind", "")).startswith(evidence_prefix) and item.get("path") not in {candidate_path, discovery_relative}]
    discovery_kind = f"{evidence_prefix}{candidate['candidateId'] if candidate else 'CREATE'}"
    evidence.append({"path": discovery_relative, "sha256": sha(discovery_path), "kind": discovery_kind})
    evidence_paths = []
    if candidate:
        evidence.append({"path": candidate_path, "sha256": candidate["evidence"]["sha256"], "kind": "OPENAPI_JSON"})
        evidence_paths = [candidate_path]
    proposed["inputs"]["codeEvidence"] = sorted(evidence, key=lambda item: item["path"])
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
    if selection["recommendedDisposition"] != selection["selectedDisposition"]:
        lines.extend([f"- 시스템 추천과 다름: {selection['recommendedDisposition']} → {selection['selectedDisposition']}", "- 이 차이는 사용자가 직접 선택해야 적용 가능"])
    lines.extend(["", "## 승인 후 변경", "", f"- 새 설계 경로 revision: `{markdown(value['output']['routePath'])}`", f"- 적용 완료 영수증: `{markdown(value['output']['applicationReceiptPath'])}`", "- 선택한 후보와 탐색 보고서의 SHA-256을 계약별 route evidence에 고정", "- 기존 route, OpenAPI, 애플리케이션 소스는 수정하지 않음", "- 이번 승인은 설계 경로 결정만 승인하며 계약 또는 코드를 적용하지 않음", "- revision 생성 중 실패하면 기존 저널 복구 절차로 롤백 가능", "", "## 선택", "", "- 이 결정 승인", "- 다른 후보 선택", "- 다시 탐색", "- 기타 내용을 자연어로 입력", "- 취소", ""])
    return "\n".join(lines)


def validate_report_shape(value: dict) -> None:
    if set(value) != REPORT_FIELDS or value.get("httpApiRouteDecisionVersion") != 1 or value.get("state") != "READY_FOR_APPROVAL":
        raise ValueError("decision report schema or state is invalid")
    selection_fields = {"contractId", "recommendedDisposition", "selectedDisposition", "selectionSource", "reasonCode", "reason", "candidateId", "candidatePath", "candidateSha256"}
    if not isinstance(value.get("selection"), dict) or set(value["selection"]) != selection_fields:
        raise ValueError("decision selection schema is invalid")
    if not isinstance(value.get("output"), dict) or set(value["output"]) != {"routePath", "applicationReceiptPath"}:
        raise ValueError("decision output schema is invalid")


def validate_bound_report(root: Path, value: dict, report_path: Path, view: Path, extra_derived: list[Path] | None = None) -> tuple[Path, Path, Path, Path, dict, dict | None]:
    validate_report_shape(value)
    if view.read_text() != render(value):
        raise ValueError("decision user view is stale")
    current = target_path(root, value["currentRoute"]["path"], "current route"); proposal = target_path(root, value["proposal"]["path"], "route proposal"); discovery_path = target_path(root, value["discovery"]["path"], "discovery report"); discovery_view = target_path(root, value["discovery"]["view"]["path"], "discovery view")
    if reference(current, root) != value["currentRoute"] or reference(proposal, root) != value["proposal"] or reference(discovery_path, root) != {key: value["discovery"][key] for key in ("path", "sha256")} or reference(discovery_view, root) != value["discovery"]["view"]:
        raise ValueError("decision inputs changed")
    derived = [report_path, view, proposal, *(extra_derived or [])]
    current_discovery = revalidate_discovery(root, discovery_path, discovery_view, derived)
    selection = value["selection"]
    candidate, _ = decision(current_discovery, selection["selectedDisposition"], selection["selectionSource"], selection["reasonCode"], selection["reason"], selection["candidateId"])
    if selection["recommendedDisposition"] != current_discovery["summary"]["recommendedDisposition"] or (candidate["evidence"]["path"] if candidate else None) != selection["candidatePath"] or (candidate["evidence"]["sha256"] if candidate else None) != selection["candidateSha256"]:
        raise ValueError("selected candidate or recommendation changed")
    expected = build_proposal(load_object(current), current_discovery, root, discovery_path, selection["contractId"], selection["selectedDisposition"], selection["reason"], candidate)
    if load_object(proposal) != expected:
        raise ValueError("route proposal contains changes outside the approved HTTP API decision")
    return current, proposal, discovery_path, discovery_view, current_discovery, candidate


def prepare(args: argparse.Namespace) -> int:
    written: list[tuple[Path, bytes]] = []
    try:
        root = args.target.resolve(strict=True)
        current = argument_path(root, args.current, "current route"); discovery_path = argument_path(root, args.discovery, "discovery report"); discovery_view = argument_path(root, args.discovery_view, "discovery view")
        proposal = argument_path(root, args.proposal, "route proposal"); output = argument_path(root, args.output, "decision report"); view = argument_path(root, args.view, "decision view")
        future_route = argument_path(root, args.route_output, "future route revision"); receipt = argument_path(root, args.application_receipt, "application receipt")
        if args.target.is_symlink() or view != output.with_suffix(".md") or receipt == future_route.with_suffix(".md") or len({current, discovery_path, discovery_view, proposal, output, view, future_route, receipt}) != 8:
            raise ValueError("target or decision paths are unsafe or duplicated")
        if any(not path.is_file() for path in (current, discovery_path, discovery_view)) or any(path.exists() for path in (proposal, output, view, future_route, future_route.with_suffix('.md'), receipt)):
            raise ValueError("decision inputs are missing or an output already exists")
        report = revalidate_discovery(root, discovery_path, discovery_view)
        candidate, clean_reason = decision(report, args.disposition, args.selection_source, args.reason_code, args.reason, args.candidate_id)
        route = load_object(current); proposed = build_proposal(route, report, root, discovery_path, args.contract_id, args.disposition, clean_reason, candidate)
        proposal_bytes = encoded(proposed)
        value = {"httpApiRouteDecisionVersion": 1, "state": "READY_FOR_APPROVAL", "currentRoute": reference(current, root), "discovery": {**reference(discovery_path, root), "view": reference(discovery_view, root)}, "proposal": {"path": proposal.relative_to(root).as_posix(), "sha256": hashlib.sha256(proposal_bytes).hexdigest()}, "output": {"routePath": future_route.relative_to(root).as_posix(), "applicationReceiptPath": receipt.relative_to(root).as_posix()}, "selection": {"contractId": args.contract_id, "recommendedDisposition": report["summary"]["recommendedDisposition"], "selectedDisposition": args.disposition, "selectionSource": args.selection_source, "reasonCode": args.reason_code, "reason": clean_reason, "candidateId": candidate["candidateId"] if candidate else None, "candidatePath": candidate["evidence"]["path"] if candidate else None, "candidateSha256": candidate["evidence"]["sha256"] if candidate else None}, "effects": {"routeChanged": False, "sourceChanged": False, "openApiChanged": False, "gitCommitOrPush": "NOT_RUN"}}
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
        if not re.fullmatch(r"[a-f0-9]{64}", args.expected_report_hash) or sha(report_path) != args.expected_report_hash or output.exists(): raise ValueError("decision report or view changed after review")
        validate_bound_report(root, value, report_path, view)
        approval = {"httpApiRouteDecisionApprovalVersion": 1, "decision": reference(report_path, root), "view": reference(view, root), "approvedBy": "user", "approvedAt": datetime.now(timezone.utc).isoformat(), "state": "APPROVED"}
        output.parent.mkdir(parents=True, exist_ok=True); atomic_create(encoded(approval), output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"HTTP_API_ROUTE_DECISION_APPROVED: no\nERROR: {error}"); return 1
    print("HTTP_API_ROUTE_DECISION_APPROVED: yes\nROUTE_CHANGED: no"); return 0


def apply(args: argparse.Namespace) -> int:
    prepared_receipt: tuple[Path, bytes] | None = None
    route_committed = False
    route_journal_path: Path | None = None
    try:
        root = args.target.resolve(strict=True); report_path = argument_path(root, args.report, "decision report"); approval_path = argument_path(root, args.approval, "decision approval"); value = load_object(report_path); approval = load_object(approval_path)
        if set(approval) != APPROVAL_FIELDS or approval.get("httpApiRouteDecisionApprovalVersion") != 1 or approval.get("state") != "APPROVED" or approval.get("decision") != reference(report_path, root): raise ValueError("approval does not bind the exact decision report")
        view = target_path(root, approval["view"]["path"], "decision view")
        if reference(view, root) != approval["view"] or view.read_text() != render(value): raise ValueError("approved decision view is stale")
        validate_report_shape(value); receipt = target_path(root, value["output"]["applicationReceiptPath"], "application receipt"); output = target_path(root, value["output"]["routePath"], "route revision")
        current_hint = target_path(root, value["currentRoute"]["path"], "current route"); journal_hint = target_path(root, f".starter-harness/design-route-draft-updates/{sha(current_hint)}.json", "route update journal")
        current, proposal, discovery_path, discovery_view, current_discovery, candidate = validate_bound_report(root, value, report_path, view, [approval_path, receipt, output, output.with_suffix('.md'), journal_hint])
        selection = value["selection"]
        feature = target_path(root, current_discovery["inputs"]["feature"]["path"], "feature"); profile = target_path(root, current_discovery["inputs"]["technologyProfile"]["path"], "profile")
        project = target_path(root, load_object(current)["inputs"]["projectBrief"]["path"], "project brief")
        if receipt.exists(): raise ValueError("application receipt already exists; inspect or recover the prior apply")
        receipt_value = {"httpApiRouteDecisionApplicationVersion": 1, "decision": reference(report_path, root), "approval": reference(approval_path, root), "previousRoute": reference(current, root), "nextRoute": {"path": output.relative_to(root).as_posix(), "sha256": "PENDING"}, "nextView": {"path": output.with_suffix('.md').relative_to(root).as_posix(), "sha256": "PENDING"}, "routeJournal": {"path": f".starter-harness/design-route-draft-updates/{sha(current)}.json", "sha256": "PENDING"}, "state": "PREPARED"}
        route_journal_path = target_path(root, receipt_value["routeJournal"]["path"], "route update journal")
        receipt.parent.mkdir(parents=True, exist_ok=True); prepared_bytes = encoded(receipt_value); atomic_create(prepared_bytes, receipt); prepared_receipt = (receipt, prepared_bytes)
        argv = ["advance", "--current", str(current), "--proposal", str(proposal), "--answer", selection["reason"], "--feature", str(feature), "--project-brief", str(project), "--profile", str(profile), "--target", str(root), "--output", str(output), "--view", str(output.with_suffix('.md'))]
        stream = io.StringIO(); previous_argv = sys.argv
        try:
            sys.argv = argv
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream): code = advance.main()
        finally:
            sys.argv = previous_argv
        if code: raise ValueError("atomic route revision failed: " + stream.getvalue().strip())
        route_committed = True
        journal = route_journal_path
        committed = {**receipt_value, "nextRoute": reference(output, root), "nextView": reference(output.with_suffix('.md'), root), "routeJournal": reference(journal, root), "state": "COMMITTED"}
        atomic_write_bytes(encoded(committed), receipt); prepared_receipt = None
    except (OSError, ValueError, KeyError, TypeError) as error:
        if prepared_receipt and not route_committed and not (route_journal_path and route_journal_path.exists()) and prepared_receipt[0].exists() and prepared_receipt[0].read_bytes() == prepared_receipt[1]: prepared_receipt[0].unlink()
        print(f"HTTP_API_ROUTE_DECISION_APPLIED: no\nERROR: {error}"); return 1
    print("HTTP_API_ROUTE_DECISION_APPLIED: yes\nROUTE_REVISION_STATE: COMMITTED\nSOURCE_CHANGED: no\nOPENAPI_CHANGED: no"); return 0


def recover(args: argparse.Namespace) -> int:
    try:
        root = args.target.resolve(strict=True); receipt = argument_path(root, args.receipt, "application receipt"); value = load_object(receipt)
        if set(value) != APPLICATION_FIELDS or value.get("httpApiRouteDecisionApplicationVersion") != 1 or value.get("state") not in {"PREPARED", "COMMITTED"}:
            raise ValueError("application receipt schema or state is invalid")
        if value["state"] == "COMMITTED":
            for label in ("decision", "approval", "previousRoute", "nextRoute", "nextView", "routeJournal"):
                path = target_path(root, value[label]["path"], label)
                if reference(path, root) != value[label]: raise ValueError(f"committed {label} evidence drifted")
            print("HTTP_API_ROUTE_DECISION_RECOVERED: yes\nAPPLICATION_STATE: COMMITTED\nRECOVERY_ACTION: NONE"); return 0
        original = receipt.read_bytes(); previous = value["previousRoute"]
        previous_path = target_path(root, previous["path"], "previous route")
        if reference(previous_path, root) != previous: raise ValueError("previous route changed; refusing recovery")
        journal = target_path(root, value["routeJournal"]["path"], "route update journal")
        next_route = target_path(root, value["nextRoute"]["path"], "next route"); next_view = target_path(root, value["nextView"]["path"], "next route view")
        if journal.exists():
            journal_value = load_object(journal)
            if journal_value.get("state") == "COMMITTED":
                if reference(next_route, root) != journal_value["next"] or reference(next_view, root) != journal_value["view"]: raise ValueError("committed route journal evidence drifted")
                committed = {**value, "nextRoute": reference(next_route, root), "nextView": reference(next_view, root), "routeJournal": reference(journal, root), "state": "COMMITTED"}
                atomic_write_bytes(encoded(committed), receipt)
                print("HTTP_API_ROUTE_DECISION_RECOVERED: yes\nAPPLICATION_STATE: COMMITTED\nRECOVERY_ACTION: FINALIZED_RECEIPT"); return 0
            if journal_value.get("state") != "PREPARED": raise ValueError("route journal state is not recoverable")
            argv = ["recover", "--previous-hash", previous["sha256"], "--target", str(root)]; stream = io.StringIO(); previous_argv = sys.argv
            try:
                sys.argv = argv
                import recover_design_route_draft_update as route_recovery
                with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream): code = route_recovery.main()
            finally: sys.argv = previous_argv
            if code: raise ValueError("route recovery failed: " + stream.getvalue().strip())
        elif next_route.exists() or next_view.exists():
            raise ValueError("route artifacts exist without a journal; refusing recovery")
        if receipt.read_bytes() != original: raise ValueError("application receipt changed during recovery")
        receipt.unlink()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"HTTP_API_ROUTE_DECISION_RECOVERED: no\nERROR: {error}"); return 1
    print("HTTP_API_ROUTE_DECISION_RECOVERED: yes\nAPPLICATION_STATE: ROLLED_BACK\nRECOVERY_ACTION: REMOVED_PREPARED_RECEIPT"); return 0


def status(args: argparse.Namespace) -> int:
    try:
        root = args.target.resolve(strict=True); report_path = argument_path(root, args.report, "decision report"); value = load_object(report_path); validate_report_shape(value)
        receipt = target_path(root, value["output"]["applicationReceiptPath"], "application receipt")
        approval_exists = False
        if args.approval:
            approval_path = argument_path(root, args.approval, "decision approval")
            if approval_path.exists():
                approval = load_object(approval_path)
                approval_exists = set(approval) == APPROVAL_FIELDS and approval.get("state") == "APPROVED" and approval.get("decision") == reference(report_path, root)
        if receipt.exists():
            application = load_object(receipt); state = application.get("state")
            if set(application) != APPLICATION_FIELDS or state not in {"PREPARED", "COMMITTED"}: raise ValueError("application receipt is invalid")
            if state == "COMMITTED":
                for label in ("decision", "approval", "previousRoute", "nextRoute", "nextView", "routeJournal"):
                    path = target_path(root, application[label]["path"], label)
                    if reference(path, root) != application[label]: raise ValueError(f"committed {label} evidence drifted")
            status_value = "RECOVERY_REQUIRED" if state == "PREPARED" else "COMMITTED"
            action = "복구 후 다시 상태 확인" if state == "PREPARED" else "다음 계약 설계 단계로 진행"
        elif approval_exists:
            status_value, action = "APPROVED_NOT_APPLIED", "승인된 결정을 적용"
        else:
            status_value, action = "WAITING_FOR_APPROVAL", "결정 미리보기를 검토하고 승인 또는 수정"
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"HTTP_API_ROUTE_DECISION_STATUS_VALID: no\nERROR: {error}"); return 1
    print(f"HTTP_API_ROUTE_DECISION_STATUS_VALID: yes\nDECISION_STATUS: {status_value}\nNEXT_ACTION: {action}"); return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(); commands = value.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    for name in ("current", "discovery", "discovery-view", "proposal", "output", "view", "route-output", "application-receipt"): prepare_parser.add_argument(f"--{name}", required=True, type=Path)
    prepare_parser.add_argument("--target", required=True, type=Path); prepare_parser.add_argument("--contract-id", required=True); prepare_parser.add_argument("--disposition", required=True); prepare_parser.add_argument("--selection-source", required=True); prepare_parser.add_argument("--reason-code", required=True); prepare_parser.add_argument("--reason", required=True); prepare_parser.add_argument("--candidate-id")
    approve_parser = commands.add_parser("approve")
    for name in ("report", "view", "output", "target"): approve_parser.add_argument(f"--{name}", required=True, type=Path)
    approve_parser.add_argument("--expected-report-hash", required=True)
    apply_parser = commands.add_parser("apply")
    for name in ("report", "approval", "target"): apply_parser.add_argument(f"--{name}", required=True, type=Path)
    recover_parser = commands.add_parser("recover")
    for name in ("receipt", "target"): recover_parser.add_argument(f"--{name}", required=True, type=Path)
    status_parser = commands.add_parser("status"); status_parser.add_argument("--report", required=True, type=Path); status_parser.add_argument("--approval", type=Path); status_parser.add_argument("--target", required=True, type=Path)
    return value


def main() -> int:
    args = parser().parse_args()
    return {"prepare": prepare, "approve": approve, "apply": apply, "recover": recover, "status": status}[args.command](args)


if __name__ == "__main__": sys.exit(main())
