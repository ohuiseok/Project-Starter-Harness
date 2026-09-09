#!/usr/bin/env python3
"""Record explicit approval of one exact HTTP API contract dry-run."""
from __future__ import annotations
import argparse,datetime,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create,encoded
from prepare_http_api_contract_handoff import argument_path,reference
from validate_feature_specs import load_object

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--dry-run",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--approved-by",required=True); p.add_argument("--approved-at",required=True); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); dry=argument_path(root,a.dry_run,"dry-run"); out=argument_path(root,a.output,"approval")
  if out.exists(): raise ValueError("approval output already exists")
  report=load_object(dry)
  if report.get("httpApiContractDryRunVersion")!=1 or report.get("status")!="READY_FOR_APPROVAL" or report.get("blockers"): raise ValueError("only a clear dry-run can be approved")
  if not a.approved_by.strip(): raise ValueError("approved-by is required")
  datetime.datetime.fromisoformat(a.approved_at.replace("Z","+00:00"))
  value={"httpApiContractDryRunApprovalVersion":1,"state":"APPROVED","dryRun":reference(dry,root),"approvedBy":a.approved_by.strip(),"approvedAt":a.approved_at}
  out.parent.mkdir(parents=True,exist_ok=True); atomic_create(encoded(value),out)
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"HTTP_API_CONTRACT_DRY_RUN_APPROVED: no\nERROR: {e}"); return 1
 print("HTTP_API_CONTRACT_DRY_RUN_APPROVED: yes\nTARGET_CHANGED: no"); return 0
if __name__=="__main__":sys.exit(main())
