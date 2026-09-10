#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from spring_code_verification_v2 import JOURNAL,build_plan,render_plan
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--dry-run-approval",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--timeout-seconds",type=int,default=600);a=p.parse_args();written=[]
 try:
  root=a.target.resolve(strict=True);approval=a.dry_run_approval.resolve(strict=True);output=a.output.resolve();view=a.view.resolve()
  if not 30<=a.timeout_seconds<=1800 or output.exists() or view.exists() or view!=output.with_suffix(".md") or root not in output.parents or output.relative_to(root).parts[0]!="docs" or (root/JOURNAL).exists():raise ValueError("verification plan paths, limits, or journal are unsafe")
  plan=build_plan(root,approval,a.timeout_seconds);payload=(json.dumps(plan,ensure_ascii=False,indent=2)+"\n").encode();markdown=render_plan(plan).encode();output.parent.mkdir(parents=True,exist_ok=True)
  for path,data in ((output,payload),(view,markdown)):atomic_create(data,path);written.append((path,data))
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,data in reversed(written):
   if path.exists() and path.read_bytes()==data:path.unlink()
  print(f"SPRING_CODE_VERIFICATION_PLAN_V2_CREATED: no\nERROR: {e}");return 1
 print(f"SPRING_CODE_VERIFICATION_PLAN_V2_CREATED: yes\nBLOCKERS: {len(plan['blockers'])}\nREADY_FOR_APPROVAL: {'yes' if plan['readyForApproval'] else 'no'}\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
