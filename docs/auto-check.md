# Auto-check

Auto-check는 git pull 이후 변경사항을 놓치지 않기 위한 Level 2 기능입니다.

핵심:

- AI를 호출하지 않습니다.
- code/Knowledge를 수정하지 않습니다.
- rule-based recommendation만 만듭니다.
- report는 Source of Truth가 아닙니다.
- Knowledge 반영은 proposal과 human approval 이후에만 합니다.

## Baseline Branch

`baseline.branch`는 장기 학습과 Knowledge 검증 기준 브랜치입니다. 필수 설정입니다.

```yaml
baseline:
  branch: release
```

회사의 기준 브랜치가 `main`이면 `main`으로 바꿉니다.

baseline이 없거나 target repository에서 확인할 수 없으면 `daily-check`는 UNKNOWN을
출력하고 중단합니다.

## Manual Daily Check

```bash
scripts/daily-check --target /absolute/path/to/spring-solution --base ORIG_HEAD --head HEAD --baseline release
```

생성 위치:

```text
reports/auto-check/unreviewed/<timestamp>.md
reports/auto-check/latest.md
```

`reports/`는 Git에 포함하지 않습니다.

Recommendation 값:

- `PROPOSE_KNOWLEDGE`
- `NEEDS_REVIEW`
- `REPORT_ONLY`
- `DISCARD`

Recommendation은 fact가 아닙니다.

## Hook Installer

장기 운영에서는 Target repository에 non-blocking `post-merge` hook을 설치할 수
있습니다.

설치 전 확인:

```bash
scripts/install-target-hooks --target /absolute/path/to/spring-solution --baseline release --dry-run
```

설치:

```bash
scripts/install-target-hooks --target /absolute/path/to/spring-solution --baseline release
```

동작:

- merge 기반 `git pull` 이후 `scripts/daily-check`를 실행합니다.
- hook은 `exit 0`으로 끝나며 git pull을 막지 않습니다.
- AI/Codex/API를 호출하지 않습니다.
- code/Knowledge를 수정하지 않습니다.
- 기존 `post-merge` hook이 있으면 덮어쓰지 않고 중단합니다.

제한:

- rebase 기반 pull에서는 실행되지 않을 수 있습니다.
- fetch-only나 IDE 특수 Git 동작에서는 놓칠 수 있습니다.
- 기존 hook이 있으면 수동 병합이 필요합니다.

이 경우 `scripts/daily-check`를 직접 실행합니다.
