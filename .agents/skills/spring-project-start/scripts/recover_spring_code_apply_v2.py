#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from apply_approved_spring_code_v2 import durable_json,managed_paths,rollback,validate_final,verify_backup,write_result
from spring_code_apply_v2 import MANAGED,apply_lock
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--target",required=True,type=Path);p.add_argument("--transaction-id",required=True);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True)
  if not a.transaction_id.startswith("spring-code-v2-") or "/" in a.transaction_id or ".." in a.transaction_id:raise ValueError("transaction ID is invalid")
  backup,path=managed_paths(root,a.transaction_id)
  with apply_lock(root):
   record=load_object(path)
   if record.get("springCodeTransactionV2Version")!=1 or record.get("transactionId")!=a.transaction_id or Path(record.get("target","")).resolve()!=root:raise ValueError("transaction journal identity is invalid")
   if record.get("backup")!=backup.relative_to(root).as_posix():raise ValueError("transaction backup path is invalid")
   manifest=backup/"backup-manifest.json"
   if __import__("spring_code_apply_v2").sha(manifest)!=record["backupManifestSha256"]:raise ValueError("backup manifest reference changed")
   verify_backup(backup)
   if record["state"]=="COMMITTED_REPORT_PENDING":
    validate_final(root,record);write_result(root,record);record["state"]="COMMITTED";durable_json(record,path)
   elif record["state"] in {"PREPARED","APPLYING","BASELINE_WRITTEN","ROLLING_BACK"}:
    record=rollback(root,record,path)
    if record["state"]=="ROLLBACK_INCOMPLETE":raise ValueError("rollback is incomplete: "+"; ".join(record["rollbackErrors"]))
   elif record["state"] in {"COMMITTED","ROLLED_BACK"}:pass
   else:raise ValueError("transaction state needs manual review: "+str(record["state"]))
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_APPLY_V2_RECOVERED: no\nERROR: {e}");return 1
 print(f"SPRING_CODE_APPLY_V2_RECOVERED: yes\nTRANSACTION_STATE: {record['state']}");return 0
if __name__=="__main__":sys.exit(main())
