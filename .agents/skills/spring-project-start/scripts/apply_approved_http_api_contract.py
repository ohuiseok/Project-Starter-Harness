#!/usr/bin/env python3
"""Atomically apply the exact artifacts from an approved HTTP API dry-run."""
from __future__ import annotations
import argparse,hashlib,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create,encoded
from http_api_contract_execution import current_handoff,render_artifacts
from prepare_http_api_contract_handoff import argument_path,reference
from record_spec_approval import atomic_write_bytes
from validate_feature_specs import load_object

def sha_bytes(v:bytes)->str:return hashlib.sha256(v).hexdigest()
def tx_path(root:Path,dry:Path)->Path:return root/".starter-harness/http-api-contract-transactions"/f"{hashlib.sha256(dry.read_bytes()).hexdigest()}.json"

def recover(root:Path,transaction:Path)->dict:
 value=load_object(transaction)
 if value.get("state") not in {"PREPARED","APPLYING"}: raise ValueError("transaction is not recoverable")
 for item in reversed(value["creates"]):
  path=argument_path(root,root/item["path"],"created output")
  if path.exists():
   if hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]: raise ValueError(f"created output changed; refusing recovery: {item['path']}")
   path.unlink()
 value["state"]="RECOVERED"; atomic_write_bytes(encoded(value),transaction); return value

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--dry-run",required=True,type=Path); p.add_argument("--approval",required=True,type=Path); p.add_argument("--target",required=True,type=Path); a=p.parse_args()
 transaction=None; root=None
 try:
  root=a.target.resolve(strict=True); dry=argument_path(root,a.dry_run,"dry-run"); approval_path=argument_path(root,a.approval,"approval"); report=load_object(dry); approval=load_object(approval_path)
  if report.get("status")!="READY_FOR_APPROVAL" or approval.get("state")!="APPROVED" or approval.get("dryRun")!=reference(dry,root): raise ValueError("approval does not bind the exact ready dry-run")
  hp=argument_path(root,root/report["handoff"]["path"],"handoff"); hv=argument_path(root,root/report["handoffView"]["path"],"handoff view"); handoff=current_handoff(root,hp,hv,[dry,approval_path])
  source=argument_path(root,root/report["source"]["path"],"OpenAPI source") if report.get("source") else None
  writes,assessment=render_artifacts(root,handoff,source)
  if assessment["blockers"]: raise ValueError("contract assessment changed or is blocked: "+"; ".join(assessment["blockers"]))
  planned=[{"path":path,"sha256":sha_bytes(content),"size":len(content),"action":"CREATE"} for path,content in sorted(writes.items())]
  if planned!=report["plannedFiles"]: raise ValueError("planned artifacts changed after dry-run")
  transaction=tx_path(root,dry)
  if transaction.exists(): raise ValueError("transaction already exists; recover or inspect it before retrying")
  for item in planned:
   if argument_path(root,root/item["path"],"planned output").exists(): raise ValueError(f"CREATE target changed after dry-run: {item['path']}")
  record={"httpApiContractTransactionVersion":1,"state":"PREPARED","dryRun":reference(dry,root),"approval":reference(approval_path,root),"creates":planned,"backup":{"required":False,"reason":"all outputs are create-only"}}
  transaction.parent.mkdir(parents=True,exist_ok=True); atomic_create(encoded(record),transaction); record["state"]="APPLYING"; atomic_write_bytes(encoded(record),transaction)
  for path,content in sorted(writes.items()):
   dest=argument_path(root,root/path,"contract output"); dest.parent.mkdir(parents=True,exist_ok=True); atomic_create(content,dest)
  record["state"]="COMMITTED"; record["baseline"]={item["path"]:item["sha256"] for item in planned}; atomic_write_bytes(encoded(record),transaction)
 except (OSError,ValueError,KeyError,TypeError) as e:
  recovery=""
  if root is not None and transaction is not None and transaction.exists():
   try: recover(root,transaction); recovery="\nROLLBACK: complete"
   except (OSError,ValueError,KeyError,TypeError) as rollback_error: recovery=f"\nROLLBACK: incomplete; recovery required: {rollback_error}"
  print(f"HTTP_API_CONTRACT_APPLIED: no\nERROR: {e}{recovery}"); return 1
 print(f"HTTP_API_CONTRACT_APPLIED: yes\nTRANSACTION: {transaction.relative_to(root)}\nBASELINE_RECORDED: yes"); return 0
if __name__=="__main__":sys.exit(main())
