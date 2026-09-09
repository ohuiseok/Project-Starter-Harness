#!/usr/bin/env python3
"""Revalidate an exact HTTP API evidence discovery report and view."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from discover_http_api_evidence import discover,render
from spring_milestone_completion import target_path
from validate_feature_specs import load_object

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--report",required=True,type=Path); p.add_argument("--view",required=True,type=Path); p.add_argument("--target",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); report_path=target_path(root,a.report.absolute().relative_to(root).as_posix(),"discovery report"); view_path=target_path(root,a.view.absolute().relative_to(root).as_posix(),"discovery view"); saved=load_object(report_path)
  if saved.get("httpApiEvidenceDiscoveryVersion")!=1 or saved.get("target")!=str(root) or not view_path.is_file(): raise ValueError("discovery report or view is invalid")
  scope=saved["scope"]; feature=target_path(root,saved["inputs"]["feature"]["path"],"feature"); profile=target_path(root,saved["inputs"]["technologyProfile"]["path"],"profile")
  expected=discover(root,feature,profile,scope["modules"],scope["maxFiles"],scope["maxFileBytes"],scope["maxTotalBytes"],scope["excludedPaths"])
  if saved!=expected or view_path.read_text()!=render(saved): raise ValueError("discovery evidence or user view is stale")
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"HTTP_API_EVIDENCE_DISCOVERY_CURRENT: no\nERROR: {e}"); return 1
 print("HTTP_API_EVIDENCE_DISCOVERY_CURRENT: yes"); print("READY_FOR_ROUTE_DECISION: yes"); return 0
if __name__=="__main__": sys.exit(main())
