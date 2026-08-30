# Project Starter Harness

Spring Boot를 처음 배우는 개발 입문자가 GPT와 같은 세션에서 작은 프로젝트를
처음부터 만들고 실행해보도록 돕는 Harness입니다.

처음 사용하는 사람은 이 README의 **1~3번만** 보면 됩니다.

## 1. 준비

필요한 것:

- ChatGPT Desktop 또는 Codex가 이 폴더를 열 수 있는 환경
- Git
- Java 17 이상

권장 구조:

```text
/work/
├── Project-Starter-Harness/
└── my-spring-project/
```

중요:

- 만들 Spring 프로젝트는 Harness 폴더 밖에 둡니다.
- Harness Git 상태와 target 프로젝트 Git 상태를 섞지 않습니다.
- 처음에는 빈 repo 또는 README만 있는 repo여도 됩니다.

## 2. 바로 시작

ChatGPT/Codex에서 이 Harness 폴더를 연 뒤 아래처럼 말하면 됩니다.

```text
이 repo에서 Spring Boot 프로젝트를 시작해줘.
Target repository: /tmp/Verasure
```

더 짧게 말해도 됩니다.

```text
시작해줘.
```

Codex가 먼저 target repo와 README를 확인하고, 필요한 질문을 하나씩 합니다.

## 3. 자주 쓰는 말

```text
이 repo에서 Spring Boot 프로젝트를 시작해줘.
```

```text
추천으로 진행해줘.
```

```text
이어가자.
```

```text
다음 기능을 추가하자.
```

## 4. 진행 방식

한 세션에는 작은 목표 하나만 진행합니다.

예:

```text
README를 읽었습니다.
추천 MVP로 시작할까요?

1. 추천으로 시작
2. 직접 고르기
```

사용자가 잘 모르겠다고 하면 추천으로 진행합니다.

세션 끝에는 항상 다음을 남깁니다.

- 완료한 것
- 배운 것
- 실행 또는 테스트 방법
- 다음에 이어갈 선택지

## 5. 포함된 도구

```bash
scripts/check-target --target /tmp/Verasure
scripts/check-spring-project --target /tmp/Verasure
scripts/run-verification --target /tmp/Verasure
```

스크립트는 결과를 간단히 출력합니다. 확인하지 못한 내용은 `UNKNOWN`으로 표시합니다.

## 6. 자세한 문서

- [Workflow](docs/workflow.md): 시작부터 세션 종료까지의 흐름
- [Learning Sessions](docs/learning-sessions.md): 입문자에게 설명하는 방식
- [AGENTS.md](AGENTS.md): 에이전트 동작 규칙 (단일 출처)
- [Examples](examples/verasure.md): 프로젝트별 MVP 예시
- [Troubleshooting](docs/troubleshooting.md): 자주 막히는 문제 해결

