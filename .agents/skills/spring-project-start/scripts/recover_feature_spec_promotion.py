#!/usr/bin/env python3
"""Recover an interrupted feature-spec promotion without overwriting drift."""
from __future__ import annotations
import argparse,re,sys
from pathlib import Path
from feature_draft_chain import encoded
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--transaction",required=True); p.add_argument("--target",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True)
  if not re.fullmatch(r"[a-f0-9]{64}",a.transaction): raise ValueError("transaction ID must be a SHA-256 value")
  txdir=root/".starter-harness/feature-spec-promotion-transactions"/a.transaction; journal=txdir/"transaction.json"
  if (root/".starter-harness").is_symlink() or txdir.parent.is_symlink() or txdir.is_symlink(): raise ValueError("promotion recovery path is unsafe")
  value=load_object(journal)
  if value.get("featureSpecPromotionTransactionVersion")!=1 or value.get("state") not in {"PREPARED","APPLYING"}: raise ValueError("transaction is not recoverable")
  targets=[]
  for record in value["targets"]:
   path=target_path(root,record["path"],"promotion target")
   if path.exists() and not path.is_file(): raise ValueError(f"{path}: target is not a regular file")
   current=sha(path) if path.exists() else None
   if current not in {record["beforeSha256"],record["afterSha256"]}: raise ValueError(f"{path}: target drifted; refusing recovery")
   if record["beforeSha256"] is not None:
    backup=txdir/record["backup"]
    if not backup.is_file() or sha(backup)!=record["beforeSha256"]: raise ValueError("promotion backup changed")
   targets.append((path,record))
  for path,record in reversed(targets):
   if record["beforeSha256"] is None:
    if path.exists(): path.unlink()
   else: atomic_write_bytes((txdir/record["backup"]).read_bytes(),path)
  value["state"]="ROLLED_BACK"; atomic_write_bytes(encoded(value),journal)
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"FEATURE_SPEC_PROMOTION_RECOVERY_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_SPEC_PROMOTION_RECOVERY_VALID: yes"); print("TRANSACTION_STATE: ROLLED_BACK"); return 0
if __name__=="__main__": sys.exit(main())
