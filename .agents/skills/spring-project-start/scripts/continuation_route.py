#!/usr/bin/env python3
"""Evidence-first, privacy-minimized natural-language continuation routing."""
from __future__ import annotations
import datetime as dt,hashlib,json,re
from pathlib import Path
from next_feature_id import next_feature_id
from spring_milestone_completion import sha,target_path,validate_progress
from validate_feature_specs import load_object,validate_project
ROUTES={"NEXT_FEATURE","NEW_FEATURE","REVISE_FEATURE","BUG_FIX","TECHNOLOGY_CHANGE","RETRY_VERIFICATION","RESUME_DEFERRED","NEEDS_CLARIFICATION","BLOCKED"}
SECRET=re.compile(r"(?i)(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|(?:password|passwd|token|api[_-]?key|secret)\s*[:=]\s*\S+)")
EMAIL=re.compile(r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9_])"); PHONE=re.compile(r"(?<!\d)(?:01[016789][ -]?\d{3,4}[ -]?\d{4})(?!\d)"); RRN=re.compile(r"(?<!\d)\d{6}[ -]?[1-4]\d{6}(?!\d)"); NAMED_PERSON=re.compile(r"([가-힣]{2,4})(?=\s*(?:님|씨|의\s*이메일|\s*이메일))")
def sanitize(value:str)->str:
    if not isinstance(value,str) or not value.strip() or len(value)>2000 or SECRET.search(value): raise ValueError("request is empty, too long, or may contain a secret")
    value=RRN.sub("[개인식별번호]",PHONE.sub("[전화번호]",EMAIL.sub("[이메일]",value))); value=NAMED_PERSON.sub("[이름]",value)
    return re.sub(r"[\x00-\x1f\x7f]+"," ",value).strip()
def markdown(value:str)->str: return value.replace("\\","\\\\").replace("`","\\`").replace("<","&lt;").replace(">","&gt;").replace("#","\\#").replace("|","\\|")
def ref(path:Path,root:Path)->dict: return {"path":path.resolve().relative_to(root).as_posix(),"sha256":sha(path)}
def words(value:str)->set[str]: return {word for word in re.findall(r"[0-9A-Za-z가-힣]+",value.lower()) if len(word)>1}
def contains(value:str,terms:tuple[str,...])->bool: return any(term in value.lower() for term in terms)
def technology_terms()->set[str]:
    catalog=load_object(Path(__file__).resolve().parents[1]/"references/technology-options.json"); values=[]
    def visit(value):
        if isinstance(value,str): values.append(value.lower())
        elif isinstance(value,dict):
            for item in value.values(): visit(item)
        elif isinstance(value,list):
            for item in value: visit(item)
    visit(catalog); result=set()
    for value in values:
        result.update(token for token in re.findall(r"[a-z0-9.+#-]{2,}|[가-힣]{2,}",value) if len(token)>=2)
    return result|{"db","database","데이터베이스","postgres","postgresql","mysql","mariadb","mongodb","redis","kafka","rabbitmq","jwt","oauth","세션","인증","보안","jsp","msa"}
def select_candidate(request:str,project:dict,explicit:str|None)->tuple[dict|None,str,list[str]]:
    candidates=project["featureCandidates"]
    if explicit:
        matches=[item for item in candidates if item["id"]==explicit]
        if len(matches)!=1: return None,"UNKNOWN_FEATURE_ID",[f"존재하지 않는 기능 ID: {explicit}"]
        return matches[0],"EXPLICIT_FEATURE_ID",[]
    ids=[]
    for item in re.findall(r"(?<![A-Z0-9])F\d{3}(?![A-Z0-9])",request.upper()):
        if item not in ids: ids.append(item)
    if len(ids)>1: return None,"MULTIPLE_FEATURE_IDS",["여러 기능을 한 요청에서 발견: "+", ".join(ids)]
    if ids:
        matches=[item for item in candidates if item["id"]==ids[0]]
        return (matches[0],"REQUEST_FEATURE_ID",[]) if matches else (None,"UNKNOWN_FEATURE_ID",[f"존재하지 않는 기능 ID: {ids[0]}"])
    exact=[item for item in candidates if item["name"].lower() in request.lower()]
    if len(exact)==1: return exact[0],"EXACT_CANDIDATE_NAME",[]
    scored=[(len(words(request)&words(item["name"]+" "+item["userValue"])),item) for item in candidates]; scored.sort(key=lambda pair:(-pair[0],pair[1]["recommendedOrder"]))
    return ((scored[0][1],"TOKEN_OVERLAP",[]) if scored and scored[0][0]>=2 and (len(scored)==1 or scored[0][0]>scored[1][0]) else (None,"NO_UNIQUE_MATCH",[]))
