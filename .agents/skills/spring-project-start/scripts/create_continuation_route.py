#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from continuation_route import build_route,render
from record_spec_approval import atomic_write_bytes
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--request",required=True); p.add_argument("--project-brief",required=True,type=Path); p.add_argument("--progress",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--view",required=True,type=Path); p.add_argument("--feature-id"); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); project=a.project_brief.resolve(strict=True); progress=a.progress.resolve(strict=True); output=a.output.resolve(strict=False); view=a.view.resolve(strict=False)
  if a.target.is_symlink() or any(root not in path.parents for path in (project,progress,output,view)) or any(path.is_symlink() for path in (project,progress,output,view)) or output.exists() or view.exists(): raise ValueError("continuation paths are unsafe or already exist")
  route=build_route(root,a.request,project,progress,a.feature_id); route_bytes=(json.dumps(route,ensure_ascii=False,indent=2)+"\n").encode(); view_bytes=render(route).encode(); output.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(route_bytes,output)
  try: atomic_write_bytes(view_bytes,view)
  except BaseException:
   if output.read_bytes()==route_bytes: output.unlink()
   raise
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"CONTINUATION_ROUTE_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("CONTINUATION_ROUTE_VALID: yes"); print(f"ROUTE_TYPE: {route['route']['type']}"); print(f"NEXT_WORKFLOW: {route['route']['nextWorkflow']}"); print(f"CONFIRMATION_REQUIRED: {'yes' if route['route']['requiresConfirmation'] else 'no'}"); return 0
if __name__=="__main__": sys.exit(main())
