#!/usr/bin/env python3
"""Prepare an immutable, source-bound HTTP API contract dry-run."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create,encoded
from http_api_contract_execution import current_handoff,render_artifacts
from prepare_http_api_contract_handoff import argument_path,reference

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--handoff",required=True,type=Path); p.add_argument("--handoff-view",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--openapi-source",type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); hp=argument_path(root,a.handoff,"handoff"); hv=argument_path(root,a.handoff_view,"handoff view"); out=argument_path(root,a.output,"dry-run output")
  if out.exists(): raise ValueError("dry-run output already exists")
  handoff=current_handoff(root,hp,hv)
  if handoff["status"]=="BLOCKED": raise ValueError("handoff is blocked")
  source=argument_path(root,a.openapi_source,"OpenAPI source") if a.openapi_source else None
  writes,assessment=render_artifacts(root,handoff,source)
  planned=[]
  for path,content in sorted(writes.items()):
   destination=argument_path(root,root/path,"planned output")
   if destination.exists(): assessment["blockers"].append(f"planned output already exists: {path}")
   planned.append({"path":path,"sha256":__import__('hashlib').sha256(content).hexdigest(),"size":len(content),"action":"CREATE"})
  report={"httpApiContractDryRunVersion":1,"status":"READY_FOR_APPROVAL" if not assessment["blockers"] else "BLOCKED","handoff":reference(hp,root),"handoffView":reference(hv,root),"source":assessment["source"],"plannedFiles":planned,"blockers":assessment["blockers"],"effects":{"targetChanged":False,"adapterExecuted":False,"gitCommitOrPush":"NOT_RUN"}}
  out.parent.mkdir(parents=True,exist_ok=True); atomic_create(encoded(report),out)
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"HTTP_API_CONTRACT_DRY_RUN_VALID: no\nERROR: {e}"); return 1
 print(f"HTTP_API_CONTRACT_DRY_RUN_VALID: yes\nDRY_RUN_STATUS: {report['status']}\nTARGET_CHANGED: no\nAPPROVAL_REQUIRED: yes"); return 0
if __name__=="__main__":sys.exit(main())
