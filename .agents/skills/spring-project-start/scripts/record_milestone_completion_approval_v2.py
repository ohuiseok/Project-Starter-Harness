#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,json,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create
from http_api_spring_mapping import reference
from milestone_completion_v2 import render,validate_review
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--review",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--approved-by",required=True);p.add_argument("--approved-at",required=True);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);review_path=a.review.resolve(strict=True);view=a.view.resolve(strict=True);output=a.output.resolve();review=validate_review(load_object(review_path),review_path,root)
  if not review["readyForApproval"] or view!=review_path.with_suffix(".md") or view.read_text()!=render(review) or output.exists() or root not in output.parents:raise ValueError("exact ready completion review is required")
  if not a.approved_by.strip() or dt.datetime.fromisoformat(a.approved_at.replace("Z","+00:00")).utcoffset() is None or a.approved_at!=review["completion"]["document"]["completionApprovedAt"]:raise ValueError("approval identity or time is invalid")
  value={"milestoneCompletionApprovalV2Version":1,"state":"APPROVED","completionAttemptId":review["completionAttemptId"],"review":reference(review_path,root),"view":reference(view,root),"approvedBy":a.approved_by.strip(),"approvedAt":a.approved_at,"effects":{"milestoneCompletion":True,"progressMutation":True,"sourceMutation":False,"testExecution":False,"gitCommitOrPush":"NOT_RUN"}};output.parent.mkdir(parents=True,exist_ok=True);atomic_create((json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode(),output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"MILESTONE_COMPLETION_V2_APPROVED: no\nERROR: {e}");return 1
 print("MILESTONE_COMPLETION_V2_APPROVED: yes\nSOURCE_MUTATION: no\nTEST_EXECUTION: no");return 0
if __name__=="__main__":sys.exit(main())
