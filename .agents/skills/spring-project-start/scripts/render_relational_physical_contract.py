#!/usr/bin/env python3
"""Render a beginner-first view of a relational physical design."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from relational_physical_contract import validate_physical_contract
from render_design_route import atomic_write
from validate_feature_specs import approval_content_hash, load_object


def blocker_message(value: str) -> str:
    mappings = (
        ("adapter is not READY", "선택한 DB와 migration 조합은 아직 자동 생성이 준비되지 않았습니다."),
        ("changed after", "승인된 입력이 변경되어 물리 설계를 다시 만들어야 합니다."),
        ("not approved and current", "논리 데이터 계약을 먼저 최신 승인 상태로 만들어야 합니다."),
        ("does not cover", "논리 데이터가 물리 테이블과 컬럼에 빠짐없이 연결되어야 합니다."),
        ("does not implement", "모든 관계와 업무 규칙의 구현 위치를 정해야 합니다."),
        ("type does not match", "논리 유형과 PostgreSQL 유형의 연결을 수정해야 합니다."),
        ("identifier", "PostgreSQL 이름 규칙과 예약어를 다시 확인해야 합니다."),
        ("query justification", "인덱스가 필요한 실제 조회 목적을 연결해야 합니다."),
        ("UNKNOWN", "위험 또는 복구 가능성을 현재 근거로 확정해야 합니다."),
        ("must defer execution", "파일 생성·DB 실행·데이터 삭제는 이 승인에서 허용할 수 없습니다."),
        ("stale", "계약 정보가 현재 설계와 달라 다시 분석해야 합니다."),
    )
    return next((message for key, message in mappings if key in value), "물리 데이터 설계의 진행 조건을 다시 확인해야 합니다.")


def render(metadata: dict, physical: dict, logical: dict, blockers: list[str]) -> str:
    database, migration, risk, provisioning = physical["database"], physical["migrationPlan"], physical["riskAssessment"], physical["provisioningPlan"]
    lines = [
        f"# {physical['physicalModelId']} 물리 DB 설계", "", f"<!-- approval-content-sha256: {approval_content_hash(metadata)} -->",
        "<!-- 물리 모델과 승인된 논리 모델에서 생성됨. 직접 수정하지 마세요. -->", "",
        "## 선택 결과", "", f"- DB: {database['engine']} {database['version']}", f"- schema: `{database['schemaName']}`",
        f"- adapter: {physical['adapterId']} · {metadata['adapter']['status']}", f"- migration 원본: {migration['sourceOfTruth']} ({migration['strategy']})",
        f"- 생성 예정 경로: `{migration['plannedSourcePath']}`", "- 현재 단계에서는 migration 파일을 생성하거나 실행하지 않음", "",
        "## 테이블과 컬럼", "",
    ]
    for table in physical["tables"]:
        lines.extend([f"### `{table['name']}`", "", f"- 의미: {table['description']}", f"- 논리 데이터: {table['entityRef'] or '보조 테이블'}", "", "| 컬럼 | PostgreSQL 유형 | NULL | 고유 | 논리 필드 |", "|---|---|---|---|---|"])
        for column in table["columns"]:
            lines.append(f"| `{column['name']}` | `{column['sqlType']}` | {'허용' if column['nullable'] else '불가'} | {'예' if column['unique'] else '아니오'} | {column['fieldRef'] or '-'} |")
        lines.append("")
    lines.extend(["## 관계와 업무 규칙", ""])
    if physical["relationshipImplementations"]:
        lines.extend(f"- 관계 `{item['relationshipRef']}` — {item['enforcement']}: {item['reason']}" for item in physical["relationshipImplementations"])
    else: lines.append("- 물리적으로 구현할 관계 없음")
    lines.extend(f"- 규칙 `{item['invariantRef']}` — {item['enforcement']}: {item['reason']}" for item in physical["invariantImplementations"])
    lines.extend(["", "## 인덱스 근거", ""])
    if physical["queryPatterns"]:
        lines.extend(f"- `{item['queryPatternId']}` — {item['description']}" for item in physical["queryPatterns"])
    else: lines.append("- 기본 키 외 추가 조회 패턴 없음")
    lines.extend(["", "## 변경 위험과 복구", "", f"- 데이터 손실: {risk['dataLoss']}", f"- 잠금: {risk['locking']}", f"- 중단: {risk['downtime']}", f"- 판단 근거: {risk['reason']}", f"- migration에 요구하는 복구 수준: {migration['requiredRecovery']}", "- 실제 복구 가능성은 migration 파일 dry-run에서 다시 검증", "- 파일 적용의 원자적 rollback과 DB migration의 복구 보장은 서로 다름", ""])
    lines.extend(["## 로컬 실행 계획", "", f"- 방식: {provisioning['strategy']}"])
    if provisioning["compose"]:
        compose = provisioning["compose"]
        lines.extend([f"- Compose 예정 경로: `{compose['plannedPath']}`", f"- 이미지: `{compose['imageReference']}`", f"- 실행 전 확인할 포트: {compose['hostPort']}", "- 자동 시작 안 함 · volume 자동 삭제 안 함"])
    if provisioning["testcontainers"]: lines.extend([f"- Testcontainers 이미지: `{provisioning['testcontainers']['imageReference']}`", "- credential 저장 안 함 · reusable container 사용 안 함"])
    lines.extend(["", "## 지금 확인해야 할 사항", ""])
    lines.extend(f"- {item}" for item in dict.fromkeys(blocker_message(item) for item in blockers)) if blockers else lines.append("- 없음")
    status = "승인 완료" if metadata["approval"]["status"] == "APPROVED" and not blockers else ("결정 확인 필요" if blockers else "승인 대기")
    lines.extend(["", "## 현재 상태", "", f"- {status}", "", "## 다음 행동", ""])
    lines.extend(["- 추천: 표시된 물리 설계 보완", "- 항목별 수정", "- 원하는 DB 구성을 직접 설명"] if blockers else ["- 추천: 물리 DB 계약 승인", "- 항목별 수정", "- 원하는 DB 구성을 직접 설명"])
    lines.append(""); return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path); parser.add_argument("--physical-model", required=True, type=Path)
    parser.add_argument("--logical-contract", required=True, type=Path); parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path); parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path); parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true"); parser.add_argument("--force", action="store_true"); args = parser.parse_args()
    if args.check and args.force: print("RELATIONAL_PHYSICAL_MARKDOWN_VALID: no\nERROR: --check and --force cannot be combined"); return 2
    try:
        metadata = load_object(args.contract)
        _, blockers, physical, logical = validate_physical_contract(metadata, args.physical_model, args.logical_contract, load_object(args.route), args.route, args.target, load_object(args.feature), load_object(args.profile))
        expected = render(metadata, physical, logical, blockers)
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected: raise ValueError("relational physical Markdown is stale")
        else: atomic_write(expected, args.output, args.force)
    except (OSError, ValueError) as error: print(f"RELATIONAL_PHYSICAL_MARKDOWN_VALID: no\nERROR: {error}"); return 1
    print("RELATIONAL_PHYSICAL_MARKDOWN_VALID: yes"); return 0


if __name__ == "__main__": sys.exit(main())
