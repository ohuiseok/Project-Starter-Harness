#!/usr/bin/env python3
"""Render REUSE/EXTEND evidence and compatibility for a beginner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from existing_http_api_contract import validate_existing_contract
from http_api_contract import operations
from render_design_route import atomic_write
from validate_feature_specs import approval_content_hash, load_object


def compact(value: object) -> str:
    if value is None:
        return "없음"
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return rendered if len(rendered) <= 180 else rendered[:177] + "..."


def differences(before: object, after: object, prefix: str = "") -> list[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in before:
                result.append(f"{path}: 없음 → {compact(after[key])}")
            elif key not in after:
                result.append(f"{path}: {compact(before[key])} → 없음")
            else:
                result.extend(differences(before[key], after[key], path))
        return result
    return [] if before == after else [f"{prefix or '값'}: {compact(before)} → {compact(after)}"]


def render(metadata: dict, openapi: dict, report: dict, blockers: list[str], feature: dict | None = None) -> str:
    action = "기존 API 재사용" if metadata["disposition"] == "REUSE" else "기존 API 확장"
    lines = [
        f"# {openapi['info']['title']} — {action}", "",
        f"<!-- approval-content-sha256: {approval_content_hash(metadata)} -->",
        "<!-- OpenAPI evidence와 compatibility report에서 생성됨. 직접 수정하지 마세요. -->", "",
        "## 활용할 API", "",
    ]
    selected = set(metadata.get("selectedOperations", []))
    for path, method, operation in operations(openapi):
        if operation["operationId"] not in selected:
            continue
        lines.append(f"- `{method.upper()} {path}` — {operation['summary']}")
    hidden = len(operations(openapi)) - len(selected)
    if hidden > 0:
        lines.append(f"- 현재 기능과 무관한 기존 API {hidden}개는 기본 화면에서 생략")
    lines.extend(["", "## 호환성 영향", ""])
    if report["changes"]:
        labels = {"BREAKING": "호환성 깨짐", "SECURITY": "보안 위험", "UNKNOWN": "확인 불가", "REVIEW": "검토 필요", "NON_BREAKING": "호환 유지"}
        messages = {
            "OPERATION_REMOVED": "기존 API가 제거됩니다.", "OPERATION_ADDED": "새 API가 추가됩니다.",
            "ENDPOINT_CHANGED": "기존 경로나 HTTP 방식이 바뀝니다.",
            "REQUIRED_PARAMETER_ADDED": "새 필수 파라미터가 추가됩니다.",
            "RESPONSE_REMOVED": "기존 응답이 제거됩니다.", "SECURITY_REQUIRED": "기존 공개 API에 인증이 새로 필요합니다.",
            "SECURITY_REMOVED": "기존 인증이 제거됩니다.", "SECURITY_CHANGED": "인증 방식이나 권한 범위가 변경됩니다.",
            "SECURITY_SCOPE_ADDED": "추가 권한 범위가 필요해집니다.",
            "EXTERNAL_REF_UNRESOLVED": "외부 schema 참조의 실제 내용을 확인할 수 없습니다.",
            "REQUEST_SCHEMA_CHANGED": "요청 형식이 변경됩니다.", "RESPONSE_SCHEMA_CHANGED": "응답 형식이 변경됩니다.",
        }
        impacts = {
            "OPERATION_REMOVED": "기존 클라이언트가 이 기능을 호출할 수 없게 됩니다.",
            "OPERATION_ADDED": "기존 클라이언트에는 영향이 없습니다.",
            "ENDPOINT_CHANGED": "기존 주소나 호출 방식으로는 요청이 실패합니다.",
            "REQUIRED_PARAMETER_ADDED": "기존 요청이 필수값 부족으로 거절될 수 있습니다.",
            "RESPONSE_REMOVED": "기존 클라이언트의 응답 처리가 깨질 수 있습니다.",
            "SECURITY_REQUIRED": "인증 없이 호출하던 기존 클라이언트가 실패합니다.",
            "SECURITY_REMOVED": "보호되던 기능이 공개될 수 있습니다.",
            "SECURITY_CHANGED": "인증 또는 권한 정책이 달라집니다.",
            "SECURITY_SCOPE_ADDED": "기존 토큰의 권한으로 호출하지 못할 수 있습니다.",
            "REQUEST_SCHEMA_CHANGED": "기존 요청의 성공 여부가 달라질 수 있습니다.",
            "RESPONSE_SCHEMA_CHANGED": "기존 응답 파싱이나 화면 표시가 깨질 수 있습니다.",
            "EXTERNAL_REF_UNRESOLVED": "현재 증거만으로 호환성을 판단할 수 없습니다.",
        }
        recommendations = {
            "OPERATION_ADDED": "새 API에 대한 계약 테스트를 추가하세요.",
            "SECURITY_REMOVED": "보안 정책을 다시 확인하고 공개 전환을 별도로 승인하세요.",
            "SECURITY_CHANGED": "인증 방식과 권한 범위를 별도 보안 결정으로 검토하세요.",
            "EXTERNAL_REF_UNRESOLVED": "외부 schema를 고정된 로컬 증거로 가져오세요.",
        }
        for change in report["changes"]:
            lines.append(f"- {labels[change['level']]} · `{change['location']}` — {messages[change['code']]}")
            change_differences = differences(change["before"], change["after"])
            if change_differences:
                lines.extend(f"  - 차이: {item}" for item in change_differences[:8])
            else:
                lines.append(f"  - 변경 전: {compact(change['before'])}")
                lines.append(f"  - 변경 후: {compact(change['after'])}")
            lines.append(f"  - 영향: {impacts[change['code']]}")
            default_recommendation = "기존 동작을 유지하거나 새 버전 API로 분리하세요."
            lines.append(f"  - 추천: {recommendations.get(change['code'], default_recommendation)}")
    else:
        lines.append("- 기존 인터페이스 변경 없음")
    lines.extend(["", "## 기능 명세 연결", ""])
    for item in metadata["traceability"]:
        lines.append(f"- `{item['subjectRef']}`")
        descriptions = {}
        if feature:
            descriptions.update({criterion["id"]: f"{criterion['given']}일 때 {criterion['when']}하면 {criterion['then']}" for criterion in feature.get("acceptanceCriteria", [])})
            descriptions.update({rule["id"]: rule["description"] for rule in feature.get("businessRules", [])})
        for reference in item["requirementRefs"]:
            lines.append(f"  - {descriptions.get(reference, reference)}")
    lines.extend(["", "## 수용한 검토 위험", ""])
    accepted = [item for item in metadata.get("compatibilityReviews", []) if item["status"] == "ACCEPTED"]
    if accepted:
        for item in accepted:
            lines.append(f"- `{item['reviewId']}` — {item['reason']}")
    else:
        lines.append("- 없음")
    lines.extend(["", "## 지금 확인해야 할 사항", ""])
    if blockers:
        messages = []
        for blocker in blockers:
            if "breaking API changes" in blocker:
                messages.append("기존 사용자를 깨뜨리는 변경을 제거하거나 새 버전 API로 분리해야 합니다.")
            elif "unresolved compatibility reviews" in blocker:
                messages.append("검토 필요 변경의 영향과 이유를 확인해야 합니다.")
            elif "security regression" in blocker:
                messages.append("인증이나 권한이 약해지는 변경은 별도 보안 결정 없이 진행할 수 없습니다.")
            elif "compatibility is UNKNOWN" in blocker:
                messages.append("외부 schema의 현재 내용을 확인할 증거가 필요합니다.")
            elif "controller evidence" in blocker:
                messages.append("기존 Controller가 이 API를 실제로 제공하는지 확인할 수 없습니다.")
            elif "changed after assessment" in blocker:
                messages.append("기존 API 증거가 변경되어 다시 분석해야 합니다.")
            else:
                messages.append("기존 API 계약의 진행 조건을 다시 확인해야 합니다.")
        lines.extend(f"- {message}" for message in dict.fromkeys(messages))
    else:
        lines.append("- 없음")
    status = "승인 완료" if metadata["approval"]["status"] == "APPROVED" and not blockers else (
        "결정 확인 필요" if blockers else "승인 대기"
    )
    lines.extend(["", "## 현재 상태", "", f"- {status}", "", "## 다음 행동", ""])
    if blockers:
        lines.extend(["- 추천: 차단된 변경을 수정하거나 새 버전 API로 분리", "- 항목별 변경 검토", "- 원하는 해결 방식을 직접 설명"])
    else:
        lines.extend([f"- 추천: {action} 승인", "- 항목별 수정", "- 원하는 방식을 직접 설명"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.check and args.force:
        print("EXISTING_HTTP_API_MARKDOWN_VALID: no\nERROR: --check and --force cannot be combined")
        return 2
    try:
        metadata = load_object(args.contract)
        _, blockers, openapi, report = validate_existing_contract(
            metadata, load_object(args.route), args.route, args.target, args.contract,
            load_object(args.feature), load_object(args.profile),
        )
        expected = render(metadata, openapi, report, blockers, load_object(args.feature))
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected:
                raise ValueError("existing HTTP API Markdown is stale")
        else:
            atomic_write(expected, args.output, args.force)
    except (OSError, ValueError) as error:
        print(f"EXISTING_HTTP_API_MARKDOWN_VALID: no\nERROR: {error}")
        return 1
    print("EXISTING_HTTP_API_MARKDOWN_VALID: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
