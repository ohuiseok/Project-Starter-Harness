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
        f"- 구조 검사: 통과 {passed} · 실패 {failed}",
        f"- 승인 검토 가능: {'예' if report['readyForApproval'] else '아니요'}",
        "- 대상 source 변경: 없음", "- 컴파일·테스트: 실행하지 않음", "", "## 충돌과 해결", "",
    ])
    if changes["conflicts"]:
        lines.extend(f"- `{item.get('path') or '전체'}`: {item['reason']}" for item in changes["conflicts"])
    else:
        lines.append("- 없음")
    lines.extend(["", "## 생성될 코드", ""])
    for item in report["generatedFiles"]:
        lines.extend([f"### {item['kind']} · `{item['path']}`", "", "```java", item["content"].rstrip(), "```", ""])
    lines.extend(["## 승인 효과", "", "- 다음 원자적 apply 준비만 허용", "- 아직 파일 적용·컴파일·테스트·commit·push를 허용하지 않음", ""])
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
