#!/usr/bin/env python3
"""Render REUSE/EXTEND evidence and compatibility for a beginner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from existing_http_api_contract import validate_existing_contract
from http_api_contract import operations
from render_design_route import atomic_write
from validate_feature_specs import approval_content_hash, load_object


def render(metadata: dict, openapi: dict, report: dict, blockers: list[str]) -> str:
    action = "기존 API 재사용" if metadata["disposition"] == "REUSE" else "기존 API 확장"
    lines = [
        f"# {openapi['info']['title']} — {action}", "",
        f"<!-- approval-content-sha256: {approval_content_hash(metadata)} -->",
        "<!-- OpenAPI evidence와 compatibility report에서 생성됨. 직접 수정하지 마세요. -->", "",
        "## 활용할 API", "",
    ]
    for path, method, operation in operations(openapi):
        lines.append(f"- `{method.upper()} {path}` — {operation['summary']}")
    lines.extend(["", "## 호환성 영향", ""])
    if report["changes"]:
        labels = {"BREAKING": "호환성 깨짐", "REVIEW": "검토 필요", "NON_BREAKING": "호환 유지"}
        messages = {
            "OPERATION_REMOVED": "기존 API가 제거됩니다.", "OPERATION_ADDED": "새 API가 추가됩니다.",
            "ENDPOINT_CHANGED": "기존 경로나 HTTP 방식이 바뀝니다.",
            "REQUIRED_PARAMETER_ADDED": "새 필수 파라미터가 추가됩니다.",
            "RESPONSE_REMOVED": "기존 응답이 제거됩니다.", "SECURITY_REQUIRED": "기존 공개 API에 인증이 새로 필요합니다.",
            "REQUEST_SCHEMA_CHANGED": "요청 형식이 변경됩니다.", "RESPONSE_SCHEMA_CHANGED": "응답 형식이 변경됩니다.",
        }
        for change in report["changes"]:
            lines.append(f"- {labels[change['level']]} · `{change['location']}` — {messages[change['code']]}")
    else:
        lines.append("- 기존 인터페이스 변경 없음")
    lines.extend(["", "## 기능 명세 연결", ""])
    for item in metadata["traceability"]:
        lines.append(f"- `{item['subjectRef']}` → {', '.join(item['requirementRefs'])}")
    lines.extend(["", "## 지금 확인해야 할 사항", ""])
    if blockers:
        messages = []
        for blocker in blockers:
            if "breaking API changes" in blocker:
                messages.append("기존 사용자를 깨뜨리는 변경을 제거하거나 새 버전 API로 분리해야 합니다.")
            elif "unresolved compatibility reviews" in blocker:
                messages.append("요청 형식 변경의 호환성을 확인해야 합니다.")
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
    lines.extend(["", "## 현재 상태", "", f"- {status}", ""])
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
        expected = render(metadata, openapi, report, blockers)
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
