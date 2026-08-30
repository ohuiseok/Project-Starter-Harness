# Harness 통합 설계안

입문 개발자가 자연어만으로 프로젝트를 만들고, 만든 것을 이해하고, 이어서
고칠 수 있게 하는 것이 목표입니다. 지금은 그 흐름이 두 repo로 끊겨 있습니다.

이 문서는 설계안입니다. 아직 합치지 않았습니다.

## 지금 상태

| | Project-Starter-Harness | project-analysis-harness |
|---|---|---|
| 대상 | 빈 repo, README-only | 운영 중인 대형 Spring 코드 |
| 사용자 | 개발 입문자 | 실무 개발자 |
| Skill | `spring-project-start` | `spring-understand`, `spring-change`, `spring-verify-knowledge` |
| 산출물 | target의 `docs/progress.md` | Context Pack, Knowledge, Reports |
| 승인 | 모르면 추천으로 진행 | 사람이 명시적으로 승인해야 구현 |

## 이미 같은 것

두 repo가 사실상 같은 규약 위에 서 있습니다.

- target repo를 harness 밖 외부에 두고, Git 상태를 섞지 않는다
- target 명령은 target root를 명시적 작업 디렉터리로 쓴다
- 파괴적 Git 명령 금지 (목록이 글자까지 동일하다)
- 증거 우선, 확인 못 하면 `UNKNOWN`, 스크립트 실패도 `UNKNOWN`
- `AGENTS.md` + `.agents/skills/` + `docs/` + `scripts/` + `templates/` 배치
- README "1~3번만 보면 됩니다" 구조
- `--target` 플래그, `TARGET_REPOSITORY` 환경변수, `config/target.local.yaml`

중복이 이미 비용을 냈습니다. Starter 쪽 스크립트 3개에 있던 인자 파싱
무한 루프(`shift 2` 가드 누락)가 **분석 harness의 스크립트 8개에도 그대로
있습니다.** 같은 코드를 두 번 복사했기 때문에 같은 버그를 두 번 갖게 된
것이고, 한쪽만 고쳐서는 사라지지 않습니다.

## 합칠 때 충돌하는 것

### 1. 승인 모델이 정반대다

- Starter: "사용자가 모르면 추천으로 진행합니다."
- Analysis: "Do not implement until a human explicitly approves the plan."

둘 다 옳습니다. 대상이 다르기 때문입니다. 입문자는 승인할 능력이 없고,
운영 코드는 승인 없이 건드리면 안 됩니다.

따라서 이건 **한 `AGENTS.md`에 나란히 쓸 수 없는 규칙**입니다. 공통 규칙과
모드별 규칙을 분리해야 합니다.

### 2. 위험도가 다르다

분석 쪽에는 고객 영향 매트릭스, 공유 코드 강화 검토, PII/시크릿 금지 규칙이
있습니다. 입문자의 학습 프로젝트에 이걸 전부 적용하면 무겁고, 반대로 운영
코드에 입문자 규칙을 적용하면 위험합니다.

### 3. 산출물 무게가 다르다

Starter는 `progress.md` 하나. Analysis는 Knowledge, Context Pack, auto-check
리포트까지 있습니다. 입문자에게 Knowledge 승인 절차를 요구할 수는 없습니다.

## 제안 구조

공통 코어는 하나로 두고, 충돌하는 규칙만 모드로 내립니다.

```text
harness/
├── AGENTS.md              # 공통 코어 + 모드 라우팅
├── modes/
│   ├── start.md           # 입문자: 추천으로 진행, 과한 기본값 금지
│   └── maintain.md        # 실무: 명시적 승인, 고객 영향 검토
├── .agents/skills/
│   ├── spring-project-start/
│   ├── spring-understand/
│   ├── spring-change/
│   └── spring-verify-knowledge/
├── scripts/
│   ├── lib/common.sh      # target 해석, preflight, 종료 코드
│   └── ...
├── docs/  templates/  examples/  tests/
```

`AGENTS.md`에 남는 것: target 분리, preflight, Git 안전, 증거/`UNKNOWN`,
스크립트 종료 코드.
`modes/`로 내려가는 것: 승인 강도, 질문 방식, 기본값 정책, 산출물 무게.

## 라우팅

사용자는 `시작해줘` 한마디만 합니다. 모드는 preflight 결과로 정합니다.

```text
scripts/check-target
  SPRING_PROJECT: no       → start  모드   (빈 repo. 의도가 하나뿐이라 안 묻는다)
  SPRING_PROJECT: yes      → 짧은 질문 하나 (이해할까 / 고칠까 / 검증할까)
  SPRING_PROJECT: UNKNOWN  → 짧은 질문 하나
```

분기 신호는 이미 존재합니다. `check-target`이 그대로 라우터가 됩니다.

빈 repo에서는 질문하지 않는다는 점이 중요합니다. 입문자는 자기 의도를 기술
용어로 말하지 못하므로, 물어보지 않아도 되는 상황에서는 묻지 않습니다.

## 이행 순서

base repo는 **이 repo(Project-Starter-Harness)**로 정했습니다. 분석 harness는
읽기 전용 복사원으로 남습니다.

1. **공통 코어 정렬** — 완료
   - `scripts/lib/common.sh`로 target 해석, 인자 파싱, 종료 코드를 통일
   - `config/target.local.yaml`을 양쪽 동일 키로 사용
   - `check-environment`로 첫 세션 환경 확인
2. **스크립트 8개 이전 + `shift 2` 무한 루프 수정** — 완료
3. **`modes/` 분리와 `AGENTS.md` 축약** — 완료
4. **Skill 4개와 템플릿, 문서 이전 + 라우팅 규칙** — 완료
5. **`tests/run-tests` 확장** — 완료 (80개)

## 남은 것

- **ripgrep 의존성.** maintain 모드 스크립트 6개가 `rg`를 요구합니다. 입문자
  기기에는 없을 가능성이 높습니다. 지금은 `check-environment`가
  `MAINTAIN_MODE_READY: no`로 알려주고 스크립트는 `UNKNOWN`을 반환합니다.
  `grep` 폴백을 넣을지는 별도 판단이 필요합니다.
- **repo 이름.** 이제 시작 전용이 아니므로 `Project-Starter-Harness`라는
  이름이 범위와 맞지 않습니다.
- **분석 harness 정리.** 내용이 이쪽으로 왔으므로, 그쪽을 보관용으로 둘지
  삭제할지 결정이 필요합니다.
- 실무자용 maintain 모드를 입문자용 배포판에 함께 넣을지, 분리 배포할지.
