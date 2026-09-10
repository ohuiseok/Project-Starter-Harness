#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from milestone_completion_v2 import build_review,render
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--post-apply-result",required=True,type=Path);p.add_argument("--feature",required=True,type=Path);p.add_argument("--project-brief",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--completion-output",required=True);p.add_argument("--approved-at",required=True);p.add_argument("--output",required=True,type=Path);p.add_argument("--view",required=True,type=Path);a=p.parse_args();written=[]
 try:
  root=a.target.resolve(strict=True);output=a.output.resolve();view=a.view.resolve()
  if output.exists() or view.exists() or root not in output.parents or view!=output.with_suffix(".md") or output.relative_to(root).parts[0]!="docs":raise ValueError("completion review outputs are unsafe or occupied")
  review=build_review(root,a.post_apply_result.resolve(strict=True),a.feature.resolve(strict=True),a.project_brief.resolve(strict=True),a.completion_output,a.approved_at);pairs=((output,(json.dumps(review,ensure_ascii=False,indent=2)+"\n").encode()),(view,render(review).encode()));output.parent.mkdir(parents=True,exist_ok=True)
  for path,data in pairs:atomic_create(data,path);written.append((path,data))
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,data in reversed(written):
   if path.exists() and path.read_bytes()==data:path.unlink()
  print(f"MILESTONE_COMPLETION_V2_REVIEW_CREATED: no\nERROR: {e}");return 1
 print(f"MILESTONE_COMPLETION_V2_REVIEW_CREATED: yes\nREADY_FOR_APPROVAL: {'yes' if review['readyForApproval'] else 'no'}\nSOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
