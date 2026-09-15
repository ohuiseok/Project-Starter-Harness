#!/usr/bin/env python3
"""Recover an interrupted one-time continuation handoff consumption."""
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
from continuation_route import validate_handoff
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object

def encoded(value:dict)->bytes:return (json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode()
def fsync_dir(path:Path)->None:
 fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def recover(root:Path,handoff:Path)->str:
 validate_handoff(load_object(handoff),handoff,root);handoff_ref={"path":handoff.relative_to(root).as_posix(),"sha256":sha(handoff)}
 directory=root/".starter-harness/continuation-handoff-consumptions";claim_path=directory/f"{handoff_ref['sha256']}.json"
 if directory.is_symlink() or claim_path.is_symlink() or not claim_path.is_file():raise ValueError("continuation handoff consumption claim is missing or unsafe")
 claim=load_object(claim_path);required={"continuationHandoffConsumptionVersion","handoff","intake","state"}
 if set(claim)!=required or claim["continuationHandoffConsumptionVersion"]!=1 or claim["handoff"]!=handoff_ref or claim["state"] not in {"PREPARED","COMMITTED"}:raise ValueError("continuation handoff consumption claim is invalid")
 intake=target_path(root,claim["intake"]["path"],"continuation intake")
 if claim["state"]=="COMMITTED":
  if not intake.is_file() or sha(intake)!=claim["intake"]["sha256"]:raise ValueError("committed continuation intake changed")
  return "COMMITTED"
 if not intake.exists():claim_path.unlink();fsync_dir(directory);return "RELEASED"
 if not intake.is_file() or sha(intake)!=claim["intake"]["sha256"]:raise ValueError("prepared continuation intake drifted; refusing recovery")
 fsync_dir(intake.parent);claim["state"]="COMMITTED";atomic_write_bytes(encoded(claim),claim_path);fsync_dir(directory);return "COMMITTED"
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--handoff",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);handoff=a.handoff.resolve(strict=True)
  if a.target.is_symlink() or handoff.is_symlink() or root not in handoff.parents:raise ValueError("continuation recovery paths are unsafe")
  state=recover(root,handoff)
 except (OSError,ValueError,KeyError,TypeError) as error:print(f"CONTINUATION_HANDOFF_RECOVERY_VALID: no\nERROR: {error}",file=sys.stderr);return 1
 print(f"CONTINUATION_HANDOFF_RECOVERY_VALID: yes\nCONSUMPTION_STATE: {state}");return 0
if __name__=="__main__":sys.exit(main())
