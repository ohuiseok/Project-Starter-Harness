---
name: spring-project-start
description: 빈 repo, README만 있는 repo, 또는 작은 기존 repo에서 입문자용 Spring Boot 프로젝트를 시작하거나 이어갈 때 사용합니다. 사용자가 "시작해줘", "추천으로 해줘", "이어가자"라고만 말해도 이 Skill을 씁니다.
---

# spring-project-start

Use this Skill when a user wants to start, continue, or learn a beginner Spring
Boot project from an empty repo, a README-only repo, or a small existing starter
repo.

## Purpose

Help a beginner developer build one small Spring Boot project step at a time
with GPT/Codex.

The user should be able to say:

```text
시작해줘
추천으로 해줘
이어가자
```

## Rules

Follow `AGENTS.md` for the shared rules and `modes/start.md` for this mode:
the UX rules, the approval model, the recommended stack, and the default
exclusions. Do not restate them here; this file only covers the session
procedure.

Per-project MVP scope lives in `examples/`.

## Required Behavior

1. Identify the target repository.
   - Use the path provided by the user.
   - If no path is provided, ask one short question for the target path.
2. Run preflight:
   - `scripts/check-environment` on the first session of a project. If
     `ENVIRONMENT_READY` is not `yes`, say what is missing and stop before
     implementation; do not start a project the user cannot run.
   - `scripts/check-target --target <target-path>`
   - If the target already looks like a Spring project, also run
     `scripts/check-spring-project --target <target-path>`.
3. Read `<target-path>/docs/progress.md` when it exists, then the target README.
4. Summarize the project intent in 1 to 3 short bullets.
5. Ask one short question.
6. Present 2 to 4 choices, including a recommended one.
7. If the user is unsure, use the recommended choice.
8. Confirm one small session goal before implementation.
9. Implement only that goal.
10. Explain briefly while implementing.
11. Verify with tests or a run check.
12. Close the session (see Session Ending below).

## First Question

For an empty repo or README-only repo, start with:

```text
README를 읽었습니다.
추천 MVP로 시작할까요?

1. 추천으로 시작
2. 직접 고르기
```

If there is no README:

```text
아직 README가 없습니다.
추천 MVP로 시작할까요?

1. 추천으로 시작
2. 직접 고르기
```

## Session Goals

One goal per session. A goal is good when it can be verified at the end.

Good:

- Spring Boot 프로젝트 생성 + 첫 화면 확인
- 등록 API 만들기
- 목록 화면 만들기

Too large:

- 전체 서비스 완성
- 로그인, OCR, 추천, 배포까지 한 번에 구현

## Implementation Notes

- Prefer Spring Initializr or standard Spring Boot layout when creating a new
  project, but do not implement Spring Initializr inside this Harness.
- Keep the generated project simple.
- Use static `index.html` before adding a frontend framework.
- Do not force Clean Architecture on a beginner project.

## Explanation Style

Use short beginner-friendly explanations:

```text
build.gradle은 프로젝트가 사용할 라이브러리를 정합니다.
Controller는 브라우저나 API 요청을 받는 입구입니다.
Repository는 DB와 데이터를 주고받는 부분입니다.
```

Do not over-explain. Keep the session moving.

## Verification

After implementation, run:

```bash
scripts/run-verification --target <target-path>
```

Exit code 3 means verification could not run. Report it as `UNKNOWN` and say
what could not be checked. If tests fail, show the failure plainly and do not
hide output.

## Session Ending

Write the outcome to `<target-path>/docs/progress.md`, creating it from
`templates/progress.md` on the first session. Then report in chat using
`templates/session-summary.md`:

```text
완료:
- ...

배운 것:
- ...

실행/테스트:
- ...

남은 UNKNOWN:
- ...

다음:
1. 추천: ...
2. ...
3. ...
```
