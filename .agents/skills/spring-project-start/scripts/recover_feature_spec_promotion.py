#!/usr/bin/env python3
"""Recover an interrupted feature-spec promotion without overwriting drift."""
from __future__ import annotations
import argparse,re,sys
from pathlib import Path
from apply_feature_spec_promotion import transaction_id
from feature_draft_chain import encoded
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--transaction",required=True); p.add_argument("--target",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True)
  if a.target.is_symlink() or not re.fullmatch(r"[a-f0-9]{64}",a.transaction): raise ValueError("transaction target or ID is unsafe")
  txdir=target_path(root,f".starter-harness/feature-spec-promotion-transactions/{a.transaction}","promotion transaction"); journal=txdir/"transaction.json"; value=load_object(journal); required={"featureSpecPromotionTransactionVersion","transactionId","target","plan","approval","targets","state","rollbackErrors"}
  if set(value)!=required or value["featureSpecPromotionTransactionVersion"]!=2 or value["transactionId"]!=a.transaction or Path(str(value["target"])).resolve()!=root or value["state"] not in {"PREPARED","APPLYING","ROLLBACK_INCOMPLETE"} or not isinstance(value["rollbackErrors"],list): raise ValueError("transaction is not recoverable or malformed")
  plan=value["plan"]; approval=value["approval"]
  if not isinstance(plan,dict) or set(plan)!={"path","sha256"} or not isinstance(approval,dict) or set(approval)!={"approvedBy","approvedAt"} or transaction_id(plan["sha256"],approval["approvedBy"],approval["approvedAt"])!=a.transaction: raise ValueError("transaction identity does not match plan and approval")
  plan_path=target_path(root,plan["path"],"promotion plan")
  if not plan_path.is_file() or sha(plan_path)!=plan["sha256"]: raise ValueError("promotion plan changed")
  saved=load_object(plan_path); intake_hash=saved["intake"]["sha256"]; expected_paths=[saved["projectBrief"]["path"],saved["projectBriefView"]["path"],saved["officialFeaturePath"],str(Path(saved["officialFeaturePath"]).with_suffix(".md")),f".starter-harness/continuation-completions/{intake_hash}.json"]
  if not isinstance(value["targets"],list) or len(value["targets"])!=len(expected_paths): raise ValueError("promotion target manifest is invalid")
  targets=[]; seen=set()
  for index,(record,expected_path) in enumerate(zip(value["targets"],expected_paths)):
   if not isinstance(record,dict) or set(record)!={"path","beforeSha256","backup","afterSha256"} or record["path"]!=expected_path or record["path"] in seen or not re.fullmatch(r"[a-f0-9]{64}",record["afterSha256"]): raise ValueError("promotion target record is invalid")
   seen.add(record["path"]); path=target_path(root,record["path"],"promotion target")
   if path.exists() and not path.is_file(): raise ValueError(f"{path}: target is not a regular file")
   current=sha(path) if path.exists() else None
   if current not in {record["beforeSha256"],record["afterSha256"]}: raise ValueError(f"{path}: target drifted; refusing recovery")
   if record["beforeSha256"] is None:
    if record["backup"] is not None: raise ValueError("CREATE target cannot have a backup")
   else:
    if not re.fullmatch(rf"backup-{index}",str(record["backup"])): raise ValueError("promotion backup name is invalid")
    backup=txdir/record["backup"]
    if backup.is_symlink() or not backup.is_file() or sha(backup)!=record["beforeSha256"]: raise ValueError("promotion backup changed")
   targets.append((path,record))
  for path,record in reversed(targets):
   current=sha(path) if path.exists() else None
   if current==record["afterSha256"]:
    if record["beforeSha256"] is None: path.unlink()
    else: atomic_write_bytes((txdir/record["backup"]).read_bytes(),path)
  value["state"]="ROLLED_BACK"; value["rollbackErrors"]=[]; atomic_write_bytes(encoded(value),journal)
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"FEATURE_SPEC_PROMOTION_RECOVERY_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_SPEC_PROMOTION_RECOVERY_VALID: yes"); print("TRANSACTION_STATE: ROLLED_BACK"); return 0
if __name__=="__main__": sys.exit(main())
