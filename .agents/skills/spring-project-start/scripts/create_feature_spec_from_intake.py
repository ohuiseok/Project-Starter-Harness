#!/usr/bin/env python3
"""Create a non-authoritative feature draft from an approved continuation intake."""
from __future__ import annotations
import argparse,copy,hashlib,json,os,sys
from pathlib import Path
from continuation_route import markdown,validate_handoff
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object,validate_feature,validate_project

DESIGN={key:{"status":"UNKNOWN","reason":"UNKNOWN","source":"UNKNOWN","confirmedByUser":False} for key in ("httpApi","persistentState","messaging","scheduledJob","serverRenderedUi","separateClient","externalIntegration")}
def reference(path:Path,root:Path)->dict: return {"path":path.relative_to(root).as_posix(),"sha256":sha(path)}
def validate_intake(value:dict,path:Path,root:Path)->dict:
 required={"continuationWorkflowIntakeVersion","handoff","projectBrief","progress","requestSummary","target","workflow","routeType","changeKind","feature","state"}
 if not isinstance(value,dict) or set(value)!=required or value["continuationWorkflowIntakeVersion"]!=2 or value["state"]!="READY_FOR_WORKFLOW" or value["workflow"]!="FEATURE_SPECIFICATION" or Path(str(value["target"])).resolve()!=root: raise ValueError("feature specification intake is invalid")
 handoff_path=target_path(root,value["handoff"]["path"],"intake handoff")
 if set(value["handoff"])!={"path","sha256"} or not handoff_path.is_file() or sha(handoff_path)!=value["handoff"]["sha256"]: raise ValueError("intake handoff evidence changed")
 handoff=load_object(handoff_path); validate_handoff(handoff,handoff_path,root)
 route_path=target_path(root,handoff["route"]["path"],"intake route"); route=load_object(route_path)
 for key in ("projectBrief","progress"):
  evidence=target_path(root,value[key]["path"],f"intake {key}")
  if set(value[key])!={"path","sha256"} or not evidence.is_file() or sha(evidence)!=value[key]["sha256"]: raise ValueError(f"intake {key} evidence changed")
  if value[key]!=route[key]: raise ValueError(f"intake {key} does not match route")
 if any(value[key]!=handoff[key] for key in ("routeType","changeKind","feature")) or value["workflow"]!=handoff["nextWorkflow"]: raise ValueError("intake does not match handoff")
 if value["requestSummary"]!=route["request"]["summary"]: raise ValueError("intake request summary does not match route")
 if not isinstance(value["requestSummary"],str) or not value["requestSummary"].strip(): raise ValueError("intake request summary is invalid")
 if path.is_symlink() or root not in path.resolve().parents: raise ValueError("intake must be target-owned")
 return handoff
def draft(value:dict,project:dict,existing:dict|None=None)->dict:
 feature=value["feature"]; feature_id=feature["featureId"]; candidates={item["id"]:item for item in project["featureCandidates"]}; candidate=candidates.get(feature_id,{})
 if existing:
  result=copy.deepcopy(existing); result["feature"]["status"]="REVIEW_REQUIRED"; result["feature"]["goal"]=value["requestSummary"]; result["approval"]={"status":"REVIEW_REQUIRED","approvedBy":None,"approvedAt":None,"approvedContentSha256":None}; result["sources"].append({"id":"CONTINUATION-INTAKE","type":"USER_STATED","reference":value["requestSummary"]}); return result
 proposed_name=feature.get("name")
 if value["routeType"] in {"NEW_FEATURE","BUG_FIX"} and proposed_name=="새 기능 초안": proposed_name=None
 name=proposed_name or candidate.get("name") or value["requestSummary"][:120]
 user_value=feature.get("userValue") or candidate.get("userValue") or value["requestSummary"]
 return {"schemaVersion":2,"feature":{"id":feature_id,"name":name,"goal":value["requestSummary"],"userValue":user_value,"status":"DRAFT"},"actors":[],"scenario":{"preconditions":[],"trigger":"UNKNOWN","mainFlow":[],"alternateFlows":[],"postconditions":[]},"businessRules":[],"authorization":[],"dataAndState":[],"failureCases":[],"acceptanceCriteria":[],"designRequirements":DESIGN,"dependencies":candidate.get("dependsOn",[]),"unknowns":[{"id":f"U-{feature_id}-01","question":"주요 사용자 흐름과 검증 가능한 완료 조건은 무엇인가요?","impact":"답변 전에는 설계와 구현으로 진행할 수 없습니다.","blocking":True,"status":"OPEN"}],"sources":[{"id":"CONTINUATION-INTAKE","type":"USER_STATED","reference":value["requestSummary"]}],"approval":{"status":"DRAFT","approvedBy":None,"approvedAt":None,"approvedContentSha256":None}}
