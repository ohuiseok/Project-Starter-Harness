#!/usr/bin/env python3
"""Render the user view for a Spring code dry-run report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from render_design_route import atomic_write
from spring_code_dry_run import validate_report
from validate_feature_specs import load_object


def render(report: dict) -> str:
    flow = report["userFlow"]
    changes = report["plannedChanges"]
    passed = sum(item["state"] == "PASSED" for item in report["qualityChecks"])
    failed = sum(item["state"] == "FAILED" for item in report["qualityChecks"])
    contract = report["contractSummary"]
    reasons = {
        "planned-component-is-missing": ("계획된 코드가 빠졌습니다.", "누락된 component를 생성하고 다시 검토"),
        "file-is-not-in-approved-plan": ("승인 계획에 없는 파일이 포함됐습니다.", "계획을 다시 승인하거나 추가 파일 제거"),
        "existing-content-has-no-matching-baseline": ("사용자 소유 파일과 충돌합니다.", "기존 구조를 분석해 EXTEND 계획으로 재작성"),
        "jpa-entity-crosses-api-boundary": ("JPA Entity가 API 경계를 넘습니다.", "요청·응답 DTO로 분리"),
        "test-has-no-executable-assertion": ("테스트에 실행 가능한 검증문이 없습니다.", "행동과 결과를 확인하는 assertion 추가"),
        "hardcoded-secret-like-literal": ("하드코딩된 비밀값 후보가 있습니다.", "환경 변수 또는 secret binding 사용"),
    }
    lines = [
        f"# {flow['name']} 코드 dry-run",
        "",
        "## 사용자 기능 흐름",
        "",
        f"- 시작: {flow['trigger']}",
    ]
    lines.extend(f"- {index}. {step}" for index, step in enumerate(flow["steps"], 1))
    lines.extend([
        f"- 결과: {flow['outcome']}", "", "## 검토 결론", "",
        f"- 생성 {len(changes['creates'])} · 변경 {len(changes['updates'])} · 그대로 {len(changes['unchanged'])} · 충돌 {len(changes['conflicts'])}",
        f"- 정적 계약 검사: 통과 {passed} · 실패 {failed}",
        f"- 격리 검증 승인 준비: {'예' if report['readyForApproval'] else '아니요'}",
        "- 대상 source 변경: 없음", "- 컴파일·테스트: 아직 실행하지 않음", "",
        "## 계약 구현 요약", "", f"- API: `{contract['httpMethod']} {contract['httpPath']}`", f"- 저장 table: `{contract['table']}`", f"- 요구사항: {', '.join(contract['requirements'])}", "", "## 충돌과 해결", "",
    ])
    if changes["conflicts"]:
        for item in changes["conflicts"]:
            key = item["reason"].split(":", 1)[0]
            message, action = reasons.get(key, (item["reason"], "해당 component 계약을 확인하고 다시 dry-run"))
            lines.extend([f"- `{item.get('path') or '전체'}`: {message}", f"  - 해결: {action}"])
    else:
        lines.append("- 없음")
    lines.extend(["", "## 생성될 코드 상세", "", "필요할 때만 펼쳐서 확인합니다.", ""])
    for item in report["generatedFiles"]:
        lines.extend(["<details>", f"<summary>{item['kind']} · <code>{item['path']}</code></summary>", "", "```java", item["content"].rstrip(), "```", "", "</details>", ""])
    lines.extend(["## 승인 효과", "", "- 다음 격리 컴파일·테스트 실행만 허용", "- 파일 적용·commit·push는 계속 허용하지 않음", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        root = args.target.resolve(strict=True)
        report_path = args.report.resolve(strict=True)
        output_path = args.output.resolve(strict=False)
        if not root.is_dir() or args.target.is_symlink() or root not in report_path.parents or root not in output_path.parents or args.report.is_symlink() or args.output.is_symlink():
            raise ValueError("report or Markdown output is not safely target-owned")
        report = load_object(args.report)
        validate_report(report, root)
        expected = render(report)
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected:
                raise ValueError("Spring code dry-run Markdown is stale")
        else:
            atomic_write(expected, output_path, args.force)
    except (OSError, ValueError, KeyError) as error:
        print(f"SPRING_CODE_DRY_RUN_MARKDOWN_VALID: no\nERROR: {error}")
        return 1
    print("SPRING_CODE_DRY_RUN_MARKDOWN_VALID: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
