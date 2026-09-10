#!/usr/bin/env python3
"""Atomically create a source-free code renderability report and view."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from http_api_spring_mapping import reference
from render_spring_code_renderability_v2 import render
from spring_code_renderability_v2 import assess
from validate_feature_specs import load_object
from validate_spring_implementation_plan_v2_approval import validate_approval
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan-approval",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--view",required=True,type=Path);a=p.parse_args();written=[]
 try:
  root=a.target.resolve(strict=True);approval=a.plan_approval.resolve(strict=True);out=a.output.resolve();view=a.view.resolve()
  if out.exists() or view.exists() or view!=out.with_suffix(".md") or root not in out.parents or out.relative_to(root).parts[0]!="docs":raise ValueError("renderability outputs are unsafe or occupied")
  receipt=validate_approval(root,approval);plan=load_object(root/receipt["implementationPlan"]["path"]);report=assess(plan,root,reference(approval,root));payload=(__import__("json").dumps(report,ensure_ascii=False,indent=2)+"\n").encode();markdown=render(report).encode();out.parent.mkdir(parents=True,exist_ok=True)
  for path,content in ((out,payload),(view,markdown)):atomic_create(content,path);written.append((path,content))
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,content in reversed(written):
   if path.exists() and path.read_bytes()==content:path.unlink()
  print(f"SPRING_CODE_RENDERABILITY_V2_CREATED: no\nERROR: {e}");return 1
 print(f"SPRING_CODE_RENDERABILITY_V2_CREATED: yes\nBLOCKERS: {len(report['blockers'])}\nCODE_DRY_RUN_READY: no\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
