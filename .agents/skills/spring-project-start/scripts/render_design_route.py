#!/usr/bin/env python3
"""Render a user-facing design-routing summary."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from validate_design_route import load_object, validate
from validate_feature_specs import approval_content_hash


KIND_LABELS = {
    "HTTP_API": "웹 API", "PERSISTENCE": "상태 저장", "MESSAGING": "메시징",
    "SCHEDULED_JOB": "예약 작업", "SERVER_UI": "서버 화면",
    "CLIENT_INTEGRATION": "별도 클라이언트 연결", "EXTERNAL_INTEGRATION": "외부 연동",
    "SECURITY": "보안과 권한", "VERIFICATION": "테스트와 검증",
}
DISPOSITION_LABELS = {
    "CREATE": "새로 설계", "EXTEND": "기존 설계 확장", "REUSE": "기존 설계 재사용",
    "NOT_NEEDED": "필요 없음", "DEFERRED": "나중에 설계", "UNKNOWN": "확인 필요",
}


def render(route: dict, feature: dict, project: dict, profile: dict, detail: str = "basic") -> str:
    _, blockers = validate(route, feature, project, profile)
    active = [item for item in route["routes"] if item["disposition"] in {"CREATE", "EXTEND", "REUSE"}]
    immediate = [item for item in route["routes"] if item["disposition"] == "UNKNOWN"]
    immediate.extend(
        item for item in route["routes"]
        if item["source"] in {"RECOMMENDED", "INFERRED"} and not item["confirmedByUser"]
        and item not in immediate
    )
    deferred = [item for item in route["routes"] if item["disposition"] == "DEFERRED"]
    lines = [
        f"# {feature['feature']['name']} 설계 경로", "",
        f"<!-- approval-content-sha256: {approval_content_hash(route)} -->",
        "<!-- design-route.json에서 생성됨. 직접 수정하지 마세요. -->", "",
        "## 이번에 만들거나 활용할 설계", "",
    ]
    lines.extend(
        f"- {KIND_LABELS[item['kind']]} — {DISPOSITION_LABELS[item['disposition']]} · {item['reason']}"
        for item in active
    )
    if not active:
        lines.append("- 없음")
    lines.extend(["", "## 지금 확인해야 할 사항", ""])
    lines.extend(
        [f"- {KIND_LABELS[item['kind']]} — {item['reason']}" for item in immediate]
        or ["- 없음"]
    )
    lines.extend(["", "## 나중에 설계할 사항", ""])
    lines.extend(
        [f"- {KIND_LABELS[item['kind']]} — {item['reason']}" for item in deferred]
        or ["- 없음"]
    )
    lines.extend(["", "## 현재 상태", "", f"- {'승인됨' if route['approval']['status'] == 'APPROVED' else '확인 필요'}"])
    if detail == "full":
        lines.extend(["", "## 개발자 상세", ""])
        for item in route["routes"]:
            target = item["target"]
            lines.append(
                f"- {item['kind']} · {item['disposition']} · project={target['projectId']} "
                f"· module={target['modulePath']} · stores={','.join(target['dataStoreIds']) or '-'}"
            )
        for blocker in blockers:
            lines.append(f"- BLOCKER · {blocker}")
    lines.append("")
    return "\n".join(lines)


def atomic_write(content: str, output: Path, force: bool) -> None:
    if output.exists() and not force:
        raise ValueError(f"output already exists; use --force to regenerate it: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--detail", choices=("basic", "full"), default="basic")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.check and args.force:
        print("DESIGN_ROUTE_MARKDOWN_VALID: no\nERROR: --check and --force cannot be combined")
        return 2
    try:
        expected = render(
            load_object(args.route), load_object(args.feature),
            load_object(args.project_brief), load_object(args.profile), args.detail,
        )
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected:
                raise ValueError("design route Markdown is stale")
        else:
            atomic_write(expected, args.output, args.force)
    except (OSError, ValueError) as error:
        print(f"DESIGN_ROUTE_MARKDOWN_VALID: no\nERROR: {error}")
        return 1
    print("DESIGN_ROUTE_MARKDOWN_VALID: yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
