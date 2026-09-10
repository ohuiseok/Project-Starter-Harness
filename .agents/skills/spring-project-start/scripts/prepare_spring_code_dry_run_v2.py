#!/usr/bin/env python3
"""Atomically prepare an exact Java MVC API-only code dry-run v2."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from render_spring_code_dry_run_v2_markdown import render
from spring_code_dry_run_v2 import build_report,current_context
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan-approval",required=True,type=Path);p.add_argument("--renderability",required=True,type=Path);p.add_argument("--rendered-source",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--view",required=True,type=Path);a=p.parse_args();written=[]
 try:
  root=a.target.resolve(strict=True);approval=a.plan_approval.resolve(strict=True);gate=a.renderability.resolve(strict=True);output=a.output.resolve();view=a.view.resolve();candidate=a.rendered_source.resolve(strict=True)
  if root in candidate.parents:raise ValueError("rendered source must be temporary storage outside the target")
  if output.exists() or view.exists() or view!=output.with_suffix(".md") or root not in output.parents or output.relative_to(root).parts[0]!="docs":raise ValueError("dry-run outputs are unsafe or occupied")
  plan,approval_ref,renderability,gate_ref=current_context(root,approval,gate);report=build_report(plan,approval_ref,gate_ref,renderability,candidate,root);payload=(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode();markdown=render(report).encode();output.parent.mkdir(parents=True,exist_ok=True)
  for path,content in ((output,payload),(view,markdown)):atomic_create(content,path);written.append((path,content))
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,content in reversed(written):
   if path.exists() and path.read_bytes()==content:path.unlink()
  print(f"SPRING_CODE_DRY_RUN_V2_CREATED: no\nERROR: {e}");return 1
 print(f"SPRING_CODE_DRY_RUN_V2_CREATED: yes\nBLOCKERS: {len(report['blockers'])}\nREADY_FOR_VERIFICATION_APPROVAL: {'yes' if report['readyForVerificationApproval'] else 'no'}\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
