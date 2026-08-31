# Project Starter Harness

자연어만으로 외부 Spring Boot 프로젝트를 처음 만들고 계속 확장하도록 돕는
Harness입니다. 간단한 애플리케이션부터 여러 단계로 개발하는 대형 프로젝트까지
같은 스타터 흐름으로 다룹니다.

프로젝트 전체 규모는 제한하지 않습니다. 대신 현재 상태와 목표를 확인하고,
검증 가능한 마일스톤을 하나씩 완성하며 진행 상황을 target 저장소에 남깁니다.
기술 스택 선택에 그치지 않고 프로젝트 목표를 기능 명세로 구체화한 뒤 API·데이터
설계, Spring 구현, 테스트로 이어가는 것을 목표로 합니다.

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
- target은 빈 repo, README-only repo, 또는 이미 개발 중인 Spring repo여도 됩니다.

매번 경로를 말하기 번거로우면 `config/target.example.yaml`을
`config/target.local.yaml`로 복사해서 경로를 한 번만 적어둘 수 있습니다.

## 2. 바로 시작

```text
이 repo에서 Spring Boot 프로젝트를 시작해줘.
Target repository: /work/my-spring-project
```

이미 프로젝트가 시작됐다면 다음처럼 말하면 됩니다.

```text
이어가자.
```

```text
다음 기능을 만들어줘.
```

Codex가 target과 진행 기록을 확인하고, 필요한 경우에만 질문을 하나씩 합니다.

## 3. 프로젝트 규모 알려주기

작은 프로젝트는 목표를 바로 첫 기능으로 나눕니다.

```text
개인용 일정 관리 API를 만들어줘.
```

큰 프로젝트는 전체를 한 번에 만들지 않고 먼저 단계별 로드맵을 잡습니다.

```text
주문, 결제, 배송, 운영자 기능이 있는 쇼핑몰 백엔드를 만들고 싶어.
단계별로 설계하고 첫 마일스톤부터 시작해줘.
```

규모를 모르겠으면 Codex가 요구사항을 기준으로 추천합니다.

기술 구성을 모두 알고 있을 필요도 없습니다. Codex가 프로젝트 설명을 바탕으로
추천 구성을 먼저 보여주며 다음 중 선택할 수 있습니다.

```text
1. 추천 구성으로 진행
2. 항목별 수정
3. 기타 / 원하는 구성을 직접 설명
```

항목별 선택에도 항상 `기타 / 직접 입력`이 있습니다. 세션, JWT, 보안 없음,
단일·다중 DB, JSP, 별도 프론트엔드, 모놀리스, MSA처럼 프로젝트마다 다른 구성을
선택하거나 직접 설명할 수 있습니다. 아직 필요하지 않은 결정은 보류할 수 있습니다.

## 4. 진행 방식

```text
환경과 Target 확인
  ↓
README, 진행 기록, 현재 코드 확인
  ↓
전체 목표와 단계 확인
  ↓
프로젝트 개요와 다음 기능 명세 확인
  ↓
이번 마일스톤 구현
  ↓
테스트 또는 실행 검증
  ↓
progress.md 갱신과 다음 선택지
```

한 마일스톤은 여러 계층과 파일을 포함할 수 있습니다. 중요한 기준은 작아 보이는
수정인지가 아니라, 하나의 유용한 결과를 만들고 검증할 수 있는지입니다.

Codex는 먼저 이해한 목표, 사용자, 기능 후보와 추천 첫 기능을 쉬운 요약으로
보여줍니다. 승인된 기능은 사용자 시나리오, 업무 규칙, 권한, 상태, 실패 사례와 인수
조건을 기준으로 설계하고 구현합니다. REST API가 아닌 화면, 배치, 메시지, 스케줄
기능도 같은 흐름에서 다룹니다.

## 5. Harness가 확인하는 것

필요한 명령은 Codex가 실행합니다.

- target 폴더와 Git 저장소 여부
- 기존 변경과 현재 브랜치
- Spring 프로젝트가 이미 시작됐는지
- 빌드 파일과 소스 레이아웃
- 테스트 또는 실행 결과

확인하지 못한 것은 추측하지 않고 `UNKNOWN`으로 알려줍니다.

## 6. 자세한 문서

- [Start Workflow](docs/start-workflow.md): 전체 작업 흐름
- [Learning Sessions](docs/learning-sessions.md): 설명과 학습 방식
- [AGENTS.md](AGENTS.md): 공통 안전 및 실행 규칙
- [modes/start.md](modes/start.md): 단일 스타터 모드 규칙
- [Examples](examples/verasure.md): 구체적인 MVP 예시
- [Troubleshooting](docs/troubleshooting.md): 자주 막히는 문제 해결
- [Skills and Scripts](docs/skills-and-scripts.md): 스타터 Skill과 스크립트

## 7. Harness를 고치는 경우

이 Harness 자체를 수정했다면 다음 테스트를 실행합니다.

```bash
tests/run-tests
```
