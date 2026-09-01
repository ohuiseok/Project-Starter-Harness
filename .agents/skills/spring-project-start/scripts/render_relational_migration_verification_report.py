#!/usr/bin/env python3
"""Render an evidence-first view of isolated migration verification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from render_design_route import atomic_write
from run_relational_migration_verification import sha, validate_plan, version_key
from relational_schema_fingerprint import expected as expected_schema, fingerprint
from validate_feature_specs import load_object


def validate(report: dict, report_path: Path, target: Path) -> None:
    required = {"migrationVerificationReportVersion", "plan", "approval", "target", "executedAt", "runtime", "result"}
    if not isinstance(report, dict) or set(report) != required or report["migrationVerificationReportVersion"] != 4: raise ValueError("migration verification report is invalid")
    if not isinstance(report["runtime"], dict) or set(report["runtime"]) != {"dockerServerVersion"} or not isinstance(report["runtime"]["dockerServerVersion"], str) or not report["runtime"]["dockerServerVersion"].strip(): raise ValueError("verification runtime evidence is invalid")
    if Path(str(report["target"])).resolve() != target.resolve(): raise ValueError("verification report target does not match")
    result = report["result"]
    if not isinstance(result, dict): raise ValueError("verification result must be an object")
    result_keys = {"state", "events", "cleanup", "images", "appliedMigrations", "schemaFingerprint", "targetDatabaseAccessed", "targetSourceFilesChanged", "persistentVolumeCreated"}
    if result.get("state") != "PASSED": result_keys.add("failure")
    if set(result) != result_keys or result["state"] not in {"PASSED", "FAILED", "CLEANUP_FAILED"}: raise ValueError("verification result is invalid")
    if result["targetDatabaseAccessed"] is not False or result["targetSourceFilesChanged"] is not False or result["persistentVolumeCreated"] is not False: raise ValueError("verification report violates isolation claims")
    if not isinstance(result["events"], list) or not all(isinstance(item, dict) and set(item) == {"step", "exitCode", "output"} and isinstance(item["step"], str) and isinstance(item["exitCode"], int) and isinstance(item["output"], str) for item in result["events"]): raise ValueError("verification events are invalid")
    if not isinstance(result["cleanup"], dict) or set(result["cleanup"]) != {"databaseContainerRemoved", "flywayContainersRemoved", "networkRemoved"} or not all(isinstance(value, bool) for value in result["cleanup"].values()): raise ValueError("verification cleanup evidence is invalid")
    if not isinstance(result["images"], dict) or (result["state"] == "PASSED" and set(result["images"]) != {"postgres", "flyway"}): raise ValueError("verification image evidence is invalid")
    for evidence in result["images"].values():
        if not isinstance(evidence, dict) or set(evidence) != {"reference", "imageId", "repoDigests"} or not isinstance(evidence["reference"], str) or not isinstance(evidence["imageId"], str) or not evidence["imageId"].startswith("sha256:") or not isinstance(evidence["repoDigests"], list) or not all(isinstance(item, str) and "@sha256:" in item for item in evidence["repoDigests"]): raise ValueError("verification image identity is invalid")
    if not isinstance(result["appliedMigrations"], list) or not all(isinstance(item, dict) and set(item) == {"version", "description", "state"} and all(isinstance(value, str) for value in item.values()) for item in result["appliedMigrations"]): raise ValueError("applied migration evidence is invalid")
    schema = result["schemaFingerprint"]
    if not isinstance(schema, dict) or set(schema) != {"state", "expectedSha256", "actualSha256", "differences"} or schema["state"] not in {"NOT_RUN", "MATCHED", "MISMATCHED"} or not isinstance(schema["expectedSha256"], str) or (schema["actualSha256"] is not None and not isinstance(schema["actualSha256"], str)) or not isinstance(schema["differences"], list): raise ValueError("schema fingerprint evidence is invalid")
    if result["state"] == "PASSED" and (schema["state"] != "MATCHED" or schema["differences"]): raise ValueError("successful report lacks matching schema fingerprint evidence")
    plan_ref = report["plan"]
    plan_path = Path(plan_ref.get("path", "")) if isinstance(plan_ref, dict) else Path("")
    if not isinstance(plan_ref, dict) or set(plan_ref) != {"path", "sha256"} or target.resolve() not in (plan_path.resolve(), *plan_path.resolve().parents) or not plan_path.is_file() or sha(plan_path) != plan_ref["sha256"]: raise ValueError("verification plan evidence is stale")
    plan = load_object(plan_path)
    _, _, physical = validate_plan(plan, plan_path, target)
    if schema["expectedSha256"] != fingerprint(expected_schema(physical)): raise ValueError("schema fingerprint no longer matches the approved physical model")
    if result["state"] == "PASSED":
        expected = plan.get("migrations") if isinstance(plan, dict) else None
        if not isinstance(expected, list) or len(expected) != len(result["appliedMigrations"]): raise ValueError("successful migration history does not match the plan")
        for planned, applied in zip(expected, result["appliedMigrations"]):
            if version_key(planned.get("version")) != version_key(applied["version"].replace("_", ".")) or planned.get("description") != applied["description"] or applied["state"].lower() != "success": raise ValueError("successful migration history does not match the plan")
        if not isinstance(plan.get("images"), dict) or any(result["images"].get(name, {}).get("reference") != reference for name, reference in plan["images"].items()): raise ValueError("executed image evidence does not match the plan")
    approval_ref = report["approval"]; approval_path = Path(approval_ref.get("path", "")) if isinstance(approval_ref, dict) else Path("")
    if not isinstance(approval_ref, dict) or set(approval_ref) != {"path", "sha256", "approvedBy", "approvedAt"} or target.resolve() not in (approval_path.resolve(), *approval_path.resolve().parents) or not approval_path.is_file() or sha(approval_path) != approval_ref["sha256"]: raise ValueError("verification approval evidence is stale")
    approval = load_object(approval_path)
    if not isinstance(approval, dict) or approval.get("planSha256") != plan_ref["sha256"] or Path(str(approval.get("target", ""))).resolve() != target.resolve(): raise ValueError("verification approval no longer matches the plan or target")
    if report_path.is_symlink(): raise ValueError("verification report must not be a symbolic link")


def render(report: dict) -> str:
    result = report["result"]; lines = ["# migration 격리 검증 결과", "", "## 결론", "", f"- 상태: {result['state']}", f"- Docker Engine: {report['runtime']['dockerServerVersion']}", "- 실제 대상 DB 접속: 안 함", "- 대상 source 파일 변경: 없음", "- persistent volume 생성: 없음", "", "## 실제 실행 이미지", ""]
    for name, evidence in result["images"].items(): lines.extend([f"- {name}: `{evidence['reference']}`", f"  - image ID: `{evidence['imageId']}`", f"  - repo digest: `{', '.join(evidence['repoDigests']) or '제공되지 않음'}`"])
    lines.extend(["", "## 적용된 migration chain", ""])
    if result["appliedMigrations"]:
        for migration in result["appliedMigrations"]: lines.append(f"- V{migration['version']} · `{migration['description']}` · {migration['state']}")
    else: lines.append("- 적용 이력을 확인하지 못함")
    schema = result["schemaFingerprint"]; lines.extend(["", "## Physical model 일치", "", f"- 상태: {schema['state']}", f"- 승인 모델 fingerprint: `{schema['expectedSha256']}`", f"- 실제 schema fingerprint: `{schema['actualSha256'] or '확인하지 못함'}`"])
    if schema["differences"]:
        lines.extend(["", "### 차이", ""])
        for item in schema["differences"]: lines.append(f"- `{item['path']}` · expected `{item['expected']}` · actual `{item['actual']}`")
    lines.extend(["", "## 단계별 증거", ""])
    for event in result["events"]: lines.extend([f"### {event['step']} · exit {event['exitCode']}", "", "```text", event["output"].rstrip(), "```", ""])
    cleanup_labels = {"databaseContainerRemoved": "임시 PostgreSQL 컨테이너", "flywayContainersRemoved": "Flyway 컨테이너", "networkRemoved": "내부 Docker 네트워크"}
    lines.extend(["## 정리 결과", ""]); lines.extend(f"- {cleanup_labels[name]}: {'정리 완료' if value else '정리 실패'}" for name, value in result["cleanup"].items())
    if "failure" in result: lines.extend(["", "## 실패 원인", "", f"- {result['failure']}"])
    if result["state"] == "CLEANUP_FAILED": lines.extend(["", "## 안전한 다음 조치", "", "- 새 검증을 실행하지 않음", "- pending journal을 임의로 삭제하지 않음", "- Harness의 migration verification 복구 절차로 라벨이 확인된 임시 자원만 정리", "- 복구가 완료된 뒤 새 계획을 다시 검토하고 승인"])
    lines.extend(["", "## 해석", "", "- PASSED는 전체 versioned migration chain, Flyway info 이력, 승인 physical model과 실제 PostgreSQL catalog가 모두 일치한다는 의미", "- production 데이터·권한·성능·lock·rollback 성공을 의미하지 않음", ""]); return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--report", required=True, type=Path); parser.add_argument("--target", required=True, type=Path); parser.add_argument("--output", required=True, type=Path); parser.add_argument("--check", action="store_true"); parser.add_argument("--force", action="store_true"); args = parser.parse_args()
    try:
        if args.check and args.force: raise ValueError("--check and --force cannot be combined")
        report = load_object(args.report); validate(report, args.report, args.target); expected = render(report)
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected: raise ValueError("migration verification report Markdown is stale")
        else: atomic_write(expected, args.output, args.force)
    except (OSError, ValueError, KeyError) as error: print(f"RELATIONAL_MIGRATION_REPORT_MARKDOWN_VALID: no\nERROR: {error}"); return 1
    print("RELATIONAL_MIGRATION_REPORT_MARKDOWN_VALID: yes"); return 0


if __name__ == "__main__": sys.exit(main())
