#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from spring_code_apply_v2 import build_review,render_review
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--verification-report",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--result",required=True);a=p.parse_args();written=[]
 try:
  root=a.target.resolve(strict=True);verification=a.verification_report.resolve(strict=True);output=a.output.resolve();view=a.view.resolve()
  if output.exists() or view.exists() or view!=output.with_suffix(".md") or root not in output.parents or output.relative_to(root).parts[0]!="docs":raise ValueError("apply review outputs are unsafe or occupied")
  review=build_review(root,verification,a.result);payload=(json.dumps(review,ensure_ascii=False,indent=2)+"\n").encode();markdown=render_review(review).encode();output.parent.mkdir(parents=True,exist_ok=True)
  for path,data in ((output,payload),(view,markdown)):atomic_create(data,path);written.append((path,data))
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,data in reversed(written):
   if path.exists() and path.read_bytes()==data:path.unlink()
  print(f"SPRING_CODE_APPLY_REVIEW_V2_CREATED: no\nERROR: {e}");return 1
 print(f"SPRING_CODE_APPLY_REVIEW_V2_CREATED: yes\nBLOCKERS: {len(review['blockers'])}\nREADY_FOR_APPROVAL: {'yes' if review['readyForApproval'] else 'no'}\nSOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
