#!/usr/bin/env python3
"""Validate milestone completion evidence and maintain a cumulative ledger."""
from __future__ import annotations
from pathlib import Path, PurePosixPath
from apply_approved_spring_code import MANAGED
from render_generation_dry_run import digest
from run_spring_code_verification import validate_verification_report
from spring_code_dry_run import BASELINE, sha, validate_report
from spring_implementation_plan import validate as validate_plan
from validate_feature_specs import load_object, validate_feature, validate_project

ELIGIBLE_STATUSES={"DRAFT","REVIEW_REQUIRED","APPROVED"}

def target_path(root:Path,value:str,description:str)->Path:
    relative=PurePosixPath(value)
    if not isinstance(value,str) or not value or relative.is_absolute() or ".." in relative.parts: raise ValueError(f"{description} path is unsafe")
    path=root/relative
    parent=path.parent
    while parent!=root:
        if parent.is_symlink(): raise ValueError(f"{description} parent is a symbolic link")
        parent=parent.parent
    if path.is_symlink(): raise ValueError(f"{description} is a symbolic link")
    return path

def ref(path:Path,root:Path)->dict: return {"path":path.resolve().relative_to(root).as_posix(),"sha256":sha(path)}

def build_completion(root:Path,transaction_id:str,project_path:Path,feature_path:Path,dry_path:Path,verification_path:Path,completed_at:str)->dict:
    project=load_object(project_path); feature=load_object(feature_path); approved,blockers=validate_feature(feature,project); project_approved,project_blockers=validate_project(project)
    if not approved or blockers or not project_approved or project_blockers: raise ValueError("project and feature contracts must be approved and current")
    dry=load_object(dry_path); validate_report(dry,root,verify_current_baseline=False); verification=load_object(verification_path); validate_verification_report(verification,verification_path,root,allow_applied_baseline=True)
    if verification["result"]["state"]!="PASSED": raise ValueError("isolated verification did not pass")
    if not transaction_id or "/" in transaction_id or transaction_id in {".",".."}: raise ValueError("transaction ID is invalid")
    record_path=target_path(root,f"{MANAGED}/implementation-transactions/{transaction_id}/transaction.json","implementation transaction"); record=load_object(record_path)
    if record.get("state")!="COMMITTED" or Path(str(record.get("target",""))).resolve()!=root: raise ValueError("implementation transaction is not committed")
    if record.get("desiredManifest")!=dry["plannedChanges"]["desiredManifest"]: raise ValueError("transaction and dry-run manifests differ")
    baseline_path=root/BASELINE
    if baseline_path.is_symlink() or not baseline_path.is_file() or record.get("baselineAfterSha256")!=sha(baseline_path): raise ValueError("implementation baseline does not match the committed transaction")
    baseline=load_object(baseline_path); manifest=dry["plannedChanges"]["desiredManifest"]
    applied_slices=baseline.get("appliedSlices",[])
    if not any(item.get("dryRunSha256")==sha(dry_path) and item.get("verificationSha256")==sha(verification_path) and item.get("files")==sorted(manifest["files"]) for item in applied_slices if isinstance(item,dict)): raise ValueError("dry-run or verification evidence changed after the applied baseline was recorded")
    for relative,expected in manifest["files"].items():
        path=root/relative
        if path.is_symlink() or not path.is_file() or digest(path)!=expected or path.stat().st_mode&0o777!=manifest["modes"][relative] or baseline["files"].get(relative)!=expected or baseline["modes"].get(relative)!=manifest["modes"][relative]: raise ValueError(f"applied materialization changed: {relative}")
    plan_path=root/dry["implementationPlan"]["path"]; plan=load_object(plan_path)
    if validate_plan(plan,root) or plan["featureId"]!=feature["feature"]["id"]: raise ValueError("implementation plan is not current for the feature")
    components={item["componentId"]:item for item in plan["components"]}; requirements=[]
    for coverage in plan["coverage"]:
        implementation=[components[item["componentRef"]]["target"]["plannedPath"] for item in coverage["enforcedBy"]]
        tests=[components[item["componentRef"]]["target"]["plannedPath"] for item in coverage["verifiedBy"]]
        if any(path not in manifest["files"] for path in implementation+tests): raise ValueError(f"requirement evidence was not applied: {coverage['requirementRef']}")
        requirements.append({"requirementRef":coverage["requirementRef"],"implementationPaths":implementation,"testPaths":tests,"result":"PASSED"})
    return {"milestoneCompletionVersion":1,"featureId":feature["feature"]["id"],"featureName":feature["feature"]["name"],"userValue":feature["feature"]["userValue"],"state":"APPLIED_PREVERIFIED","completedAt":completed_at,"projectBrief":ref(project_path,root),"featureSpec":ref(feature_path,root),"implementationPlan":dry["implementationPlan"],"dryRun":ref(dry_path,root),"verification":ref(verification_path,root),"transaction":ref(record_path,root),"baseline":ref(baseline_path,root),"requirements":requirements,"summary":{"requirementsPassed":len(requirements),"appliedFiles":len(manifest["files"]),"automatedTestFiles":len({path for item in requirements for path in item["testPaths"]})},"postApplyRuntimeVerification":"NOT_RUN","gitCommitOrPush":"NOT_RUN"}

