# Skill and Scripts

## spring-project-start

이 Harness의 유일한 Skill입니다.

대상:

- 빈 repo 또는 README-only repo
- 이미 생성된 Spring Boot 프로젝트
- 작은 단일 애플리케이션
- 여러 단계와 모듈이 필요한 대형 프로젝트

역할:

- 환경과 target preflight
- 목표와 요구사항 정리
- 규모에 맞는 단계별 로드맵
- 추천·선택·직접 입력 기반 기술 프로필과 호환성 검토
- 자연어 목표의 프로젝트 개요·기능 후보·첫 기능 계약
- 현재 마일스톤 구현
- 테스트 또는 실행 검증
- `docs/progress.md` 갱신

기존 Spring 프로젝트라는 이유로 이해·수정·검증용 별도 모드로 전환하지 않습니다.
현재 프로젝트를 만들고 확장하는 같은 흐름을 계속 사용합니다.

기술 선택의 상세 결정 축과 호환성 규칙은 Skill의 `references/`에 두고 필요한
시점에만 읽습니다. 확정 결과는 target의 `docs/project-profile.json`과
`docs/project-profile.md`에 기록합니다. JSON은 선택 ID와 상태의 구조화된 기준이고,
Markdown은 사용자가 읽는 이유와 영향 설명입니다.

생성 전에는 `GENERATION_READY: yes`가 필요합니다. 빈 프로필이 파싱되고 충돌이
없다는 이유만으로 생성 가능한 것으로 취급하지 않습니다.

기능 설계 전에는 프로젝트 개요와 해당 기능 명세가 승인되고
`ADVANCEMENT_READY: yes`여야 합니다. 구조화 JSON을 기준 원본으로 사용하고 Markdown은
사용자용 보기로 생성하여 동기화를 검사합니다.

readiness를 통과하면 `generation-mappings.json`과 현재 Spring Initializr
메타데이터로 `docs/generation-plan.json`을 만듭니다. 계획 컴파일러는 target
소스를 생성하거나 수정하지 않으며, 실제 변경 목록은 이후 dry-run의 책임입니다.

`render_generation_dry_run.py`는 Initializr 결과를 임시 공간에 렌더링하고 target과
비교합니다. 이전 생성 해시가 확인되는 경우에만 `UPDATE`로 분류하고 나머지 기존 파일
차이는 `CONFLICT`로 보호합니다. 보고서 작성 외에는 target을 변경하지 않습니다.

`apply_approved_generation.py`는 정확한 dry-run 해시가 포함된 명시적 승인만 받습니다.
재렌더링과 적용 직전 검증을 통과하면 백업 후 파일별 원자 교체를 수행하고, 실패 시
rollback하며, 성공 시 다음 비교를 위한 baseline manifest를 기록합니다.

## Scripts

스크립트는 결정론적인 evidence 수집과 검증만 담당합니다. 프로젝트 요구사항과
아키텍처 판단은 실제 evidence, 사용자 목표, 현재 개발 단계를 함께 봐야 합니다.

| Script | Purpose |
|---|---|
| `scripts/check-environment` | 로컬 Git과 Java 확인 |
| `scripts/check-target` | target 경로, Git 상태, Spring 시작 여부 확인 |
| `scripts/check-spring-project` | 빌드 파일과 소스 레이아웃 확인 |
| `scripts/run-verification` | target 테스트 실행 |
| `spring-project-start/scripts/validate_feature_specs.py` | 프로젝트 개요·기능 계약과 진행 gate 검증 |
| `spring-project-start/scripts/migrate_design_route_v2.py` | 단일 대상 v1 설계 경로를 안정적인 계약 ID가 있는 v2 사본으로 변환 |
| `spring-project-start/scripts/validate_design_contract.py` | 상세 설계 메타데이터와 승인된 라우팅·대상·추적성의 일치 검증 |
| `spring-project-start/scripts/render_design_contract.py` | 상세 설계 메타데이터의 사용자용 Markdown 보기 생성·검사 |
| `spring-project-start/scripts/create_http_api_contract.py` | 승인된 HTTP_API CREATE 경로에서 OpenAPI JSON 초안과 파생 메타데이터를 안전하게 생성 |
| `spring-project-start/scripts/validate_http_api_contract.py` | OpenAPI·기능 추적성·인증 방식·응답 계약의 일관성 검증 |
| `spring-project-start/scripts/render_http_api_contract.py` | 실제 OpenAPI에서 초보자용 API 계약 보기 생성·검사 |
| `spring-project-start/scripts/record_http_api_contract_approval.py` | 적용 직전 재검증 후 API 메타데이터와 보기를 원자적으로 승인 |
| `spring-project-start/scripts/create_existing_http_api_contract.py` | 기존 OpenAPI를 재사용하거나 별도 확장 제안과 호환성 보고서 생성 |
| `spring-project-start/scripts/validate_existing_http_api_contract.py` | baseline drift·Controller 근거·파괴적 변경·검토 수용 상태 검증 |
| `spring-project-start/scripts/render_existing_http_api_contract.py` | REUSE/EXTEND 영향과 확인 사항의 사용자용 보기 생성·검사 |
| `spring-project-start/scripts/record_existing_http_api_contract_approval.py` | 기존 인터페이스를 수정하지 않고 현재 증거와 비교 결과만 원자적으로 승인 |
| `spring-project-start/scripts/render_spec_markdown.py` | JSON에서 사용자용 Markdown 생성·동기화 확인 |
| `spring-project-start/scripts/record_spec_approval.py` | 승인 상태 동기화와 JSON·Markdown 원자적 갱신 |
| `spring-project-start/scripts/next_feature_id.py` | 프로젝트 개요와 기존 디렉터리에서 다음 기능 ID 확인 |
| `spring-project-start/scripts/migrate_feature_spec_v2.py` | v1 기능 명세를 원본 보존 상태로 v2 검토본에 변환 |
| `spring-project-start/scripts/validate_design_route.py` | 설계 경로와 입력·코드 evidence·대상 참조 검증 |
| `spring-project-start/scripts/render_design_route.py` | 설계 경로의 기본·상세 Markdown 생성 |
| `spring-project-start/scripts/record_design_route_approval.py` | 표시된 설계 경로를 재검증하고 JSON·Markdown 승인 |

Exit code:

| Code | Meaning |
|---|---|
| `0` | confirmed |
| `1` | confirmed negative 또는 테스트 실패 |
| `2` | usage error 또는 unsafe condition |
| `3` | cannot verify (`UNKNOWN`) |

스크립트가 확인하지 못한 결과를 AI가 상상해서 채우지 않습니다.
