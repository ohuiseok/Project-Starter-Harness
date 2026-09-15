#!/usr/bin/env python3
"""Run the production v2 Spring CREATE flow in an external temporary Git target."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
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
    DEFAULT_SCENARIO, atomic_output, create_target, load_scenario, prerequisites, safe_message, sha, write,
)

APPROVED_BY = "acceptance-user"
PHASES = ["PREPARE", "CANDIDATE_VERIFICATION", "APPLY", "POST_APPLY_VERIFICATION", "COMPLETION"]


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


def failure_state(phase: str, message: str, injected_stale: bool = False) -> tuple[str, str]:
    if injected_stale or any(marker in message.lower() for marker in ("stale", "changed after", "target context changed", "approved mapping is stale")):
        return "BLOCKED", "BLOCKED_STALE"
    if any(marker in message for marker in ("COMPILATION_FAILURE", "SPRING_CONTEXT_FAILURE", "TEST_FAILURE", "BUILD_FAILURE", "VERIFICATION_RESULT: FAILED")):
        return "FAILED", "FAILED_CODE"
    if any(marker in message for marker in ("OFFLINE_DEPENDENCY", "UNKNOWN", "TIMEOUT", "SENSITIVE_OUTPUT")) or phase in {"PREPARE", "CANDIDATE_VERIFICATION", "POST_APPLY_VERIFICATION"}:
        return "UNKNOWN", "UNKNOWN_ENVIRONMENT"
    return "FAILED", "PRODUCTION_FLOW_ERROR"


def run_command(target: Path, label: str, script: str, *arguments: str) -> str:
    done = subprocess.run([sys.executable, str(SCRIPTS / script), *arguments], cwd=target, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if done.returncode:
        raise RuntimeError(f"{label}: {done.stdout.strip()[-2000:]}")
    return done.stdout


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
                               "blockingUnknownIds": [], "recommendedOrder": 1, "status": "APPROVED"}],
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
    profile = {"project": {"artifactId": "orders-acceptance"}, "projects": [], "dataStores": [], "decisions": {
        "application": {"option": "application.rest-api"}, "view": {"option": "view.none"},
        "security": {"option": "security.none"}, "authorization": {"option": "authorization.none"},
        "database": {"option": "database.none"}, "persistence": {"option": "persistence.none"},
        "integration": {"option": "integration.none"}, "language": {"option": "language.java"}}}
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


def evidence_index(target: Path, initial_head: str, artifacts: dict[str, Path]) -> dict:
    indexed = {name: {"path": path.relative_to(target).as_posix(), "sha256": sha(path), "mode": path.stat().st_mode & 0o777}
               for name, path in artifacts.items() if path.is_file()}
    final_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=target, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=target, text=True).splitlines()
    return {"initialGitHead": initial_head, "finalGitHead": final_head, "gitHeadUnchanged": final_head == initial_head, "gitStatus": status, "artifacts": indexed}


def execute(scenario_path: Path, timeout: int | None = None, inject: str | None = None) -> dict:
    try: scenario = load_scenario(scenario_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        return outcome("BLOCKED", "PREPARE", "SCENARIO_INVALID", "acceptance 시나리오를 수정", error=str(error))
    ready = prerequisites(scenario)
    if ready["acceptanceState"] != "RUNNABLE":
        return outcome(ready["acceptanceState"], "PREPARE", ready["category"], ready["nextAction"], prerequisite=ready)
    timeout = timeout or scenario["limits"]["timeoutSeconds"]
    with tempfile.TemporaryDirectory(prefix="spring-v2-production-acceptance-", dir="/var/tmp") as temporary:
        target = Path(temporary) / "external-target"; candidate = Path(temporary) / "candidate"; target.mkdir(); candidate.mkdir()
        artifacts: dict[str, Path] = {}; phase = "PREPARE"; initial_head = "UNKNOWN"
        try:
            initial_head = create_target(target, ready["details"]["gradleExecutable"], scenario)
            paths = base_documents(target); artifacts.update(paths); common = ["--target", str(target)]
            mapping = target / "docs/features/F001/spring-mapping.json"
            run_command(target, "mapping prepare", "prepare_http_api_spring_mapping.py", "--feature", str(paths["feature"]), "--profile", str(paths["profile"]), "--route", str(paths["route"]), "--http-api-contract", str(paths["contract"]), *common, "--output", str(mapping), "--view", str(mapping.with_suffix(".md")), "--module-path", ".", "--package-name", "com.example", "--decision-source", "USER_CONFIRMED")
            artifacts["springMapping"] = mapping; mapping_approval = mapping.with_name("spring-mapping-approval.json")
            run_command(target, "mapping approval", "record_http_api_spring_mapping_approval.py", "--mapping", str(mapping), "--view", str(mapping.with_suffix(".md")), *common, "--output", str(mapping_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            artifacts["springMappingApproval"] = mapping_approval; plan = mapping.with_name("implementation-plan-v2.json")
            run_command(target, "plan prepare", "prepare_spring_implementation_plan_v2.py", "--mapping-approval", str(mapping_approval), *common, "--output", str(plan), "--view", str(plan.with_suffix(".md")))
            artifacts["implementationPlan"] = plan; plan_approval = plan.with_name("implementation-plan-v2-approval.json")
            run_command(target, "plan approval", "record_spring_implementation_plan_v2_approval.py", "--plan", str(plan), "--view", str(plan.with_suffix(".md")), *common, "--output", str(plan_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            artifacts["implementationPlanApproval"] = plan_approval; renderability = plan.with_name("spring-code-renderability-v2.json")
            run_command(target, "renderability", "prepare_spring_code_renderability_v2.py", "--plan-approval", str(plan_approval), *common, "--output", str(renderability), "--view", str(renderability.with_suffix(".md")))
            artifacts["renderability"] = renderability; candidate_files(candidate, json.loads(plan.read_text())); dry = plan.with_name("spring-code-dry-run-v2.json")
            run_command(target, "dry run", "prepare_spring_code_dry_run_v2.py", "--plan-approval", str(plan_approval), "--renderability", str(renderability), "--rendered-source", str(candidate), *common, "--output", str(dry), "--view", str(dry.with_suffix(".md")))
            artifacts["dryRun"] = dry; dry_approval = dry.with_name("spring-code-dry-run-v2-approval.json")
            run_command(target, "dry-run approval", "record_spring_code_dry_run_v2_approval.py", "--report", str(dry), "--view", str(dry.with_suffix(".md")), *common, "--output", str(dry_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            artifacts["dryRunApproval"] = dry_approval

            phase = "CANDIDATE_VERIFICATION"; verification_plan = dry.with_name("spring-code-verification-plan-v2.json")
            run_command(target, "candidate plan", "prepare_spring_code_verification_plan_v2.py", "--dry-run-approval", str(dry_approval), *common, "--output", str(verification_plan), "--view", str(verification_plan.with_suffix(".md")), "--timeout-seconds", str(timeout))
            verification_approval = dry.with_name("spring-code-verification-plan-v2-approval.json")
            run_command(target, "candidate approval", "record_spring_code_verification_plan_v2_approval.py", "--plan", str(verification_plan), "--view", str(verification_plan.with_suffix(".md")), *common, "--output", str(verification_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            verification = dry.with_name("spring-code-verification-report-v2.json")
            run_command(target, "candidate verification", "run_spring_code_verification_v2.py", "--plan", str(verification_plan), "--approval", str(verification_approval), *common, "--output", str(verification))
            artifacts.update(candidateVerificationPlan=verification_plan, candidateVerificationApproval=verification_approval, candidateVerification=verification)
            if inject == "target-drift-before-apply": write(target / "build.gradle", (target / "build.gradle").read_text() + "\n// injected relevant drift\n")

            phase = "APPLY"; apply_review = dry.with_name("spring-code-apply-review-v2.json"); apply_result = dry.with_name("spring-code-apply-result-v2.json")
            run_command(target, "apply review", "prepare_spring_code_apply_review_v2.py", "--verification-report", str(verification), *common, "--output", str(apply_review), "--view", str(apply_review.with_suffix(".md")), "--result", apply_result.relative_to(target).as_posix())
            apply_approval = dry.with_name("spring-code-apply-approval-v2.json")
            run_command(target, "apply approval", "record_spring_code_apply_approval_v2.py", "--review", str(apply_review), "--view", str(apply_review.with_suffix(".md")), *common, "--output", str(apply_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            run_command(target, "apply", "apply_approved_spring_code_v2.py", "--review", str(apply_review), "--approval", str(apply_approval), *common)
            artifacts.update(applyReview=apply_review, applyApproval=apply_approval, applyResult=apply_result, baseline=target / ".starter-harness-implementation-v2.json")

            phase = "POST_APPLY_VERIFICATION"; post_plan = dry.with_name("post-apply-verification-plan-v2.json")
            run_command(target, "post-apply plan", "prepare_post_apply_verification_v2.py", "--apply-result", str(apply_result), *common, "--output", str(post_plan), "--view", str(post_plan.with_suffix(".md")), "--timeout-seconds", str(timeout))
            post_approval = dry.with_name("post-apply-verification-approval-v2.json")
            run_command(target, "post-apply approval", "record_post_apply_verification_approval_v2.py", "--plan", str(post_plan), "--view", str(post_plan.with_suffix(".md")), *common, "--output", str(post_approval), "--approved-by", APPROVED_BY, "--approved-at", now())
            post_result = dry.with_name("post-apply-verification-report-v2.json")
            run_command(target, "post-apply verification", "run_post_apply_verification_v2.py", "--plan", str(post_plan), "--approval", str(post_approval), *common, "--output", str(post_result))
            artifacts.update(postApplyPlan=post_plan, postApplyApproval=post_approval, postApplyResult=post_result)

            phase = "COMPLETION"; completion_time = now(); completion_review = dry.with_name("milestone-completion-review-v2.json"); completion = dry.with_name("milestone-completion-v2.json")
            run_command(target, "completion review", "prepare_milestone_completion_v2.py", "--post-apply-result", str(post_result), "--feature", str(paths["feature"]), "--project-brief", str(paths["project"]), *common, "--completion-output", completion.relative_to(target).as_posix(), "--approved-at", completion_time, "--output", str(completion_review), "--view", str(completion_review.with_suffix(".md")))
            completion_approval = dry.with_name("milestone-completion-approval-v2.json")
            run_command(target, "completion approval", "record_milestone_completion_approval_v2.py", "--review", str(completion_review), "--view", str(completion_review.with_suffix(".md")), *common, "--output", str(completion_approval), "--approved-by", APPROVED_BY, "--approved-at", completion_time)
            run_command(target, "completion apply", "apply_milestone_completion_v2.py", "--review", str(completion_review), "--approval", str(completion_approval), *common)
            artifacts.update(completionReview=completion_review, completionApproval=completion_approval, completion=completion, progress=target / "docs/progress-v2.json")
            return {**outcome("PASSED", "COMPLETION", "PRODUCTION_V2_FLOW_COMPLETED", "자연어 연속 개발 acceptance로 확장", evidence=evidence_index(target, initial_head, artifacts)),
                    "completedPhases": PHASES, "proof": {"candidateExecuted": True, "productionApplyTransaction": True, "postApplyExecuted": True,
                    "completionRecorded": True, "productionValidatorsMocked": False, "targetWasExternal": True,
                    "upstreamApprovedInput": "CANONICAL_ACCEPTANCE_FIXTURE", "productionApprovalsRecordedFrom": "SPRING_MAPPING"}}
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            expected_block = inject == "target-drift-before-apply" and phase == "APPLY"
            state, category = failure_state(phase, str(error), expected_block)
            feature_files = sorted(path.relative_to(target).as_posix() for path in target.glob("src/**/*") if path.is_file() and "AcceptanceApplication" not in path.name)
            diagnostics = {}
            for name in ("renderability", "dryRun", "candidateVerification", "applyReview", "postApplyPlan", "postApplyResult", "completionReview"):
                path = artifacts.get(name)
                if path and path.is_file():
                    value = json.loads(path.read_text()); diagnostics[name] = {key: value[key] for key in ("state", "status", "blockers", "result") if key in value}
            return outcome(state, phase, category, "현재 증거와 실행 로그를 확인한 뒤 새 시도로 재실행",
                           error=safe_message(error), injection=inject, appliedFeatureFiles=feature_files, diagnostics=diagnostics,
                           evidence=evidence_index(target, initial_head, artifacts) if initial_head != "UNKNOWN" else {})


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO); parser.add_argument("--timeout", type=int)
    parser.add_argument("--inject", choices=["target-drift-before-apply"]); parser.add_argument("--output", type=Path); args = parser.parse_args()
    result = execute(args.scenario.resolve(), args.timeout, args.inject); rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try: atomic_output(args.output.resolve(), rendered)
        except (OSError, ValueError) as error:
            result = outcome("BLOCKED", "PREPARE", "OUTPUT_UNSAFE", "비어 있는 안전한 결과 경로를 선택", error=str(error)); rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end=""); return {"PASSED": 0, "FAILED": 1, "BLOCKED": 2, "UNKNOWN": 3}.get(result["acceptanceState"], 2)


if __name__ == "__main__": sys.exit(main())
