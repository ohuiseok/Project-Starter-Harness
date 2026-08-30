# Starter Rules

## UX Rules

- 질문은 한 번에 하나만 합니다.
- 선택지는 2~4개만 줍니다.
- 선택지에는 항상 추천이 있어야 합니다.
- 사용자가 모르면 추천으로 진행합니다.
- 한 세션에는 하나의 작은 목표만 구현합니다.
- 구현하면서 짧게 설명합니다.
- 테스트 또는 실행 확인을 합니다.
- 끝에는 요약과 다음 선택지를 줍니다.

## Technical Defaults

추천 기본값:

- Java 17
- Spring Boot
- Gradle
- Spring Web
- Spring Data JPA
- H2
- JUnit
- static `index.html`

기본 제외:

- Spring Security
- Docker
- MySQL
- React/Vue
- OCR
- RAG
- PDF 분석
- Kafka
- Kubernetes
- MSA
- 강제 Clean Architecture

## Evidence Rules

확인 우선순위:

```text
Actual files
Tests
Runtime output
Git state
README
User approval
AI inference
```

확인할 수 없으면 `UNKNOWN`으로 둡니다.

## Repository Rules

- Harness repo와 target repo를 분리합니다.
- target 명령은 target root에서 실행합니다.
- dirty 변경을 덮어쓰지 않습니다.
- `/root/project-analysis-harness`는 참고만 하고 수정하지 않습니다.

