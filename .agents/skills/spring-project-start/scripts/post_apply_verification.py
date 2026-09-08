#!/usr/bin/env python3
"""Contracts for explicit post-apply verification of an actual target."""
from __future__ import annotations
import datetime as dt,hashlib,json,os
from pathlib import Path
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object

def context_sha(root:Path)->str:
    evidence={}
    for path in sorted(root.rglob("*")):
        if path.is_symlink(): continue
        relative=path.relative_to(root).as_posix()
        if path.is_file() and (relative.startswith("src/") or path.name in {"build.gradle","build.gradle.kts","settings.gradle","settings.gradle.kts","gradle.properties","pom.xml","gradlew","mvnw"} or relative==".starter-harness-implementation.json"): evidence[relative]=sha(path)
    return hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def command(root:Path)->list[str]:
    if (root/"gradlew").is_file(): return ["./gradlew","--offline","--no-daemon","test"]
    if (root/"mvnw").is_file(): return ["./mvnw","-o","test"]
    raise ValueError("target has no Gradle or Maven wrapper")

def cache_info(root:Path)->dict:
    if (root/"gradlew").is_file():
        base=Path(os.environ.get("GRADLE_USER_HOME",Path.home()/".gradle")); ready=(base/"caches").is_dir() and (base/"wrapper").is_dir(); return {"kind":"GRADLE","status":"READY" if ready else "MISSING"}
    base=Path.home()/".m2/repository"; return {"kind":"MAVEN","status":"READY" if base.is_dir() else "MISSING"}

def validate_plan(plan:dict,path:Path,root:Path)->dict:
    required={"postApplyVerificationPlanVersion","target","completion","targetContextSha256","command","dependencyCache","effects","limits","readyForApproval"}
    if not isinstance(plan,dict) or set(plan)!=required or plan["postApplyVerificationPlanVersion"]!=1 or Path(str(plan["target"])).resolve()!=root: raise ValueError("post-apply verification plan is invalid")
    completion=plan["completion"]
    if not isinstance(completion,dict) or set(completion)!={"path","sha256"}: raise ValueError("completion reference is invalid")
    completion_path=target_path(root,completion["path"],"completion report")
    if not completion_path.is_file() or sha(completion_path)!=completion["sha256"] or load_object(completion_path).get("state")!="APPLIED_PREVERIFIED": raise ValueError("completion is not current and preverified")
    expected_effects={"network":"DISABLED","dockerSocket":"HIDDEN","targetSource":"TEMP_COPY_MONITORED","buildOutputs":"TEMPORARY","database":"NOT_STARTED","ports":"NOT_PUBLISHED"}
    current_cache=cache_info(root)
    if plan["command"]!=command(root) or plan["targetContextSha256"]!=context_sha(root) or plan["dependencyCache"]!=current_cache or plan["effects"]!=expected_effects or plan["readyForApproval"] is not (current_cache["status"]=="READY"): raise ValueError("post-apply plan no longer matches the target")
    if plan["readyForApproval"] is not True: raise ValueError("local dependency cache is missing; verification readiness is UNKNOWN")
    if not isinstance(plan["limits"],dict) or set(plan["limits"])!={"timeoutSeconds","maxOutputCharacters"} or not 30<=plan["limits"]["timeoutSeconds"]<=1800 or not 1000<=plan["limits"]["maxOutputCharacters"]<=50000: raise ValueError("post-apply limits are invalid")
    if path.is_symlink() or root not in path.resolve().parents: raise ValueError("plan must be target-owned")
    return load_object(completion_path)

def validate_approval(value:dict,plan_path:Path,root:Path)->None:
    required={"postApplyVerificationApprovalVersion","approved","planSha256","viewSha256","target","approvedBy","approvedAt"}
    if not isinstance(value,dict) or set(value)!=required or value["postApplyVerificationApprovalVersion"]!=1 or value["approved"] is not True or value["planSha256"]!=sha(plan_path) or Path(str(value["target"])).resolve()!=root or not isinstance(value["approvedBy"],str) or not value["approvedBy"].strip(): raise ValueError("exact post-apply plan approval is required")
    timestamp=dt.datetime.fromisoformat(value["approvedAt"].replace("Z","+00:00"))
    if timestamp.utcoffset() is None: raise ValueError("approval time must include a timezone")

def validate_report(report:dict,report_path:Path,root:Path)->dict:
    required={"postApplyVerificationReportVersion","verificationLevel","plan","approval","target","targetContextSha256","command","isolation","result","verifiedAt","readyForFinalization"}
    if not isinstance(report,dict) or set(report)!=required or report["postApplyVerificationReportVersion"]!=1 or report["verificationLevel"]!="APPLIED_TEST_ISOLATED" or Path(str(report["target"])).resolve()!=root: raise ValueError("post-apply verification report is invalid")
    refs={}
    for name in ("plan","approval"):
        ref=report[name]
        if not isinstance(ref,dict) or set(ref)!={"path","sha256"}: raise ValueError(f"post-apply {name} reference is invalid")
        path=target_path(root,ref["path"],f"post-apply {name}")
        if not path.is_file() or sha(path)!=ref["sha256"]: raise ValueError(f"post-apply {name} evidence changed")
        refs[name]=path
    plan=load_object(refs["plan"]); validate_plan(plan,refs["plan"],root); validate_approval(load_object(refs["approval"]),refs["plan"],root)
    result=report["result"]
    if report["targetContextSha256"]!=plan["targetContextSha256"] or report["command"]!=plan["command"] or report["isolation"]!=plan["effects"] or not isinstance(result,dict) or set(result)!={"state","exitCode","output"} or result["state"] not in {"PASSED","FAILED","UNKNOWN"} or not isinstance(result["exitCode"],int) or not isinstance(result["output"],str) or report["readyForFinalization"] is not (result["state"]=="PASSED" and result["exitCode"]==0): raise ValueError("post-apply verification result is inconsistent")
    if report_path.is_symlink() or root not in report_path.resolve().parents: raise ValueError("post-apply report must be target-owned")
    return plan

def render(plan:dict,completion:dict)->str:
    cache="준비됨" if plan["dependencyCache"]["status"]=="READY" else "없음 · 현재 실행 불가"
    return "\n".join([f"# {completion['featureName']} 적용 후 검증","",f"> {completion['userValue']}"
,"","## 현재 상태","","- 코드 적용: 완료","- 적용 전 격리 테스트: 통과","- 적용 상태 기반 격리 재검증: 아직 실행하지 않음","","## 실행할 검증","",f"- 명령: `{' '.join(plan['command'])}`",f"- 로컬 {plan['dependencyCache']['kind']} 의존성 캐시: {cache}","- 네트워크: 차단","- Docker·DB·포트: 사용하지 않음","- 호스트 환경변수와 사용자 홈: 노출하지 않음","- 소스: 적용된 target의 임시 복사본이며 실행 전후 변경 감지","- 실제 target 소스: 변경하지 않음","- 빌드 출력: 임시 디렉터리에서 생성 후 삭제","",f"- 제한 시간: {plan['limits']['timeoutSeconds']}초","","## 선택","","- 이 검증으로 진행","- 지금은 보류","- DB·애플리케이션 시작 등 다른 검증을 자연어로 요청",""])
