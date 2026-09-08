#!/usr/bin/env python3
"""Prove that the latest continuation draft is ready for final spec approval."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from continuation_route import markdown
from feature_draft_chain import encoded,head,load_context
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha
from validate_feature_specs import load_object,validate_feature
def readiness(spec:dict)->list[str]:
 _,blockers=validate_feature(spec,None); scenario=spec["scenario"]
 if spec["feature"]["name"]=="UNKNOWN": blockers.append("feature name is unresolved")
 if spec["feature"]["goal"]=="UNKNOWN": blockers.append("feature goal is unresolved")
 if spec["feature"]["userValue"]=="UNKNOWN": blockers.append("user value is unresolved")
 if not spec["actors"] or "UNKNOWN" in spec["actors"]: blockers.append("at least one resolved actor is required")
 if scenario["trigger"]=="UNKNOWN": blockers.append("trigger is unresolved")
 if not scenario["mainFlow"] or "UNKNOWN" in scenario["mainFlow"]: blockers.append("resolved main flow is required")
 if not spec["acceptanceCriteria"]: blockers.append("at least one acceptance criterion is required")
 return list(dict.fromkeys(blockers))
def render(spec:dict,blockers:list[str])->str:
 labels={"feature name is unresolved":"기능 이름 확인 필요","feature goal is unresolved":"기능 목표 확인 필요","user value is unresolved":"사용자 가치 확인 필요","at least one resolved actor is required":"주요 사용자 확인 필요","trigger is unresolved":"시작 조건 확인 필요","resolved main flow is required":"정상 흐름 확인 필요","at least one acceptance criterion is required":"검증 가능한 완료 조건 필요"}
 lines=["# 기능 명세 승인 준비 점검","",f"- 기능: {spec['feature']['id']} · {markdown(spec['feature']['name'])}",f"- 결과: {'준비 완료' if not blockers else '추가 결정 필요'}","","## 남은 사항",""]
 lines.extend([f"- {markdown(labels.get(item,item))}" for item in blockers] or ["- 없음"]); lines.extend(["","## 다음 행동","",*( ["- 최종 기능 명세 검토로 이동"] if not blockers else ["- 자연어로 남은 사항 보완"]),""]); return "\n".join(lines)
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--intake",required=True,type=Path); p.add_argument("--draft",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--view",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); intake_path=a.intake.resolve(strict=True); draft_path=a.draft.resolve(strict=True); output=a.output.resolve(strict=False); view=a.view.resolve(strict=False)
  if a.target.is_symlink() or output==view or any(root not in x.parents or x.is_symlink() for x in (intake_path,draft_path,output,view)) or output.exists() or view.exists(): raise ValueError("approval readiness paths are unsafe, duplicated, or already exist")
  intake,receipt,_=load_context(root,intake_path); actual_head,current_ref=head(root,receipt)
  if draft_path!=actual_head: raise ValueError("draft is stale; readiness requires the latest immutable draft")
  spec=load_object(draft_path); blockers=readiness(spec); value={"featureSpecApprovalReadinessVersion":1,"intake":{"path":intake_path.relative_to(root).as_posix(),"sha256":sha(intake_path)},"draft":current_ref,"projectBrief":intake["projectBrief"],"progress":intake["progress"],"featureId":spec["feature"]["id"],"blockers":blockers,"state":"READY_FOR_SPEC_APPROVAL" if not blockers else "AWAITING_USER_DECISIONS"}; output.parent.mkdir(parents=True,exist_ok=True); output_bytes=encoded(value); view_bytes=render(spec,blockers).encode(); atomic_write_bytes(output_bytes,output)
  try: atomic_write_bytes(view_bytes,view)
  except BaseException:
   try:
    if output.exists() and output.read_bytes()==output_bytes: output.unlink()
   except OSError: pass
   raise
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"FEATURE_SPEC_APPROVAL_READINESS_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_SPEC_APPROVAL_READINESS_VALID: yes"); print(f"STATE: {value['state']}"); return 0 if not value["blockers"] else 1
if __name__=="__main__": sys.exit(main())
