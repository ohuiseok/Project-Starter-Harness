# 자동 변경 점검 리포트

이 리포트는 로컬 script가 생성한 임시 산출물입니다. Source of Truth가 아니며,
Recommendation은 rule-based candidate입니다. Knowledge 저장, Knowledge 수정,
Business Rule 확정은 사람 승인 없이 수행하지 않습니다.

```yaml
status: UNREVIEWED
created_at: UNKNOWN
target_repository: UNKNOWN
baseline_branch: <required-baseline-branch>
current_branch: UNKNOWN
base_ref: UNKNOWN
head_ref: UNKNOWN
knowledge_recommendation: NEEDS_REVIEW
recommendation_confidence: RULE_BASED
```

## 요약

Target repository의 Git 변경사항을 기준으로 자동 점검 후보를 생성했습니다.

## 변경된 파일

| 상태 | 파일 | 영역 | 위험 | Knowledge 추천 |
|---|---|---|---|---|
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | NEEDS_REVIEW |

## 위험 후보

- UNKNOWN

## 오래된 Knowledge 후보

| Knowledge | 이유 | 추천 |
|---|---|---|
| UNKNOWN | Approved Knowledge가 없거나 evidence path 형식이 표준화되지 않았을 수 있습니다. | NEEDS_REVIEW |

## 현재 작업 영향

UNKNOWN

## 추천 프롬프트

```text
spring-verify-knowledge를 사용해서 reports/auto-check/latest.md를 검토해줘.
방금 pull한 변경사항이 기존 Knowledge, 고객사 로직, 현재 작업 브랜치에 미치는 영향을 분석해줘.
Knowledge는 자동 수정하지 말고 proposal만 작성해줘.
확인하지 못한 내용은 UNKNOWN으로 표시해줘.
```

## 사용자 확인 상태

```yaml
reviewed: false
reviewed_at: UNKNOWN
reviewed_by: UNKNOWN
review_decision: UNKNOWN
knowledge_update: UNKNOWN
```
