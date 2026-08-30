# Workflows

이 문서는 **maintain 모드**의 상세 작업 흐름입니다. 이미 코드가 있는 프로젝트를
이해하고, 고치고, 검증할 때 씁니다.

빈 repo에서 새로 시작하는 흐름은 [start-workflow](start-workflow.md)에 있습니다.
모드 규칙은 [modes/maintain.md](../modes/maintain.md)에 있습니다.

## 기본 흐름

```text
분석
  spring-understand
    |
    v
계획
  spring-change, source 수정 금지
    |
    v
사용자 승인
    |
    v
구현
  spring-change, 승인 범위만 수정
    |
    v
검증
  spring-verify-knowledge, source 자동 수정 금지
    |
    v
Knowledge proposal
  human approval 후 반영
```

## 프로젝트 처음 분석

사용 목적:

- Target 프로젝트의 구조를 처음 파악
- Controller, Service, Persistence, Test 흐름 확인
- MyBatis/JPA/JDBC/Mixed persistence 후보 확인
- 확인되지 않은 부분을 UNKNOWN으로 분리

예시:

```text
spring-understand를 사용해서 /absolute/path/to/spring-solution 프로젝트를 처음부터 분석해줘.
코드는 수정하지 말고 실제 코드 evidence를 기준으로 설명해줘.
```

## 기능 학습

학습은 AI 설명만 읽는 것이 아니라 실제 코드를 따라가는 방식이어야 합니다.

권장 흐름:

```text
What
Where
Entry Point
Call Flow
Business Rule
Customer Difference
Persistence Layer
External System
Exception
Legacy / Workaround
Evidence
Self Check
```

예시:

```text
spring-understand를 사용해서 주문 생성부터 결제 완료까지 흐름을 학습용으로 설명해줘.
각 단계마다 내가 직접 볼 파일과 메서드를 알려줘.
```

## 신규 기능 개발

신규 기능도 바로 구현하지 않습니다.

1. `spring-understand`로 현재 구조와 확장 지점을 확인합니다.
2. `spring-change`로 영향도와 변경 계획을 만듭니다.
3. 사용자가 계획을 승인합니다.
4. 승인된 범위만 구현합니다.
5. 관련 테스트와 verification을 실행합니다.

계획 프롬프트:

```text
spring-change를 사용해서 신규 기능 구현 계획을 작성해줘.

요구사항:
<요구사항>

현재 코드 evidence를 기준으로 수정 대상, 영향 범위, 테스트 계획, 위험,
UNKNOWN을 정리해줘. 아직 코드는 수정하지 마.
```

구현 승인 프롬프트:

```text
계획을 승인합니다.
승인된 범위 안에서만 최소 구현하고, 관련 테스트를 추가하거나 수정한 뒤 실행해줘.
기존 dirty 변경은 건드리지 마.
```

## Bug Investigation / RCA

장애 조사는 증상과 Root Cause를 분리합니다.

```text
Symptom
Initial Facts
Hypotheses
Evidence Collection
Eliminated Hypotheses
Root Cause
Confidence
Affected Scope
Fix Plan
Regression Plan
```

주의:

- Exception 발생 위치가 Root Cause라는 보장은 없습니다.
- JPA/MyBatis/JDBC 같은 기술명만 보고 원인을 확정하지 않습니다.
- evidence가 부족하면 UNKNOWN으로 남깁니다.

## 기존 dirty 상태에서 작업

Target repository가 dirty일 수 있습니다. 이 경우 먼저 Target root에서 diff와 status를
확인하고, 기존 변경을 덮어쓰지 않습니다.

예시:

```text
spring-change를 사용해줘.
먼저 Target git status와 diff를 확인하고, 기존 dirty 변경은 건드리지 마.
이번 승인 범위에 포함된 파일만 최소 수정해줘.
```
