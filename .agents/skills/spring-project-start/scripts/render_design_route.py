#!/usr/bin/env python3
"""Render a user-facing design-routing summary."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from validate_design_route import assess, load_object, validate
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


def user_blocker(blocker: str) -> str:
    exact = {
        "active persistence route must select data stores": "상태 저장에 사용할 데이터 저장소를 선택해야 합니다.",
        "verification route must be CREATE, EXTEND, or REUSE": "테스트와 검증 방법을 반드시 만들거나 기존 것을 활용해야 합니다.",
        "authorized feature requires an active security route": "권한이 있는 기능에는 보안 설계가 필요합니다.",
        "feature input hash is stale": "기능 명세가 변경되어 설계 경로를 다시 확인해야 합니다.",
        "project brief input hash is stale": "프로젝트 개요가 변경되어 설계 경로를 다시 확인해야 합니다.",
        "technology profile input hash is stale": "기술 구성이 변경되어 설계 경로를 다시 확인해야 합니다.",
    }
    if blocker in exact:
        return exact[blocker]
    mappings = (
        ("technology profile:", "기술 구성을 먼저 확정해야 합니다."),
        ("code evidence is missing:", "재사용 근거 파일을 찾을 수 없습니다."),
        ("code evidence is stale:", "재사용 근거 파일이 변경되어 다시 확인해야 합니다."),
        ("code evidence escapes target:", "재사용 근거가 대상 프로젝트 밖을 가리킵니다."),
        ("route target project is not in technology profile:", "대상 프로젝트를 기술 구성에서 다시 선택해야 합니다."),
        ("route references unknown data store:", "대상 데이터 저장소를 기술 구성에서 다시 선택해야 합니다."),
        ("REUSE requires code evidence:", "기존 설계를 재사용하려면 실제 코드 근거가 필요합니다."),
        ("EXTEND requires code evidence:", "기존 설계를 확장하려면 실제 코드 근거가 필요합니다."),
        ("CREATE requires artifactPath:", "새 설계 문서의 위치를 정해야 합니다."),
        ("EXTEND requires artifactPath:", "확장할 설계 문서의 위치를 정해야 합니다."),
        ("required design cannot be", "필수 설계를 생략하거나 보류할 수 없습니다."),
        ("unused design must be NOT_NEEDED:", "사용하지 않는 설계는 필요 없음으로 정리해야 합니다."),
        ("deferred design must remain DEFERRED:", "보류한 설계는 이번 단계에서 진행할 수 없습니다."),
        ("active routes share artifactPath:", "여러 설계가 같은 문서 위치를 사용하고 있습니다."),
        ("input path does not match the manifest", "입력 문서 위치가 기록된 경로와 다릅니다."),
        ("input escapes target", "입력 문서가 대상 프로젝트 밖을 가리킵니다."),
        ("route modulePath escapes target:", "대상 모듈이 프로젝트 밖을 가리킵니다."),
        ("route artifactPath escapes target:", "설계 문서 위치가 프로젝트 밖을 가리킵니다."),
        ("input hash is UNKNOWN:", "입력 문서의 현재 상태를 확인해야 합니다."),
    )
    for prefix, message in mappings:
        if prefix in blocker:
            return message
    return "설계 진행 조건을 다시 확인해야 합니다."


def route_status(route: dict, blockers: list[str]) -> str:
    if route["approval"]["status"] == "APPROVED" and not blockers:
        return "승인 완료"
    drift_terms = ("stale", "changed", "does not match", "missing", "escapes target")
    if any(any(term in blocker for term in drift_terms) for blocker in blockers):
        return "입력 변경으로 재검토 필요"
    if blockers and route["approval"]["status"] == "DRAFT":
        return "초안 작성 중"
    if blockers:
        return "결정 확인 필요"
    return "승인 대기"


def render(
    route: dict, feature: dict, project: dict, profile: dict, detail: str = "basic",
    runtime_blockers: list[str] | None = None,
) -> str:
    _, structural_blockers = validate(route, feature, project, profile)
    blockers = structural_blockers if runtime_blockers is None else runtime_blockers
    active = [item for item in route["routes"] if item["disposition"] in {"CREATE", "EXTEND", "REUSE"}]
    immediate = [item for item in route["routes"] if item["disposition"] == "UNKNOWN"]
    immediate.extend(
        item for item in route["routes"]
        if item["source"] in {"RECOMMENDED", "INFERRED"} and not item["confirmedByUser"]
        and item not in immediate
    )
    represented_prefixes = (
        "route disposition is UNKNOWN:", "route reason or source is UNKNOWN:",
        "AI-proposed route is not user-confirmed:",
    )
    gate_questions = [
        user_blocker(blocker) for blocker in blockers
        if not blocker.startswith(represented_prefixes)
    ]
    gate_questions = list(dict.fromkeys(gate_questions))
    deferred = [item for item in route["routes"] if item["disposition"] == "DEFERRED"]
    lines = [
        f"# {feature['feature']['name']} 설계 경로", "",
        f"<!-- approval-content-sha256: {approval_content_hash(route)} -->",
        "<!-- design-route.json에서 생성됨. 직접 수정하지 마세요. -->", "",
        "## 이번에 만들거나 활용할 설계", "",
    ]
    kind_counts = {kind: sum(item["kind"] == kind for item in route["routes"]) for kind in KIND_LABELS}
    def label(item: dict) -> str:
        suffix = f" ({item['contractId']})" if kind_counts[item["kind"]] > 1 else ""
        return KIND_LABELS[item["kind"]] + suffix
    lines.extend(
        f"- {label(item)} — {DISPOSITION_LABELS[item['disposition']]} · {item['reason']}"
        for item in active
    )
    if not active:
        lines.append("- 없음")
    lines.extend(["", "## 지금 확인해야 할 사항", ""])
    lines.extend(
        [f"- {label(item)} — {item['reason']}" for item in immediate]
        + [f"- {item}" for item in gate_questions]
        or ["- 없음"]
    )
    lines.extend(["", "## 나중에 설계할 사항", ""])
    lines.extend(
        [f"- {label(item)} — {item['reason']}" for item in deferred]
        or ["- 없음"]
    )
    lines.extend(["", "## 현재 상태", "", f"- {route_status(route, blockers)}"])
    if detail == "full":
        lines.extend(["", "## 개발자 상세", ""])
        for item in route["routes"]:
            target = item["target"]
            identity = item.get("contractId", item["kind"])
            lines.append(
                f"- {item['kind']} · contract={identity} · {item['disposition']} · project={target['projectId']} "
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
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--detail", choices=("basic", "full"), default="basic")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.check and args.force:
        print("DESIGN_ROUTE_MARKDOWN_VALID: no\nERROR: --check and --force cannot be combined")
        return 2
    try:
        route = load_object(args.route)
        feature = load_object(args.feature)
        project = load_object(args.project_brief)
        profile = load_object(args.profile)
        _, _, blockers = assess(
            route, feature, project, profile,
            args.feature, args.project_brief, args.profile, args.target,
        )
        expected = render(route, feature, project, profile, args.detail, blockers)
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