def validate_completion_report(report:dict,item:dict,root:Path)->None:
    required={"milestoneCompletionVersion","featureId","featureName","userValue","state","completedAt","projectBrief","featureSpec","implementationPlan","dryRun","verification","transaction","baseline","requirements","summary","postApplyRuntimeVerification","gitCommitOrPush"}
    if not isinstance(report,dict) or set(report)!=required or report["milestoneCompletionVersion"]!=1 or report["state"] not in {"APPLIED_PREVERIFIED","APPLIED_AND_VERIFIED"}: raise ValueError("completion report is invalid")
    if any(report[key]!=item[target] for key,target in (("featureId","featureId"),("featureName","name"),("userValue","userValue"),("completedAt","completedAt"))): raise ValueError("completion report and progress entry differ")
    for name in ("projectBrief","featureSpec","implementationPlan","dryRun","verification","transaction","baseline"):
        evidence=report[name]
        if not isinstance(evidence,dict) or set(evidence)!={"path","sha256"}: raise ValueError(f"completion {name} evidence is invalid")
        target_path(root,evidence["path"],f"completion {name}")

def validate_progress(value:dict,root:Path)->None:
    required={"progressVersion","target","project","completedMilestones","current","nextCandidates","blockedCandidates","unknowns","updatedAt"}
    if not isinstance(value,dict) or set(value)!=required or value["progressVersion"]!=1 or Path(str(value["target"])).resolve()!=root: raise ValueError("progress ledger is invalid")
    if not isinstance(value["project"],dict) or set(value["project"])!={"name","goal"} or not all(isinstance(value["project"][key],str) and value["project"][key].strip() for key in ("name","goal")): raise ValueError("progress project is invalid")
    if not isinstance(value["updatedAt"],str) or not value["updatedAt"].strip(): raise ValueError("progress timestamp is invalid")
    ids=[]
    for item in value["completedMilestones"]:
        if not isinstance(item,dict) or set(item)!={"featureId","name","userValue","state","completedAt","completionReport"} or item["state"] not in {"APPLIED_PREVERIFIED","APPLIED_AND_VERIFIED"} or not isinstance(item["userValue"],str) or not item["userValue"].strip(): raise ValueError("completed milestone entry is invalid")
        evidence=item["completionReport"]
        if not isinstance(evidence,dict) or set(evidence)!={"path","sha256"}: raise ValueError("completion report reference is invalid")
        report=target_path(root,evidence["path"],"completion report")
        if not report.is_file() or sha(report)!=evidence["sha256"]: raise ValueError("completion report evidence changed")
        validate_completion_report(load_object(report),item,root)
        ids.append(item["featureId"])
    if len(ids)!=len(set(ids)): raise ValueError("completed feature IDs must be unique")
    candidates=value["nextCandidates"]
    if not isinstance(candidates,list): raise ValueError("next candidates are invalid")
    candidate_ids=[]
    for item in candidates:
        if not isinstance(item,dict) or set(item)!={"featureId","name","userValue","reason"} or not all(isinstance(item[key],str) and item[key].strip() for key in item): raise ValueError("next candidate entry is invalid")
        candidate_ids.append(item["featureId"])
    if len(candidate_ids)!=len(set(candidate_ids)) or set(candidate_ids)&set(ids): raise ValueError("next candidate IDs are invalid")
    if not isinstance(value["blockedCandidates"],list): raise ValueError("blocked candidates are invalid")
    blocked_ids=[]
    for item in value["blockedCandidates"]:
        if not isinstance(item,dict) or set(item)!={"featureId","name","userValue","reason","blockers"} or not all(isinstance(item[key],str) and item[key].strip() for key in ("featureId","name","userValue","reason")) or not isinstance(item["blockers"],list) or not item["blockers"] or not all(isinstance(reason,str) and reason.strip() for reason in item["blockers"]): raise ValueError("blocked candidate entry is invalid")
        blocked_ids.append(item["featureId"])
    if len(blocked_ids)!=len(set(blocked_ids)) or (set(blocked_ids)&(set(ids)|set(candidate_ids))): raise ValueError("blocked candidate IDs are invalid")
    current=value["current"]
    expected_state="READY_FOR_NEXT_FEATURE" if candidates else "NO_ELIGIBLE_FEATURE"
    expected_recommendation=candidate_ids[0] if candidates else None
    if not isinstance(current,dict) or set(current)!={"state","recommendedFeatureId"} or current!={"state":expected_state,"recommendedFeatureId":expected_recommendation}: raise ValueError("current progress state is invalid")
    if not isinstance(value["unknowns"],list): raise ValueError("progress unknowns are invalid")
    unknown_ids=[]
    for item in value["unknowns"]:
        if not isinstance(item,dict) or set(item)!={"id","question","blocking"} or not isinstance(item["id"],str) or not item["id"].strip() or not isinstance(item["question"],str) or not item["question"].strip() or not isinstance(item["blocking"],bool): raise ValueError("progress unknown entry is invalid")
        unknown_ids.append(item["id"])
    if len(unknown_ids)!=len(set(unknown_ids)): raise ValueError("progress unknown IDs must be unique")

