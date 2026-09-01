#!/usr/bin/env python3
"""Render a user-first view of a Spring implementation plan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from render_design_route import atomic_write
from spring_implementation_plan import validate
from validate_feature_specs import load_object


def render(plan: dict, blockers: list[str]) -> str:
    flow = plan["userFlow"]
    summary = plan["summary"]
    lines = [
        f"# {flow['name']} 구현 계획",
        "",
        "## 사용자 기능 흐름",
        "",
        f"- 시작: {flow['trigger']}",
    ]
    lines.extend(f"- {index}. {step}" for index, step in enumerate(flow["steps"], 1))
    lines.extend([
        f"- 결과: {flow['outcome']}",
        "",
        "## 구현 준비",
        "",
        f"- 생성 {summary['create']} · 재사용 {summary['reuse']} · 보류 {summary['defer']} · 충돌 {len(plan['conflicts'])}",
        f"- 자동화 테스트 component: {summary['automatedTests']}",
        f"- 지원 판정: {plan['capability']['status']}",
        f"- 상태: {plan['status']}",
        "",
        "## 트랜잭션과 오류",
        "",
        f"- 쓰기 transaction: {sum(item['transaction']['required'] and not item['transaction']['readOnly'] for item in plan['components'])}개",
        f"- HTTP 오류 mapping: {len(plan['errorMappings'])}개",
        "",
        "## 요구사항 coverage",
        "",
    ])
    lines.extend(
        f"- {item['requirementRef']} → 구현 {len(item['enforcedBy'])} · 검증 {len(item['verifiedBy'])}"
        for item in plan["coverage"]
    )
    lines.extend(["", "## 충돌과 다음 행동", ""])
    if plan["conflicts"]:
        for item in plan["conflicts"]:
            lines.extend([f"- {item['message']}", f"  - 추천: {' / '.join(item['recommendedActions'])}"])
    else:
        lines.append("- 없음")
    if blockers:
        lines.extend(["", "### 검증 차단 사유", ""])
        lines.extend(f"- {item}" for item in blockers)
    lines.extend(["", "## 상세 component", ""])
    for item in plan["components"]:
        lines.append(f"- {item['kind']} · {item['disposition']} · `{item['target']['plannedPath']}`")
    lines.extend([
        "",
        "## 승인 효과",
        "",
        "- 다음 code dry-run 준비만 허용",
        "- Java source·build·설정 파일 생성 또는 수정 안 함",
        "- 테스트 실행, commit, push 허용 안 함",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        root = args.target.resolve(strict=True)
        plan = load_object(args.plan)
        blockers = validate(plan, root)
        expected = render(plan, blockers)
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected:
                raise ValueError("implementation plan Markdown is stale")
        else:
            output = args.output.resolve(strict=False)
            if root not in output.parents:
                raise ValueError("implementation plan Markdown output must be target-owned")
            atomic_write(expected, output, args.force)
    except (OSError, ValueError, KeyError) as error:
        print(f"SPRING_IMPLEMENTATION_PLAN_MARKDOWN_VALID: no\nERROR: {error}")
        return 1
    print("SPRING_IMPLEMENTATION_PLAN_MARKDOWN_VALID: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
