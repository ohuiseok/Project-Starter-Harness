#!/usr/bin/env python3
"""Cancel an exact latest mapping without deleting its evidence."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create,encoded
from http_api_spring_mapping import reference,validate,child_mappings,mapping_cancellations,SECRET,PII
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--mapping",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--reason",required=True);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);mapping=a.mapping.resolve(strict=True);output=a.output.resolve()
  if output.exists() or root not in output.parents or output.relative_to(root).parts[0]!="docs":raise ValueError("cancellation output is unsafe or occupied")
  if child_mappings(root,mapping) or mapping_cancellations(root,mapping):raise ValueError("mapping is not a current cancellable revision")
  if not a.reason.strip() or SECRET.search(a.reason) or PII.search(a.reason):raise ValueError("cancellation reason is empty or contains sensitive data")
  value=load_object(mapping)
  if validate(value,root):raise ValueError("only a current mapping can be cancelled")
  receipt={"httpApiSpringMappingCancellationVersion":1,"state":"CANCELLED","mapping":reference(mapping,root),"reason":a.reason.strip(),"effects":{"mappingDeleted":False,"implementationPlanAuthorized":False,"sourceChanged":False,"gitCommitOrPush":"NOT_RUN"}};output.parent.mkdir(parents=True,exist_ok=True);atomic_create(encoded(receipt),output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"HTTP_API_SPRING_MAPPING_CANCELLED: no\nERROR: {e}");return 1
 print("HTTP_API_SPRING_MAPPING_CANCELLED: yes\nIMPLEMENTATION_PLAN_AUTHORIZED: no\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