def build_route(root:Path,request:str,project_path:Path,progress_path:Path,explicit_feature_id:str|None=None,reserved_feature_id:str|None=None,reservation:dict|None=None)->dict:
    request=sanitize(request); project=load_object(project_path); project_approved,_=validate_project(project); progress=load_object(progress_path); validate_progress(progress,root)
    if not project_approved: raise ValueError("continuation requires an approved current project brief")
    if progress["project"]!={"name":project["project"]["name"],"goal":project["project"]["goal"]}: raise ValueError("progress and project brief identify different projects")
    candidate,matched_by,decisions=select_candidate(request,project,explicit_feature_id); completed={item["featureId"] for item in progress["completedMilestones"]}; blocked={item["featureId"]:item for item in progress["blockedCandidates"]}; generic_next=contains(request,("다음","추천","계속","next","continue")); lower=request.lower(); change=contains(lower,("변경","바꿔","교체","전환","추가","제거","change","switch","replace","add","remove")); tech=change and any(term in lower for term in technology_terms())
    route_type="NEW_FEATURE"; workflow="FEATURE_SPECIFICATION"; change_kind="FEATURE"; blockers=[]; warnings=[]; confidence="MEDIUM"; selected=None
    if decisions: route_type="NEEDS_CLARIFICATION"; workflow="CONTINUATION_ROUTING"; confidence="LOW"
    elif contains(request,("검증 재시도","테스트 재시도","retry verification","retry test")): route_type="RETRY_VERIFICATION"; workflow="POST_APPLY_VERIFICATION"; change_kind="VERIFICATION_RETRY"; confidence="HIGH"
    elif tech: route_type="TECHNOLOGY_CHANGE"; workflow="TECHNOLOGY_SELECTION"; change_kind="TECHNOLOGY_CHANGE"; confidence="HIGH"
    elif contains(request,("기존 기능 수정","기능 변경","요구사항 변경","revise","change feature")): route_type="REVISE_FEATURE"; change_kind="REVISION"; confidence="HIGH" if candidate else "LOW"
    elif contains(request,("버그","오류","에러","고쳐","수정해줘","bug","fix")): route_type="BUG_FIX"; change_kind="BUG_FIX"; confidence="MEDIUM"
    elif contains(request,("보류 재개","다시 시작","resume")): route_type="RESUME_DEFERRED"; change_kind="RESUME"; confidence="HIGH" if candidate else "LOW"
    elif candidate: route_type="NEXT_FEATURE"; confidence="HIGH" if matched_by!="TOKEN_OVERLAP" else "MEDIUM"
    elif generic_next:
        feature_id=progress["current"]["recommendedFeatureId"]
        if feature_id: candidate=next(item for item in project["featureCandidates"] if item["id"]==feature_id); route_type="NEXT_FEATURE"; matched_by="CURRENT_RECOMMENDATION"; confidence="HIGH"
        else: route_type="NEEDS_CLARIFICATION"; workflow="CONTINUATION_ROUTING"; confidence="LOW"; decisions.append("현재 추천 후보가 없어 원하는 기능 설명 필요")
    if route_type=="RETRY_VERIFICATION":
        candidate=None; pending=[item for item in progress["completedMilestones"] if item["state"]=="APPLIED_PREVERIFIED"]
        if pending: item=pending[-1]; selected={"featureId":item["featureId"],"name":item["name"],"userValue":item["userValue"]}
        else: route_type="NEEDS_CLARIFICATION"; workflow="CONTINUATION_ROUTING"; confidence="LOW"; decisions.append("재검증을 기다리는 마일스톤이 없음")
    elif route_type=="TECHNOLOGY_CHANGE": candidate=None
    if candidate:
        selected={"featureId":candidate["id"],"name":candidate["name"],"userValue":candidate["userValue"]}
        if candidate["id"] in completed and route_type not in {"REVISE_FEATURE","BUG_FIX"}: route_type="REVISE_FEATURE"; change_kind="REVISION"; warnings.append("완료 기능이므로 별도 revision 명세 필요")
        if candidate["id"] in blocked:
            for reason in blocked[candidate["id"]]["blockers"]:
                (warnings if reason=="status:DEFERRED" and route_type=="RESUME_DEFERRED" else blockers).append(reason)
        if candidate["status"]=="DEFERRED" and route_type=="NEXT_FEATURE": route_type="RESUME_DEFERRED"; change_kind="RESUME"; warnings.append("보류 기능 재개 확인 필요")
    elif route_type in {"REVISE_FEATURE","RESUME_DEFERRED"}: route_type="NEEDS_CLARIFICATION"; workflow="CONTINUATION_ROUTING"; decisions.append("대상 기능 식별 필요")
    proposed=None
    if route_type in {"NEW_FEATURE","BUG_FIX"} and not selected:
        feature_id=reserved_feature_id or next_feature_id(project_path,root/"docs/features"); proposed={"featureId":feature_id,"workingName":"새 기능 초안","userValue":"기능 명세에서 확인 필요"}
        if reservation: proposed["reservation"]=reservation
    if blockers: route_type="BLOCKED"; workflow="CONTINUATION_ROUTING"
    requires_confirmation=True
    return {"continuationRouteVersion":2,"request":{"summary":request,"storage":"PII_MINIMIZED","source":"USER_STATED"},"target":str(root),"projectBrief":ref(project_path,root),"progress":ref(progress_path,root),"route":{"type":route_type,"changeKind":change_kind,"matchedBy":matched_by,"confidence":confidence,"selectedFeature":selected,"proposedFeature":proposed,"blockers":blockers,"warnings":warnings,"requiredDecisions":decisions,"nextWorkflow":workflow,"requiresConfirmation":requires_confirmation},"effects":{"projectBriefChanged":False,"featureContractChanged":False,"sourceChanged":False,"runtimeExecuted":False,"gitCommitOrPush":"NOT_RUN"},"readyForHandoff":route_type not in {"NEEDS_CLARIFICATION","BLOCKED"}}
