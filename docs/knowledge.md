# Knowledge

Knowledge는 장기적으로 남길 가치가 있는 context입니다. Source of Truth가 아니라
탐색과 학습을 돕는 index입니다.

## 저장할 만한 것

- 반복적으로 등장하는 business rule
- customer-specific rule의 이유
- legacy/workaround의 배경
- 중요한 architecture decision
- incident에서 확인된 root cause와 evidence
- 자주 확인해야 하는 workflow

저장하지 않는 것이 나은 것:

- 일회성 분석 결과
- 금방 stale될 파일 목록
- evidence 없는 AI 추론
- 테스트 실행 로그 전체
- production log 원문
- secret/PII/customer data

## Metadata

Knowledge entry는 다음 metadata를 기준으로 합니다.

```yaml
id:
type:
status:
scope:
observed_behavior:
intended_behavior:
evidence:
related:
last_verified:
```

## Status

| Status | Meaning |
|---|---|
| `CONFIRMED` | evidence와 human approval이 있는 장기 Knowledge |
| `INFERRED` | AI 추론. 단독 구현 근거로 사용 금지 |
| `UNKNOWN` | evidence 부족 |
| `STALE` | evidence 파일 변경/삭제/rename 등으로 재확인 필요 |
| `REVIEW_REQUIRED` | AI proposal 또는 human review 필요 |

`CONFIRMED`는 AI가 혼자 부여할 수 없습니다.

## Proposal Flow

```text
AI proposal
  |
  v
Human review
  |
  v
Approved Knowledge update
```

Knowledge 자동 overwrite는 금지입니다.

## Report와 Knowledge 구분

- `reports/`: 일회성 또는 임시 산출물. Git에 포함하지 않습니다.
- `knowledge/`: 승인된 장기 context.

Context Pack, RCA report, verification report는 기본적으로 report입니다. 장기 가치가
확인된 내용만 Knowledge proposal을 거쳐 승격합니다.
