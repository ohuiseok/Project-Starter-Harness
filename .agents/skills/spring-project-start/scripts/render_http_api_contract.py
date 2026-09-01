#!/usr/bin/env python3
"""Render a beginner-facing summary from OpenAPI, not duplicated metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from http_api_contract import operations, validate_http_contract
from render_design_route import atomic_write
from validate_feature_specs import approval_content_hash, load_object


def user_blocker(blocker: str) -> str:
    mappings = (
        ("operation has no requirement traceability", "기능 요구사항과 연결되지 않은 API가 있습니다."),
        ("operation references unknown feature requirements", "존재하지 않는 기능 요구사항을 참조한 API가 있습니다."),
        ("acceptance criteria are not covered", "API에 반영되지 않은 인수 조건이 있습니다."),
        ("business rules are not covered", "API에 연결되지 않은 업무 규칙이 있습니다."),
        ("feature failure cases have no API error response", "기능의 실패 상황에 대응하는 오류 응답이 필요합니다."),
        ("security.none", "보안 없음 선택과 API 인증 설정이 일치하지 않습니다."),
        ("security.session", "세션 인증 선택과 API 보안 설정이 일치하지 않습니다."),
        ("security.token", "토큰 인증 선택과 API 보안 설정이 일치하지 않습니다."),
        ("security.oidc", "OIDC 선택과 API 보안 설정이 일치하지 않습니다."),
        ("authorized operation must describe", "권한이 있는 각 API에는 401과 403 응답이 모두 필요합니다."),
        ("path parameters do not match", "API 경로 변수와 파라미터 정의가 일치하지 않습니다."),
        ("unknown security scheme", "API가 존재하지 않는 인증 방식을 참조합니다."),
        ("contract traceability does not match", "OpenAPI와 기능 연결 기록이 달라 다시 생성해야 합니다."),
        ("design route changed", "설계 경로가 변경되어 API 계약을 다시 확인해야 합니다."),
    )
    for prefix, message in mappings:
        if prefix in blocker:
            return message
    return "API 계약의 진행 조건을 다시 확인해야 합니다."


def render(metadata: dict, openapi: dict, blockers: list[str]) -> str:
    lines = [
        f"# {openapi['info']['title']} API 계약", "",
        f"<!-- approval-content-sha256: {approval_content_hash(metadata)} -->",
        f"<!-- openapi-sha256: {hashlib.sha256((json.dumps(openapi, ensure_ascii=False, indent=2) + chr(10)).encode()).hexdigest()} -->",
        "<!-- OpenAPI와 metadata.json에서 생성됨. 직접 수정하지 마세요. -->", "",
        "## 이번에 제공할 기능", "",
    ]
    for path, method, operation in operations(openapi):
        security = operation.get("security", openapi.get("security"))
        auth = "인증 필요" if security else "인증 없음"
        lines.append(f"- `{method.upper()} {path}` — {operation['summary']} · {auth}")
    lines.extend(["", "## 응답과 실패", ""])
    for path, method, operation in operations(openapi):
        responses = ", ".join(
            f"{code} {response.get('description', '')}" for code, response in operation["responses"].items()
        )
        lines.append(f"- `{method.upper()} {path}` — {responses}")
    lines.extend(["", "## 기능 명세 연결", ""])
    for item in metadata["traceability"]:
        lines.append(f"- `{item['subjectRef']}` → {', '.join(item['requirementRefs'])}")
    lines.extend(["", "## 지금 확인해야 할 사항", ""])
    questions = list(dict.fromkeys(user_blocker(blocker) for blocker in blockers))
    lines.extend(f"- {question}" for question in questions) if questions else lines.append("- 없음")
    approved = metadata["approval"]["status"] == "APPROVED"
    status = "승인 완료" if approved and not blockers else ("결정 확인 필요" if blockers else "승인 대기")
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
        print("HTTP_API_MARKDOWN_VALID: no\nERROR: --check and --force cannot be combined")
        return 2
    try:
        metadata = load_object(args.contract)
        _, blockers, openapi = validate_http_contract(
            metadata, load_object(args.route), args.route, args.target, args.contract,
            load_object(args.feature), load_object(args.profile),
        )
        expected = render(metadata, openapi, blockers)
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected:
                raise ValueError("HTTP API contract Markdown is stale")
        else:
            atomic_write(expected, args.output, args.force)
    except (OSError, ValueError) as error:
        print(f"HTTP_API_MARKDOWN_VALID: no\nERROR: {error}")
        return 1
    print("HTTP_API_MARKDOWN_VALID: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
