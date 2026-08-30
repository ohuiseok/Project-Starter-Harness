# Troubleshooting

막히면 Codex에게 그냥 말로 물어보면 됩니다. 아래는 자주 나오는 상황과, 그때
하면 되는 말입니다.

## Java나 Git이 없는 경우

첫 세션에 Codex가 확인해서 알려줍니다.

```text
환경 확인해줘.
```

`ENVIRONMENT_READY: no`가 나오면 무엇이 없는지 함께 알려줍니다. Java는 17
이상이 필요합니다.

## Target 경로를 모르겠는 경우

만들 프로젝트 폴더의 경로를 알려주면 됩니다.

```text
target은 /work/my-spring-project야.
```

경로가 아직 없다면 폴더부터 만들어 달라고 해도 됩니다.

## Git repo가 아니라고 하는 경우

Codex가 `TARGET_IS_GIT_REPOSITORY: no`라고 알려주는 경우입니다.

```text
target 폴더를 Git repo로 만들어줘.
```

## README만 있는 경우

정상입니다. 이 Harness는 빈 repo나 README만 있는 repo에서 시작할 수 있습니다.

Codex가 README를 읽고 프로젝트 의도를 요약한 뒤, 추천 MVP로 진행할지 묻습니다.

## 아직 Spring 프로젝트가 아닌 경우

`build.gradle`이나 `pom.xml`이 없으면 아직 Spring 프로젝트가 아닙니다.
프로젝트 생성이 이번 세션 목표가 됩니다.

```text
추천으로 시작해줘.
```

## 테스트를 실행할 수 없다고 하는 경우

Gradle이나 Maven wrapper가 없으면 테스트를 돌릴 수 없습니다. Codex는 이걸
실패가 아니라 `UNKNOWN`으로 알려줍니다.

이 경우 프로젝트 생성 또는 wrapper 추가가 다음 목표가 될 수 있습니다.

## 기존 변경이 남아 있는 경우

target repo에 커밋하지 않은 변경이 있으면 Codex가 먼저 알려줍니다. 이 Harness는
사용자가 만든 변경을 덮어쓰지 않습니다.

그대로 두고 이번 목표에 필요한 파일만 고칩니다.

## 이전 세션 내용이 기억나지 않는 경우

진행 기록은 target repo의 `docs/progress.md`에 남아 있습니다.

```text
이어가자.
```

이렇게 말하면 Codex가 기록을 읽고 다음 할 일부터 이어갑니다.

## `UNKNOWN`이 나오는 경우

`UNKNOWN`은 오류가 아닙니다. "확인하지 못했다"는 뜻입니다.

Codex는 확인하지 못한 것을 추측으로 채우지 않습니다. 무엇을 확인하지 못했는지
물어보면 알려줍니다.
