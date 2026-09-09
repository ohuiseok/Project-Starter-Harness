#!/usr/bin/env python3
"""Render implementation plan v2 with progressive disclosure."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from spring_implementation_plan_v2 import validate
from validate_feature_specs import load_object
def esc(v):return str(v).replace("`","\\`").replace("<","&lt;").replace(">","&gt;")
def render(plan,blockers):
 s=plan["summary"];lines=[f"# {esc(plan['featureId'])} 범용 Spring 구현 계획", "",f"- 상태: {plan['status']}",f"- capability: {plan['capability']['adapterId']}",f"- API {s['operations']} · 컴포넌트 {s['components']} · 생성 {s['create']} · 확장 {s['extend']} · 재사용 {s['reuse']}",f"- 테스트 {s['tests']}개","","## 사용자 영향과 지원 범위","","- API-only: 지원","- DB·외부 client·build 변경: 이번 계획에서 사용하지 않음",f"- 코드 dry-run: 불가 · {plan['advancement']['reason']}","","## API별 구현",""]
 for op in plan["operationLinks"]:lines.extend([f"- **{op['method']} `{esc(op['path'])}`** · `{esc(op['operationId'])}`",f"  - 구현 {len(op['componentRefs'])}개 · 테스트 {len(op['testRefs'])}개 · 요구사항 {len(op['requirementRefs'])}개"])
 shared=[i for i in plan["components"] if len(i["operationRefs"])>1];lines.extend(["","## 공유 컴포넌트",""]+[f"- `{esc(i['target']['typeName'])}` · {', '.join(i['operationRefs'])}" for i in shared] if shared else ["","## 공유 컴포넌트","","- 없음"])
 lines.extend(["","## 충돌과 UNKNOWN",""])
 if not plan["conflicts"] and not plan["unknowns"] and not blockers:lines.append("- 없음")
 for i in plan["conflicts"]+plan["unknowns"]:lines.append(f"- {esc(i['message'])} · `{esc(i['subject'])}`")
 for i in blockers:lines.append(f"- 검증: {esc(i)}")
 lines.extend(["","## 상세 심볼과 파일",""])
 for i in plan["components"]:lines.append(f"- {i['role']} · {i['disposition']} · `{esc(i['target']['path'])}` · 심볼 {len(i['symbols'])}개")
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
