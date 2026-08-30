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

## Required Behavior

1. Identify the target repository.
   - Use the path provided by the user.
   - If no path is provided, ask one short question for the target path.
2. Run preflight:
   - `scripts/check-target --target <target-path>`
   - If the target already looks like a Spring project, also run
     `scripts/check-spring-project --target <target-path>`.
3. Read the target README first when it exists.
4. Summarize the project intent in 1 to 3 short bullets.
5. Ask one short question.
6. Present 2 to 4 choices.
7. Always include a recommended choice.
8. If the user is unsure, use the recommended choice.
9. Confirm one small session goal before implementation.
10. Implement only that goal.
11. Explain briefly while implementing.
12. Verify with tests or a run check.
13. End with:
    - 완료한 것
    - 배운 것
    - 실행/테스트 방법
    - 다음 선택지

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

## Recommended Session Goals

Use one goal per session.

Recommended order:

1. Spring Boot project creation and first page
2. Domain model and status enum
3. Create insurance information
4. List insurance information
5. Detail view
6. Validation and error messages
7. Tests and cleanup

## Verasure Recommended MVP

For `/tmp/Verasure`, recommend:

- Java 17
- Spring Boot
- Gradle
- Spring Web
- Spring Data JPA
- H2
- JUnit
- static `index.html`
- insurance information create
- insurance information list
- insurance information detail
- status display: `CONFIRMED`, `UNKNOWN`, `NEEDS_REVIEW`

Do not include by default:

- login
- PDF upload
- OCR
- RAG
- insurance recommendation or judgment
- Spring Security
- Docker
- MySQL
- MSA, Kafka, Kubernetes
- forced Clean Architecture

## Implementation Rules

- Prefer Spring Initializr or standard Spring Boot structure when creating a
  new project, but do not implement Spring Initializr inside this Harness.
- Keep the generated project simple.
- Prefer Gradle for the recommended path.
- Use Java 17 for the recommended path.
- Use H2 for the recommended path.
- Use static `index.html` before adding a frontend framework.
- Do not add React or Vue by default.
- Do not add Docker by default.
- Do not add Spring Security by default.
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

If wrappers do not exist, report `UNKNOWN` and explain what could not be run.

If tests fail, show the failure plainly and do not hide output.

## Session Ending Template

Use this shape:

```text
완료:
- ...

배운 것:
- ...

실행/테스트:
- ...

다음:
1. 추천: ...
2. ...
3. ...
```

