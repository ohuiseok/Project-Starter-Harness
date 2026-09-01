#!/usr/bin/env python3
"""Render a logical relational data contract as a beginner-friendly view."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from relational_data_contract import validate_relational_contract
from render_design_route import atomic_write
from validate_feature_specs import approval_content_hash, load_object


def mermaid_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def blocker_message(value: str) -> str:
    mappings = (
        ("data model ID is UNKNOWN", "데이터 모델의 안정적인 ID를 정해야 합니다."),
        ("data model purpose is UNKNOWN", "이 기능이 데이터를 저장하는 목적을 확인해야 합니다."),
        ("data model has no entities", "기억해야 할 비즈니스 데이터를 하나 이상 정의해야 합니다."),
        ("data model has no feature traceability", "데이터 구조를 기능 요구사항과 연결해야 합니다."),
        ("entity has no identifier", "각 데이터 객체를 구별할 식별자를 정해야 합니다."),
        ("entity lifecycle is UNKNOWN", "데이터의 생성·삭제·보존 정책을 확인해야 합니다."),
        ("relationship references an unknown entity", "관계가 가리키는 데이터 객체를 다시 선택해야 합니다."),
        ("changed after", "입력이나 데이터 모델이 변경되어 다시 분석해야 합니다."),
        ("pinned non-latest image", "Docker 이미지는 `latest`나 동적 변수가 아닌 고정 버전이어야 합니다."),
        ("does not match the technology profile", "DB 또는 migration 선택을 승인된 기술 구성과 맞춰야 합니다."),
        ("custom", "기타 선택의 구체적인 내용을 입력해야 합니다."),
        ("secret", "비밀값 대신 환경변수 이름만 기록해야 합니다."),
    )
    return next((message for key, message in mappings if key in value), "데이터 계약의 진행 조건을 다시 확인해야 합니다.")


def render(metadata: dict, model: dict, blockers: list[str], feature: dict | None = None) -> str:
    runtime = model["runtimeProvisioning"]
    strategy_labels = {
        "DOCKER_COMPOSE": "Docker Compose로 로컬 DB 실행", "TESTCONTAINERS": "Testcontainers로 테스트 DB 실행",
        "BOTH": "Docker Compose와 Testcontainers 사용", "EXTERNAL": "외부에서 관리되는 DB 사용",
        "CUSTOM": "사용자 지정 방식", "DEFERRED": "다음 단계에서 결정",
    }
    lines = [
        f"# {model['modelId']} 데이터 설계", "",
        f"<!-- approval-content-sha256: {approval_content_hash(metadata)} -->",
        "<!-- 관계형 data model에서 생성됨. 직접 수정하지 마세요. -->", "",
        "## 이번 기능에서 기억할 데이터", "", f"- 목적: {model['purpose']}",
        f"- 저장소: {model['storeId']}", f"- 향후 물리 원본: {model['physicalArtifactStrategy']}", "",
        "## 데이터 구조", "",
    ]
    for entity in model["entities"]:
        lines.append(f"### {entity['name']}")
        lines.extend(["", f"- 의미: {entity['description']}", f"- 소유: {entity['owner']['projectId']} / {entity['owner']['modulePath']}",
                      f"- 민감도: {entity['sensitivity']}", f"- 생성: {entity['lifecycle']['creation']}",
                      f"- 삭제: {entity['lifecycle']['deletion']}", f"- 보존: {entity['lifecycle']['retention']}", "", "| 필드 | 의미 | 유형 | 필수 | 식별자 | 민감도 |", "|---|---|---|---|---|---|"])
        for field in entity["fields"]:
            lines.append(f"| {field['name']} | {field['description']} | {field['logicalType']} | {'예' if field['required'] else '아니오'} | {'예' if field['identifier'] else '아니오'} | {field['sensitivity']} |")
        if entity["invariants"]:
            lines.extend(["", "업무 규칙:"])
            lines.extend(f"- {rule['description']}" for rule in entity["invariants"])
        lines.append("")
    lines.extend(["## 관계", ""])
    if model["relationships"]:
        lines.extend(f"- {item['fromEntityId']} ({item['fromCardinality']}) → {item['toEntityId']} ({item['toCardinality']}) — {item['description']}" for item in model["relationships"])
    else:
        lines.append("- 현재 기능에는 엔티티 간 관계 없음")
    lines.extend(["", "```mermaid", "erDiagram"])
    for entity in model["entities"]:
        lines.append(f"    {mermaid_name(entity['entityId'])} {{")
        for field in entity["fields"]:
            marker = " PK" if field["identifier"] else ""
            lines.append(f"        {field['logicalType'].lower()} {mermaid_name(field['fieldId'])}{marker}")
        lines.append("    }")
    left_cardinality = {"ONE": "||", "ZERO_OR_ONE": "o|", "ONE_OR_MORE": "}|", "ZERO_OR_MORE": "}o"}
    right_cardinality = {"ONE": "||", "ZERO_OR_ONE": "|o", "ONE_OR_MORE": "|{", "ZERO_OR_MORE": "o{"}
    for item in model["relationships"]:
        connector = left_cardinality[item["fromCardinality"]] + "--" + right_cardinality[item["toCardinality"]]
        lines.append(f"    {mermaid_name(item['fromEntityId'])} {connector} {mermaid_name(item['toEntityId'])} : {mermaid_name(item['relationshipId'])}")
    lines.extend(["```", "", "## 로컬 DB와 테스트 환경", "", f"- 방식: {strategy_labels[runtime['strategy']]}", f"- DB 엔진: {runtime['databaseEngine']}"])
    if runtime["imageReference"]: lines.append(f"- 고정 이미지: `{runtime['imageReference']}`")
    if runtime["customDatabaseEngine"]: lines.append(f"- 사용자 지정 DB: {runtime['customDatabaseEngine']}")
    if runtime["customDescription"]: lines.append(f"- 사용자 지정 실행 방식: {runtime['customDescription']}")
    if runtime["composePath"]: lines.append(f"- 생성 예정 Compose 파일: `{runtime['composePath']}`")
    if runtime["credentialSecretNames"]: lines.append(f"- 필요한 환경변수 이름: {', '.join(runtime['credentialSecretNames'])}")
    lines.append("- 이 승인 단계에서는 컨테이너나 DB를 설치·실행하지 않음")
    lines.extend(["", "## 기능 명세 연결", ""])
    descriptions = {}
    if feature:
        descriptions.update({item["id"]: f"{item['given']}일 때 {item['when']}하면 {item['then']}" for item in feature.get("acceptanceCriteria", [])})
        descriptions.update({item["id"]: item["description"] for item in feature.get("businessRules", [])})
    refs = dict.fromkeys(ref for item in metadata["traceability"] for ref in item["requirementRefs"])
    lines.extend(f"- {descriptions.get(ref, ref)}" for ref in refs)
    lines.extend(["", "## 지금 확인해야 할 사항", ""])
    lines.extend(f"- {item}" for item in dict.fromkeys(blocker_message(blocker) for blocker in blockers)) if blockers else lines.append("- 없음")
    status = "승인 완료" if metadata["approval"]["status"] == "APPROVED" and not blockers else ("결정 확인 필요" if blockers else "승인 대기")
    lines.extend(["", "## 현재 상태", "", f"- {status}", "", "## 다음 행동", ""])
    if blockers:
        lines.extend(["- 추천: 표시된 데이터 결정 보완", "- 항목별 수정", "- 원하는 구조를 직접 설명"])
    else:
        lines.extend(["- 추천: 논리 데이터 계약 승인", "- 항목별 수정", "- 원하는 구조를 직접 설명"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path); parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path); parser.add_argument("--profile", required=True, type=Path); parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path); parser.add_argument("--check", action="store_true"); parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.check and args.force:
        print("RELATIONAL_DATA_MARKDOWN_VALID: no\nERROR: --check and --force cannot be combined"); return 2
    try:
        metadata, route, feature = load_object(args.contract), load_object(args.route), load_object(args.feature)
        _, blockers, model = validate_relational_contract(metadata, route, args.route, args.target, args.contract, feature, load_object(args.profile))
        expected = render(metadata, model, blockers, feature)
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected: raise ValueError("relational data Markdown is stale")
        else: atomic_write(expected, args.output, args.force)
    except (OSError, ValueError) as error:
        print(f"RELATIONAL_DATA_MARKDOWN_VALID: no\nERROR: {error}"); return 1
    print("RELATIONAL_DATA_MARKDOWN_VALID: yes"); return 0


if __name__ == "__main__":
    sys.exit(main())
