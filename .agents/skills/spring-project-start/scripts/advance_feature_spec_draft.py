#!/usr/bin/env python3
"""Append one validated, immutable feature draft revision."""
from __future__ import annotations
import argparse,hashlib,json,os,sys
from pathlib import Path
from continuation_route import markdown
from feature_draft_chain import encoded,head,load_context
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha
from validate_feature_specs import load_object,validate_feature
def ref(path:Path,root:Path,digest:str|None=None)->dict: return {"path":path.relative_to(root).as_posix(),"sha256":digest or sha(path)}
def review(old:dict,new:dict)->str:
 changes=[]
 for label,path in (("사용자 가치",("feature","userValue")),("시작 조건",("scenario","trigger")),("주요 사용자",("actors",)),("정상 흐름",("scenario","mainFlow")),("완료 조건",("acceptanceCriteria",)),("설계 필요성",("designRequirements",))):
  before=old
  after=new
  for key in path: before=before[key]; after=after[key]
  if before!=after: changes.append(f"- {label}: 변경됨")
 open_unknowns=[item["question"] for item in new["unknowns"] if item["blocking"] and item["status"]!="RESOLVED"]
 return "\n".join(["# 기능 명세 답변 반영","","## 이번 답변으로 바뀐 내용","",*(changes or ["- 표시할 의미 변경 없음"]),"","## 지금 결정해야 할 내용","",*([f"- {markdown(item)}" for item in open_unknowns] or ["- 없음"]),"","## 다음 행동","","- 남은 질문에 자연어로 답변","- 이전 답변 수정","- 승인 준비 상태 확인","- 취소",""])
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
  if len(new_sources)<=len(old_sources): raise ValueError("proposal must add provenance for the new answer")
  old_unknowns={item["id"] for item in old["unknowns"]}
  if not old_unknowns.issubset({item["id"] for item in new["unknowns"]}): raise ValueError("proposal must preserve prior decision IDs")
  output_bytes=encoded(new); view_bytes=review(old,new).encode(); next_ref=ref(output,root,hashlib.sha256(output_bytes).hexdigest()); view_ref=ref(view,root,hashlib.sha256(view_bytes).hexdigest()); edge={"featureDraftUpdateVersion":1,"previous":previous_ref,"next":next_ref,"view":view_ref,"intakeSha256":sha(intake_path),"state":"COMMITTED"}; edge_bytes=encoded(edge); prepared_bytes=encoded({**edge,"state":"PREPARED"}); edge_path=root/".starter-harness/feature-draft-updates"/f"{previous_ref['sha256']}.json"
  control=root/".starter-harness"; directory=edge_path.parent
  if control.is_symlink() or directory.is_symlink(): raise ValueError("draft update evidence directory is unsafe")
  directory.mkdir(parents=True,exist_ok=True); fd=os.open(edge_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,"wb") as stream: stream.write(prepared_bytes); stream.flush(); os.fsync(stream.fileno())
  written.append((edge_path,prepared_bytes)); output.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(output_bytes,output); written.append((output,output_bytes)); atomic_write_bytes(view_bytes,view); written.append((view,view_bytes)); atomic_write_bytes(edge_bytes,edge_path); written[0]=(edge_path,edge_bytes)
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,payload in reversed(written):
   if path.exists() and path.read_bytes()==payload: path.unlink()
  print(f"FEATURE_DRAFT_UPDATE_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_DRAFT_UPDATE_VALID: yes"); print("OFFICIAL_CONTRACT_CHANGED: no"); return 0
if __name__=="__main__": sys.exit(main())
