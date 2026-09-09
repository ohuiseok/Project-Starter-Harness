#!/usr/bin/env python3
"""Create an immutable disposition-specific handoff from an approved HTTP API route."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from discover_http_api_evidence import atomic_create, encoded
from existing_http_api_contract import scoped_external_references
from http_api_contract import operations
from http_api_route_decision import APPLICATION_FIELDS, APPROVAL_FIELDS, committed_route_transition_is_current, reference, revalidate_discovery
from continuation_route import markdown
from spring_milestone_completion import sha, target_path
from validate_design_route import assess
from validate_feature_specs import load_object


def argument_path(root: Path, value: Path, label: str) -> Path:
    try: relative = value.absolute().relative_to(root).as_posix()
    except ValueError as error: raise ValueError(f"{label} must be inside the target") from error
    return target_path(root, relative, label)


def local_pointer(document: dict, ref: str):
    current = document
    for raw in ref[2:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or key not in current: raise ValueError(f"unresolved local reference: {ref}")
        current = current[key]
    return current


def operation_scope(document: dict, selected_ids: set[str]) -> dict:
    selected = []; operation_documents = {}; local: dict[str, object] = {}; external: set[str] = set(); visiting: set[str] = set()
    def visit(value):
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str):
                if not ref.startswith("#/"): external.add(ref)
                elif ref not in visiting:
                    visiting.add(ref); resolved = local_pointer(document, ref); local[ref] = resolved; visit(resolved)
            for key, child in value.items():
                if key != "$ref": visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    for path, method, operation in operations(document):
        operation_id = operation.get("operationId")
        if operation_id not in selected_ids: continue
        refs = operation.get("x-harness-requirement-refs", [])
        selected.append({"operationId": operation_id, "method": method.upper(), "path": path, "requirementRefs": sorted(refs) if isinstance(refs, list) else []})
        path_item = document.get("paths", {}).get(path, {}); path_parameters = path_item.get("parameters", []); effective_security = operation.get("security", document.get("security", [])); effective_servers = operation.get("servers", path_item.get("servers", document.get("servers", [])))
        operation_documents[operation_id] = {"method": method.upper(), "path": path, "operation": operation, "pathParameters": path_parameters, "effectiveSecurity": effective_security, "effectiveServers": effective_servers}
        visit(operation); visit(path_parameters)
        security = effective_security
        definitions = document.get("components", {}).get("securitySchemes", {})
        if isinstance(security, list) and isinstance(definitions, dict):
            for requirement in security:
                if isinstance(requirement, dict):
                    for name in requirement:
                        if name in definitions: local[f"#/components/securitySchemes/{name}"] = definitions[name]; visit(definitions[name])
    selected.sort(key=lambda item: item["operationId"])
    normalized = {"operations": selected, "operationDocuments": {key: operation_documents[key] for key in sorted(operation_documents)}, "reachableLocalComponents": {key: local[key] for key in sorted(local)}}
    return {**normalized, "localRefs": sorted(local), "externalRefs": sorted(external | scoped_external_references(document, selected_ids)), "snapshotSha256": hashlib.sha256(encoded(normalized)).hexdigest()}


def expected_outputs(selected: dict) -> dict:
    metadata = selected["artifactPath"]; parent = str(Path(metadata).parent).replace("\\", "/")
    disposition = selected["disposition"]
    if disposition == "CREATE":
        return {"metadata": metadata, "openApi": f"{parent}/openapi.json", "comparison": None, "adapter": "CREATE_HTTP_API_CONTRACT", "requiredInput": "AGENT_PREPARED_OPENAPI"}
    if disposition == "EXTEND":
        return {"metadata": metadata, "openApi": f"{parent}/proposed-openapi.json", "comparison": f"{parent}/compatibility.json", "adapter": "EXTEND_EXISTING_HTTP_API_CONTRACT", "requiredInput": "AGENT_PREPARED_PROPOSED_OPENAPI"}
    return {"metadata": metadata, "openApi": None, "comparison": f"{parent}/compatibility.json", "adapter": "REUSE_EXISTING_HTTP_API_CONTRACT", "requiredInput": None}


def route_descends_from_application(root: Path, route_path: Path, application: dict) -> bool:
    if not committed_route_transition_is_current(root, application): return False
    target = application["nextRoute"]; current_path = route_path; visited = set()
    for _ in range(1000):
        relative = current_path.relative_to(root).as_posix()
        if relative in visited: return False
        visited.add(relative)
        if relative == target["path"]:
            return sha(current_path) == target["sha256"] or committed_route_transition_is_current(root, application)
        current = load_object(current_path); previous = current.get("revision", {}).get("previous")
        if not isinstance(previous, dict) or set(previous) != {"path", "sha256"}: return False
        previous_path = target_path(root, previous["path"], "previous route revision")
        if not previous_path.is_file() or sha(previous_path) != previous["sha256"]: return False
        current_path = previous_path
    return False


def render(value: dict) -> str:
    lines = ["# HTTP API 계약 준비", "", f"- 계약: {value['contractId']}", f"- 방식: {value['disposition']}", f"- 상태: {value['status']}", f"- 대상: {value['target']['projectId']} · `{markdown(value['target']['modulePath'])}`", ""]
    if value["disposition"] == "CREATE": lines.extend(["## 수행할 작업", "", "- 승인된 기능으로 새 OpenAPI 초안과 계약 metadata 준비", "- 기존 OpenAPI는 변경하지 않음", ""])
    elif value["disposition"] == "EXTEND": lines.extend(["## 수행할 작업", "", f"- 기준 계약: `{markdown(value['baseline']['path'])}`", "- 별도 제안 OpenAPI와 전체 호환성 보고서 준비", "- 기준 OpenAPI는 변경하지 않음", ""])
    else: lines.extend(["## 수행할 작업", "", f"- 그대로 사용할 계약: `{markdown(value['baseline']['path'])}`", "- 새 OpenAPI 없이 선택 operation의 metadata와 검증 보고서만 준비", "- 기존 OpenAPI는 변경하지 않음", ""])
    scope = value.get("operationScope")
    if scope:
        selection=value.get("operationSelection") or {}
        source_labels={"RECOMMENDATION_ACCEPTED":"추천 범위 확인","USER_CONFIRMED":"사용자 직접 선택"}
        lines.extend(["## 선택 근거", "", f"- 선택 방식: {source_labels.get(selection.get('source'), selection.get('source','UNKNOWN'))}", f"- 추천: {', '.join(selection.get('suggestedOperationIds',[]))}", f"- 최종 선택: {', '.join(selection.get('selectedOperationIds',[]))}", ""])
        lines.extend(["## 선택한 API", ""])
        for item in scope["operations"]: lines.append(f"- {item['method']} `{markdown(item['path'])}` · {markdown(item['operationId'])}")
        lines.extend(["", f"- 외부 참조: {len(scope['externalRefs'])}개", ""])
    lines.extend(["## 예상 산출물", "", f"- metadata: `{markdown(value['expectedOutputs']['metadata'])}`"])
    for label in ("openApi", "comparison"):
        if value["expectedOutputs"][label]: lines.append(f"- {label}: `{markdown(value['expectedOutputs'][label])}`")
    if value["blockers"]:
        lines.extend(["", "## 먼저 해결할 항목", ""]); lines.extend(f"- {markdown(item)}" for item in value["blockers"])
    else:
        next_action={"READY_FOR_CREATE_SOURCE":"새 OpenAPI 초안을 준비한 뒤 dry-run 검토","READY_FOR_EXTENSION_PROPOSAL":"제안 OpenAPI를 준비한 뒤 호환성 dry-run 검토","READY_FOR_REUSE_DRY_RUN":"선택한 operation 범위의 dry-run 검토"}.get(value["status"],"상태 확인")
        lines.extend(["", "## 다음 한 단계", "", f"- {next_action}"])
    lines.extend(["", "이 handoff는 계약 adapter를 실행하거나 계약·소스·기존 OpenAPI를 변경하지 않습니다.", ""])
    return "\n".join(lines)


def build(root: Path, application_path: Path, route_path: Path, feature_path: Path, project_path: Path, profile_path: Path, contract_id: str, handoff_paths: list[Path] | None = None, selected_operation_ids: list[str] | None = None, operation_selection_source: str | None = None) -> dict:
    application = load_object(application_path)
    if set(application) != APPLICATION_FIELDS or application.get("httpApiRouteDecisionApplicationVersion") != 1 or application.get("state") != "COMMITTED": raise ValueError("a committed HTTP API route application receipt is required")
    for label in ("decision", "approval", "previousRoute", "routeJournal"):
        path = target_path(root, application[label]["path"], label)
        if reference(path, root) != application[label]: raise ValueError(f"application {label} evidence is stale")
    if not route_descends_from_application(root, route_path, application): raise ValueError("approved route is not the applied route transition or its verified descendant")
    decision_path = target_path(root, application["decision"]["path"], "route decision"); approval_path = target_path(root, application["approval"]["path"], "route decision approval"); decision = load_object(decision_path); decision_approval = load_object(approval_path); journal = load_object(target_path(root, application["routeJournal"]["path"], "route journal"))
    if set(decision_approval) != APPROVAL_FIELDS or decision_approval.get("state") != "APPROVED" or decision_approval.get("decision") != reference(decision_path, root): raise ValueError("route decision approval lineage is invalid")
    if journal.get("state") != "COMMITTED" or journal.get("previous") != application["previousRoute"] or journal.get("next") != application["nextRoute"] or journal.get("view") != application["nextView"]: raise ValueError("route application journal lineage is invalid")
    route, feature, project, profile = map(load_object, (route_path, feature_path, project_path, profile_path))
    approved, profile_ready, blockers = assess(route, feature, project, profile, feature_path, project_path, profile_path, root)
    if not approved or not profile_ready or blockers: raise ValueError("design route is not approved and current: " + "; ".join(blockers))
    child = target_path(root, f".starter-harness/design-route-draft-updates/{sha(route_path)}.json", "route child journal")
    if child.exists(): raise ValueError("approved route has a newer or interrupted child revision")
    matches = [item for item in route["routes"] if item.get("kind") == "HTTP_API" and item.get("contractId") == contract_id]
    if len(matches) != 1 or matches[0]["disposition"] not in {"CREATE", "EXTEND", "REUSE"}: raise ValueError("contract-id must select one active HTTP API route")
    selected = matches[0]
    if decision.get("selection", {}).get("contractId") != contract_id or decision["selection"].get("selectedDisposition") != selected["disposition"]: raise ValueError("application decision does not match the selected route contract")
    outputs = expected_outputs(selected); semantic_blockers = []
    for path in [value for key, value in outputs.items() if key in {"metadata", "openApi", "comparison"} and value]:
        if target_path(root, path, "expected contract output").exists(): semantic_blockers.append(f"expected output already exists: {path}")
    baseline = None; scope = None; operation_selection = None; discovery_refs = [item for item in route["inputs"]["codeEvidence"] if item["kind"].startswith(f"HTTP_API_DISCOVERY:{contract_id}:")]
    if len(discovery_refs) != 1: raise ValueError("contract-scoped discovery evidence is missing or ambiguous")
    discovery_ref = discovery_refs[0]
    discovery_path = target_path(root, discovery_ref["path"], "discovery evidence")
    if not discovery_path.is_file() or sha(discovery_path) != discovery_ref["sha256"]: raise ValueError("discovery evidence is stale")
    discovery = load_object(discovery_path)
    discovery_view = discovery_path.with_suffix(".md"); proposal_path = target_path(root, decision["proposal"]["path"], "route proposal")
    derived = [application_path, route_path, route_path.with_suffix(".md"), decision_path, target_path(root, decision_approval["view"]["path"], "decision view"), approval_path, proposal_path, target_path(root, application["routeJournal"]["path"], "route journal"), *(handoff_paths or [])]
    derived.extend(target_path(root,item,"expected contract output") for key,item in outputs.items() if key in {"metadata","openApi","comparison"} and item)
    revalidate_discovery(root, discovery_path, discovery_view, derived)
    if selected["disposition"] in {"EXTEND", "REUSE"}:
        candidate_id = discovery_ref["kind"].split(":", 2)[2]; candidates = [item for item in discovery["candidates"] if item.get("candidateId") == candidate_id]
        if len(candidates) != 1: raise ValueError("selected discovery candidate is missing")
        candidate = candidates[0]; baseline_path = target_path(root, candidate["evidence"]["path"], "baseline OpenAPI")
        if candidate["evidence"]["path"] not in selected["evidencePaths"] or not baseline_path.is_file() or sha(baseline_path) != candidate["evidence"]["sha256"]: raise ValueError("selected baseline evidence is stale")
        document = load_object(baseline_path); suggested_ids = {item.get("operationId") for item in candidate["requirementMatches"] if isinstance(item.get("operationId"), str)}; selected_ids = set(selected_operation_ids or [])
        if operation_selection_source not in {"RECOMMENDATION_ACCEPTED", "USER_CONFIRMED"} or not selected_ids: raise ValueError("existing API handoff requires user-confirmed operation IDs")
        available_ids = {operation.get("operationId") for _,_,operation in operations(document) if isinstance(operation.get("operationId"),str)}
        if not selected_ids <= suggested_ids or not selected_ids <= available_ids: raise ValueError("selected operation IDs are not in the discovered candidate scope")
        if operation_selection_source == "RECOMMENDATION_ACCEPTED" and selected_ids != suggested_ids: raise ValueError("recommendation acceptance must keep the complete suggested operation set")
        operation_selection = {"source": operation_selection_source, "suggestedOperationIds": sorted(suggested_ids), "selectedOperationIds": sorted(selected_ids)}
        if not selected_ids: semantic_blockers.append("no selected operation IDs are proven by discovery")
        scope = operation_scope(document, selected_ids)
        required = {item["id"] for item in feature["acceptanceCriteria"]} | {item["id"] for item in feature["businessRules"]}; covered = {ref for item in scope["operations"] for ref in item["requirementRefs"]}
        if not required <= covered: semantic_blockers.append("selected operations do not cover every feature requirement")
        if scope["externalRefs"]: semantic_blockers.append("selected operation scope contains unresolved external references")
        baseline = reference(baseline_path, root)
    ready_status = {"CREATE": "READY_FOR_CREATE_SOURCE", "EXTEND": "READY_FOR_EXTENSION_PROPOSAL", "REUSE": "READY_FOR_REUSE_DRY_RUN"}[selected["disposition"]]
    return {"httpApiContractHandoffVersion": 2, "status": ready_status if not semantic_blockers else "BLOCKED", "contractId": contract_id, "disposition": selected["disposition"], "target": selected["target"], "inputs": {"applicationReceipt": reference(application_path, root), "approvedRoute": reference(route_path, root), "feature": reference(feature_path, root), "projectBrief": reference(project_path, root), "technologyProfile": reference(profile_path, root), "discovery": reference(discovery_path, root)}, "baseline": baseline, "operationSelection": operation_selection, "operationScope": scope, "expectedOutputs": outputs, "blockers": semantic_blockers, "effects": {"adapterExecuted": False, "contractChanged": False, "sourceChanged": False, "existingOpenApiChanged": False, "gitCommitOrPush": "NOT_RUN"}}


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("application", "route", "feature", "project-brief", "profile", "target", "output", "view"): parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--contract-id", required=True); parser.add_argument("--operation-id",action="append",default=[]); parser.add_argument("--operation-selection-source",choices=["RECOMMENDATION_ACCEPTED","USER_CONFIRMED"]); args = parser.parse_args(); written=[]
    try:
        root=args.target.resolve(strict=True); paths={name.replace('_','-'): argument_path(root,getattr(args,name),name) for name in ("application","route","feature","project_brief","profile","output","view")}
        if args.target.is_symlink() or paths["view"] != paths["output"].with_suffix(".md") or len(set(paths.values())) != len(paths) or paths["output"].exists() or paths["view"].exists(): raise ValueError("handoff paths are unsafe, duplicated, or occupied")
        value=build(root,paths["application"],paths["route"],paths["feature"],paths["project-brief"],paths["profile"],args.contract_id,[paths["output"],paths["view"]],args.operation_id,args.operation_selection_source)
        expected_paths={target_path(root,item,"expected contract output") for key,item in value["expectedOutputs"].items() if key in {"metadata","openApi","comparison"} and item}
        if paths["output"] in expected_paths or paths["view"] in expected_paths: raise ValueError("handoff output overlaps a future contract output")
        payload=encoded(value); view_payload=render(value).encode(); paths["output"].parent.mkdir(parents=True,exist_ok=True)
        for path,content in ((paths["output"],payload),(paths["view"],view_payload)): atomic_create(content,path); written.append((path,content))
    except (OSError,ValueError,KeyError,TypeError) as error:
        for path,content in reversed(written):
            if path.exists() and path.read_bytes()==content: path.unlink()
        print(f"HTTP_API_CONTRACT_HANDOFF_VALID: no\nERROR: {error}"); return 1
    print(f"HTTP_API_CONTRACT_HANDOFF_VALID: yes\nHANDOFF_STATUS: {value['status']}\nADAPTER_EXECUTED: no\nSOURCE_CHANGED: no"); return 0

if __name__=="__main__": sys.exit(main())
