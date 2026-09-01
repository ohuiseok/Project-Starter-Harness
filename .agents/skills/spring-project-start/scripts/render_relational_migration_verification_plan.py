#!/usr/bin/env python3
"""Render the explicit host-side effects of migration verification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from render_design_route import atomic_write
from run_relational_migration_verification import sha, validate_plan
from validate_feature_specs import load_object


def render(plan: dict, plan_hash: str) -> str:
    return "\n".join([f"# {plan['planId']} migration 격리 검증 계획", "", f"<!-- verification-plan-sha256: {plan_hash} -->", "", "## 한눈에 보기", "", "- 확인: 선택한 migration이 빈 격리 PostgreSQL에서 migrate/validate 되는지", "- 확인하지 않음: production 데이터·권한·성능·rollback", "- 실행 흐름: 환경 확인 → 이미지 준비 → DB 시작 → migrate → validate → 정리", f"- 최대 대기: DB {plan['limits']['startupTimeoutSeconds']}초, 명령별 {plan['limits']['commandTimeoutSeconds']}초", "", "## 검증 대상", "", f"- migration: `{plan['migration']['path']}`", f"- PostgreSQL: `{plan['images']['postgres']}`", f"- Flyway: `{plan['images']['flyway']}`", f"- 임시 DB/schema: `{plan['database']['name']}` / `{plan['database']['schema']}`", "", "## 실제로 발생하는 로컬 효과", "", "- Docker 이미지가 없으면 내려받음(이미지에 따라 수백 MB 가능)", "- 내려받은 이미지는 검증 후에도 Docker cache에 남음", "- 실제 image ID와 repository digest를 결과에 기록하고 해당 image ID로 실행", "- 외부 통신이 차단된 임시 Docker network 생성", "- 포트를 공개하지 않는 PostgreSQL 컨테이너 생성", f"- 최대 {plan['limits']['tmpfsBytes']} bytes tmpfs 사용", "- Flyway migrate와 validate 프로세스 실행", "- 검증 evidence 보고서 파일 생성", "- 완료 또는 실패 후 컨테이너와 network 제거", "", "## 발생하지 않는 일", "", "- 프로젝트의 실제 DB 또는 production DB 접속 안 함", "- 프로젝트 Compose 서비스 시작 안 함", "- persistent Docker volume 생성 안 함", "- 대상 migration이나 소스 파일 변경 안 함", "- 애플리케이션 credential 사용·저장 안 함", "", "## 한계", "", "- tag는 registry에서 가리키는 내용이 바뀔 수 있음; 최고의 재현성이 필요하면 digest reference 사용", "- host가 swap을 사용하면 tmpfs 메모리 페이지가 swap에 기록될 가능성이 있음", "- production 권한·데이터·성능·lock 시간·rollback은 검증하지 않음", "- 성공은 선택한 이미지 조합의 빈 격리 DB에서 migrate/validate가 통과했다는 의미", "", "## 다음 행동", "", "- 추천: 이 정확한 계획을 별도 승인하고 격리 검증 실행", "- 이미지 또는 제한값 수정", "- 실행하지 않고 보류", ""])


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--plan", required=True, type=Path); parser.add_argument("--target", required=True, type=Path); parser.add_argument("--output", required=True, type=Path); parser.add_argument("--check", action="store_true"); parser.add_argument("--force", action="store_true"); args = parser.parse_args()
    try:
        if args.check and args.force: raise ValueError("--check and --force cannot be combined")
        plan = load_object(args.plan); validate_plan(plan, args.plan, args.target); expected = render(plan, sha(args.plan))
        if args.check:
            if args.output.read_text(encoding="utf-8") != expected: raise ValueError("migration verification plan Markdown is stale")
        else: atomic_write(expected, args.output, args.force)
    except (OSError, ValueError) as error: print(f"RELATIONAL_MIGRATION_PLAN_MARKDOWN_VALID: no\nERROR: {error}"); return 1
    print("RELATIONAL_MIGRATION_PLAN_MARKDOWN_VALID: yes"); return 0


if __name__ == "__main__": sys.exit(main())
