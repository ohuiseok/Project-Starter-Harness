#!/usr/bin/env python3
"""Render implementation plan v2 with progressive disclosure."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from spring_implementation_plan_v2 import validate
from validate_feature_specs import load_object
def esc(v):return str(v).replace("`","\\`").replace("<","&lt;").replace(">","&gt;")
def render(plan,blockers):
 s=plan["summary"];ready=plan["status"]=="REVIEW_READY" and not blockers;capability_ready=plan["capability"]["planning"]=="SUPPORTED" and not any(i["source"]=="CAPABILITY_CATALOG" for i in plan["conflicts"]);lines=[f"# {esc(plan['featureId'])} 범용 Spring 구현 계획", "",f"- 상태: {plan['status']}",f"- 다음 단계 진행 가능: {'예' if ready else '아니요'}",f"- capability: {plan['capability']['adapterId']}",f"- API {s['operations']} · 컴포넌트 {s['components']} · 생성 {s['create']} · 확장 {s['extend']} · 재사용 {s['reuse']}",f"- 테스트 {s['tests']}개","","## 사용자 영향과 지원 범위","",f"- API-only: {'지원' if capability_ready else '현재 조합은 차단'}",f"- 보안: {'이번 작업에서 사용하지 않음' if plan['scope']['security']=='NOT_USED' else '현재 adapter 미지원'}","- DB·외부 client·build 변경: 이번 계획에서 사용하지 않음",f"- 코드 dry-run: 불가 · {plan['advancement']['reason']}","","## API별 구현",""]
 for op in plan["operationLinks"]:
  semantics=op["implementationSemantics"];body=", ".join(semantics["requestBody"]["content"]) if semantics["requestBody"] else "없음"
  lines.extend([f"- **{op['method']} `{esc(op['path'])}`** · `{esc(op['operationId'])}`",f"  - 구현 {len(op['componentRefs'])}개 · 테스트 {len(op['testRefs'])}개 · 요구사항 {len(op['requirementRefs'])}개",f"  - 입력 parameter {len(semantics['parameters'])}개 · body {esc(body)} · 응답 {', '.join(esc(i) for i in semantics['responses'])}",f"  - 보안 {'필요' if op['security']['required'] else '없음'} · 요구사항 {', '.join(esc(i) for i in op['requirementRefs']) or '없음'}"])
 shared=[i for i in plan["components"] if len(i["operationRefs"])>1];lines.extend(["","## 공유 컴포넌트",""]+[f"- `{esc(i['target']['typeName'])}` · {', '.join(i['operationRefs'])}" for i in shared] if shared else ["","## 공유 컴포넌트","","- 없음"])
 lines.extend(["","## 충돌과 UNKNOWN",""])
 if not plan["conflicts"] and not plan["unknowns"] and not blockers:lines.append("- 없음")
 for i in plan["conflicts"]+plan["unknowns"]:lines.append(f"- `{esc(i['code'])}` · {esc(i['message'])} · `{esc(i['subject'])}`")
 for i in blockers:lines.append(f"- 검증: {esc(i)}")
 lines.extend(["","## 상세 심볼과 파일",""])
 for i in plan["components"]:lines.append(f"- {i['role']} · {i['fileAction']} · `{esc(i['target']['path'])}` · {', '.join(sorted({s['action'] for s in i['symbols']}))}")
 lines.extend(["","## 검증 범위","","- 현재 자동화 연결: API 계약·validation 경계","- 비즈니스 행동 검증: 별도 구현 행동 증거가 필요","- build 변경: 허용하지 않음",f"- 전용 baseline: `{esc(plan['baseline']['path'])}`"])
 lines.extend(["","## 선택",""])
 if ready:lines.extend(["- 추천: 이 구현 계획 승인","- 항목별 수정: 먼저 Spring 매핑을 새 revision으로 수정","- 자연어로 변경 요청","- 취소"])
 else:lines.extend(["- 추천: 표시된 충돌·UNKNOWN을 해결한 Spring 매핑 revision 생성","- 자연어로 수정 방향 입력","- 취소"])
 lines.extend(["","## 현재 승인 효과","","- 이 단계는 구현 계획 검토만 가능","- v2 코드 dry-run renderer가 준비되기 전에는 코드 생성·검증·적용 불가","- 소스, 테스트 실행, commit, push 변경 없음",""])
 return "\n".join(lines)
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--check",action="store_true");a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);plan=load_object(a.plan);content=render(plan,validate(plan,root))
  if not a.check:raise ValueError("v2 view is created atomically with its plan")
  if not a.output.is_file() or a.output.read_text()!=content:raise ValueError("implementation plan v2 view is stale")
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_IMPLEMENTATION_PLAN_V2_VIEW_VALID: no\nERROR: {e}");return 1
 print("SPRING_IMPLEMENTATION_PLAN_V2_VIEW_VALID: yes");return 0
if __name__=="__main__":sys.exit(main())
