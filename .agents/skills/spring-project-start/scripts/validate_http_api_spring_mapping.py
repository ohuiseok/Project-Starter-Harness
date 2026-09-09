#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from http_api_spring_mapping import validate
from render_http_api_spring_mapping import render
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--mapping",required=True,type=Path);p.add_argument("--view",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);value=load_object(a.mapping);blockers=validate(value,root)
  if a.view!=a.mapping.with_suffix(".md") or not a.view.is_file() or a.view.read_text()!=render(value,blockers):raise ValueError("mapping view is missing or stale")
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"HTTP_API_SPRING_MAPPING_VALID: no\nERROR: {e}");return 1
 print(f"HTTP_API_SPRING_MAPPING_VALID: yes\nMAPPING_STATUS: {value['status']}\nINPUTS_CURRENT: {'no' if blockers else 'yes'}");return 0
if __name__=="__main__":sys.exit(main())
