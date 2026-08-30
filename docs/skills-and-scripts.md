# Skills and Scripts

## Skills

Skill은 반복되는 작업 흐름을 Codex가 선택할 수 있게 만든 지침입니다.

모드는 `scripts/check-target`의 preflight 결과로 정해집니다. 자세한 규칙은
[AGENTS.md](../AGENTS.md)의 Routing을 참고하세요.

### spring-project-start

모드: start

목적:

- 빈 repo 또는 README-only repo에서 새 Spring Boot 프로젝트 시작
- 입문자 학습 세션 진행
- 이전 세션 이어가기

경계:

- 사용자가 모르면 추천으로 진행 (maintain 모드와 정반대)
- 한 세션에 작은 목표 하나
- 과한 기본값 금지

아래 세 Skill은 모두 maintain 모드입니다.

### spring-understand

목적:

- 프로젝트 onboarding
- 기능 학습
- 장애 조사
- codebase understanding
- context pack 생성
- RCA

경계:

- source code 수정 금지
- Knowledge 수정 금지
- Knowledge는 index/context로만 사용
- evidence가 부족하면 UNKNOWN

### spring-change

목적:

- impact analysis
- customer impact review
- implementation plan
- 승인 후 최소 구현

경계:

- human approval 전 source 수정 금지
- 불필요한 refactoring 금지
- customer-specific 동작을 common code로 임의 이동 금지
- customer scope 추측 금지

### spring-verify-knowledge

목적:

- diff review
- verification
- Git pull impact analysis
- stale Knowledge candidate detection
- Knowledge proposal
- auto-check report 검토

경계:

- review/verification 중 source 수정 금지
- Knowledge 자동 overwrite 금지
- auto-check report를 읽었다고 reviewed 처리하지 않음

## Scripts

Script는 결정론적인 evidence 수집과 점검만 담당합니다. Business Rule 판단, Root
Cause 판단, impact 판단은 AI reasoning과 human review가 필요합니다.

| Script | Mode | Purpose |
|---|---|---|
| `scripts/check-environment` | both | 로컬 Git/Java/ripgrep 확인 |
| `scripts/check-target` | both | Target preflight 및 모드 라우팅 |
| `scripts/check-spring-project` | both | build file, 소스 레이아웃 확인 |
| `scripts/run-verification` | both | Target 테스트 실행 |
| `scripts/detect-changes` | maintain | Target Git 변경 파일 후보 확인 |
| `scripts/map-codebase` | maintain | Target branch, build file, module, Spring annotation, persistence 후보 개요 |
| `scripts/find-entrypoints` | maintain | Controller, Scheduler, Event, Batch entry point 후보 검색 |
| `scripts/find-persistence-links` | maintain | MyBatis/JPA/JDBC persistence 후보 검색 |
| `scripts/build-context-pack` | maintain | Context Pack 초안 생성 |
| `scripts/stale-candidates` | maintain | Git 변경과 Knowledge evidence path 비교 |
| `scripts/daily-check` | maintain | git pull 이후 rule-based auto-check report 생성 |
| `scripts/install-target-hooks` | maintain | 선택형 non-blocking post-merge hook 설치 |

Exit code:

| Code | Meaning |
|---|---|
| `0` | confirmed |
| `1` | confirmed negative, or an expected empty result |
| `2` | usage error or unsafe condition |
| `3` | cannot verify (UNKNOWN) |

Script가 실패하면 AI는 결과를 상상해서 채우지 않고 UNKNOWN으로 보고해야 합니다.

## Persistence 후보

`find-persistence-links`는 완전한 ORM/SQL semantic analyzer가 아닙니다. 후보를
찾고 evidence를 보여주는 도구입니다.

탐색 대상:

- MyBatis: Mapper interface, XML mapper, statement id, SQL, resultMap, include,
  dynamic SQL 후보
- JPA/Spring Data JPA: Repository, Entity, Table, relationship annotation,
  derived query, `@Query`, EntityManager
- JDBC: JdbcTemplate, NamedParameterJdbcTemplate, raw SQL, DataSource
- Mixed: MyBatis와 JPA/JDBC가 함께 있는 경우

확인할 수 없는 값은 UNKNOWN으로 남깁니다.
