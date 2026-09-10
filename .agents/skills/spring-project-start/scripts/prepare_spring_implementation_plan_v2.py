#!/usr/bin/env python3
"""Create source-free implementation plan v2 from an approved Spring mapping."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from http_api_spring_mapping import reference
from render_spring_implementation_plan_v2 import render
from spring_implementation_plan_v2 import build,encoded,plans_for_mapping,validate
from validate_feature_specs import load_object
from validate_http_api_spring_mapping_approval import validate_approval
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--mapping-approval",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--view",required=True,type=Path);a=p.parse_args();written=[]
 try:
  root=a.target.resolve(strict=True);approval=a.mapping_approval.resolve(strict=True);out=a.output.resolve();view=a.view.resolve()
  if out.exists() or view.exists() or view!=out.with_suffix(".md") or root not in out.parents or out.relative_to(root).parts[0]!="docs":raise ValueError("implementation plan v2 outputs are unsafe or occupied")
  receipt=validate_approval(root,approval);mapping_path=root/receipt["mapping"]["path"];mapping_ref=reference(mapping_path,root)
  if plans_for_mapping(root,mapping_ref):raise ValueError("this approved mapping already has an implementation plan v2")
  mapping=load_object(mapping_path);plan=build(mapping,mapping_ref,reference(approval,root),root);blockers=validate(plan,root);payload=encoded(plan);markdown=render(plan,blockers).encode();out.parent.mkdir(parents=True,exist_ok=True)
  for path,content in ((out,payload),(view,markdown)):atomic_create(content,path);written.append((path,content))
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,content in reversed(written):
   if path.exists() and path.read_bytes()==content:path.unlink()
  print(f"SPRING_IMPLEMENTATION_PLAN_V2_CREATED: no\nERROR: {e}");return 1
 print(f"SPRING_IMPLEMENTATION_PLAN_V2_CREATED: yes\nPLAN_STATUS: {plan['status']}\nCODE_DRY_RUN_PREPARATION_AVAILABLE: {'yes' if plan['advancement']['codeDryRun'] else 'no'}\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
