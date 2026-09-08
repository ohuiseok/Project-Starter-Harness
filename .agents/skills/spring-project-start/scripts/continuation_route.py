#!/usr/bin/env python3
"""Evidence-first natural-language continuation routing contracts."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from next_feature_id import next_feature_id
from spring_milestone_completion import sha,target_path,validate_progress
from validate_feature_specs import load_object,validate_project
ROUTES={"NEXT_FEATURE","NEW_FEATURE","REVISE_FEATURE","BUG_FIX","TECHNOLOGY_CHANGE","RETRY_VERIFICATION","RESUME_DEFERRED","NEEDS_CLARIFICATION","BLOCKED"}
SECRET=re.compile(r"(?i)(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|(?:password|passwd|token|api[_-]?key|secret)\s*[:=]\s*\S+)")
def ref(path:Path,root:Path)->dict: return {"path":path.resolve().relative_to(root).as_posix(),"sha256":sha(path)}
def words(value:str)->set[str]: return {word for word in re.findall(r"[0-9A-Za-z가-힣]+",value.lower()) if len(word)>1}
def contains(value:str,terms:tuple[str,...])->bool: return any(term in value.lower() for term in terms)
def select_candidate(request:str,project:dict,explicit:str|None)->tuple[dict|None,str]:
    candidates=project["featureCandidates"]
    if explicit:
        matches=[item for item in candidates if item["id"]==explicit]
        if len(matches)!=1: raise ValueError(f"requested feature ID is not in the project brief: {explicit}")
        return matches[0],"EXPLICIT_FEATURE_ID"
    ids=re.findall(r"\bF\d{3}\b",request.upper())
    if ids:
        matches=[item for item in candidates if item["id"]==ids[0]]
        return (matches[0],"REQUEST_FEATURE_ID") if matches else (None,"UNKNOWN_FEATURE_ID")
    exact=[item for item in candidates if item["name"].lower() in request.lower()]
    if len(exact)==1: return exact[0],"EXACT_CANDIDATE_NAME"
    scored=[(len(words(request)&words(item["name"]+" "+item["userValue"])),item) for item in candidates]; scored.sort(key=lambda pair:(-pair[0],pair[1]["recommendedOrder"]))
    return (scored[0][1],"TOKEN_OVERLAP") if scored and scored[0][0]>=2 and (len(scored)==1 or scored[0][0]>scored[1][0]) else (None,"NO_UNIQUE_MATCH")
def build_route(root:Path,request:str,project_path:Path,progress_path:Path,explicit_feature_id:str|None=None)->dict:
    if not isinstance(request,str) or not request.strip() or len(request)>2000 or SECRET.search(request): raise ValueError("request is empty, too long, or may contain a secret")
    project=load_object(project_path); project_approved,_=validate_project(project); progress=load_object(progress_path); validate_progress(progress,root)
    if not project_approved: raise ValueError("continuation requires an approved current project brief")
    if progress["project"]!={"name":project["project"]["name"],"goal":project["project"]["goal"]}: raise ValueError("progress and project brief identify different projects")
    candidate,matched_by=select_candidate(request,project,explicit_feature_id); completed={item["featureId"] for item in progress["completedMilestones"]}; blocked={item["featureId"]:item for item in progress["blockedCandidates"]}; generic_next=contains(request,("다음","추천","계속","next","continue"))
    route_type="NEW_FEATURE"; workflow="FEATURE_SPECIFICATION"; change_kind="FEATURE"; blockers=[]; confidence="MEDIUM"; selected=None
    if contains(request,("검증 재시도","테스트 재시도","retry verification","retry test")): route_type="RETRY_VERIFICATION"; workflow="POST_APPLY_VERIFICATION"; change_kind="VERIFICATION_RETRY"; confidence="HIGH"
    elif contains(request,("기술 스택","기술스택","프레임워크 변경","데이터베이스 변경","db 변경","technology","tech stack")): route_type="TECHNOLOGY_CHANGE"; workflow="TECHNOLOGY_SELECTION"; change_kind="TECHNOLOGY_CHANGE"; confidence="HIGH"
    elif contains(request,("기존 기능 수정","기능 변경","요구사항 변경","revise","change feature")): route_type="REVISE_FEATURE"; workflow="FEATURE_SPECIFICATION"; change_kind="REVISION"; confidence="HIGH" if candidate else "LOW"
    elif contains(request,("버그","오류","에러","고쳐","수정해줘","bug","fix")): route_type="BUG_FIX"; workflow="FEATURE_SPECIFICATION"; change_kind="BUG_FIX"; confidence="MEDIUM"
    elif contains(request,("보류 재개","다시 시작","resume")): route_type="RESUME_DEFERRED"; workflow="FEATURE_SPECIFICATION"; change_kind="RESUME"; confidence="HIGH" if candidate else "LOW"
    elif candidate: route_type="NEXT_FEATURE"; confidence="HIGH" if matched_by!="TOKEN_OVERLAP" else "MEDIUM"
    elif generic_next and progress["current"]["recommendedFeatureId"]:
        feature_id=progress["current"]["recommendedFeatureId"]; candidate=next(item for item in project["featureCandidates"] if item["id"]==feature_id); route_type="NEXT_FEATURE"; matched_by="CURRENT_RECOMMENDATION"; confidence="HIGH"
    if route_type=="RETRY_VERIFICATION":
        pending=[item for item in progress["completedMilestones"] if item["state"]=="APPLIED_PREVERIFIED"]
        candidate=None
        if pending:
            item=pending[-1]; selected={"featureId":item["featureId"],"name":item["name"],"userValue":item["userValue"]}
        else:
            route_type="NEEDS_CLARIFICATION"; workflow="CONTINUATION_ROUTING"; confidence="LOW"; blockers.append("no preverified milestone is waiting for verification")
    elif route_type=="TECHNOLOGY_CHANGE": candidate=None
    if candidate:
        selected={"featureId":candidate["id"],"name":candidate["name"],"userValue":candidate["userValue"]}
        if candidate["id"] in completed and route_type not in {"REVISE_FEATURE","BUG_FIX"}: route_type="REVISE_FEATURE"; workflow="FEATURE_SPECIFICATION"; change_kind="REVISION"; blockers.append("completed feature requires a revision contract")
        if candidate["id"] in blocked: blockers.extend(blocked[candidate["id"]]["blockers"])
        if candidate["status"]=="DEFERRED" and route_type=="NEXT_FEATURE": route_type="RESUME_DEFERRED"; change_kind="RESUME"
    elif route_type in {"REVISE_FEATURE","RESUME_DEFERRED"}: route_type="NEEDS_CLARIFICATION"; workflow="CONTINUATION_ROUTING"; blockers.append("feature identification required")
    proposed=None
    if route_type in {"NEW_FEATURE","BUG_FIX"} and not selected:
        feature_id=next_feature_id(project_path,root/"docs/features"); proposed={"featureId":feature_id,"workingName":request.strip()[:120],"userValue":"확인 필요"}
    if blockers and route_type not in {"REVISE_FEATURE","RESUME_DEFERRED","NEEDS_CLARIFICATION"}: route_type="BLOCKED"; workflow="CONTINUATION_ROUTING"
    requires_confirmation=confidence!="HIGH" or route_type in {"NEW_FEATURE","REVISE_FEATURE","BUG_FIX","TECHNOLOGY_CHANGE","RESUME_DEFERRED","NEEDS_CLARIFICATION","BLOCKED"}
    return {"continuationRouteVersion":1,"request":{"text":request.strip(),"source":"USER_STATED"},"target":str(root),"projectBrief":ref(project_path,root),"progress":ref(progress_path,root),"route":{"type":route_type,"changeKind":change_kind,"matchedBy":matched_by,"confidence":confidence,"selectedFeature":selected,"proposedFeature":proposed,"blockers":blockers,"nextWorkflow":workflow,"requiresConfirmation":requires_confirmation},"effects":{"projectBriefChanged":False,"featureContractChanged":False,"sourceChanged":False,"runtimeExecuted":False,"gitCommitOrPush":"NOT_RUN"},"readyForHandoff":route_type not in {"NEEDS_CLARIFICATION","BLOCKED"}}
def render(value:dict)->str:
    route=value["route"]; labels={"NEXT_FEATURE":"다음 기능","NEW_FEATURE":"새 기능","REVISE_FEATURE":"기존 기능 수정","BUG_FIX":"버그 수정","TECHNOLOGY_CHANGE":"기술 변경","RETRY_VERIFICATION":"검증 재시도","RESUME_DEFERRED":"보류 기능 재개","NEEDS_CLARIFICATION":"추가 확인 필요","BLOCKED":"현재 진행 차단"}; workflows={"FEATURE_SPECIFICATION":"기능 명세","TECHNOLOGY_SELECTION":"기술 선택","POST_APPLY_VERIFICATION":"적용 상태 재검증","CONTINUATION_ROUTING":"요청 해석 보완"}; confidence={"HIGH":"높음","MEDIUM":"보통 · 확인 권장","LOW":"낮음 · 확인 필요"}; lines=["# 다음 개발 요청 해석","",f"> {value['request']['text']}","","## 이해한 진행 방향","",f"- 유형: {labels[route['type']]}",f"- 해석 확실성: {confidence[route['confidence']]}",f"- 다음 절차: {workflows[route['nextWorkflow']]}"]
    feature=route["selectedFeature"] or route["proposedFeature"]
    if feature: lines.extend([f"- 기능: {feature['featureId']} · {feature.get('name',feature.get('workingName'))}",f"- 사용자 가치: {feature['userValue']}"])
    blocker_lines=[]
    for item in route["blockers"]:
        if item.startswith("dependencies:"): blocker_lines.append("선행 기능 완료 필요: "+item.split(":",1)[1])
        elif item.startswith("unknowns:"): blocker_lines.append("결정이 필요한 항목: "+item.split(":",1)[1])
        elif item.startswith("status:DEFERRED"): blocker_lines.append("현재 보류된 기능 · 재개 확인 필요")
        elif item.startswith("status:IMPLEMENTING"): blocker_lines.append("이미 구현 중인 기능 · 현재 작업 확인 필요")
        else: blocker_lines.append(item)
    lines.extend(["","## 진행을 막는 사항",""]+[f"- {item}" for item in blocker_lines] if blocker_lines else ["","## 진행을 막는 사항","","- 없음"])
    lines.extend(["","## 이 확인으로 하지 않는 일","","- 기능 명세·설계·코드 자동 승인 안 함","- 파일 적용·런타임 실행 안 함","- Git commit·push 안 함","","## 선택","","- 이 해석으로 계속","- 다른 기존 후보 선택","- 해석을 자연어로 수정","- 요청 취소",""])
    return "\n".join(lines)
def validate_route(value:dict,path:Path,root:Path)->None:
    required={"continuationRouteVersion","request","target","projectBrief","progress","route","effects","readyForHandoff"}
    if not isinstance(value,dict) or set(value)!=required or value["continuationRouteVersion"]!=1 or Path(str(value["target"])).resolve()!=root: raise ValueError("continuation route is invalid")
    evidence={}
    for name in ("projectBrief","progress"):
        item=value[name]
        if not isinstance(item,dict) or set(item)!={"path","sha256"}: raise ValueError(f"route {name} evidence is invalid")
        evidence[name]=target_path(root,item["path"],f"route {name}")
        if not evidence[name].is_file() or sha(evidence[name])!=item["sha256"]: raise ValueError(f"route {name} evidence changed")
    selected=value.get("route",{}).get("selectedFeature"); explicit=selected["featureId"] if value.get("route",{}).get("matchedBy")=="EXPLICIT_FEATURE_ID" and selected else None
    expected=build_route(root,value.get("request",{}).get("text",""),evidence["projectBrief"],evidence["progress"],explicit)
    if value!=expected: raise ValueError("continuation route interpretation is stale or inconsistent")
    if path.is_symlink() or root not in path.resolve().parents: raise ValueError("continuation route must be target-owned")
def validate_handoff(value:dict,path:Path,root:Path)->None:
    required={"continuationHandoffVersion","route","approval","target","routeType","changeKind","feature","nextWorkflow","state"}
    if not isinstance(value,dict) or set(value)!=required or value["continuationHandoffVersion"]!=1 or value["state"]!="READY" or Path(str(value["target"])).resolve()!=root: raise ValueError("continuation handoff is invalid")
    refs={}
    for name in ("route","approval"):
        item=value[name]
        if not isinstance(item,dict) or set(item)!={"path","sha256"}: raise ValueError(f"handoff {name} reference is invalid")
        refs[name]=target_path(root,item["path"],f"handoff {name}")
        if not refs[name].is_file() or sha(refs[name])!=item["sha256"]: raise ValueError(f"handoff {name} evidence changed")
    route=load_object(refs["route"]); validate_route(route,refs["route"],root); approval=load_object(refs["approval"])
    approval_required={"continuationRouteApprovalVersion","approved","routeSha256","viewSha256","target","approvedBy","approvedAt"}
    if not isinstance(approval,dict) or set(approval)!=approval_required or approval["continuationRouteApprovalVersion"]!=1 or approval["approved"] is not True or approval["routeSha256"]!=sha(refs["route"]) or Path(str(approval["target"])).resolve()!=root: raise ValueError("handoff approval is invalid")
    expected={"routeType":route["route"]["type"],"changeKind":route["route"]["changeKind"],"feature":route["route"]["selectedFeature"] or route["route"]["proposedFeature"],"nextWorkflow":route["route"]["nextWorkflow"]}
    if any(value[key]!=expected[key] for key in expected) or not route["readyForHandoff"]: raise ValueError("handoff does not match the approved route")
    if path.is_symlink() or root not in path.resolve().parents: raise ValueError("handoff must be target-owned")
