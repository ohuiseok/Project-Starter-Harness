#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,json,sys
from pathlib import Path
from continuation_consumption_migration import build,render
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object
def argument_path(root:Path,value:Path,label:str)->Path:
 try: relative=value.absolute().relative_to(root).as_posix()
 except ValueError as error: raise ValueError(f"{label} must be inside the target") from error
 return target_path(root,relative,label)
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--input",required=True,type=Path); p.add_argument("--proposal",required=True,type=Path); p.add_argument("--view",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--expected-proposal-hash",required=True); p.add_argument("--approved-by",required=True); p.add_argument("--approved-at",required=True); p.add_argument("--base-feature",type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); source=argument_path(root,a.input,"v1 consumption"); proposal=argument_path(root,a.proposal,"migration proposal"); view=argument_path(root,a.view,"migration view")
  if a.target.is_symlink() or any(not path.is_file() for path in (source,proposal,view)) or sha(proposal)!=a.expected_proposal_hash or not a.approved_by.strip(): raise ValueError("migration approval inputs are unsafe or stale")
  timestamp=dt.datetime.fromisoformat(a.approved_at.replace("Z","+00:00"))
  if timestamp.utcoffset() is None: raise ValueError("migration approval time must include a timezone")
  old=load_object(source); expected=build(root,source,a.base_feature); migrated=load_object(proposal)
  if migrated!=expected or view.read_text()!=render(old,migrated): raise ValueError("migration proposal or view is stale")
  backup=target_path(root,f".starter-harness/continuation-consumption-migrations/{sha(source)}.v1.json","migration backup")
  backup.parent.mkdir(parents=True,exist_ok=True); original=source.read_bytes()
  if backup.exists() and backup.read_bytes()!=original: raise ValueError("migration backup conflicts with current v1 consumption")
  if not backup.exists(): atomic_write_bytes(original,backup)
  if source.read_bytes()!=original: raise ValueError("v1 consumption changed before migration apply")
  atomic_write_bytes((json.dumps(migrated,ensure_ascii=False,indent=2)+"\n").encode(),source)
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"CONTINUATION_CONSUMPTION_MIGRATION_APPLIED: no\nERROR: {e}",file=sys.stderr); return 1
 print("CONTINUATION_CONSUMPTION_MIGRATION_APPLIED: yes"); print("BACKUP_RECORDED: yes"); return 0
if __name__=="__main__": sys.exit(main())
