#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from apply_approved_spring_code_v2 import atomic_file,durable_json
from apply_milestone_completion_v2 import rollback
from milestone_completion_v2 import render_progress
from http_api_spring_mapping import reference
from spring_code_apply_v2 import MANAGED,apply_lock,sha
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--target",required=True,type=Path);p.add_argument("--attempt-id",required=True);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True)
  if not a.attempt_id.startswith("completion-v2-") or "/" in a.attempt_id or ".." in a.attempt_id:raise ValueError("completion attempt ID is invalid")
  journal=root/MANAGED/"milestone-completion-v2"/a.attempt_id/"transaction.json"
  with apply_lock(root):
   record=load_object(journal)
   if record.get("milestoneCompletionTransactionV2Version")!=1 or record.get("attemptId")!=a.attempt_id or Path(record.get("target","")).resolve()!=root:raise ValueError("completion transaction identity is invalid")
   if record["state"] in {"PREPARED","APPLYING","ROLLING_BACK"}:
    record=rollback(root,record,journal)
    if record["state"]=="ROLLBACK_INCOMPLETE":raise ValueError("completion rollback is incomplete: "+"; ".join(record["rollbackErrors"]))
    print("MILESTONE_COMPLETION_V2_RECOVERED: yes\nTRANSACTION_STATE: ROLLED_BACK");return 0
   if record["state"]=="COMMITTED":print("MILESTONE_COMPLETION_V2_RECOVERED: yes\nTRANSACTION_STATE: COMMITTED");return 0
   if record["state"]!="COMMITTED_VIEW_PENDING":raise ValueError("completion transaction is not recoverable")
   for item in record["artifacts"]:
    if sha(root/item["path"])!=item["afterSha256"]:raise ValueError("committed completion artifact changed")
   review_path=root/record["review"]["path"]
   if reference(review_path,root)!=record["review"]:raise ValueError("completion review evidence changed")
   review=load_object(review_path);view=root/record["view"]["path"];current=sha(view) if view.exists() and view.is_file() and not view.is_symlink() else None
   if current not in {record["view"]["beforeSha256"],record["view"]["sha256"]}:raise ValueError("progress view drifted")
   data=render_progress(review["progressAfter"]["document"]).encode()
   if __import__("hashlib").sha256(data).hexdigest()!=record["view"]["sha256"]:raise ValueError("derived progress view contract changed")
   if current!=record["view"]["sha256"]:atomic_file(data,0o644,view)
   record["state"]="COMMITTED";durable_json(record,journal)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"MILESTONE_COMPLETION_V2_RECOVERED: no\nERROR: {e}");return 1
 print("MILESTONE_COMPLETION_V2_RECOVERED: yes\nTRANSACTION_STATE: COMMITTED");return 0
if __name__=="__main__":sys.exit(main())
