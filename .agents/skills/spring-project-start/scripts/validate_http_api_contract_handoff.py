#!/usr/bin/env python3
"""Rebuild and validate an exact HTTP API contract preparation handoff."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from prepare_http_api_contract_handoff import argument_path,build,render
from validate_feature_specs import load_object

def validate_saved(root:Path,handoff_path:Path,view_path:Path,derived_paths:list[Path]|None=None)->dict:
 saved=load_object(handoff_path)
 if saved.get("httpApiContractHandoffVersion")!=2 or view_path!=handoff_path.with_suffix(".md") or not view_path.is_file(): raise ValueError("handoff identity or view is invalid")
 inputs=saved["inputs"]; selection=saved.get("operationSelection") or {}
 expected=build(root,argument_path(root,root/inputs["applicationReceipt"]["path"],"application receipt"),argument_path(root,root/inputs["approvedRoute"]["path"],"approved route"),argument_path(root,root/inputs["feature"]["path"],"feature"),argument_path(root,root/inputs["projectBrief"]["path"],"project brief"),argument_path(root,root/inputs["technologyProfile"]["path"],"technology profile"),saved["contractId"],[handoff_path,view_path,*(derived_paths or [])],selection.get("selectedOperationIds",[]),selection.get("source"))
 if saved!=expected or view_path.read_text()!=render(saved): raise ValueError("handoff inputs, assessment, or user view are stale")
 return saved

def main()->int:
 parser=argparse.ArgumentParser(); parser.add_argument("--handoff",required=True,type=Path); parser.add_argument("--view",required=True,type=Path); parser.add_argument("--target",required=True,type=Path); args=parser.parse_args()
 try:
  root=args.target.resolve(strict=True); handoff_path=argument_path(root,args.handoff,"handoff"); view_path=argument_path(root,args.view,"handoff view"); saved=validate_saved(root,handoff_path,view_path)
 except (OSError,ValueError,KeyError,TypeError) as error:
  print(f"HTTP_API_CONTRACT_HANDOFF_CURRENT: no\nERROR: {error}"); return 1
 print(f"HTTP_API_CONTRACT_HANDOFF_CURRENT: yes\nHANDOFF_STATUS: {saved['status']}\nREADY_FOR_ADAPTER: {'yes' if saved['status']!='BLOCKED' else 'no'}"); return 0

if __name__=="__main__": sys.exit(main())
