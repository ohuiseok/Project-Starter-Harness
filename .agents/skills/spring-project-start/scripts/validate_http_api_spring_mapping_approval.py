#!/usr/bin/env python3
"""Validate an exact, latest HTTP API Spring mapping approval for consumption."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from http_api_spring_mapping import reference,validate,child_mappings,validate_contract_current,mapping_cancellations
from render_http_api_spring_mapping import render
from validate_feature_specs import load_object
def validate_approval(root:Path,approval_path:Path)->dict:
 receipt=load_object(approval_path)
 required={"httpApiSpringMappingApprovalVersion","state","mapping","view","approvedBy","approvedAt","effects"}
 if set(receipt)!=required or receipt.get("httpApiSpringMappingApprovalVersion")!=1 or receipt.get("state")!="APPROVED":raise ValueError("mapping approval receipt is invalid")
 mapping=root/receipt["mapping"]["path"];view=root/receipt["view"]["path"]
 if reference(mapping,root)!=receipt["mapping"] or reference(view,root)!=receipt["view"]:raise ValueError("mapping approval evidence changed")
 value=load_object(mapping);blockers=validate(value,root)
 validate_contract_current(value,root)
 if blockers or value["status"]!="REVIEW_READY" or view!=mapping.with_suffix(".md") or view.read_text()!=render(value,blockers):raise ValueError("approved mapping is stale or blocked")
 if child_mappings(root,mapping):raise ValueError("approved mapping is no longer the latest revision")
 if mapping_cancellations(root,mapping):raise ValueError("approved mapping was cancelled")
 return receipt
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--approval",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:root=a.target.resolve(strict=True);validate_approval(root,a.approval.resolve(strict=True))
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"HTTP_API_SPRING_MAPPING_APPROVAL_CURRENT: no\nERROR: {e}");return 1
 print("HTTP_API_SPRING_MAPPING_APPROVAL_CURRENT: yes\nIMPLEMENTATION_PLAN_AUTHORIZED: yes\nCODE_DRY_RUN_AUTHORIZED: no");return 0
if __name__=="__main__":sys.exit(main())
