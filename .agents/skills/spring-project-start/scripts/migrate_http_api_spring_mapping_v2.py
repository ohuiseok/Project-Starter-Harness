#!/usr/bin/env python3
"""Rebuild a legacy v1 HTTP API Spring mapping as a separate reviewed v2 revision."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create,encoded
from http_api_spring_mapping import build,reference,validate
from render_http_api_spring_mapping import render
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--input",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--view",required=True,type=Path);a=p.parse_args();written=[]
 try:
  root=a.target.resolve(strict=True);source=a.input.resolve(strict=True);out=a.output.resolve();view=a.view.resolve()
  if out.exists() or view.exists() or view!=out.with_suffix(".md") or root not in out.parents or out.relative_to(root).parts[0]!="docs":raise ValueError("migration outputs are unsafe or occupied")
  old=load_object(source)
  if old.get("httpApiSpringMappingVersion")!=1:raise ValueError("migration requires a legacy v1 mapping")
  inputs=old["inputs"]
  for item in inputs.values():
   if reference(root/item["path"],root)!=item:raise ValueError("legacy mapping input changed")
  feature=load_object(root/inputs["featureSpec"]["path"]);profile=load_object(root/inputs["technologyProfile"]["path"]);openapi=load_object(root/inputs["openApi"]["path"]);choices={k:v["value"] for k,v in old["decisions"].items()};details={k:v.get("detail") for k,v in old["decisions"].items() if v.get("detail")};sources={v["source"] for v in old["decisions"].values()}
  if len(sources)!=1:raise ValueError("legacy decision sources are ambiguous")
  value=build(feature,profile,openapi,root,old["target"]["modulePath"],old["target"]["packageName"],choices,next(iter(sources)),inputs,details,revision={"previous":reference(source,root),"changeSummary":"MIGRATED_FROM_V1_REVIEW_REQUIRED"});payload=encoded(value);markdown=render(value,validate(value,root)).encode();out.parent.mkdir(parents=True,exist_ok=True)
  for path,content in ((out,payload),(view,markdown)):atomic_create(content,path);written.append((path,content))
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,content in reversed(written):
   if path.exists() and path.read_bytes()==content:path.unlink()
  print(f"HTTP_API_SPRING_MAPPING_MIGRATED: no\nERROR: {e}");return 1
 print(f"HTTP_API_SPRING_MAPPING_MIGRATED: yes\nMAPPING_STATUS: {value['status']}\nAPPROVAL_INHERITED: no\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
