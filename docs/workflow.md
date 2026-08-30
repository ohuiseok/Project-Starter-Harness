# Workflow

Project Starter Harness는 작은 학습 세션을 반복하는 방식으로 사용합니다.

## 기본 흐름

```text
Target 확인
  |
README 읽기
  |
짧은 질문 하나
  |
이번 세션 목표 확인
  |
작게 구현
  |
테스트 또는 실행 확인
  |
요약과 다음 선택지
```

## 시작

사용자는 자세한 명령어를 몰라도 됩니다.

```text
시작해줘
```

Codex는 target repo를 확인하고 README가 있으면 먼저 읽습니다.

## 추천 MVP

입문자가 모르면 추천으로 진행합니다.

```text
추천 MVP로 시작할까요?

1. 추천으로 시작
2. 직접 고르기
```

추천은 작고 확인 가능한 기능부터 시작합니다.

## 한 세션 한 목표

한 번에 모든 것을 만들지 않습니다.

좋은 세션 목표:

- Spring Boot 프로젝트 생성 + 첫 화면 확인
- 보험 정보 등록 API 만들기
- 목록 화면 만들기
- 상세 보기 만들기

너무 큰 목표:

- 전체 서비스 완성
- 로그인, OCR, 추천, 배포까지 한 번에 구현
- MSA 구조로 재설계

## 구현 전 확인

구현 전에는 이번 목표를 짧게 확인합니다.

```text
이번 세션 목표:
Spring Boot 프로젝트 생성 + 첫 화면 확인

진행합니다.
```

## 검증

가능하면 테스트를 실행합니다.

```bash
scripts/run-verification --target /work/my-spring-project
```

실행할 수 없으면 `UNKNOWN`으로 남기고 이유를 설명합니다.


## 기록

세션 결과는 target repo에 남깁니다. Harness에는 남기지 않습니다.

| 템플릿 | 목적지 | 시점 |
|---|---|---|
| `templates/progress.md` | `<target>/docs/progress.md` | 첫 세션에 생성, 매 세션 갱신 |
| `templates/session-summary.md` | 채팅 출력 | 매 세션 종료 |
| `templates/project-readme.md` | `<target>/README.md` | target에 README가 없을 때만 |

`이어가자`라고 하면 `<target>/docs/progress.md`를 먼저 읽고 Next 항목에서
이어갑니다.
