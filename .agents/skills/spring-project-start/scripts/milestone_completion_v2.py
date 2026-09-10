#!/usr/bin/env python3
"""Evidence-first completion/progress v2 contracts."""
from __future__ import annotations
import datetime as dt,hashlib,json
from pathlib import Path,PurePosixPath
from http_api_spring_mapping import reference
from post_apply_verification_v2 import validate_approval as validate_post_approval,validate_plan as validate_post_plan
from render_post_apply_verification_result_v2 import validate as validate_post_result
from spring_code_apply_v2 import BASELINE,MANAGED,sha
from validate_feature_specs import load_object
PROGRESS="docs/progress-v2.json";VIEW="docs/progress-v2.md";LOCK=f"{MANAGED}/locks/milestone-completion-v2.lock"
def encoded(v:dict)->bytes:return (json.dumps(v,ensure_ascii=False,indent=2)+"\n").encode()
def timestamp(value:str)->dt.datetime:
 parsed=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
 if parsed.utcoffset() is None:raise ValueError("completion time must include timezone")
 return parsed
def ref_load(root:Path,ref:dict,name:str)->tuple[Path,dict]:
 path=root/ref["path"]
 if reference(path,root)!=ref:raise ValueError(name+" evidence changed")
 return path,load_object(path)
def evidence_chain(root:Path,post_path:Path,feature_path:Path)->dict:
 post=load_object(post_path);validate_post_result(post,post_path,root)
 if post["state"]!="VERIFIED" or not post["readyForMilestoneCompletion"] or post["milestoneCompletionAuthorized"]:raise ValueError("post-apply result is not completion-ready")
 post_plan_path,post_plan=ref_load(root,post["plan"],"post-apply plan");validate_post_plan(post_plan,post_plan_path,root,False);validate_post_approval(root,root/post["approval"]["path"],post_plan_path,False)
 apply_path,apply_result=ref_load(root,post["applyResult"],"apply result");verification_path,verification=ref_load(root,apply_result["verification"],"candidate verification");dry_path,dry=ref_load(root,verification["dryRun"],"dry run");plan_approval_path,plan_approval=ref_load(root,dry["implementationPlanApproval"],"implementation plan approval");plan_path,plan=ref_load(root,plan_approval["implementationPlan"],"implementation plan")
 mapping_path,mapping=ref_load(root,plan["inputs"]["springMapping"],"Spring mapping")
 feature=load_object(feature_path);feature_id=feature.get("feature",{}).get("id")
 if mapping.get("inputs",{}).get("featureSpec")!=reference(feature_path,root) or mapping.get("featureId")!=feature_id or plan.get("featureId")!=feature_id or plan.get("planId")!=dry.get("planId") or verification.get("result",{}).get("state")!="PASSED":raise ValueError("feature-to-verification evidence chain is inconsistent")
 baseline=root/BASELINE
 if apply_result["baseline"]!={"path":BASELINE,"sha256":sha(baseline)}:raise ValueError("implementation baseline changed")
 times={"implementedAt":apply_result["committedAt"],"verifiedAt":post["finishedAt"]}
 if timestamp(times["implementedAt"])>timestamp(times["verifiedAt"]):raise ValueError("implementation and verification times are inconsistent")
 return {"feature":feature,"featureId":feature_id,"featureRef":reference(feature_path,root),"implementationPlan":reference(plan_path,root),"dryRun":reference(dry_path,root),"candidateVerification":reference(verification_path,root),"applyResult":reference(apply_path,root),"postApplyVerification":reference(post_path,root),"baseline":apply_result["baseline"],"times":times}
def candidates(project:dict,completed:set[str])->tuple[list[dict],list[dict]]:
 ready=[];blocked=[];unknown={i["id"]:i["status"] for i in project.get("unknowns",[])}
 for item in sorted(project.get("featureCandidates",[]),key=lambda x:x["recommendedOrder"]):
  if item["id"] in completed:continue
  reasons=[];missing=[i for i in item["dependsOn"] if i not in completed];unresolved=[i for i in item["blockingUnknownIds"] if unknown.get(i)!="RESOLVED"]
  if item["status"]=="DEFERRED":reasons.append("DEFERRED")
  if missing:reasons.append("DEPENDENCIES:"+",".join(missing))
  if unresolved:reasons.append("UNKNOWNS:"+",".join(unresolved))
  value={"featureId":item["id"],"name":item["name"],"userValue":item["userValue"],"reason":item["recommendationReason"]}
  (blocked if reasons else ready).append({**value,**({"blockers":reasons} if reasons else {})})
 return ready,blocked
