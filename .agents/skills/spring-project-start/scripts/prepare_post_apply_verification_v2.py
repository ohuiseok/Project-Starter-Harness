#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from post_apply_verification_v2 import build_plan,render_plan
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--apply-result",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--timeout-seconds",type=int,default=600);a=p.parse_args();written=[]
 try:
  root=a.target.resolve(strict=True);result=a.apply_result.resolve(strict=True);output=a.output.resolve();view=a.view.resolve()
  if output.exists() or view.exists() or root not in output.parents or view!=output.with_suffix(".md") or output.relative_to(root).parts[0]!="docs":raise ValueError("verification review outputs are unsafe or occupied")
  plan=build_plan(root,result,a.timeout_seconds);data=(json.dumps(plan,ensure_ascii=False,indent=2)+"\n").encode();markdown=render_plan(plan,load_object(result)).encode();output.parent.mkdir(parents=True,exist_ok=True)
  for path,payload in ((output,data),(view,markdown)):atomic_create(payload,path);written.append((path,payload))
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,payload in reversed(written):
   if path.exists() and path.read_bytes()==payload:path.unlink()
  print(f"POST_APPLY_VERIFICATION_V2_PLAN_CREATED: no\nERROR: {e}");return 1
 print(f"POST_APPLY_VERIFICATION_V2_PLAN_CREATED: yes\nREADY_FOR_APPROVAL: {'yes' if plan['readyForApproval'] else 'no'}\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
