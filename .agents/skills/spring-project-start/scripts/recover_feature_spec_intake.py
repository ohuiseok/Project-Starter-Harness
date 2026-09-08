#!/usr/bin/env python3
"""Recover only an incomplete, exact continuation consumption."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--intake",required=True,type=Path); p.add_argument("--target",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); intake=a.intake.resolve(strict=True)
  if root not in intake.parents or intake.is_symlink(): raise ValueError("intake path is unsafe")
  control=root/".starter-harness"; consumption=control/"continuation-consumptions"; receipt=consumption/f"{sha(intake)}.json"
  if control.is_symlink() or consumption.is_symlink() or not receipt.is_file() or receipt.is_symlink(): raise ValueError("consumption receipt not found or unsafe")
  value=load_object(receipt); required={"continuationConsumptionVersion","intake","draft","view","featureId","state"}
  if set(value)!=required or value["continuationConsumptionVersion"]!=1 or value["state"]!="AWAITING_USER_DECISIONS" or value["intake"]!={"path":intake.relative_to(root).as_posix(),"sha256":sha(intake)}: raise ValueError("consumption receipt is invalid")
  paths=[]; missing=[]
  for key in ("draft","view"):
   path=target_path(root,value[key]["path"],key); paths.append((path,value[key]["sha256"])); missing.append(not path.exists())
  if not any(missing): raise ValueError("consumption is complete; recovery is not allowed")
  for path,expected in paths:
   if path.exists() and (not path.is_file() or sha(path)!=expected): raise ValueError(f"{path}: drifted partial artifact; refusing recovery")
  for path,_ in paths:
   if path.exists(): path.unlink()
  receipt.unlink()
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"FEATURE_INTAKE_RECOVERY_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_INTAKE_RECOVERY_VALID: yes"); print("RECOVERY_STATE: ROLLED_BACK"); return 0
if __name__=="__main__": sys.exit(main())