def build_review(root:Path,post_path:Path,feature_path:Path,project_path:Path,completion_path:str,approved_at:str)->dict:
 relative=PurePosixPath(completion_path)
 if not completion_path or relative.is_absolute() or ".." in relative.parts or relative.suffix!=".json" or relative.parts[0]!="docs":raise ValueError("completion output path is unsafe")
 chain=evidence_chain(root,post_path,feature_path);project=load_object(project_path);approved_time=timestamp(approved_at)
 if approved_time<timestamp(chain["times"]["verifiedAt"]):raise ValueError("completion approval time precedes verification")
 progress_path=root/PROGRESS;legacy=root/"docs/progress.json";blockers=[]
 for target in (root/relative,progress_path,root/VIEW):
  if target.is_symlink() or root not in target.resolve().parents:raise ValueError("completion target path is unsafe")
 if legacy.exists() and not progress_path.exists():blockers.append({"code":"PROGRESS_V1_MIGRATION_REQUIRED","subject":"docs/progress.json"})
 existing=load_object(progress_path) if progress_path.exists() else None
 if existing and existing.get("progressV2Version")!=1:raise ValueError("existing progress v2 is invalid")
 completed=list(existing["completedMilestones"] if existing else [])
 if chain["featureId"] in {i["featureId"] for i in completed}:blockers.append({"code":"FEATURE_ALREADY_COMPLETED","subject":chain["featureId"]})
 completion={"milestoneCompletionV2Version":1,"featureId":chain["featureId"],"state":"COMPLETED","verificationLevels":{"candidateIsolated":"PASSED","appliedIsolated":"PASSED","databaseIntegration":"NOT_RUN","applicationStartup":"NOT_RUN","httpSmoke":"NOT_RUN","deployment":"NOT_RUN"},"evidence":{k:chain[k] for k in ("featureRef","implementationPlan","dryRun","candidateVerification","applyResult","postApplyVerification","baseline")},"implementedAt":chain["times"]["implementedAt"],"verifiedAt":chain["times"]["verifiedAt"],"completionApprovedAt":approved_at,"recordedAt":approved_at,"gitCommitOrPush":"NOT_RUN"};completion_sha=hashlib.sha256(encoded(completion)).hexdigest();completed.append({"featureId":chain["featureId"],"name":chain["feature"]["feature"]["name"],"userValue":chain["feature"]["feature"]["userValue"],"state":"COMPLETED","completion":{"path":completion_path,"sha256":completion_sha}});ready,blocked_candidates=candidates(project,{i["featureId"] for i in completed})
 progress={"progressV2Version":1,"target":str(root),"project":project["project"],"completedMilestones":completed,"verificationLevelModelVersion":1,"recommendationPolicyVersion":1,"nextCandidates":ready,"blockedCandidates":blocked_candidates,"current":{"state":"READY_FOR_NEXT_FEATURE" if ready else "NO_ELIGIBLE_FEATURE","recommendedFeatureId":ready[0]["featureId"] if ready else None},"updatedAt":approved_at}
 before=reference(progress_path,root) if progress_path.exists() else None;identity=hashlib.sha256((chain["postApplyVerification"]["sha256"]+"\0"+(before or {}).get("sha256","")+"\0"+completion_path).encode()).hexdigest()[:24]
 return {"milestoneCompletionReviewV2Version":1,"state":"REVIEW_READY" if not blockers else "BLOCKED","completionAttemptId":"completion-v2-"+identity,"target":str(root),"projectBrief":reference(project_path,root),"feature":chain["featureRef"],"postApplyVerification":chain["postApplyVerification"],"progressBefore":before,"completion":{"path":completion_path,"sha256":completion_sha,"document":completion},"progressAfter":{"path":PROGRESS,"sha256":hashlib.sha256(encoded(progress)).hexdigest(),"document":progress},"progressViewPath":VIEW,"blockers":blockers,"effects":{"sourceMutation":False,"testExecution":False,"progressMutation":True,"gitCommitOrPush":"NOT_RUN"},"readyForApproval":not blockers}
def render(review:dict)->str:
 c=review["completion"]["document"];p=review["progressAfter"]["document"];next_id=p["current"]["recommendedFeatureId"] or "없음"
 return "\n".join(["# 마일스톤 완료 검토","",f"- 완료 기능: `{c['featureId']}`",f"- 완료 상태: `{c['state']}`","- 후보 격리 테스트: 통과","- 적용 상태 격리 테스트: 통과","- DB·구동·HTTP·배포 검증: 아직 실행하지 않음",f"- 다음 추천 기능: `{next_id}`",f"- 차단: {len(review['blockers'])}개","- 소스 변경·테스트·Git commit/push: 실행하지 않음","","## 선택","","1. 추천: 완료 기록 적용","2. 완료 내용 검토","3. 지금은 기록하지 않음","4. 기타 / 자연어 입력",""])
def validate_review(value:dict,path:Path,root:Path,current:bool=True)->dict:
 required={"milestoneCompletionReviewV2Version","state","completionAttemptId","target","projectBrief","feature","postApplyVerification","progressBefore","completion","progressAfter","progressViewPath","blockers","effects","readyForApproval"}
 if not isinstance(value,dict) or set(value)!=required or value["milestoneCompletionReviewV2Version"]!=1 or Path(value["target"]).resolve()!=root:raise ValueError("milestone completion v2 review is invalid")
 if current:
  expected=build_review(root,root/value["postApplyVerification"]["path"],root/value["feature"]["path"],root/value["projectBrief"]["path"],value["completion"]["path"],value["completion"]["document"]["completionApprovedAt"])
  if expected!=value:raise ValueError("milestone completion review is stale")
 if path.is_symlink() or root not in path.resolve().parents:raise ValueError("completion review must be target-owned")
 return value
def render_progress(value:dict)->str:
 lines=[f"# {value['project']['name']} 진행 상황","",f"> {value['project']['goal']}","","## 완료",""]
 for item in value["completedMilestones"]:lines.extend([f"- `{item['featureId']}` · {item['name']} · 완료",f"  - 사용자 가치: {item['userValue']}"])
 lines.extend(["","## 다음 추천",""])
 if value["nextCandidates"]:
  for i,item in enumerate(value["nextCandidates"],1):lines.append(f"{i}. `{item['featureId']}` · {item['name']} — {item['reason']}")
 else:lines.append("- 현재 바로 시작할 수 있는 후보가 없습니다.")
 lines.extend(["","## 계속 개발하기","","- 추천 기능으로 진행","- 다른 기존 후보 선택","- 새 기능을 자연어로 입력","- 완료 기능 수정","- 기술 스택 변경","- 기타 / 직접 입력",""])
 return "\n".join(lines)
