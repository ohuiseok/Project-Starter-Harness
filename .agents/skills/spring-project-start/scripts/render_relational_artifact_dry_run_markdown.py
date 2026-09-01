#!/usr/bin/env python3
"""Render a user-facing relational artifact dry-run review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from render_design_route import atomic_write
from validate_feature_specs import load_object


def render(report: dict) -> str:
    changes = report["plannedChanges"]; conflicts = changes["conflicts"]
    lines = ["# DB 구현 파일 dry-run", "", "## 결론", "", f"- 상태: {'승인 검토 가능' if report['readyForApproval'] else '충돌 해결 필요'}", "- 실제 프로젝트 파일 변경: 없음", "- DB 연결·migration 실행: 없음", "- 컨테이너 시작·volume 변경: 없음", "", "## 생성 예정", ""]
    if changes["creates"]: lines.extend(f"- 새 파일 `{item['path']}`" for item in changes["creates"])
    if changes["updates"]: lines.extend(f"- 관리 중인 파일 갱신 `{item['path']}`" for item in changes["updates"])
    if changes["unchanged"]: lines.extend(f"- 변경 없음 `{item}`" for item in changes["unchanged"])
    if not changes["creates"] and not changes["updates"] and not changes["unchanged"]: lines.append("- 없음")
    lines.extend(["", "## 정확한 생성 내용", ""])
    for artifact in report.get("generatedArtifacts", []):
        language = {"FLYWAY_SQL": "sql", "DOCKER_COMPOSE": "yaml", "TESTCONTAINERS_JAVA": "java"}.get(artifact["kind"], "text")
        lines.extend([f"### `{artifact['path']}`", "", f"- 종류: {artifact['kind']}", f"- SHA-256: `{artifact['sha256']}`", "", f"```{language}", artifact["content"].rstrip(), "```", ""])
    lines.extend(["", "## 충돌", ""])
    lines.extend(f"- `{item.get('path') or '공통'}`: 기존 파일을 덮어쓸 근거가 없습니다." for item in conflicts) if conflicts else lines.append("- 없음")
    recovery = report["recoveryAssessment"]
    lines.extend(["", "## 복구 판단", "", f"- 계약이 요구한 수준: {recovery['required']}", f"- 생성된 DDL 분류: {recovery['renderedDdlClass']}", "- 격리 PostgreSQL 실행 검증: 아직 안 함", "- 파일 적용 rollback과 DB migration rollback은 별도 검증 대상", "", "## 다음 행동", ""])
    lines.extend(["- 충돌을 해결하고 dry-run 다시 생성"] if conflicts else ["- 추천: 이 파일 목록을 검토한 뒤 별도 적용 승인", "- 생성 내용을 항목별로 수정", "- 적용하지 않고 보류"])
    lines.append(""); return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--report", required=True, type=Path); parser.add_argument("--output", required=True, type=Path); parser.add_argument("--check", action="store_true"); parser.add_argument("--force", action="store_true"); args = parser.parse_args()
    try:
        if args.check and args.force: raise ValueError("--check and --force cannot be combined")
        expected = render(load_object(args.report))
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected: raise ValueError("relational artifact dry-run Markdown is stale")
        else: atomic_write(expected, args.output, args.force)
    except (OSError, ValueError, KeyError) as error: print(f"RELATIONAL_ARTIFACT_MARKDOWN_VALID: no\nERROR: {error}"); return 1
    print("RELATIONAL_ARTIFACT_MARKDOWN_VALID: yes"); return 0


if __name__ == "__main__": sys.exit(main())
