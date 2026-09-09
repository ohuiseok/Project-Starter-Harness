#!/usr/bin/env python3
"""Record explicit approval of one exact current HTTP API Spring mapping view."""
from __future__ import annotations
import argparse,datetime,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create,encoded
from http_api_spring_mapping import reference,validate,child_mappings,validate_contract_current,mapping_cancellations
from render_http_api_spring_mapping import render
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--mapping",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--approved-by",required=True);p.add_argument("--approved-at",required=True);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);mapping=a.mapping.resolve(strict=True);view=a.view.resolve(strict=True);output=a.output.resolve()
  if any(path.is_symlink() for path in (a.mapping,a.view,a.output)) or any(root not in path.parents for path in (mapping,view,output)) or output.exists():raise ValueError("mapping approval paths are unsafe or occupied")
  value=load_object(mapping);blockers=validate(value,root)
  validate_contract_current(value,root)
  if child_mappings(root,mapping):raise ValueError("only the latest mapping revision can be approved")
  if mapping_cancellations(root,mapping):raise ValueError("cancelled mapping cannot be approved")
  if value["status"]!="REVIEW_READY" or blockers:raise ValueError("only a current REVIEW_READY mapping can be approved")
  if view!=mapping.with_suffix(".md") or view.read_text()!=render(value,blockers):raise ValueError("mapping view is stale")
  if not a.approved_by.strip():raise ValueError("approved-by is required")
  datetime.datetime.fromisoformat(a.approved_at.replace("Z","+00:00"));receipt={"httpApiSpringMappingApprovalVersion":1,"state":"APPROVED","mapping":reference(mapping,root),"view":reference(view,root),"approvedBy":a.approved_by.strip(),"approvedAt":a.approved_at,"effects":{"implementationPlanAuthorized":True,"codeDryRunAuthorized":False,"sourceChanged":False,"testsExecuted":False,"gitCommitOrPush":"NOT_RUN"}};output.parent.mkdir(parents=True,exist_ok=True);atomic_create(encoded(receipt),output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"HTTP_API_SPRING_MAPPING_APPROVED: no\nERROR: {e}");return 1
 print("HTTP_API_SPRING_MAPPING_APPROVED: yes\nIMPLEMENTATION_PLAN_AUTHORIZED: yes\nCODE_DRY_RUN_AUTHORIZED: no\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
