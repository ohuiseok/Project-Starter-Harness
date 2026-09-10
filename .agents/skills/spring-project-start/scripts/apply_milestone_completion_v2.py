#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,json,sys
from pathlib import Path
from apply_approved_spring_code_v2 import atomic_file,durable_json,fsync_dir
from http_api_spring_mapping import reference
from milestone_completion_v2 import PROGRESS,VIEW,encoded,render,render_progress,validate_review
from spring_code_apply_v2 import MANAGED,apply_lock,sha
from validate_feature_specs import load_object
def validate_approval(root:Path,path:Path,review_path:Path)->dict:
 value=load_object(path);required={"milestoneCompletionApprovalV2Version","state","completionAttemptId","review","view","approvedBy","approvedAt","effects"}
 if not isinstance(value,dict) or set(value)!=required or value["milestoneCompletionApprovalV2Version"]!=1 or value["state"]!="APPROVED" or value["review"]!=reference(review_path,root):raise ValueError("exact completion approval is required")
 review=validate_review(load_object(review_path),review_path,root);view=root/value["view"]["path"]
 if value["completionAttemptId"]!=review["completionAttemptId"] or reference(view,root)!=value["view"] or view.read_text()!=render(review):raise ValueError("completion approval evidence changed")
 if not isinstance(value["approvedBy"],str) or not value["approvedBy"].strip() or dt.datetime.fromisoformat(value["approvedAt"].replace("Z","+00:00")).utcoffset() is None or value["approvedAt"]!=review["completion"]["document"]["completionApprovedAt"]:raise ValueError("completion approval identity or time is invalid")
 if value["effects"]!={"milestoneCompletion":True,"progressMutation":True,"sourceMutation":False,"testExecution":False,"gitCommitOrPush":"NOT_RUN"}:raise ValueError("completion approval effects are invalid")
 return value
def rollback(root:Path,record:dict,journal:Path)->dict:
 errors=[];record["state"]="ROLLING_BACK";durable_json(record,journal)
 for item in reversed(record["artifacts"]):
  path=root/item["path"]
  try:
   current=sha(path) if path.exists() and path.is_file() and not path.is_symlink() else None
   if current==item["beforeSha256"]:continue
   if current!=item["afterSha256"]:raise OSError("artifact drifted")
   if item["beforeSha256"] is None:path.unlink();fsync_dir(path.parent)
   else:atomic_file((root/record["backup"]/item["backupName"]).read_bytes(),0o644,path)
  except OSError as e:errors.append(f"{item['path']}: {e}")
 record["state"]="ROLLBACK_INCOMPLETE" if errors else "ROLLED_BACK";record["rollbackErrors"]=errors;durable_json(record,journal);return record
def apply(root:Path,review_path:Path,approval_path:Path)->dict:
 with apply_lock(root):
  validate_approval(root,approval_path,review_path);review=load_object(review_path);attempt=review["completionAttemptId"];base=root/MANAGED/"milestone-completion-v2"/attempt;journal=base/"transaction.json";consumed=base/"approval-consumed.json";backup=base/"before"
  if base.exists() or base.is_symlink() or any(path.exists() and path.is_symlink() for path in (root/MANAGED,root/MANAGED/"milestone-completion-v2")):raise ValueError("completion attempt already exists or managed path is unsafe")
  completion=root/review["completion"]["path"];progress=root/PROGRESS;view=root/VIEW
  if completion.exists() or completion.is_symlink():raise ValueError("completion output is occupied")
  before_progress=progress.read_bytes() if progress.exists() else None;before_view=view.read_bytes() if view.exists() else None;completion_data=encoded(review["completion"]["document"]);progress_data=encoded(review["progressAfter"]["document"]);view_data=render_progress(review["progressAfter"]["document"]).encode();base.mkdir(parents=True);backup.mkdir();artifacts=[]
  for index,(path,before,after) in enumerate(((completion,None,completion_data),(progress,before_progress,progress_data))):
   name=f"{index}.bak"
   if before is not None:atomic_file(before,0o644,backup/name)
   artifacts.append({"path":path.relative_to(root).as_posix(),"beforeSha256":__import__("hashlib").sha256(before).hexdigest() if before else None,"afterSha256":__import__("hashlib").sha256(after).hexdigest(),"backupName":name})
  if before_view is not None:atomic_file(before_view,0o644,backup/"view.bak")
  durable_json({"attemptId":attempt,"approval":reference(approval_path,root)},consumed);record={"milestoneCompletionTransactionV2Version":1,"attemptId":attempt,"state":"PREPARED","target":str(root),"review":reference(review_path,root),"approval":reference(approval_path,root),"backup":backup.relative_to(root).as_posix(),"artifacts":artifacts,"view":{"path":VIEW,"beforeSha256":__import__("hashlib").sha256(before_view).hexdigest() if before_view else None,"sha256":__import__("hashlib").sha256(view_data).hexdigest()},"rollbackErrors":[]};durable_json(record,journal)
  try:
   record["state"]="APPLYING";durable_json(record,journal)
   for path,before,after in ((completion,None,completion_data),(progress,before_progress,progress_data)):
    if (path.read_bytes() if path.exists() else None)!=before:raise ValueError("completion target changed before write")
    path.parent.mkdir(parents=True,exist_ok=True);atomic_file(after,0o644,path)
   record["state"]="COMMITTED_VIEW_PENDING";record["committedAt"]=dt.datetime.now(dt.timezone.utc).isoformat();durable_json(record,journal)
  except Exception as e:
   state=rollback(root,record,journal)
   if state["state"]=="ROLLBACK_INCOMPLETE":raise RuntimeError("completion rollback is incomplete")
   raise ValueError("completion failed and was rolled back: "+str(e))
  try:
   if view.is_symlink() or (view.read_bytes() if view.exists() else None)!=before_view:raise ValueError("progress view changed before derived write")
   atomic_file(view_data,0o644,view);record["state"]="COMMITTED";durable_json(record,journal)
  except Exception:return record
  return record
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--review",required=True,type=Path);p.add_argument("--approval",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:record=apply(a.target.resolve(strict=True),a.review.resolve(strict=True),a.approval.resolve(strict=True))
 except (OSError,ValueError,RuntimeError,KeyError,TypeError) as e:print(f"MILESTONE_COMPLETION_V2_VALID: no\nERROR: {e}");return 1
 print(f"MILESTONE_COMPLETION_V2_VALID: yes\nTRANSACTION_STATE: {record['state']}\nMILESTONE_STATE: COMPLETED\nGIT_COMMIT_OR_PUSH: NOT_RUN");return 0
if __name__=="__main__":sys.exit(main())