def render(value:dict)->str:
    route=value["route"]; labels={"NEXT_FEATURE":"다음 기능","NEW_FEATURE":"새 기능","REVISE_FEATURE":"기존 기능 수정","BUG_FIX":"버그 수정","TECHNOLOGY_CHANGE":"기술 변경","RETRY_VERIFICATION":"검증 재시도","RESUME_DEFERRED":"보류 기능 재개","NEEDS_CLARIFICATION":"추가 확인 필요","BLOCKED":"현재 진행 차단"}; workflows={"FEATURE_SPECIFICATION":"기능 명세","TECHNOLOGY_SELECTION":"기술 선택","POST_APPLY_VERIFICATION":"적용 상태 재검증","CONTINUATION_ROUTING":"요청 해석 보완"}; confidence={"HIGH":"높음","MEDIUM":"보통 · 확인 권장","LOW":"낮음 · 확인 필요"}; lines=["# 다음 개발 요청 해석","","- 요청 원문은 저장하지 않음",f"- 개인정보 최소화 요약: {markdown(value['request']['summary'])}","","## 이해한 진행 방향","",f"- 유형: {labels[route['type']]}",f"- 해석 확실성: {confidence[route['confidence']]}",f"- 다음 절차: {workflows[route['nextWorkflow']]}" ]; feature=route["selectedFeature"] or route["proposedFeature"]
    if feature: lines.extend([f"- 기능: {feature['featureId']} · {markdown(feature.get('name',feature.get('workingName')))}",f"- 사용자 가치: {markdown(feature['userValue'])}"])
    def readable(item):
        if item.startswith("dependencies:"): return "선행 기능 완료 필요: "+item.split(":",1)[1]
        if item.startswith("unknowns:"): return "결정이 필요한 항목: "+item.split(":",1)[1]
        if item.startswith("status:IMPLEMENTING"): return "이미 구현 중인 기능 · 현재 작업 확인 필요"
        return item
    for title,key,empty in (("진행을 막는 사항","blockers","없음"),("확인 후 진행 가능한 주의사항","warnings","없음"),("필요한 결정","requiredDecisions","없음")): lines.extend(["",f"## {title}",""]+([f"- {markdown(readable(item))}" for item in route[key]] or [f"- {empty}"]))
    lines.extend(["","## 이 확인으로 하지 않는 일","","- 기능 명세·설계·코드 자동 승인 안 함","- 파일 적용·런타임 실행 안 함","- Git commit·push 안 함","","## 선택","","- 이 해석으로 계속","- 다른 기존 후보 선택","- 해석을 자연어로 수정","- 요청 취소",""]); return "\n".join(lines)
