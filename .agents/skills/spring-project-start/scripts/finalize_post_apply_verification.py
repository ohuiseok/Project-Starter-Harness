#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,json,secrets,sys
from pathlib import Path
from complete_spring_milestone import ACTIVE,MANAGED,digest_bytes,encoded,journal_path,pending_transactions,recover
from post_apply_verification import context_sha,validate_report
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import render_progress,sha,target_path,validate_progress
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--completion",required=True,type=Path); p.add_argument("--verification-report",required=True,type=Path); p.add_argument("--target",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); completion_path=a.completion.resolve(strict=True); report_path=a.verification_report.resolve(strict=True); progress_path=target_path(root,"docs/progress.json","progress ledger"); view_path=target_path(root,"docs/progress.md","progress view")
  if a.target.is_symlink() or any(root not in p.parents for p in (completion_path,report_path)) or pending_transactions(root): raise ValueError("finalization paths are unsafe or a completion transaction is pending")
  completion=load_object(completion_path); report=load_object(report_path); progress=load_object(progress_path); validate_progress(progress,root)
  validate_report(report,report_path,root)
  if report["result"]["state"]!="PASSED" or report["readyForFinalization"] is not True or report["targetContextSha256"]!=context_sha(root): raise ValueError("passing current post-apply verification is required")
  match=[item for item in progress["completedMilestones"] if item["featureId"]==completion["featureId"]]
  if len(match)!=1 or match[0]["completionReport"]!={"path":completion_path.relative_to(root).as_posix(),"sha256":sha(completion_path)} or completion.get("state")!="APPLIED_PREVERIFIED": raise ValueError("progress and preverified completion do not match")
  updated=dict(completion); updated["state"]="APPLIED_AND_VERIFIED"; updated["postApplyRuntimeVerification"]={"path":report_path.relative_to(root).as_posix(),"sha256":sha(report_path),"verificationLevel":report["verificationLevel"]}
  completion_bytes=encoded(updated); updated_progress=json.loads(json.dumps(progress)); item=next(item for item in updated_progress["completedMilestones"] if item["featureId"]==completion["featureId"]); item["state"]="APPLIED_AND_VERIFIED"; item["completionReport"]["sha256"]=digest_bytes(completion_bytes); updated_progress["updatedAt"]=report["verifiedAt"]
  before=[completion_path.read_bytes(),progress_path.read_bytes(),view_path.read_bytes()]; after=[completion_bytes,encoded(updated_progress),render_progress(updated_progress).encode()]; paths=[completion_path,progress_path,view_path]
  transaction_id=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-")+secrets.token_hex(4); record_path=journal_path(root,transaction_id); backup=record_path.parent/"before"; artifacts=[]
  for path,old,new in zip(paths,before,after):
   relative=path.relative_to(root).as_posix(); artifacts.append({"path":relative,"beforeSha256":digest_bytes(old),"afterSha256":digest_bytes(new)}); destination=backup/relative; destination.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(old,destination)
  record={"version":1,"transactionId":transaction_id,"state":"PREPARED","target":str(root),"artifacts":artifacts}; record_path.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(encoded(record),record_path); record["state"]="APPLYING"; atomic_write_bytes(encoded(record),record_path)
  try:
   for path,old,new in zip(paths,before,after):
    if path.read_bytes()!=old: raise ValueError("finalization artifact changed before write")
    atomic_write_bytes(new,path)
   record["state"]="COMMITTED"; atomic_write_bytes(encoded(record),record_path)
  except Exception as error:
   recover(root,transaction_id); raise ValueError(f"finalization rolled back: {error}") from error
 except (OSError,ValueError,RuntimeError,KeyError,TypeError) as e: print(f"POST_APPLY_FINALIZATION_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("POST_APPLY_FINALIZATION_VALID: yes"); print("MILESTONE_STATE: APPLIED_AND_VERIFIED"); return 0
if __name__=="__main__": sys.exit(main())
