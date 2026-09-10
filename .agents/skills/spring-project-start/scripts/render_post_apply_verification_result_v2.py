#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from http_api_spring_mapping import reference
from post_apply_verification_v2 import validate_approval,validate_plan
from spring_code_apply_v2 import MANAGED,sha
from validate_feature_specs import load_object
def validate(value:dict,path:Path,root:Path)->None:
 required={"postApplyVerificationReportV2Version","state","category","verificationLevel","plan","approval","applyResult","target","preRunSnapshotSha256","postRunSnapshotSha256","command","result","log","startedAt","finishedAt","readyForMilestoneCompletion","milestoneCompletionAuthorized"}
 if not isinstance(value,dict) or set(value)!=required or value["postApplyVerificationReportV2Version"]!=1 or value["state"] not in {"VERIFIED","FAILED","UNKNOWN"} or value["verificationLevel"]!="APPLIED_TEST_ISOLATED" or Path(value["target"]).resolve()!=root:raise ValueError("post-apply verification v2 result is invalid")
 for key in ("plan","approval","applyResult"):
  if reference(root/value[key]["path"],root)!=value[key]:raise ValueError(f"verification {key} evidence changed")
 plan_path=root/value["plan"]["path"];plan=load_object(plan_path);validate_plan(plan,plan_path,root,False);validate_approval(root,root/value["approval"]["path"],plan_path,False)
 if value["applyResult"]!=plan["applyResult"] or value["command"]!=plan["command"] or value["preRunSnapshotSha256"]!=plan["preRunSnapshot"]["sha256"] or value["postRunSnapshotSha256"]!=plan["preRunSnapshot"]["sha256"]:raise ValueError("verification result does not match its plan and snapshots")
 log=root/value["log"]["path"]
 expected_prefix=f"{MANAGED}/logs/post-apply-v2/"
 if not value["log"]["path"].startswith(expected_prefix):raise ValueError("verification log path is unsafe")
 if sha(log)!=value["log"]["sha256"] or log.stat().st_size!=value["log"]["sizeBytes"]:raise ValueError("verification log changed")
 if value["readyForMilestoneCompletion"] is not (value["state"]=="VERIFIED") or value["milestoneCompletionAuthorized"] is not False:raise ValueError("verification completion boundary is invalid")
 if path.is_symlink() or root not in path.resolve().parents:raise ValueError("verification result must be target-owned")
def render(v:dict)->str:
 action={"VERIFIED":"추천: 별도 검토 후 milestone 완료 기록","FAILED":"추천: 실패 원인 수정안 생성 후 새 attempt로 재검증","UNKNOWN":"추천: 환경·timeout·변경 원인을 해결한 뒤 새 attempt로 재검증"}[v["state"]]
 return "\n".join(["# 적용 후 검증 결과","",f"- 상태: `{v['state']}`",f"- 분류: `{v['category']}`",f"- 종료 코드: {v['result']['exitCode']}",f"- timeout: {'예' if v['result']['timedOut'] else '아니요'}",f"- 예상하지 않은 입력 변경: {'예' if v['result']['unexpectedMutation'] else '아니요'}",f"- 로그 잘림·마스킹: {'예' if v['log']['truncated'] or v['log']['redacted'] else '아니요'}","- 실제 target 입력 무결성: 유지","- milestone 완료·progress 변경: 아직 승인되지 않음","",f"다음: {action}","기타 / 자연어 입력도 가능합니다.",""])
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--result",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);path=a.result.resolve(strict=True);value=load_object(path);validate(value,path,root);output=a.output.resolve()
  if output.exists() or root not in output.parents:raise ValueError("result view output is unsafe or occupied")
  from discover_http_api_evidence import atomic_create;output.parent.mkdir(parents=True,exist_ok=True);atomic_create(render(value).encode(),output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"POST_APPLY_VERIFICATION_V2_RESULT_VALID: no\nERROR: {e}");return 1
 print("POST_APPLY_VERIFICATION_V2_RESULT_VALID: yes");return 0
if __name__=="__main__":sys.exit(main())
