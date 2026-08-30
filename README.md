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

매번 경로를 말하기 번거로우면 `config/target.example.yaml`을
`config/target.local.yaml`로 복사해서 경로를 한 번만 적어두면 됩니다.

## 2. 바로 시작

ChatGPT/Codex에서 이 Harness 폴더를 연 뒤 아래처럼 말하면 됩니다.

```text
이 repo에서 Spring Boot 프로젝트를 시작해줘.
Target repository: /work/my-spring-project
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

## 5. Harness가 확인하는 것

명령어를 직접 칠 일은 없습니다. 필요한 확인은 Codex가 알아서 합니다.

- target 폴더가 있는지, Git repo인지, 기존 변경이 남아 있는지
- 이미 Spring 프로젝트인지, 아직 빈 repo인지
- 테스트가 통과하는지

확인하지 못한 것은 `UNKNOWN`이라고 알려줍니다. 추측으로 넘어가지 않습니다.

## 6. 자세한 문서

- [Workflow](docs/workflow.md): 시작부터 세션 종료까지의 흐름
- [Learning Sessions](docs/learning-sessions.md): 입문자에게 설명하는 방식
- [AGENTS.md](AGENTS.md): 모드 공통 규칙 (단일 출처)
- [modes/start.md](modes/start.md): 처음 만들 때의 규칙
- [modes/maintain.md](modes/maintain.md): 기존 코드를 다룰 때의 규칙
- [Examples](examples/verasure.md): 프로젝트별 MVP 예시
- [통합 설계안](docs/integration-plan.md): 분석 harness와 합치는 방향 (설계 단계)
- [Troubleshooting](docs/troubleshooting.md): 자주 막히는 문제 해결

## 7. Harness를 고치는 경우

이 Harness 자체를 수정했다면 테스트를 돌립니다. 프로젝트를 만드는 사용자는
이 절을 볼 필요가 없습니다.

```bash
tests/run-tests
```

