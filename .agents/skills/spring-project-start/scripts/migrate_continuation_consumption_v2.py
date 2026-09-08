#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from continuation_consumption_migration import build,render
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import target_path
from validate_feature_specs import load_object
def argument_path(root:Path,value:Path,label:str)->Path:
 try: relative=value.absolute().relative_to(root).as_posix()
 except ValueError as error: raise ValueError(f"{label} must be inside the target") from error
 return target_path(root,relative,label)
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--input",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--view",required=True,type=Path); p.add_argument("--base-feature",type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); source=argument_path(root,a.input,"v1 consumption"); output=argument_path(root,a.output,"migration proposal"); view=argument_path(root,a.view,"migration view")
  if a.target.is_symlink() or len({source,output,view})!=3 or not source.is_file() or output.exists() or view.exists(): raise ValueError("migration paths are unsafe, duplicated, missing, or already exist")
  old=load_object(source); value=build(root,source,a.base_feature); payload=(json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode(); view_payload=render(old,value).encode(); output.parent.mkdir(parents=True,exist_ok=True); view.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(payload,output)
  try: atomic_write_bytes(view_payload,view)
  except BaseException:
   if output.exists() and output.read_bytes()==payload: output.unlink()
   raise
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"CONTINUATION_CONSUMPTION_MIGRATION_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("CONTINUATION_CONSUMPTION_MIGRATION_VALID: yes"); print("SOURCE_CHANGED: no"); return 0
if __name__=="__main__": sys.exit(main())
