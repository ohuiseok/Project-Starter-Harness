#!/usr/bin/env python3
"""Contracts for approved verification of an applied Spring code v2 transaction."""
from __future__ import annotations
import datetime as dt,hashlib,json,os
from pathlib import Path
from http_api_spring_mapping import reference
from render_spring_code_apply_result_v2 import validate as validate_apply_result
from spring_code_apply_v2 import BASELINE,MANAGED,sha
from spring_code_verification_v2 import cache,git_state
from validate_feature_specs import load_object
JOURNAL=f"{MANAGED}/transactions/post-apply-v2-active.json"
INPUT_NAMES={"build.gradle","build.gradle.kts","settings.gradle","settings.gradle.kts","gradle.properties","pom.xml","gradlew","mvnw"}
def manifest(root:Path)->dict:
 files={};unsafe=[]
 for path in sorted(root.rglob("*")):
  rel=path.relative_to(root).as_posix()
  relevant=rel.startswith("src/") or path.name in INPUT_NAMES or rel==BASELINE
  if path.is_symlink():
   if relevant:unsafe.append(rel)
   continue
  if path.is_file() and relevant:files[rel]={"sha256":sha(path),"mode":path.stat().st_mode&0o777}
 evidence={"files":files,"unsafeSymlinks":unsafe};digest=hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 return {"sha256":digest,**evidence}
def command(root:Path)->dict:
 if (root/"gradlew").is_file():return {"executable":"./gradlew","arguments":["--offline","--no-daemon","test"],"workingDirectory":"."}
 if (root/"mvnw").is_file():return {"executable":"./mvnw","arguments":["-o","test"],"workingDirectory":"."}
 raise ValueError("target has no Gradle or Maven wrapper")
def cache_evidence(root:Path)->dict:return cache("GRADLE" if (root/"gradlew").is_file() else "MAVEN")
def build_plan(root:Path,result_path:Path,timeout:int=600,attempt_seed:str="default")->dict:
 result=load_object(result_path);validate_apply_result(result,result_path,root);snapshot=manifest(root);cmd=command(root);dependency=cache_evidence(root);paths=set(snapshot["files"]);blockers=[]
 if dependency["status"]!="READY":blockers.append({"code":"DEPENDENCY_CACHE_MISSING","subject":dependency["kind"]})
 if not os.access(root/cmd["executable"],os.X_OK):blockers.append({"code":"WRAPPER_NOT_EXECUTABLE","subject":cmd["executable"]})
 blockers.extend({"code":"UNSAFE_SYMLINK","subject":i} for i in snapshot["unsafeSymlinks"]);attempt=hashlib.sha256((reference(result_path,root)["sha256"]+"\0"+attempt_seed).encode()).hexdigest()[:24]
 return {"postApplyVerificationPlanV2Version":1,"state":"PLAN_READY" if not blockers else "BLOCKED","attemptId":"post-apply-v2-"+attempt,"target":str(root),"applyResult":reference(result_path,root),"applyTransactionId":result["transactionId"],"preRunSnapshot":snapshot,"git":git_state(root,paths),"command":cmd,"dependencyCache":dependency,"allowedOutputs":[".gradle/","build/","target/"],"limits":{"timeoutSeconds":timeout,"maxLogBytes":1000000,"termGraceSeconds":5},"effects":{"network":"DISABLED","dockerSocket":"HIDDEN","database":"NOT_STARTED","ports":"NOT_PUBLISHED","targetInputs":"READ_ONLY_TEMP_COPY","logs":f"{MANAGED}/logs/post-apply-v2/"},"blockers":blockers,"readyForApproval":not blockers}
def validate_plan(value:dict,path:Path,root:Path,current:bool=True)->dict:
 required={"postApplyVerificationPlanV2Version","state","attemptId","target","applyResult","applyTransactionId","preRunSnapshot","git","command","dependencyCache","allowedOutputs","limits","effects","blockers","readyForApproval"}
 if not isinstance(value,dict) or set(value)!=required or value["postApplyVerificationPlanV2Version"]!=1 or Path(value["target"]).resolve()!=root:raise ValueError("post-apply verification v2 plan is invalid")
 result_path=root/value["applyResult"]["path"]
 if reference(result_path,root)!=value["applyResult"]:raise ValueError("apply result changed")
 limits=value["limits"]
 if set(limits)!={"timeoutSeconds","maxLogBytes","termGraceSeconds"} or not 30<=limits["timeoutSeconds"]<=1800 or not 10000<=limits["maxLogBytes"]<=5000000 or not 1<=limits["termGraceSeconds"]<=30:raise ValueError("verification limits are invalid")
 if current:
  expected=build_plan(root,result_path,limits["timeoutSeconds"],path.relative_to(root).as_posix());expected["limits"]=limits
  if value!=expected:raise ValueError("post-apply verification v2 plan is stale")
 if path.is_symlink() or root not in path.resolve().parents:raise ValueError("verification plan must be target-owned")
 return load_object(result_path)
def render_plan(plan:dict,result:dict)->str:
 cmd=plan["command"];shown=" ".join([cmd["executable"],*cmd["arguments"]]);lines=["# 적용 후 실제 검증","","## 결론","",f"- 실행 준비: {'예' if plan['readyForApproval'] else '아니요'}","- 적용 상태: `APPLIED_PREVERIFIED`",f"- 명령: `{shown}`","- 실행 위치: 프로젝트의 격리된 임시 복사본","- 실제 target 소스·설정·baseline: 변경하지 않음","- 네트워크·Docker·DB·포트: 사용하지 않음",f"- 제한 시간: {plan['limits']['timeoutSeconds']}초",f"- 로그 최대 크기: {plan['limits']['maxLogBytes']} bytes","- 결과가 통과해도 milestone 완료·progress 변경은 별도 승인","","## 실패 시 선택","","- 테스트 수정안 만들기 / 동일 검증 재실행 / 보류","- 환경 UNKNOWN 해결 / 제한 시간 조정 / 다른 검증 요청","- 기타 / 자연어 입력",""]
 if plan["blockers"]:lines[3:3]=[f"- 차단 `{i['code']}` · {i['subject']}" for i in plan["blockers"]]+[""]
 return "\n".join(lines)
def validate_approval(root:Path,path:Path,plan_path:Path,current:bool=True)->dict:
 value=load_object(path);required={"postApplyVerificationApprovalV2Version","state","plan","view","approvedBy","approvedAt","effects"}
 if not isinstance(value,dict) or set(value)!=required or value["postApplyVerificationApprovalV2Version"]!=1 or value["state"]!="APPROVED" or value["plan"]!=reference(plan_path,root):raise ValueError("exact post-apply verification v2 approval is required")
 plan=load_object(plan_path);result=validate_plan(plan,plan_path,root,current);view=root/value["view"]["path"]
 if reference(view,root)!=value["view"] or view.read_text()!=render_plan(plan,result):raise ValueError("approved verification review changed")
 if not value["approvedBy"].strip() or dt.datetime.fromisoformat(value["approvedAt"].replace("Z","+00:00")).utcoffset() is None:raise ValueError("approval identity or time is invalid")
 if value["effects"]!={"commandExecution":True,"milestoneCompletion":False,"gitCommitOrPush":"NOT_RUN"}:raise ValueError("approval effects are invalid")
 return value
