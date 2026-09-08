#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from feature_draft_chain import encoded
from feature_spec_promotion import build,render
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import target_path
def argument_path(root:Path,value:Path,label:str)->Path:
 try: relative=value.absolute().relative_to(root).as_posix()
 except ValueError as error: raise ValueError(f"{label} must be inside the target") from error
 return target_path(root,relative,label)
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--intake",required=True,type=Path); p.add_argument("--readiness",required=True,type=Path); p.add_argument("--readiness-view",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--view",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); paths=[argument_path(root,value,label) for value,label in ((a.intake,"intake"),(a.readiness,"readiness"),(a.readiness_view,"readiness view"),(a.output,"promotion output"),(a.view,"promotion view"))]
  if a.target.is_symlink() or len(set(paths))!=len(paths) or any(not path.is_file() for path in paths[:3]) or paths[3].exists() or paths[4].exists(): raise ValueError("promotion paths are unsafe, duplicated, missing, or already exist")
  plan=build(root,*paths[:3]); plan_bytes=encoded(plan); view_bytes=render(plan).encode(); paths[3].parent.mkdir(parents=True,exist_ok=True); paths[4].parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(plan_bytes,paths[3])
  try: atomic_write_bytes(view_bytes,paths[4])
  except BaseException:
   if paths[3].exists() and paths[3].read_bytes()==plan_bytes: paths[3].unlink()
   raise
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"FEATURE_SPEC_PROMOTION_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_SPEC_PROMOTION_VALID: yes"); print("STATE: READY_FOR_APPROVAL"); print("OFFICIAL_CONTRACT_CHANGED: no"); return 0
if __name__=="__main__": sys.exit(main())
