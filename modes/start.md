# Mode: start

빈 repo 또는 README만 있는 repo에서 입문자가 작은 Spring Boot 프로젝트를
처음부터 만드는 모드입니다.

공통 규칙은 `AGENTS.md`에 있습니다. 여기에는 이 모드에서만 다른 것만 씁니다.

## 승인 모델

**사용자가 모르면 추천으로 진행합니다.**

입문자는 선택지를 평가할 능력이 없습니다. 매번 승인을 요구하면 세션이 앞으로
나가지 않습니다. 대신 무엇을 했는지 짧게 설명하고, 되돌릴 수 있게 작게
만듭니다.

이 규칙은 `modes/maintain.md`와 정반대입니다. 기존 코드에는 절대 적용하지
않습니다.

## UX 규칙

- 질문은 한 번에 하나만 합니다.
- 질문은 짧게 합니다.
- 선택지는 2~4개만 줍니다.
- 선택지에는 항상 추천이 있어야 합니다.
- 사용자가 모르면 추천으로 진행합니다.
- 한 세션에는 작은 목표 하나만 구현합니다.
- 구현하면서 짧게 설명합니다.
- 세션이 끝나기 전에 테스트 또는 실행 확인을 합니다.
- 끝에는 요약과 다음 선택지를 줍니다.
- 과한 기본값을 넣지 않습니다.

사용자는 이 정도만 말할 수 있다고 가정합니다.

```text
시작해줘
추천으로 해줘
이어가자
```

## 세션 흐름

```text
Preflight
README summary
One short question
One small session goal
Implementation
Verification
Summary
Next-step choices
```

구현 전에 이번 세션 목표를 짧게 확인합니다.

## 기술 기본값

target README가 다르게 말하지 않으면 이 스택을 추천합니다.

- Java 17
- Spring Boot
- Gradle
- Spring Web
- Spring Data JPA
- H2
- JUnit
- static `index.html`

기본 제외:

- 로그인, Spring Security
- PDF 업로드, OCR, RAG
- 추천 또는 판단 자동화
- Docker, MySQL
- React/Vue
- MSA, Kafka, Kubernetes
- 강제 Clean Architecture

추천 MVP 형태는 **첫 화면 → 등록 → 목록 → 상세**입니다. 도메인 하나만 씁니다.
프로젝트별 구체적인 MVP는 `examples/`에 있습니다.

## 산출물

- `<target>/docs/progress.md` — 세션마다 갱신. 다음 세션이 여기서 이어갑니다.
- 세션 요약 — 채팅 출력. 파일로 저장하지 않습니다.

Knowledge, Context Pack, 리포트는 이 모드에서 쓰지 않습니다. 입문자에게
승인 절차가 있는 산출물을 요구하지 않습니다.
