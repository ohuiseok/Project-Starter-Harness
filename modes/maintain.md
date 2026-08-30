# Mode: maintain

이미 코드가 있는 외부 Spring 프로젝트를 이해하고, 고치고, 검증하는 모드입니다.
운영 중인 코드일 수 있다고 가정합니다.

공통 규칙은 `AGENTS.md`에 있습니다. 여기에는 이 모드에서만 다른 것만 씁니다.

## 승인 모델

**사람이 구현 계획을 명시적으로 승인하기 전에는 구현하지 않습니다.**

이 규칙은 `modes/start.md`와 정반대입니다. 빈 repo에서는 추천으로 진행하지만,
남이 의존하는 코드에서는 추측으로 진행하지 않습니다.

- onboarding, learning, investigation, context building, impact analysis,
  planning, review, verification 중에는 target source를 수정하지 않습니다.
- review와 verification에서는 확인하고 보고만 합니다. 자동으로 고치지
  않습니다.
- Knowledge를 자동으로 덮어쓰지 않습니다.
- 증거와 사람의 승인 없이 중요한 결론을 `CONFIRMED`로 표시하지 않습니다.

## 증거 구분

Knowledge는 색인이자 맥락 보조일 뿐 Source of Truth가 아닙니다. 중요한
판단에는 실제 소스, 테스트, 설정, 영속성 아티팩트, Git 이력, 런타임 증거를
씁니다.

다음 셋을 반드시 구분합니다.

- `observed_behavior`: 시스템이 지금 실제로 하는 것
- `intended_behavior`: 비즈니스가 기대하거나 사람이 승인한 것
- baseline branch 동작 / current branch 동작

충돌하면 충돌 자체를 보고하고, 검토 전까지 `UNKNOWN`으로 둡니다.

## 고객 안전

작업 범위를 항상 다음 중 하나로 분류합니다.

```text
COMMON
CUSTOMER_SPECIFIC
CONFIGURATION
FEATURE_FLAG
LEGACY
WORKAROUND
TEMPORARY
UNKNOWN
```

고객 특화 작업에서는 Customer, Module, Entry Point, Configuration 또는
Feature Flag, Existing Customer Pattern, Common Impact, Other Customer Impact,
Tests, Unknowns를 확인합니다.

Shared Service, Shared Mapper, Shared DB, Common Config, Shared API,
Common Business Rule 변경은 구현 전에 강화된 영향 검토가 필요합니다.

고객 범위는 증거가 나오기 전까지 `UNKNOWN`이 기본값입니다.

## 최소 변경

Feature Change는 Refactoring이 아닙니다. Bug Fix는 Cleanup이 아닙니다.
Customer Change는 자동으로 Common Abstraction이 되지 않습니다.

변경을 좁게 유지하고, 피할 수 없는 공유 코드 변경은 승인 요청 전에
설명합니다.

예외가 발생한 위치는 Root Cause가 아닙니다.

## Auto-Check

target 작업 전에 `reports/auto-check/unreviewed/*.md`가 있으면, 검토되지 않은
auto-check가 있다는 사실을 짧게 보고합니다. 현재 작업과 관련이 있을 수 있으면
최신 target 코드 증거를 다시 확인한 뒤 진행합니다.

- 리포트를 읽었다는 것만으로 검토 완료로 표시하지 않습니다.
- auto-check 리포트는 규칙 기반 후보이며 Source of Truth가 아닙니다.
- `daily-check`가 실패하면 결과를 `UNKNOWN`으로 취급합니다.

auto-check 규칙은 에이전트 행동 지침이지 스크립트 수준의 하드 게이트가
아닙니다. 중요한 판단에는 여전히 실제 증거와 사람의 승인이 필요합니다.

## 산출물

- Context Pack — `templates/context-pack.md`
- Customer Impact Matrix — `templates/customer-impact-matrix.md`
- Root Cause Analysis — `templates/root-cause-analysis.md`
- Verification Report — `templates/verification-report.md`
- Knowledge Proposal — `templates/knowledge-proposal.md`

Knowledge 갱신은 사람의 승인에 맡깁니다.
