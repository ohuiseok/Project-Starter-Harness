#!/usr/bin/env python3
"""Run the production v2 Spring CREATE flow in an external temporary Git target."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
sys.path[:0] = [str(SCRIPTS), str(ROOT)]

from http_api_contract import derived_traceability  # noqa: E402
from http_api_spring_mapping import reference  # noqa: E402
from render_spec_markdown import render_feature, render_project  # noqa: E402
from validate_design_route import validate as validate_route  # noqa: E402
from validate_feature_specs import approval_content_hash, validate_feature, validate_project  # noqa: E402
from tests.spring_gradle_acceptance import (  # noqa: E402
    DEFAULT_SCENARIO, PII, SECRET, atomic_output, create_target, load_scenario, prerequisites, safe_message, sha, write,
)

APPROVED_BY = "acceptance-user"
PHASES = ["PREPARE", "CANDIDATE_VERIFICATION", "APPLY", "POST_APPLY_VERIFICATION", "COMPLETION"]
CONTINUATION_PHASES = ["CONTINUATION_ROUTING", "FEATURE_SPECIFICATION", "DESIGN_ROUTE_PREPARATION"]
STATUS_LINE = re.compile(r"^([A-Z][A-Z0-9_]*):\s*(.*)$")


class CommandFailure(RuntimeError):
    def __init__(self, receipt: dict):
        super().__init__(f"{receipt['stage']}: {receipt['summary']}")
        self.receipt = receipt


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def approved(document: dict, approved_at: str) -> dict:
    value = json.loads(json.dumps(document))
    if "feature" in value:
        value["feature"]["status"] = "APPROVED"
    value["approval"] = {"status": "APPROVED", "approvedBy": APPROVED_BY, "approvedAt": approved_at, "approvedContentSha256": None}
    value["approval"]["approvedContentSha256"] = approval_content_hash(value)
    return value


def json_file(path: Path, value: dict) -> None:
    write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def outcome(state: str, phase: str, category: str, next_action: str, **details: object) -> dict:
    completed = PHASES[:PHASES.index(phase)] if phase in PHASES else []
    return {
        "productionV2AcceptanceVersion": 1, "acceptanceState": state, "phase": phase,
        "category": category, "completedPhases": completed, "nextAction": next_action,
        "scope": {"adapter": "JAVA_MVC_API_ONLY_V1", "build": "GRADLE", "fileActions": ["CREATE_FILE"],
                  "databaseRuntime": "NOT_RUN", "applicationStartup": "NOT_RUN", "httpSmoke": "NOT_RUN", "gitCommitOrPush": "NOT_RUN"},
        "details": details,
    }


def failure_state(phase: str, message: str, injected_stale: bool = False, fields: dict | None = None) -> tuple[str, str]:
    fields = fields or {}
    if injected_stale or any(marker in message.lower() for marker in ("stale", "changed after", "target context changed", "approved mapping is stale")):
        return "BLOCKED", "BLOCKED_STALE"
    if fields.get("VERIFICATION_RESULT") == "FAILED" or fields.get("TRANSACTION_STATE") in {"ROLLED_BACK", "ROLLBACK_INCOMPLETE"}:
        return "FAILED", "FAILED_CODE"
    if fields.get("VERIFICATION_RESULT") == "UNKNOWN" or any(marker in message for marker in ("OFFLINE_DEPENDENCY", "TIMEOUT", "SENSITIVE_OUTPUT")):
        return "UNKNOWN", "UNKNOWN_ENVIRONMENT"
    if phase in {"PREPARE", "CANDIDATE_VERIFICATION", "POST_APPLY_VERIFICATION"}:
        return "UNKNOWN", "UNKNOWN_ENVIRONMENT"
    return "FAILED", "PRODUCTION_FLOW_ERROR"


def run_command(target: Path, receipts: list[dict], label: str, script: str, *arguments: str) -> str:
    started = time.monotonic()
    done = subprocess.run([sys.executable, str(SCRIPTS / script), *arguments], cwd=target, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    fields = {match.group(1): match.group(2) for line in done.stdout.splitlines() if (match := STATUS_LINE.match(line))}
    receipt = {"stage": label, "entryPoint": script, "exitCode": done.returncode,
               "durationMilliseconds": round((time.monotonic() - started) * 1000), "fields": fields,
               "outputSha256": hashlib.sha256(done.stdout.encode()).hexdigest(), "summary": safe_message(done.stdout.strip()[-1000:])}
    receipts.append(receipt)
    if done.returncode:
        raise CommandFailure(receipt)
    return done.stdout


def assert_feature_absent_from_head(target: Path, head: str, plan: dict) -> list[str]:
    tracked = set(subprocess.check_output(["git", "ls-tree", "-r", "--name-only", head], cwd=target, text=True).splitlines())
    planned = sorted(component["target"]["path"] for component in plan["components"] if component["fileAction"] == "CREATE_FILE")
    overlap = sorted(set(planned) & tracked)
    if overlap:
        raise ValueError("planned feature files already exist in initial Git HEAD: " + ", ".join(overlap))
    return planned


def base_documents(target: Path) -> dict[str, Path]:
    docs = target / "docs"; feature_dir = docs / "features/F001"; contract_dir = feature_dir / "contracts/orders-api"
    approved_at = now()
    project = approved({
        "schemaVersion": 1,
        "project": {"name": "Orders acceptance", "goal": "Prove safe application of an approved Spring API slice.",
                    "targetUsers": ["API client"], "successCriteria": ["The endpoint passes isolated tests before and after apply."],
                    "nonFunctionalRequirements": ["No network, database, Docker, or published ports are used."]},
        "scope": {"included": ["List orders API"], "excluded": ["Persistence", "Authentication", "Deployment"]},
        "featureCandidates": [{"id": "F001", "name": "List orders", "userValue": "An API client retrieves an empty order list.",
                               "recommendationReason": "Smallest executable Spring MVC vertical slice.", "dependsOn": [],
                               "blockingUnknownIds": [], "recommendedOrder": 1, "status": "APPROVED"},
                              {"id": "F002", "name": "List order summaries", "userValue": "An API client retrieves summarized orders.",
                               "recommendationReason": "It proves natural-language continuation after F001.", "dependsOn": ["F001"],
                               "blockingUnknownIds": [], "recommendedOrder": 2, "status": "APPROVED"}],
        "unknowns": [], "sources": [{"id": "S001", "type": "USER_STATED", "reference": "Production v2 acceptance scope"}], "approval": {},
    }, approved_at)
    requirement = lambda status, reason: {"status": status, "reason": reason, "source": "USER_STATED", "confirmedByUser": True}
    feature = approved({
        "schemaVersion": 2,
        "feature": {"id": "F001", "name": "List orders", "goal": "Return the current order list.",
                    "userValue": "An API client retrieves an empty order list.", "status": "APPROVED"},
        "actors": ["API client"],
        "scenario": {"preconditions": [], "trigger": "The client requests GET /orders.",
                     "mainFlow": ["Return HTTP 200 with an empty JSON array."], "alternateFlows": [], "postconditions": ["No state is changed."]},
        "businessRules": [{"id": "BR-F001-01", "description": "The initial list is empty.", "source": "USER_STATED",
                           "status": "APPROVED", "confirmedByUser": True}],
        "authorization": [], "dataAndState": [], "failureCases": [],
        "acceptanceCriteria": [{"id": "AC-F001-01", "given": "the Spring application is available",
                                "when": "GET /orders is requested", "then": "HTTP 200 and an empty JSON array are returned"}],
        "designRequirements": {
            "httpApi": requirement("REQUIRED", "The feature is exposed over HTTP."),
            "persistentState": requirement("NOT_USED", "The slice has no stored state."),
            "messaging": requirement("NOT_USED", "No asynchronous integration is needed."),
            "scheduledJob": requirement("NOT_USED", "No scheduled work is needed."),
            "serverRenderedUi": requirement("NOT_USED", "No server-rendered UI is needed."),
            "separateClient": requirement("NOT_USED", "Only the API boundary is in scope."),
            "externalIntegration": requirement("NOT_USED", "No external service is needed."),
        },
        "dependencies": [], "unknowns": [],
        "sources": [{"id": "S001", "type": "USER_STATED", "reference": "Production v2 acceptance scope"}], "approval": {},
    }, approved_at)
    profile = {"profileVersion": 1, "project": {"groupId": "com.example", "artifactId": "orders-acceptance", "name": "orders-acceptance",
               "description": "Production v2 acceptance", "packageName": "com.example"}, "projects": [], "dataStores": [], "decisions": {
        "language": {"status": "NOW", "option": "language.java"}, "java-version": {"status": "NOW", "option": "java-version.17"},
        "spring-boot-version": {"status": "NOW", "option": "spring-boot-version.current-stable", "resolvedValue": "3.2.0"},
        "build": {"status": "NOW", "option": "build.gradle-groovy"}, "application": {"status": "NOW", "option": "application.rest-api"},
        "view": {"status": "NOW", "option": "view.none"}, "security": {"status": "NOW", "option": "security.none"},
        "authorization": {"status": "NOW", "option": "authorization.none"}, "database": {"status": "NOW", "option": "database.none"},
        "persistence": {"status": "NOW", "option": "persistence.none"}, "database-topology": {"status": "NOW", "option": "database-topology.none"},
        "architecture": {"status": "NOW", "option": "architecture.single-module"}, "packaging": {"status": "NOW", "option": "packaging.jar"},
        "verification": {"status": "NOW", "option": "verification.spring-integration"}},
        "compatibilityReview": {"result": "SUPPORTED", "findings": [], "acceptedFindings": []},
        "confirmedBy": {"user": True, "confirmedAt": approved_at}}
    paths = {"project": docs / "project-brief.json", "feature": feature_dir / "spec.json", "profile": docs / "project-profile.json",
             "route": feature_dir / "design-route.json", "contract": contract_dir / "metadata.json", "openapi": contract_dir / "openapi.json"}
    for key, value in (("project", project), ("feature", feature), ("profile", profile)): json_file(paths[key], value)
    write(paths["project"].with_suffix(".md"), render_project(project)); write(paths["feature"].with_suffix(".md"), render_feature(feature, project))
    requirements = {"HTTP_API": "httpApi", "PERSISTENCE": "persistentState", "MESSAGING": "messaging", "SCHEDULED_JOB": "scheduledJob",
                    "SERVER_UI": "serverRenderedUi", "CLIENT_INTEGRATION": "separateClient", "EXTERNAL_INTEGRATION": "externalIntegration",
                    "SECURITY": "authorization", "VERIFICATION": "acceptanceCriteria"}
    route_rows = []
    for kind, requirement_ref in requirements.items():
        contract_id = "orders-api" if kind == "HTTP_API" else kind.lower().replace("_", "-"); disposition = "CREATE" if kind in {"HTTP_API", "VERIFICATION"} else "NOT_NEEDED"
        artifact = (contract_dir / "metadata.json").relative_to(target).as_posix() if kind == "HTTP_API" else (feature_dir / "contracts/verification/metadata.json").relative_to(target).as_posix() if kind == "VERIFICATION" else None
        route_rows.append({"contractId": contract_id, "kind": kind, "requirementRef": requirement_ref, "disposition": disposition,
                           "target": {"projectId": "orders-acceptance", "modulePath": ".", "dataStoreIds": []}, "evidencePaths": [],
                           "artifactPath": artifact, "reason": "Matches the approved acceptance slice.", "source": "USER_STATED", "confirmedByUser": True})
    route = approved({"routeVersion": 2, "featureId": "F001", "inputs": {"feature": reference(paths["feature"], target),
                      "projectBrief": reference(paths["project"], target), "technologyProfile": reference(paths["profile"], target), "codeEvidence": []},
                      "routes": route_rows, "approval": {}}, approved_at)
    json_file(paths["route"], route)
    route_ok, route_blockers = validate_route(route, feature, project, profile)
    if not route_ok or route_blockers: raise ValueError("canonical design route is invalid: " + "; ".join(route_blockers))
    openapi = {"openapi": "3.1.0", "info": {"title": "Orders acceptance", "version": "1.0.0"}, "paths": {"/orders": {"get": {
        "operationId": "listOrders", "summary": "List orders", "x-harness-requirement-refs": ["AC-F001-01", "BR-F001-01"],
        "responses": {"200": {"description": "An empty order list", "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}}}}}}
    json_file(paths["openapi"], openapi); selected = next(item for item in route_rows if item["kind"] == "HTTP_API")
    contract = approved({"contractVersion": 1, "contractId": "orders-api", "kind": "HTTP_API", "featureId": "F001",
                         "route": reference(paths["route"], target), "disposition": "CREATE", "target": selected["target"],
                         "artifact": {"format": "OPENAPI", "path": paths["openapi"].relative_to(target).as_posix()},
                         "traceability": derived_traceability(openapi), "evidencePaths": [], "approval": {}}, approved_at)
    json_file(paths["contract"], contract)
    if validate_project(project) != (True, []) or validate_feature(feature, project) != (True, []): raise ValueError("canonical project or feature is invalid")
    return paths


def candidate_files(candidate: Path, plan: dict) -> None:
    for component in plan["components"]:
        path = candidate / component["target"]["path"]; package = path.as_posix().split("/java/", 1)[1].rsplit("/", 1)[0].replace("/", "."); name = component["target"]["typeName"]
        if component["role"] == "CONTROLLER":
            body = f'''package {package};
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
@RestController public class {name} {{ @GetMapping(value = "/orders", produces = MediaType.APPLICATION_JSON_VALUE) public String listOrders() {{ return "[]"; }} }}
'''
        elif component["role"] == "APPLICATION_SERVICE":
            body = f'''package {package};
import org.springframework.stereotype.Service;
@Service public class {name} {{ public void listOrders() {{ }} }}
'''
        elif component["role"] in {"REQUEST_DTO", "RESPONSE_DTO"}:
            body = f"package {package};\npublic class {name} {{ }}\n"
        else:
            refs = " ".join(component["requirementRefs"])
            body = f'''package {package};
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
@SpringBootTest @AutoConfigureMockMvc public class {name} {{ @Autowired MockMvc mvc; @Test void verifiesContract() throws Exception {{ String traceability = "GET /orders {refs}"; mvc.perform(get("/orders")).andExpect(status().isOk()).andExpect(content().json("[]")); }} }}
'''
        write(path, body)


def continue_to_design_review(target: Path, paths: dict[str, Path], artifacts: dict[str, Path], receipts: list[dict], request: str,
                              inject: str | None = None) -> dict:
    command = lambda label, script, *args: run_command(target, receipts, label, script, *args)
    common = ["--target", str(target)]; directory = target / "docs/continuation/F002"; feature_dir = target / "docs/features/F002"
    source_before = {path.relative_to(target).as_posix(): sha(path) for path in target.glob("src/**/*") if path.is_file()}
    route = directory / "route.json"; route_view = route.with_suffix(".md")
    command("continuation route", "create_continuation_route.py", "--request", request, "--project-brief", str(paths["project"]),
            "--progress", str(target / "docs/progress-v2.json"), *common, "--output", str(route), "--view", str(route_view))
    route_value = json.loads(route.read_text())
    selected = route_value["route"].get("selectedFeature")
    if route_value["route"]["type"] != "NEXT_FEATURE" or not selected or selected["featureId"] != "F002":
        raise ValueError("natural-language continuation did not select the recommended F002")
    approval = directory / "route-approval.json"; handoff = directory / "handoff.json"
    command("continuation approval", "record_continuation_route_approval.py", "--route", str(route), "--view", str(route_view), *common,
            "--approval-output", str(approval), "--handoff-output", str(handoff), "--expected-route-hash", sha(route),
            "--approved-by", APPROVED_BY, "--approved-at", now())
    intake = directory / "workflow-intake.json"
    command("continuation handoff", "consume_continuation_handoff.py", "--handoff", str(handoff), *common, "--output", str(intake))
    replay_blocked = False; recovery_executed = False
    if inject == "continuation-handoff-replay-and-recovery":
        duplicate = directory / "duplicate-workflow-intake.json"
        try: command("continuation handoff replay", "consume_continuation_handoff.py", "--handoff", str(handoff), *common, "--output", str(duplicate))
        except CommandFailure:
            replay_blocked = not duplicate.exists()
        if not replay_blocked: raise ValueError("continuation handoff replay was not blocked cleanly")
        claim = target / ".starter-harness/continuation-handoff-consumptions" / f"{sha(handoff)}.json"; claim_value = json.loads(claim.read_text()); claim_value["state"] = "PREPARED"; json_file(claim, claim_value)
        command("continuation handoff recovery", "recover_continuation_handoff_consumption.py", "--handoff", str(handoff), *common)
        recovery_executed = True
    draft = feature_dir / "spec.draft.v001.json"; draft_view = draft.with_suffix(".md")
    command("feature draft", "create_feature_spec_from_intake.py", "--intake", str(intake), *common,
            "--draft-output", str(draft), "--view-output", str(draft_view))
    proposal_value = json.loads(draft.read_text()); proposal_value["feature"].update({"goal": "Return summarized orders.", "status": "DRAFT"})
    proposal_value["actors"] = ["API client"]
    proposal_value["scenario"] = {"preconditions": [], "trigger": "The client requests GET /order-summaries.",
                                  "mainFlow": ["Return HTTP 200 with summarized orders."], "alternateFlows": [], "postconditions": ["No state is changed."]}
    proposal_value["acceptanceCriteria"] = [{"id": "AC-F002-01", "given": "the Spring application is available",
                                               "when": "GET /order-summaries is requested", "then": "HTTP 200 and a JSON array are returned"}]
    requirement = lambda status, reason: {"status": status, "reason": reason, "source": "USER_STATED", "confirmedByUser": True}
    proposal_value["designRequirements"] = {
        "httpApi": requirement("REQUIRED", "The continuation exposes an HTTP endpoint."),
        "persistentState": requirement("NOT_USED", "No persisted data is required by this acceptance slice."),
        "messaging": requirement("NOT_USED", "No asynchronous integration is required."),
        "scheduledJob": requirement("NOT_USED", "No scheduled work is required."),
        "serverRenderedUi": requirement("NOT_USED", "No server-rendered UI is required."),
        "separateClient": requirement("NOT_USED", "Only the API boundary is in scope."),
        "externalIntegration": requirement("NOT_USED", "No external service is required."),
    }
    for item in proposal_value["unknowns"]: item["status"] = "RESOLVED"
    proposal_value["sources"].append({"id": "ANSWER-F002-001", "type": "USER_STATED", "reference": "주문 요약 목록 API로 진행"})
    proposal = directory / "spec-proposal.json"; json_file(proposal, proposal_value)
    revised = feature_dir / "spec.draft.v002.json"; revised_view = revised.with_suffix(".md")
    command("feature draft update", "advance_feature_spec_draft.py", "--intake", str(intake), "--current", str(draft),
            "--proposal", str(proposal), *common, "--output", str(revised), "--view", str(revised_view))
    readiness = directory / "spec-readiness.json"; readiness_view = readiness.with_suffix(".md")
    command("feature readiness", "prepare_feature_spec_approval.py", "--intake", str(intake), "--draft", str(revised),
            *common, "--output", str(readiness), "--view", str(readiness_view))
    command("feature readiness validation", "validate_feature_spec_approval_readiness.py", "--intake", str(intake),
            "--report", str(readiness), "--view", str(readiness_view), *common)
    promotion = directory / "promotion.json"; promotion_view = promotion.with_suffix(".md")
    command("feature promotion review", "prepare_feature_spec_promotion.py", "--intake", str(intake), "--readiness", str(readiness),
            "--readiness-view", str(readiness_view), *common, "--output", str(promotion), "--view", str(promotion_view))
    approved_at = now()
    command("feature promotion apply", "apply_feature_spec_promotion.py", "--plan", str(promotion), "--view", str(promotion_view),
            *common, "--expected-plan-hash", sha(promotion), "--approved-by", APPROVED_BY, "--approved-at", approved_at)
    completion = target / ".starter-harness/continuation-completions" / f"{sha(intake)}.json"
    design_route = feature_dir / "design-route.json"; design_view = design_route.with_suffix(".md")
    command("design route preparation", "prepare_design_route_from_completion.py", "--completion", str(completion),
            "--project-brief", str(paths["project"]), "--profile", str(paths["profile"]), *common,
            "--output", str(design_route), "--view", str(design_view))
    source_after = {path.relative_to(target).as_posix(): sha(path) for path in target.glob("src/**/*") if path.is_file()}
    official = feature_dir / "spec.json"; official_value = json.loads(official.read_text()); design_value = json.loads(design_route.read_text())
    if official_value["approval"]["status"] != "APPROVED" or source_before != source_after:
        raise ValueError("continuation promotion changed source or did not approve F002")
    artifacts.update(continuationRoute=route, continuationApproval=approval, continuationHandoff=handoff, continuationIntake=intake,
                     featureDraft=draft, featureDraftRevision=revised, featureReadiness=readiness, featurePromotion=promotion,
                     featurePromotionCompletion=completion, nextFeature=official, nextDesignRoute=design_route)
    return {"request": request, "selectedFeatureId": "F002", "progressVersion": "V2", "officialFeatureApproved": True,
            "sourceUnchangedDuringContinuation": True, "designRouteState": design_value["approval"]["status"],
            "handoffReplayBlocked": replay_blocked, "handoffRecoveryExecuted": recovery_executed, "nextBoundary": "DESIGN_ROUTE_REVIEW"}


def evidence_index(target: Path, initial_head: str, artifacts: dict[str, Path]) -> dict:
    indexed = {name: {"path": path.relative_to(target).as_posix(), "sha256": sha(path), "mode": path.stat().st_mode & 0o777}
               for name, path in artifacts.items() if path.is_file()}
    final_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=target, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=target, text=True).splitlines()
    return {"initialGitHead": initial_head, "finalGitHead": final_head, "gitHeadUnchanged": final_head == initial_head, "gitStatus": status, "artifacts": indexed}


def render_result(result: dict) -> str:
    completed = set(result["completedPhases"]); current = result["phase"]
    labels = {"PREPARE": "준비", "CANDIDATE_VERIFICATION": "후보 검증", "APPLY": "프로젝트 적용",
              "POST_APPLY_VERIFICATION": "적용 후 검증", "COMPLETION": "완료 기록", "CONTINUATION_ROUTING": "다음 요청 해석",
              "FEATURE_SPECIFICATION": "다음 기능 명세", "DESIGN_ROUTE_PREPARATION": "다음 설계 검토 준비"}
    lines = ["# Production v2 적용 검증", "", "## 현재 상태", "", f"- 결과: `{result['acceptanceState']}`", f"- 현재 단계: {labels.get(current, current)}", f"- 분류: `{result['category']}`", "", "## 진행", ""]
    displayed = PHASES + CONTINUATION_PHASES if any(phase in completed or phase == current for phase in CONTINUATION_PHASES) else PHASES
    for phase in displayed:
        state = "완료" if phase in completed else "현재" if phase == current and result["acceptanceState"] != "PASSED" else "대기"
        lines.append(f"- {labels[phase]}: {state}")
    scope = result["scope"]
    lines += ["", "## 이번 검증 범위", "", f"- Adapter: `{scope['adapter']}`", "- Java · Gradle · 단일 모듈 Spring MVC · CREATE",
              f"- DB runtime: `{scope['databaseRuntime']}`", f"- 애플리케이션 기동·HTTP smoke: `{scope['applicationStartup']}` / `{scope['httpSmoke']}`",
              f"- Git commit/push: `{scope['gitCommitOrPush']}`", "", "## 다음", "", f"- {result['nextAction']}", ""]
    return "\n".join(lines)


def bundle_files(target: Path) -> list[Path]:
    roots = [target / "docs", target / ".starter-harness", target / "src", target / "gradle/wrapper"]
    files = [path for root in roots if root.is_dir() for path in root.rglob("*") if path.is_file() and not path.is_symlink()]
    files += [path for path in (target / "build.gradle", target / "settings.gradle", target / "gradlew", target / ".starter-harness-implementation-v2.json") if path.is_file() and not path.is_symlink()]
    return sorted(set(files))


def persist_bundle(target: Path, destination: Path, result: dict) -> dict:
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink(): raise ValueError("evidence bundle destination is occupied")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink(): raise ValueError("evidence bundle parent is unsafe")
    staging = Path(tempfile.mkdtemp(prefix=".v2-evidence-stage-", dir=destination.parent))
    records = []
    try:
        for source in bundle_files(target):
            relative = source.relative_to(target); output = staging / "target" / relative; output.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix.lower() in {".json", ".md", ".java", ".gradle", ".txt", ".log", ".properties"} or source.name in {"gradlew", "settings.gradle"}:
                content = source.read_text(encoding="utf-8", errors="replace")
                if SECRET.search(content) or PII.search(content): raise ValueError("evidence bundle contains sensitive or personal output: " + relative.as_posix())
            shutil.copy2(source, output)
            records.append({"targetPath": relative.as_posix(), "bundlePath": output.relative_to(staging).as_posix(),
                            "sha256": sha(output), "mode": output.stat().st_mode & 0o777, "sizeBytes": output.stat().st_size})
        snapshot = staging / "acceptance-result.json"; json_file(snapshot, result)
        records.append({"targetPath": None, "bundlePath": snapshot.relative_to(staging).as_posix(), "sha256": sha(snapshot),
                        "mode": snapshot.stat().st_mode & 0o777, "sizeBytes": snapshot.stat().st_size})
        manifest = {"productionV2EvidenceBundleVersion": 1, "sourceTargetWasTemporary": True, "files": records}
        manifest_path = staging / "manifest.json"; json_file(manifest_path, manifest)
        os.replace(staging, destination)
        return {"path": str(destination), "manifestSha256": sha(destination / "manifest.json"), "fileCount": len(records),
                "totalBytes": sum(item["sizeBytes"] for item in records)}
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True); raise


def finish(result: dict, target: Path, evidence_dir: Path | None) -> dict:
    if evidence_dir is not None:
        try: result["evidenceBundle"] = persist_bundle(target, evidence_dir, result)
        except (OSError, ValueError) as error:
            return outcome("BLOCKED", result.get("phase", "PREPARE"), "EVIDENCE_BUNDLE_FAILED", "증거 번들 경로와 민감정보 검사를 확인한 뒤 재실행",
                           originalState=result.get("acceptanceState"), error=safe_message(error))
    return result


def execute(scenario_path: Path, timeout: int | None = None, inject: str | None = None, evidence_dir: Path | None = None,
            continuation_request: str | None = None) -> dict:
    try: scenario = load_scenario(scenario_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        return outcome("BLOCKED", "PREPARE", "SCENARIO_INVALID", "acceptance 시나리오를 수정", error=str(error))
    ready = prerequisites(scenario)
    if ready["acceptanceState"] != "RUNNABLE":
        return outcome(ready["acceptanceState"], "PREPARE", ready["category"], ready["nextAction"], prerequisite=ready)
    timeout = timeout or scenario["limits"]["timeoutSeconds"]
    with tempfile.TemporaryDirectory(prefix="spring-v2-production-acceptance-", dir="/var/tmp") as temporary:
        target = Path(temporary) / "external-target"; candidate = Path(temporary) / "candidate"; target.mkdir(); candidate.mkdir()
        artifacts: dict[str, Path] = {}; stage_receipts: list[dict] = []; phase = "PREPARE"; initial_head = "UNKNOWN"
        command = lambda label, script, *args: run_command(target, stage_receipts, label, script, *args)
        try:
            initial_head = create_target(target, ready["details"]["gradleExecutable"], scenario)
            paths = base_documents(target); artifacts.update(paths); common = ["--target", str(target)]
            mapping = target / "docs/features/F001/spring-mapping.json"
            command("mapping prepare", "prepare_http_api_spring_mapping.py", "--feature", str(paths["feature"]), "--profile", str(paths["profile"]), "--route", str(paths["route"]), "--http-api-contract", str(paths["contract"]), *common, "--output", str(mapping), "--view", str(mapping.with_suffix(".md")), "--module-path", ".", "--package-name", "com.example", "--decision-source", "USER_CONFIRMED")
            artifacts["springMapping"] = mapping; mapping_approval = mapping.with_name("spring-mapping-approval.json")
            command("mapping approval", "record_http_api_spring_mapping_approval.py", "--mapping", str(mapping), "--view", str(mapping.with_suffix(".md")), *common, "--output", str(mapping_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            artifacts["springMappingApproval"] = mapping_approval; plan = mapping.with_name("implementation-plan-v2.json")
            command("plan prepare", "prepare_spring_implementation_plan_v2.py", "--mapping-approval", str(mapping_approval), *common, "--output", str(plan), "--view", str(plan.with_suffix(".md")))
            plan_value = json.loads(plan.read_text()); planned_feature_files = assert_feature_absent_from_head(target, initial_head, plan_value)
            artifacts["implementationPlan"] = plan; plan_approval = plan.with_name("implementation-plan-v2-approval.json")
            command("plan approval", "record_spring_implementation_plan_v2_approval.py", "--plan", str(plan), "--view", str(plan.with_suffix(".md")), *common, "--output", str(plan_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            artifacts["implementationPlanApproval"] = plan_approval; renderability = plan.with_name("spring-code-renderability-v2.json")
            command("renderability", "prepare_spring_code_renderability_v2.py", "--plan-approval", str(plan_approval), *common, "--output", str(renderability), "--view", str(renderability.with_suffix(".md")))
            artifacts["renderability"] = renderability; candidate_files(candidate, plan_value); dry = plan.with_name("spring-code-dry-run-v2.json")
            command("dry run", "prepare_spring_code_dry_run_v2.py", "--plan-approval", str(plan_approval), "--renderability", str(renderability), "--rendered-source", str(candidate), *common, "--output", str(dry), "--view", str(dry.with_suffix(".md")))
            artifacts["dryRun"] = dry; dry_approval = dry.with_name("spring-code-dry-run-v2-approval.json")
            command("dry-run approval", "record_spring_code_dry_run_v2_approval.py", "--report", str(dry), "--view", str(dry.with_suffix(".md")), *common, "--output", str(dry_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            artifacts["dryRunApproval"] = dry_approval

            phase = "CANDIDATE_VERIFICATION"; verification_plan = dry.with_name("spring-code-verification-plan-v2.json")
            command("candidate plan", "prepare_spring_code_verification_plan_v2.py", "--dry-run-approval", str(dry_approval), *common, "--output", str(verification_plan), "--view", str(verification_plan.with_suffix(".md")), "--timeout-seconds", str(timeout))
            verification_approval = dry.with_name("spring-code-verification-plan-v2-approval.json")
            command("candidate approval", "record_spring_code_verification_plan_v2_approval.py", "--plan", str(verification_plan), "--view", str(verification_plan.with_suffix(".md")), *common, "--output", str(verification_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            verification = dry.with_name("spring-code-verification-report-v2.json")
            command("candidate verification", "run_spring_code_verification_v2.py", "--plan", str(verification_plan), "--approval", str(verification_approval), *common, "--output", str(verification))
            artifacts.update(candidateVerificationPlan=verification_plan, candidateVerificationApproval=verification_approval, candidateVerification=verification)
            candidate_state = json.loads(verification.read_text())["result"]["state"]
            if candidate_state != "PASSED":
                state = "FAILED" if candidate_state == "FAILED" else "UNKNOWN"
                category = "FAILED_CODE" if state == "FAILED" else "UNKNOWN_ENVIRONMENT"
                return finish(outcome(state, phase, category, "후보 코드 또는 실행 환경을 해결한 뒤 새 시도로 검증", stageReceipts=stage_receipts), target, evidence_dir)
            if inject == "candidate-evidence-tamper-before-apply": write(dry, dry.read_text() + " ")
            if inject == "target-drift-before-apply": write(target / "build.gradle", (target / "build.gradle").read_text() + "\n// injected relevant drift\n")

            phase = "APPLY"; apply_review = dry.with_name("spring-code-apply-review-v2.json")
            apply_result = target / "docs/features/F001/acceptance-apply-result/apply.json" if inject == "apply-report-recovery" else dry.with_name("spring-code-apply-result-v2.json")
            if inject == "apply-report-recovery": apply_result.parent.mkdir()
            command("apply review", "prepare_spring_code_apply_review_v2.py", "--verification-report", str(verification), *common, "--output", str(apply_review), "--view", str(apply_review.with_suffix(".md")), "--result", apply_result.relative_to(target).as_posix())
            apply_approval = dry.with_name("spring-code-apply-approval-v2.json")
            command("apply approval", "record_spring_code_apply_approval_v2.py", "--review", str(apply_review), "--view", str(apply_review.with_suffix(".md")), *common, "--output", str(apply_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            if inject == "apply-report-recovery": apply_result.parent.rmdir()
            command("apply", "apply_approved_spring_code_v2.py", "--review", str(apply_review), "--approval", str(apply_approval), *common)
            if inject == "apply-report-recovery":
                apply_result.parent.mkdir(); transaction_id = json.loads(apply_review.read_text())["transactionId"]
                command("apply report recovery", "recover_spring_code_apply_v2.py", *common, "--transaction-id", transaction_id)
            artifacts.update(applyReview=apply_review, applyApproval=apply_approval, applyResult=apply_result, baseline=target / ".starter-harness-implementation-v2.json")
            if inject == "reuse-apply-approval":
                try: command("apply approval reuse", "apply_approved_spring_code_v2.py", "--review", str(apply_review), "--approval", str(apply_approval), *common)
                except CommandFailure:
                    result = outcome("BLOCKED", phase, "BLOCKED_APPROVAL_REUSE", "새 review와 승인으로만 다시 적용", stageReceipts=stage_receipts,
                                     evidence=evidence_index(target, initial_head, artifacts), appliedFeatureFiles=planned_feature_files)
                    return finish(result, target, evidence_dir)
                raise ValueError("consumed apply approval was unexpectedly reusable")

            phase = "POST_APPLY_VERIFICATION"; post_plan = dry.with_name("post-apply-verification-plan-v2.json")
            command("post-apply plan", "prepare_post_apply_verification_v2.py", "--apply-result", str(apply_result), *common, "--output", str(post_plan), "--view", str(post_plan.with_suffix(".md")), "--timeout-seconds", str(timeout))
            post_approval = dry.with_name("post-apply-verification-approval-v2.json")
            command("post-apply approval", "record_post_apply_verification_approval_v2.py", "--plan", str(post_plan), "--view", str(post_plan.with_suffix(".md")), *common, "--output", str(post_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            post_result = dry.with_name("post-apply-verification-report-v2.json")
            command("post-apply verification", "run_post_apply_verification_v2.py", "--plan", str(post_plan), "--approval", str(post_approval), *common, "--output", str(post_result))
            artifacts.update(postApplyPlan=post_plan, postApplyApproval=post_approval, postApplyResult=post_result)
            post_state = json.loads(post_result.read_text())["state"]
            if post_state != "VERIFIED":
                state = "FAILED" if post_state == "FAILED" else "UNKNOWN"; category = "FAILED_CODE" if state == "FAILED" else "UNKNOWN_ENVIRONMENT"
                return finish(outcome(state, phase, category, "적용된 코드 또는 실행 환경을 해결하고 새 attempt로 검증", stageReceipts=stage_receipts), target, evidence_dir)

            phase = "COMPLETION"; completion_time = now(); completion_review = dry.with_name("milestone-completion-review-v2.json"); completion = dry.with_name("milestone-completion-v2.json")
            command("completion review", "prepare_milestone_completion_v2.py", "--post-apply-result", str(post_result), "--feature", str(paths["feature"]), "--project-brief", str(paths["project"]), *common, "--completion-output", completion.relative_to(target).as_posix(), "--approved-at", completion_time, "--output", str(completion_review), "--view", str(completion_review.with_suffix(".md")))
            completion_approval = dry.with_name("milestone-completion-approval-v2.json")
            command("completion approval", "record_milestone_completion_approval_v2.py", "--review", str(completion_review), "--view", str(completion_review.with_suffix(".md")), *common, "--output", str(completion_approval), "--approved-by", APPROVED_BY, "--approved-at", completion_time)
            command("completion apply", "apply_milestone_completion_v2.py", "--review", str(completion_review), "--approval", str(completion_approval), *common)
            artifacts.update(completionReview=completion_review, completionApproval=completion_approval, completion=completion, progress=target / "docs/progress-v2.json")
            continuation = None
            if continuation_request:
                phase = "DESIGN_ROUTE_PREPARATION"
                continuation = continue_to_design_review(target, paths, artifacts, stage_receipts, continuation_request, inject)
            category = "PRODUCTION_V2_CONTINUATION_READY" if continuation else "PRODUCTION_V2_FLOW_COMPLETED"
            next_action = "F002 설계 경로를 검토하고 승인" if continuation else "자연어 연속 개발 acceptance로 확장"
            result = {**outcome("PASSED", phase, category, next_action, evidence=evidence_index(target, initial_head, artifacts), stageReceipts=stage_receipts),
                    "completedPhases": PHASES, "proof": {"candidateExecuted": True, "productionApplyTransaction": True, "postApplyExecuted": True,
                    "completionRecorded": True, "productionValidatorsMocked": False, "targetWasExternal": True,
                    "featureAbsentFromInitialCommit": True, "plannedFeatureFiles": planned_feature_files,
                    "applyReportRecoveryExecuted": inject == "apply-report-recovery",
                    "upstreamApprovedInput": "CANONICAL_ACCEPTANCE_FIXTURE", "productionApprovalsRecordedFrom": "SPRING_MAPPING"}}
            if continuation:
                result["completedPhases"] = PHASES + CONTINUATION_PHASES
                result["proof"]["continuation"] = continuation
            return finish(result, target, evidence_dir)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            expected_block = inject in {"target-drift-before-apply", "candidate-evidence-tamper-before-apply"} and phase == "APPLY"
            fields = error.receipt["fields"] if isinstance(error, CommandFailure) else {}
            state, category = failure_state(phase, str(error), expected_block, fields)
            feature_files = sorted(path.relative_to(target).as_posix() for path in target.glob("src/**/*") if path.is_file() and "AcceptanceApplication" not in path.name)
            diagnostics = {}
            for name in ("renderability", "dryRun", "candidateVerification", "applyReview", "postApplyPlan", "postApplyResult", "completionReview"):
                path = artifacts.get(name)
                if path and path.is_file():
                    value = json.loads(path.read_text()); diagnostics[name] = {key: value[key] for key in ("state", "status", "blockers", "result") if key in value}
            result = outcome(state, phase, category, "현재 증거와 실행 로그를 확인한 뒤 새 시도로 재실행",
                             error=safe_message(error), injection=inject, appliedFeatureFiles=feature_files, diagnostics=diagnostics,
                             stageReceipts=stage_receipts, evidence=evidence_index(target, initial_head, artifacts) if initial_head != "UNKNOWN" else {})
            return finish(result, target, evidence_dir)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO); parser.add_argument("--timeout", type=int)
    parser.add_argument("--inject", choices=["target-drift-before-apply", "candidate-evidence-tamper-before-apply", "reuse-apply-approval", "apply-report-recovery", "continuation-handoff-replay-and-recovery"])
    parser.add_argument("--output", type=Path); parser.add_argument("--view", type=Path); parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--continue-request"); args = parser.parse_args()
    output = args.output.resolve() if args.output else None; view = args.view.resolve() if args.view else output.with_suffix(".md") if output else None
    evidence_dir = args.evidence_dir.resolve() if args.evidence_dir else output.with_suffix(".evidence") if output else None
    occupied = [path for path in (output, view, evidence_dir) if path is not None and (path.exists() or path.is_symlink())]
    if args.view and output is None:
        result = outcome("BLOCKED", "PREPARE", "OUTPUT_UNSAFE", "--view와 함께 --output을 지정")
    elif occupied:
        result = outcome("BLOCKED", "PREPARE", "OUTPUT_UNSAFE", "비어 있는 결과·화면·증거 경로를 선택", occupied=[str(path) for path in occupied])
    else:
        result = execute(args.scenario.resolve(), args.timeout, args.inject, evidence_dir, args.continue_request)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output and not occupied:
        try:
            atomic_output(output, rendered)
            atomic_output(view, render_result(result))
        except (OSError, ValueError) as error:
            result = outcome("BLOCKED", "PREPARE", "OUTPUT_UNSAFE", "비어 있는 안전한 결과 경로를 선택", error=safe_message(error)); rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end=""); return {"PASSED": 0, "FAILED": 1, "BLOCKED": 2, "UNKNOWN": 3}.get(result["acceptanceState"], 2)


if __name__ == "__main__": sys.exit(main())