def render(value:dict,spec:dict)->str:
 kind={"NEW_FEATURE":"새 기능","NEXT_FEATURE":"다음 후보","REVISE_FEATURE":"기존 기능 수정","BUG_FIX":"버그 수정"}.get(value["routeType"],value["routeType"]); f=spec["feature"]
 return "\n".join(["# 기능 명세 초안 준비","",f"- 요청 유형: {kind}",f"- 기능: {f['id']} · {markdown(f['name'])}",f"- 요청 요약: {markdown(value['requestSummary'])}","","## 확정된 내용","",f"- 사용자 가치: {markdown(f['userValue'])}","","## 지금 결정해야 할 내용","","- 주요 사용자와 시작 조건","- 정상 흐름과 실패 흐름","- 검증 가능한 완료 조건","- API·저장소·UI 등 필요한 설계","","## 기존 프로젝트에서 달라지는 점","",("- 새 기능 후보 및 명세를 제안함" if value["routeType"] in {"NEW_FEATURE","BUG_FIX"} else "- 기존 기능의 새 명세 초안을 제안함"),"- 승인된 프로젝트 개요와 공식 기능 계약은 아직 변경하지 않음","","## 선택","","- 자연어로 내용을 보완","- 이 요청을 취소","- 개발자 상세 보기",""])
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--intake",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--draft-output",required=True,type=Path); p.add_argument("--view-output",required=True,type=Path); p.add_argument("--existing-feature",type=Path); a=p.parse_args(); written=[]
 try:
  root=a.target.resolve(strict=True); intake_path=a.intake.resolve(strict=True); draft_path=a.draft_output.resolve(strict=False); view_path=a.view_output.resolve(strict=False)
  if a.target.is_symlink() or any(root not in x.parents or x.is_symlink() for x in (intake_path,draft_path,view_path)) or draft_path.exists() or view_path.exists(): raise ValueError("feature draft paths are unsafe or already exist")
  intake=load_object(intake_path); validate_intake(intake,intake_path,root); project_path=target_path(root,intake["projectBrief"]["path"],"project brief"); project=load_object(project_path); validate_project(project); existing=None
  if intake["routeType"]=="REVISE_FEATURE" or (intake["routeType"]=="BUG_FIX" and intake["feature"].get("name")):
   if not a.existing_feature: raise ValueError("existing-feature is required for revision or targeted bug fix")
   existing_path=a.existing_feature.resolve(strict=True)
   if root not in existing_path.parents or existing_path.is_symlink(): raise ValueError("existing feature path is unsafe")
   existing=load_object(existing_path); validate_feature(existing,project)
   if existing["feature"]["id"]!=intake["feature"]["featureId"]: raise ValueError("existing feature ID does not match intake")
  spec=draft(intake,project,existing); validate_feature(spec,None); draft_bytes=(json.dumps(spec,ensure_ascii=False,indent=2)+"\n").encode(); view_bytes=render(intake,spec).encode(); intake_hash=sha(intake_path); receipt_path=root/".starter-harness/continuation-consumptions"/f"{intake_hash}.json"
  receipt={"continuationConsumptionVersion":1,"intake":reference(intake_path,root),"draft":{"path":draft_path.relative_to(root).as_posix(),"sha256":hashlib.sha256(draft_bytes).hexdigest()},"view":{"path":view_path.relative_to(root).as_posix(),"sha256":hashlib.sha256(view_bytes).hexdigest()},"featureId":spec["feature"]["id"],"state":"AWAITING_USER_DECISIONS"}; receipt_bytes=(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n").encode()
  control=root/".starter-harness"; consumption=control/"continuation-consumptions"
  if control.is_symlink() or consumption.is_symlink(): raise ValueError("consumption evidence directory is unsafe")
  consumption.mkdir(parents=True,exist_ok=True); fd=os.open(receipt_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,"wb") as stream: stream.write(receipt_bytes); stream.flush(); os.fsync(stream.fileno())
  written.append((receipt_path,receipt_bytes)); draft_path.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(draft_bytes,draft_path); written.append((draft_path,draft_bytes)); atomic_write_bytes(view_bytes,view_path); written.append((view_path,view_bytes))
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,payload in reversed(written):
   if path.exists() and path.read_bytes()==payload: path.unlink()
  print(f"FEATURE_INTAKE_DRAFT_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_INTAKE_DRAFT_VALID: yes"); print("STATE: AWAITING_USER_DECISIONS"); print("OFFICIAL_CONTRACT_CHANGED: no"); return 0
if __name__=="__main__": sys.exit(main())