def validate_route(value:dict,path:Path,root:Path)->None:
    required={"continuationRouteVersion","request","target","projectBrief","progress","route","effects","readyForHandoff"}
    if not isinstance(value,dict) or set(value)!=required or value["continuationRouteVersion"]!=2 or Path(str(value["target"])).resolve()!=root: raise ValueError("continuation route is invalid")
    evidence={}
    for name in ("projectBrief","progress"):
        item=value[name]
        if not isinstance(item,dict) or set(item)!={"path","sha256"}: raise ValueError(f"route {name} evidence is invalid")
        evidence[name]=target_path(root,item["path"],f"route {name}")
        if not evidence[name].is_file() or sha(evidence[name])!=item["sha256"]: raise ValueError(f"route {name} evidence changed")
    selected=value.get("route",{}).get("selectedFeature"); proposed=value.get("route",{}).get("proposedFeature"); explicit=selected["featureId"] if value.get("route",{}).get("matchedBy")=="EXPLICIT_FEATURE_ID" and selected else None; reserved=proposed["featureId"] if proposed else None
    reservation=proposed.get("reservation") if proposed else None
    if reservation:
        reservation_path=target_path(root,reservation.get("path",""),"feature reservation")
        if set(reservation)!={"path","sha256"} or not reservation_path.is_file() or sha(reservation_path)!=reservation["sha256"]: raise ValueError("feature reservation evidence changed")
        reservation_value=load_object(reservation_path)
        if reservation_value.get("featureId")!=reserved or reservation_value.get("requestSummary")!=value["request"]["summary"]: raise ValueError("feature reservation does not match route")
    expected=build_route(root,value.get("request",{}).get("summary",""),evidence["projectBrief"],evidence["progress"],explicit,reserved,reservation)
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
    route=load_object(refs["route"]); validate_route(route,refs["route"],root); approval=load_object(refs["approval"]); approval_required={"continuationRouteApprovalVersion","approved","routeSha256","viewSha256","target","approvedBy","approvedAt"}
    if not isinstance(approval,dict) or set(approval)!=approval_required or approval["continuationRouteApprovalVersion"]!=1 or approval["approved"] is not True or approval["routeSha256"]!=sha(refs["route"]) or Path(str(approval["target"])).resolve()!=root or not isinstance(approval["approvedBy"],str) or not approval["approvedBy"].strip() or not re.fullmatch(r"[a-f0-9]{64}",str(approval["viewSha256"])): raise ValueError("handoff approval is invalid")
    timestamp=dt.datetime.fromisoformat(approval["approvedAt"].replace("Z","+00:00"))
    if timestamp.utcoffset() is None: raise ValueError("handoff approval time is invalid")
    expected={"routeType":route["route"]["type"],"changeKind":route["route"]["changeKind"],"feature":route["route"]["selectedFeature"] or route["route"]["proposedFeature"],"nextWorkflow":route["route"]["nextWorkflow"]}
    if any(value[key]!=expected[key] for key in expected) or not route["readyForHandoff"]: raise ValueError("handoff does not match the approved route")
    if path.is_symlink() or root not in path.resolve().parents: raise ValueError("handoff must be target-owned")