def candidate_assessment(project:dict,completed:set[str])->tuple[list[dict],list[dict]]:
    unknown_status={item["id"]:item["status"] for item in project["unknowns"]}; eligible=[]; blocked=[]
    for item in sorted(project["featureCandidates"],key=lambda value:value["recommendedOrder"]):
        reasons=[]
        if item["id"] in completed or item["status"]=="VERIFIED": continue
        if item["status"] not in ELIGIBLE_STATUSES: reasons.append(f"status:{item['status']}")
        missing=[dep for dep in item["dependsOn"] if dep not in completed]
        unresolved=[unknown for unknown in item["blockingUnknownIds"] if unknown_status[unknown]!="RESOLVED"]
        if missing: reasons.append("dependencies:"+",".join(missing))
        if unresolved: reasons.append("unknowns:"+",".join(unresolved))
        result={"featureId":item["id"],"name":item["name"],"userValue":item["userValue"],"reason":item["recommendationReason"]}
        if reasons: blocked.append({**result,"blockers":reasons})
        else: eligible.append(result)
    return eligible,blocked

def build_progress(existing:dict|None,project:dict,completion:dict,completion_ref:dict,root:Path)->dict:
    milestones=list(existing["completedMilestones"] if existing else [])
    if completion["featureId"] in {item["featureId"] for item in milestones}: raise ValueError("feature milestone is already completed")
    milestones.append({"featureId":completion["featureId"],"name":completion["featureName"],"userValue":completion["userValue"],"state":completion["state"],"completedAt":completion["completedAt"],"completionReport":completion_ref})
    candidates,blocked=candidate_assessment(project,{item["featureId"] for item in milestones}); unknowns=[{"id":item["id"],"question":item["question"],"blocking":item["blocking"]} for item in project["unknowns"] if item["status"]!="RESOLVED"]
    return {"progressVersion":1,"target":str(root),"project":{"name":project["project"]["name"],"goal":project["project"]["goal"]},"completedMilestones":milestones,"current":{"state":"READY_FOR_NEXT_FEATURE" if candidates else "NO_ELIGIBLE_FEATURE","recommendedFeatureId":candidates[0]["featureId"] if candidates else None},"nextCandidates":candidates,"blockedCandidates":blocked,"unknowns":unknowns,"updatedAt":completion["completedAt"]}

def render_progress(value:dict)->str:
    lines=[f"# {value['project']['name']} 진행 상황","",f"> {value['project']['goal']}","","## 완료",""]
    for item in value["completedMilestones"]:
        lines.extend([f"- {item['featureId']} · {item['name']} · 적용 및 격리 테스트 완료 (적용 후 런타임 검증 미실행)",f"  - 사용자 가치: {item['userValue']}"])
    lines.extend(["","## 남은 UNKNOWN",""])
    if value["unknowns"]:
        for item in value["unknowns"]: lines.append(f"- {item['id']} · {item['question']} · {'차단' if item['blocking'] else '나중에 결정 가능'}")
    else: lines.append("- 없음")
    lines.extend(["","## 다음 추천",""])
    if value["nextCandidates"]:
        for index,item in enumerate(value["nextCandidates"],1): lines.extend([f"{index}. {item['featureId']} · {item['name']}",f"   - 사용자 가치: {item['userValue']}",f"   - 이유: {item['reason']}"])
    else: lines.append("- 현재 바로 시작할 수 있는 후보가 없습니다.")
    if value["blockedCandidates"]:
        lines.extend(["","## 아직 시작할 수 없는 후보",""])
        labels={"status:IMPLEMENTING":"이미 구현 중","status:DEFERRED":"나중에 진행하도록 보류됨","status:VERIFIED":"이미 검증됨"}
        for item in value["blockedCandidates"]:
            reasons=[]
            for blocker in item["blockers"]:
                if blocker.startswith("dependencies:"): reasons.append("선행 기능 미완료: "+blocker.split(":",1)[1])
                elif blocker.startswith("unknowns:"): reasons.append("결정 필요: "+blocker.split(":",1)[1])
                else: reasons.append(labels.get(blocker,"현재 상태: "+blocker.split(":",1)[1]))
            lines.append(f"- {item['featureId']} · {item['name']} — {'; '.join(reasons)}")
    lines.extend(["","## 계속 개발하기","","- 추천 기능으로 진행","- 다른 후보 선택","- 원하는 기능을 자연어로 직접 입력","- 기존 기능 수정",""])
    return "\n".join(lines)
