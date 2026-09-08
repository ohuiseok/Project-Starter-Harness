#!/usr/bin/env python3
"""Append one validated, immutable feature draft revision."""
from __future__ import annotations
import argparse,hashlib,json,os,sys
from pathlib import Path
from continuation_route import markdown,sanitize
from feature_draft_chain import encoded,head,load_context
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha
from validate_feature_specs import load_object,validate_feature
def ref(path:Path,root:Path,digest:str|None=None)->dict: return {"path":path.relative_to(root).as_posix(),"sha256":digest or sha(path)}
FIELDS=(("기능 이름",("feature","name")),("기능 목표",("feature","goal")),("사용자 가치",("feature","userValue")),("주요 사용자",("actors",)),("선행 조건",("scenario","preconditions")),("시작 조건",("scenario","trigger")),("정상 흐름",("scenario","mainFlow")),("대안 흐름",("scenario","alternateFlows")),("완료 상태",("scenario","postconditions")),("업무 규칙",("businessRules",)),("권한",("authorization",)),("데이터와 상태",("dataAndState",)),("실패 사례",("failureCases",)),("완료 조건",("acceptanceCriteria",)),("설계 필요성",("designRequirements",)),("의존 기능",("dependencies",)),("미결정 사항",("unknowns",)))
def at(value:dict,path:tuple[str,...]):
 for key in path: value=value[key]
 return value
def semantic_changes(old:dict,new:dict)->list[tuple[str,tuple[str,...],object,object]]: return [(label,path,at(old,path),at(new,path)) for label,path in FIELDS if at(old,path)!=at(new,path)]
def empty(value)->bool: return value=="UNKNOWN" or value==[] or value=={}
def concise(value)->str:
 text=json.dumps(value,ensure_ascii=False,separators=(", ",": ")) if not isinstance(value,str) else value
 return markdown(text if len(text)<=500 else text[:497]+"...")
