#!/usr/bin/env python3
"""Render a concise user view of design-contract metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from render_design_route import KIND_LABELS, atomic_write
from validate_design_contract import load_object, validate


def render(contract: dict, blockers: list[str]) -> str:
    target = contract["target"]
    status = "승인 완료" if contract["approval"]["status"] == "APPROVED" and not blockers else (
        "결정 확인 필요" if blockers else "승인 대기"
    )
    lines = [
        f"# {contract['contractId']} 상세 설계", "",
        "<!-- design contract metadata에서 생성됨. 직접 수정하지 마세요. -->", "",
        "## 설계 대상", "",
        f"- 종류: {KIND_LABELS.get(contract['kind'], contract['kind'])}",
        f"- 처리: {contract['disposition']}",
        f"- 프로젝트: {target['projectId']}",
        f"- 모듈: {target['modulePath']}",
        f"- 표준 형식: {contract['artifact']['format']}",
        f"- 설계 파일: {contract['artifact']['path']}", "",
        "## 기능 연결", "",
    ]
    lines.extend(
        f"- {item.get('subjectRef', 'UNKNOWN')} → {', '.join(item.get('requirementRefs', [])) or '연결 필요'}"
        for item in contract["traceability"] if isinstance(item, dict)
    )
    if not contract["traceability"]:
        lines.append("- 연결 필요")
    lines.extend(["", "## 지금 확인해야 할 사항", ""])
    lines.extend(f"- {blocker}" for blocker in blockers) if blockers else lines.append("- 없음")
    lines.extend(["", "## 현재 상태", "", f"- {status}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.check and args.force:
        print("DESIGN_CONTRACT_MARKDOWN_VALID: no\nERROR: --check and --force cannot be combined")
        return 2
    try:
        contract = load_object(args.contract)
        _, blockers = validate(contract, load_object(args.route), args.route, args.target, args.contract)
        expected = render(contract, blockers)
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected:
                raise ValueError("design contract Markdown is stale")
        else:
            atomic_write(expected, args.output, args.force)
    except (OSError, ValueError) as error:
        print(f"DESIGN_CONTRACT_MARKDOWN_VALID: no\nERROR: {error}")
        return 1
    print("DESIGN_CONTRACT_MARKDOWN_VALID: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
