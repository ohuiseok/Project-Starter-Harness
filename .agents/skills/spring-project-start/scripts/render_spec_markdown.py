#!/usr/bin/env python3
"""Render deterministic user-facing Markdown from a structured specification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from validate_feature_specs import (
    approval_content_hash,
    load_object,
    validate_feature,
    validate_project,
)


STATUS_LABELS = {
    "DRAFT": "초안",
    "REVIEW_REQUIRED": "확인 필요",
    "APPROVED": "승인됨",
    "IMPLEMENTING": "구현 중",
    "VERIFIED": "검증 완료",
    "DEFERRED": "나중에 진행",
}
SOURCE_LABELS = {
    "USER_STATED": "사용자가 말한 내용",
    "PROJECT_EVIDENCE": "프로젝트에서 확인한 내용",
    "RECOMMENDED": "하네스 추천",
    "INFERRED": "하네스 추론",
    "UNKNOWN": "출처 확인 필요",
}
DESIGN_LABELS = {
    "httpApi": "웹 API",
    "persistentState": "지속적인 상태 저장",
    "messaging": "메시지 송수신",
    "scheduledJob": "예약 또는 반복 작업",
    "serverRenderedUi": "서버 렌더링 화면",
    "separateClient": "별도 클라이언트",
    "externalIntegration": "외부 시스템 연동",
}
DESIGN_STATUS_LABELS = {
    "REQUIRED": "필요",
    "NOT_USED": "사용하지 않음",
    "DEFERRED": "나중에 결정",
    "UNKNOWN": "확인 필요",
}


def canonical_hash(document: dict[str, Any]) -> str:
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def bullets(values: list[str], empty: str = "없음") -> list[str]:
    return [f"- {value}" for value in values] if values else [f"- {empty}"]


def rule_label(rule: dict[str, Any]) -> str:
    label = SOURCE_LABELS[rule["source"]]
    if rule["source"] in {"RECOMMENDED", "INFERRED"}:
        label += " · " + ("사용자 확인 완료" if rule["confirmedByUser"] else "사용자 확인 필요")
    return label


def design_requirement_blocks(decision: dict[str, Any]) -> bool:
    return (
        decision["status"] == "UNKNOWN"
        or decision["reason"] == "UNKNOWN"
        or decision["source"] == "UNKNOWN"
        or (decision["source"] in {"RECOMMENDED", "INFERRED"} and not decision["confirmedByUser"])
    )


def render_project(document: dict[str, Any], detail: str = "basic") -> str:
    validate_project(document)
    project = document["project"]
    scope = document["scope"]
    candidates = sorted(document["featureCandidates"], key=lambda item: item["recommendedOrder"])
    blocking = [item for item in document["unknowns"] if item["blocking"] and item["status"] != "RESOLVED"]
    later = [item for item in document["unknowns"] if not item["blocking"] and item["status"] != "RESOLVED"]
    candidate_status = {item["id"]: item["status"] for item in candidates}
    unknown_status = {item["id"]: item["status"] for item in document["unknowns"]}
    eligible = [
        item for item in candidates
        if item["status"] in {"DRAFT", "REVIEW_REQUIRED", "APPROVED"}
        and all(candidate_status[dependency] == "VERIFIED" for dependency in item["dependsOn"])
        and all(unknown_status[unknown] == "RESOLVED" for unknown in item["blockingUnknownIds"])
    ]
    lines = [
        "# 프로젝트 개요",
        "",
        f"<!-- spec-source-sha256: {canonical_hash(document)} -->",
        f"<!-- approval-content-sha256: {approval_content_hash(document)} -->",
        "<!-- project-brief.json에서 생성됨. 직접 수정하지 마세요. -->",
        "",
        "## 제가 이해한 목표",
        "",
        project["goal"],
        "",
        "## 주요 사용자",
        "",
        *bullets(project["targetUsers"]),
        "",
        "## 성공 기준",
        "",
        *bullets(project["successCriteria"]),
        "",
        "## 비기능 요구사항",
        "",
        *bullets(project["nonFunctionalRequirements"]),
        "",
        "## 포함 범위",
        "",
        *bullets(scope["included"]),
        "",
        "## 제외 범위",
        "",
        *bullets(scope["excluded"]),
        "",
        "## 핵심 기능 후보",
        "",
    ]
    lines.extend(
        f"- {item['name']} — {item['userValue']}"
        for item in candidates
    )
    if not candidates:
        lines.append("- 없음")
    lines.extend(["", "## 추천 다음 기능", ""])
    if eligible:
        first = eligible[0]
        lines.append(f"- {first['name']} — {first['userValue']}")
        lines.append(f"- 추천 이유: {first['recommendationReason']}")
    else:
        lines.append("- 현재 추천할 다음 기능 없음")
    lines.extend(["", "## 지금 확인해야 할 사항", ""])
    lines.extend(
        [f"- {item['question']} — 이 결정의 영향: {item['impact']}" for item in blocking]
        or ["- 없음"]
    )
    lines.extend(["", "## 나중에 결정 가능한 사항", ""])
    lines.extend(
        [f"- {item['question']}" for item in later]
        or ["- 없음"]
    )
    lines.extend(["", "## 현재 상태", "", f"- {STATUS_LABELS[document['approval']['status']]}", ""])
    if detail == "full":
        lines.extend(["## 개발자 상세", ""])
        lines.extend(
            f"- {item['id']} · {STATUS_LABELS[item['status']]} · 순서 {item['recommendedOrder']}"
            for item in candidates
        )
        lines.append("")
    return "\n".join(lines)


def render_feature(
    document: dict[str, Any],
    project: dict[str, Any] | None = None,
    detail: str = "basic",
) -> str:
    validate_feature(document, project)
    feature = document["feature"]
    scenario = document["scenario"]
    requirements = document["designRequirements"]
    required = [
        f"{DESIGN_LABELS[name]} — {decision['reason']}"
        for name, decision in requirements.items() if decision["status"] == "REQUIRED"
    ]
    deferred_design = [
        f"{DESIGN_LABELS[name]} — {decision['reason']}"
        for name, decision in requirements.items()
        if decision["status"] == "DEFERRED" and not design_requirement_blocks(decision)
    ]
    design_questions = [
        f"{DESIGN_LABELS[name]} — {decision['reason']}"
        for name, decision in requirements.items()
        if design_requirement_blocks(decision)
    ]
    blocking = [item for item in document["unknowns"] if item["blocking"] and item["status"] != "RESOLVED"]
    later = [item for item in document["unknowns"] if not item["blocking"] and item["status"] != "RESOLVED"]
    lines = [
        f"# {feature['name']}",
        "",
        f"<!-- spec-source-sha256: {canonical_hash(document)} -->",
        f"<!-- approval-content-sha256: {approval_content_hash(document)} -->",
        "<!-- spec.json에서 생성됨. 직접 수정하지 마세요. -->",
        "",
        "## 이 기능으로 사용자가 할 수 있는 일",
        "",
        feature["userValue"],
        "",
        "## 주요 흐름",
        "",
        f"- 시작: {scenario['trigger']}",
        *[f"{index}. {step}" for index, step in enumerate(scenario["mainFlow"], 1)],
        "",
        "## 업무 규칙",
        "",
        *(
            [
                f"- {rule['description']} — {rule_label(rule)}"
                for rule in document["businessRules"]
            ]
            or ["- 없음"]
        ),
        "",
        "## 권한",
        "",
        *bullets(document["authorization"]),
        "",
        "## 저장하거나 변경하는 데이터",
        "",
        *bullets(document["dataAndState"]),
        "",
        "## 실패 사례",
        "",
        *bullets(document["failureCases"]),
        "",
        "## 완료 여부를 확인하는 방법",
        "",
        *(
            [
                f"- 상황: {item['given']}\n  - 행동: {item['when']}\n  - 기대 결과: {item['then']}"
                for item in document["acceptanceCriteria"]
            ]
            or ["- 없음"]
        ),
        "",
        "## 이번 기능에 필요한 설계",
        "",
        *bullets(required),
        "",
        "## 지금 확인해야 할 사항",
        "",
        *(
            [f"- {item['question']} — 이 결정의 영향: {item['impact']}" for item in blocking]
            + [f"- {item}" for item in design_questions]
            or ["- 없음"]
        ),
        "",
        "## 나중에 결정 가능한 사항",
        "",
        *(
            [f"- {item['question']}" for item in later]
            + [f"- {item}" for item in deferred_design]
            or ["- 없음"]
        ),
        "",
        "## 현재 상태",
        "",
        f"- {STATUS_LABELS[document['approval']['status']]}",
        "",
    ]
    if detail == "full":
        lines.extend(["## 개발자 상세", "", f"- 기능 ID: {feature['id']}"])
        lines.extend(
            f"- {rule['id']} · {rule['source']} · {rule['status']}"
            for rule in document["businessRules"]
        )
        lines.extend(f"- {item['id']}" for item in document["acceptanceCriteria"])
        lines.extend(
            f"- {name} · {DESIGN_STATUS_LABELS[decision['status']]} · {decision['source']}"
            + (" · 사용자 확인 완료" if decision["confirmedByUser"] else " · 사용자 확인 없음")
            for name, decision in requirements.items()
        )
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
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--project-brief", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--detail", choices=("basic", "full"), default="basic")
    args = parser.parse_args()
    if args.check and args.force:
        print("SPEC_MARKDOWN_VALID: no\nERROR: --check and --force cannot be combined")
        return 2
    try:
        document = load_object(args.input)
        if "featureCandidates" in document:
            expected = render_project(document, args.detail)
            kind = "PROJECT_BRIEF"
        elif "feature" in document:
            project = load_object(args.project_brief) if args.project_brief else None
            if project is not None:
                validate_project(project)
            expected = render_feature(document, project, args.detail)
            kind = "FEATURE_SPEC"
        else:
            raise ValueError("input is neither a project brief nor a feature spec")
        if args.check:
            try:
                actual = args.output.read_text(encoding="utf-8")
            except OSError as error:
                raise ValueError(f"cannot read Markdown view: {error}") from error
            if actual != expected:
                raise ValueError("Markdown view is stale; regenerate it from JSON")
        else:
            atomic_write(expected, args.output, args.force)
    except ValueError as error:
        print(f"SPEC_MARKDOWN_VALID: no\nERROR: {error}")
        return 1
    print("SPEC_MARKDOWN_VALID: yes")
    print(f"SPEC_KIND: {kind}")
    print(f"MODE: {'CHECK' if args.check else 'WRITE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
