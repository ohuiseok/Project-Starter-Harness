#!/usr/bin/env python3
"""Roll back one interrupted PREPARED feature-draft update."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from feature_draft_chain import load_context
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--intake",required=True,type=Path); p.add_argument("--current",required=True,type=Path); p.add_argument("--target",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); intake=a.intake.resolve(strict=True); current=a.current.resolve(strict=True)
  if any(root not in path.parents or path.is_symlink() for path in (intake,current)): raise ValueError("recovery paths are unsafe")
  load_context(root,intake); digest=sha(current); edge=root/".starter-harness/feature-draft-updates"/f"{digest}.json"; value=load_object(edge)
  if value.get("featureDraftUpdateVersion")!=2 or value.get("state")!="PREPARED" or value.get("previous")!={"path":current.relative_to(root).as_posix(),"sha256":digest} or value.get("intakeSha256")!=sha(intake): raise ValueError("no matching PREPARED update exists")
  artifacts=[]
  for key in ("next","view"):
   item=value[key]
   if not isinstance(item,dict) or set(item)!={"path","sha256"}: raise ValueError("prepared update reference is invalid")
   path=target_path(root,item["path"],key)
   if path.exists() and (not path.is_file() or sha(path)!=item["sha256"]): raise ValueError(f"{path}: drifted artifact; refusing recovery")
   artifacts.append(path)
  for path in artifacts:
   if path.exists(): path.unlink()
  edge.unlink()
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"FEATURE_DRAFT_UPDATE_RECOVERY_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_DRAFT_UPDATE_RECOVERY_VALID: yes"); print("RECOVERY_STATE: ROLLED_BACK"); return 0
if __name__=="__main__": sys.exit(main())
