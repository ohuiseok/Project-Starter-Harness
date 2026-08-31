# Start Workflow

Project Starter Harness는 외부 Spring 프로젝트를 만들고 계속 확장합니다. 빈 repo와
기존 Spring repo 모두 같은 스타터 모드에서 처리합니다.

## 기본 흐름

```text
Target과 환경 확인
  |
현재 문서, 진행 기록, 코드 확인
  |
전체 목표와 로드맵 확인
  |
프로젝트 개요와 첫 기능 명세 확인
  |
추천 기술 프로필 확인
  |
이번 마일스톤 선택
  |
구현
  |
테스트 또는 실행 확인
  |
진행 기록과 다음 선택지
```

## 처음 시작할 때

README가 있으면 프로젝트 의도를 먼저 읽습니다. 요구사항이 충분하면 불필요한 질문
없이 추천 로드맵과 첫 마일스톤을 제시합니다. README가 없거나 중요한 선택이
비어 있으면 질문을 한 번에 하나만 합니다.

## 이미 시작된 프로젝트

Spring 소스가 있다고 다른 모드로 전환하지 않습니다. 다음 evidence를 확인하고
현재 계획에서 이어갑니다.

- `docs/progress.md`
- README와 target의 지침
- 빌드 파일과 모듈 구조
- 현재 마일스톤에 관련된 소스와 테스트
- target Git 상태

## 규모 계획

작은 프로젝트는 프로젝트 생성과 첫 기능을 바로 마일스톤으로 잡을 수 있습니다.

대형 프로젝트는 먼저 전체 기능을 단계로 나눕니다. 필요에 따라 target `docs/`에
로드맵이나 아키텍처 결정을 기록합니다. 초기 단계에서는 모든 미래 기술을 미리
구성하지 않고, 가까운 단계에 필요한 결정부터 구체화합니다.

예시:

```text
1단계: 프로젝트 기반, 인증 기초, 상태 확인
2단계: 첫 핵심 업무 흐름과 데이터 저장
3단계: 두 번째 도메인과 모듈 경계
4단계: 외부 연동과 장애 처리
5단계: 배포, 관측성, 운영 검증
```

단계 구성은 실제 요구사항에 따라 달라집니다.

## 마일스톤 기준

좋은 마일스톤은 끝에서 동작이나 테스트로 확인할 수 있습니다.

- Spring Boot 기반과 health endpoint 구성
- 등록 API, 저장소, 검증 테스트 완성
- 승인된 사용자 흐름에 필요한 인증 기반 완성
- 한 도메인의 end-to-end vertical slice 완성
- 현재 단계의 배포 패키징과 실행 검증

프로젝트 전체를 한 번에 구현하거나, 유용한 동작을 만들지 못할 정도로 잘게 쪼개지
않습니다.

## 프로젝트 개요와 기능 명세

자연어 목표는 먼저 `docs/project-brief.json`에 목표, 사용자, 성공 기준, 범위, 기능
후보, UNKNOWN, 근거를 구조화합니다. 사용자는 JSON 대신 생성된
`docs/project-brief.md`에서 이해한 목표, 기능 후보, 추천 첫 기능, 지금 확인할 사항을
봅니다.

다음 vertical slice는 `docs/features/F001/spec.json`에 사용자 가치, 시나리오, 업무
규칙, 권한, 상태, 실패 사례, 인수 조건, 설계 필요 항목을 기록합니다. REST, 화면,
배치, 메시지, 스케줄, 외부 연동을 선택적으로 표현하며 API나 관계형 DB를 모든 기능에
강제하지 않습니다. `spec.md`는 JSON에서 생성한 보기이며 직접 관리하는 두 번째 원본이
아닙니다.

형식이 유효한 초안은 저장할 수 있지만 중요한 UNKNOWN, 확인되지 않은 AI 추천 규칙,
인수 조건 또는 승인이 빠졌다면 설계·구현 단계로 진행하지 않습니다.

## 기술 선택

보안, 운영 DB, 마이그레이션, 메시징, 캐시, 배치, 컨테이너, 프론트엔드,
멀티 모듈과 분산 시스템은 요구사항이 있을 때 사용할 수 있습니다. 예상 규모만으로
모두 선설치하지는 않습니다.

### 선택 UX

먼저 프로젝트 설명에서 추천 프로필을 만들고 다음 중 하나를 선택하게 합니다.

```text
1. 추천 구성으로 진행
2. 항목별 수정
3. 기타 / 원하는 구성을 직접 설명
```

항목별 수정에서는 관련 있는 대표 선택지 2~4개와 `기타 / 직접 입력`을 제공합니다.
이전 답변에 따라 필요한 질문만 이어지고, 사용자는 언제든 `나머지는 추천` 또는
`이전 선택 변경`을 말할 수 있습니다.

