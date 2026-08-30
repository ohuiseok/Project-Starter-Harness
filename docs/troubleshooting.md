# Troubleshooting

## Target 경로를 모르겠는 경우

먼저 target 경로를 확인합니다.

```bash
scripts/check-target --target /work/my-spring-project
```

`UNKNOWN`이 나오면 경로가 존재하는지 확인합니다.

## Git repo가 아닌 경우

문제:

```text
TARGET_IS_GIT_REPOSITORY: no
```

해결:

target 폴더에서 Git repo를 먼저 만듭니다.

```bash
git init
```

## README만 있는 경우

정상입니다. 이 Harness는 README-only repo에서 시작할 수 있습니다.

Codex는 README를 읽고 프로젝트 의도를 요약한 뒤 추천 MVP로 진행할지 묻습니다.

## Spring 프로젝트인지 모르겠는 경우

확인:

```bash
scripts/check-spring-project --target /work/my-spring-project
```

`build.gradle` 또는 `pom.xml`이 없으면 아직 Spring 프로젝트가 아닙니다.

## 테스트를 실행할 수 없는 경우

`scripts/run-verification`은 Gradle wrapper 또는 Maven wrapper가 있을 때 테스트를
실행합니다.

wrapper가 없으면:

```text
UNKNOWN: no Gradle or Maven wrapper found
```

이 경우 프로젝트 생성 또는 wrapper 추가가 다음 목표가 될 수 있습니다.

## 기존 변경이 있는 경우

target repo에 dirty 변경이 있으면 먼저 확인합니다.

```bash
git -C /work/my-spring-project status --short
```

기존 변경을 덮어쓰지 않고 이번 세션 목표에 필요한 파일만 수정합니다.


## 스크립트 종료 코드

```text
0  확인됨
1  확인된 부정 (target 없음, 테스트 실패)
2  사용법 오류 (예: --target 값 누락)
3  확인 불가 (UNKNOWN)
```

3은 실패가 아니라 "확인하지 못했다"는 뜻입니다. wrapper가 없어서 테스트를
돌리지 못한 경우가 여기에 해당합니다.

## 이전 세션 내용이 기억나지 않는 경우

target repo의 진행 기록을 봅니다.

```bash
cat /work/my-spring-project/docs/progress.md
```

파일이 없으면 아직 첫 세션입니다.

## 스크립트를 고친 경우

Harness 스크립트를 수정했다면 테스트를 돌립니다.

```bash
tests/run-tests
```
