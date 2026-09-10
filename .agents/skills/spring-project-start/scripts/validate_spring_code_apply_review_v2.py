#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from spring_code_apply_v2 import render_review,validate_review
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--review",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);path=a.review.resolve(strict=True);review=load_object(path);validate_review(review,path,root)
  if a.view.resolve()!=path.with_suffix(".md") or a.view.read_text()!=render_review(review):raise ValueError("apply review view is stale")
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_APPLY_REVIEW_V2_VALID: no\nERROR: {e}");return 1
 print(f"SPRING_CODE_APPLY_REVIEW_V2_VALID: yes\nREADY_FOR_APPROVAL: {'yes' if review['readyForApproval'] else 'no'}");return 0
if __name__=="__main__":sys.exit(main())