결정 영역은 런타임·빌드, 애플리케이션/UI, 보안, 데이터, 구조, 연동, 운영,
검증입니다. 각 결정은 지금 필요한지 또는 보류 가능한지 표시하며, 최종 구성의 충돌과
운영 비용을 확인한 뒤 구현합니다.

프로필 구조 검증, 기술 조합 호환성, 생성 준비 상태는 서로 다른 결과입니다. 충돌이
없더라도 필수 결정, 정확한 동적 버전, 복합 DB·MSA 정의, 사용자 확인이 끝나지 않으면
프로젝트를 생성하지 않습니다.

### 생성 계획

`GENERATION_READY: yes`가 되면 현재 Spring Initializr 메타데이터와 기술 매핑을
사용해 `docs/generation-plan.json`을 만듭니다. 이 단계에서는 소스를 생성하지
않습니다. Initializr 요청, 구조 contributor, 외부 선행조건, secret 이름, 검증
전략만 미리 보여줍니다.

파일 생성·수정·충돌 목록은 다음 dry-run 단계에서 계산합니다. 생성 계획 자체의
`executionReady`는 그 전까지 항상 `false`입니다.

### 안전한 dry-run

생성 결과는 임시 디렉터리에만 풀고 target과 해시로 비교합니다. target에 없는 파일은
`CREATE`, 이전 승인된 생성본과 일치하는 파일의 새 버전은 `UPDATE`, 출처를 확인할 수
없는 기존 파일 차이와 심볼릭 링크·경로 타입 충돌은 `CONFLICT`입니다. 따라서 기존
사용자 코드를 단순히 업데이트 대상으로 오판하지 않습니다.

결과는 `docs/generation-dry-run.json`에 기록할 수 있지만 소스는 변경하지 않습니다.
충돌이 없어도 사용자가 목록을 승인하기 전에는 `executionReady: false`입니다. MSA는
서비스별 child plan이 준비된 뒤 각각 dry-run 합니다.

### 승인 후 적용

승인은 dry-run 보고서의 SHA-256과 target 절대 경로를 포함하는 별도 문서로 기록합니다.
적용 직전에 동일 결과를 다시 렌더링하고 보고서의 파일 해시·권한 및 현재 target 상태를
재확인합니다. 바뀐 항목이 있으면 아무 파일도 적용하지 않습니다.

교체 파일과 승인 증거는 `<target>/.starter-harness/backups/`에 보존합니다. 파일은 같은
파일시스템에서 staging한 뒤 원자적으로 교체하고, 중간 실패 시 이미 적용한 항목을
rollback합니다. 성공하면 `.starter-harness-generation.json`을 마지막에 기록하여 다음
dry-run이 안전한 `UPDATE`를 판별하게 합니다.

## 기록

| 템플릿 | 목적지 | 시점 |
|---|---|---|
| `templates/progress.md` | `<target>/docs/progress.md` | 첫 세션 생성, 매 세션 갱신 |
| `templates/project-brief.json` | `<target>/docs/project-brief.json` | 목표와 기능 후보의 구조화 기준 |
| `templates/project-brief.md` | `<target>/docs/project-brief.md` | 프로젝트 개요의 생성된 사용자 보기 |
| `templates/feature-spec.json` | `<target>/docs/features/F001/spec.json` | 한 기능의 구현 전 계약 |
| `templates/feature-spec.md` | `<target>/docs/features/F001/spec.md` | 기능 명세의 생성된 사용자 보기 |
| `templates/project-profile.json` | `<target>/docs/project-profile.json` | 구조화된 기술 선택의 기준 |
| `templates/project-profile.md` | `<target>/docs/project-profile.md` | 사람이 읽는 선택 이유와 검토 결과 |
| `templates/generation-plan.json` | `<target>/docs/generation-plan.json` | readiness 통과 후 생성 계획 컴파일 |
| `templates/generation-dry-run.json` | `<target>/docs/generation-dry-run.json` | 임시 렌더링 후 변경·충돌 검토 |
| `templates/generation-approval.json` | 승인 증거 파일 | 정확한 dry-run 해시와 target 승인 |
| `templates/generation-baseline.json` | `<target>/.starter-harness-generation.json` | 성공적으로 적용된 파일 해시·권한 |
| `templates/session-summary.md` | 채팅 출력 | 매 세션 종료 |
| `templates/project-readme.md` | `<target>/README.md` | target에 README가 없을 때 |

`이어가자`라고 하면 `<target>/docs/progress.md`와 현재 코드를 확인하고 다음
마일스톤에서 이어갑니다.