def review(old:dict,new:dict,changes:list,source:dict)->str:
 lines=["# 기능 명세 답변 반영","",f"- 이번 답변 근거: {markdown(source['reference'])}","","## 이번 답변으로 바뀐 내용",""]
 for label,_,before,after in changes: lines.extend([f"### {label}","",f"- 이전: {concise(before)}",f"- 변경: {concise(after)}",""])
 open_unknowns=[item["question"] for item in new["unknowns"] if item["blocking"] and item["status"]!="RESOLVED"]
 design_open=[key for key,item in new["designRequirements"].items() if item["status"]=="UNKNOWN" or item["reason"]=="UNKNOWN" or item["source"]=="UNKNOWN"]
 question=(open_unknowns[:1] or ([f"{design_open[0]} 설계가 필요한가요?"] if design_open else [])); remaining=max(0,len(open_unknowns)+len(design_open)-len(question))
 lines.extend(["## 지금 결정할 한 가지","",*([f"- {markdown(item)}" for item in question] or ["- 없음"]),f"- 이후 남은 결정: {remaining}개","","## 다음 행동","","- 자연어로 답변","- 이전 답변 수정","- 추천 요청","- 나중에 결정","- 승인 준비 상태 확인","- 취소",""]); return "\n".join(lines)
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--intake",required=True,type=Path); p.add_argument("--current",required=True,type=Path); p.add_argument("--proposal",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--view",required=True,type=Path); a=p.parse_args(); written=[]
 try:
  root=a.target.resolve(strict=True); intake_path=a.intake.resolve(strict=True); current_path=a.current.resolve(strict=True); proposal_path=a.proposal.resolve(strict=True); output=a.output.resolve(strict=False); view=a.view.resolve(strict=False)
  if a.target.is_symlink() or output==view or any(root not in x.parents or x.is_symlink() for x in (intake_path,current_path,proposal_path,output,view)) or output.exists() or view.exists(): raise ValueError("draft update paths are unsafe, duplicated, or already exist")
  intake,receipt,_=load_context(root,intake_path); actual_head,previous_ref=head(root,receipt)
  if current_path!=actual_head: raise ValueError("current draft is stale; use the latest immutable draft")
  old=load_object(current_path); new=load_object(proposal_path); validate_feature(new,None)
  if new==old or new["feature"]["id"]!=receipt["featureId"] or new["feature"]["id"]!=old["feature"]["id"]: raise ValueError("proposal must change the same feature")
  if new["approval"]!={"status":new["approval"].get("status"),"approvedBy":None,"approvedAt":None,"approvedContentSha256":None} or new["approval"]["status"] not in {"DRAFT","REVIEW_REQUIRED"}: raise ValueError("draft proposal cannot approve itself")
  old_sources={item["id"]:item for item in old["sources"]}; new_sources={item["id"]:item for item in new["sources"]}
  if any(new_sources.get(key)!=value for key,value in old_sources.items()): raise ValueError("proposal cannot remove or rewrite existing sources")
  added=[item for key,item in new_sources.items() if key not in old_sources]
  if len(added)!=1: raise ValueError("proposal must add exactly one provenance source for the new answer")
  if sanitize(added[0]["reference"])!=added[0]["reference"]: raise ValueError("new answer provenance must be PII-minimized")
  old_unknowns={item["id"]:item for item in old["unknowns"]}; new_unknowns={item["id"]:item for item in new["unknowns"]}
  if not set(old_unknowns).issubset(new_unknowns): raise ValueError("proposal must preserve prior decision IDs")
  for key,value in old_unknowns.items():
   candidate=new_unknowns[key]
   if any(candidate[field]!=value[field] for field in ("id","question","impact","blocking")): raise ValueError("proposal cannot rewrite prior decision meaning")
  changes=semantic_changes(old,new)
  if not changes: raise ValueError("proposal has no semantic change")
  if any(not empty(before) and empty(after) for _,_,before,after in changes): raise ValueError("proposal cannot erase confirmed content; use an explicit removal workflow")
  output_bytes=encoded(new); view_bytes=review(old,new,changes,added[0]).encode(); next_ref=ref(output,root,hashlib.sha256(output_bytes).hexdigest()); view_ref=ref(view,root,hashlib.sha256(view_bytes).hexdigest()); change_evidence=[{"field":".".join(path),"sourceId":added[0]["id"],"beforeSha256":hashlib.sha256(json.dumps(before,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),"afterSha256":hashlib.sha256(json.dumps(after,ensure_ascii=False,sort_keys=True).encode()).hexdigest()} for _,path,before,after in changes]; edge={"featureDraftUpdateVersion":2,"previous":previous_ref,"next":next_ref,"view":view_ref,"intakeSha256":sha(intake_path),"changes":change_evidence,"state":"COMMITTED"}; edge_bytes=encoded(edge); prepared_bytes=encoded({**edge,"state":"PREPARED"}); edge_path=root/".starter-harness/feature-draft-updates"/f"{previous_ref['sha256']}.json"
  control=root/".starter-harness"; directory=edge_path.parent
  if control.is_symlink() or directory.is_symlink(): raise ValueError("draft update evidence directory is unsafe")
  directory.mkdir(parents=True,exist_ok=True); fd=os.open(edge_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,"wb") as stream: stream.write(prepared_bytes); stream.flush(); os.fsync(stream.fileno())
  written.append((edge_path,prepared_bytes)); output.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(output_bytes,output); written.append((output,output_bytes)); atomic_write_bytes(view_bytes,view); written.append((view,view_bytes)); atomic_write_bytes(edge_bytes,edge_path); written[0]=(edge_path,edge_bytes)
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,payload in reversed(written):
   try:
    if path.exists() and path.read_bytes()==payload: path.unlink()
   except OSError: pass
  print(f"FEATURE_DRAFT_UPDATE_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_DRAFT_UPDATE_VALID: yes"); print("OFFICIAL_CONTRACT_CHANGED: no"); return 0
if __name__=="__main__": sys.exit(main())
