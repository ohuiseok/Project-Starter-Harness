#!/usr/bin/env python3
"""Prepare a reviewed HTTP API-to-Spring mapping without changing source."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from discover_http_api_evidence import atomic_create,encoded
from existing_http_api_contract import validate_existing_contract
from http_api_contract import validate_http_contract
from http_api_spring_mapping import build,reference,validate
from render_http_api_spring_mapping import render
from validate_feature_specs import load_object

def main()->int:
 p=argparse.ArgumentParser()
 for name in ("feature","profile","route","http-api-contract","target","output","view"):p.add_argument("--"+name,required=True,type=Path)
 p.add_argument("--module-path",required=True);p.add_argument("--package-name",required=True);p.add_argument("--decision-source",required=True,choices=["USER_CONFIRMED","PROJECT_EVIDENCE","RECOMMENDATION_ACCEPTED"])
 p.add_argument("--architecture",choices=["LAYERED","HEXAGONAL","CLEAN","MODULAR","MICROSERVICE","CUSTOM"]);p.add_argument("--web-stack",choices=["SPRING_MVC","WEBFLUX"]);p.add_argument("--dto-style",choices=["CLASS","RECORD","KOTLIN_DATA_CLASS","CUSTOM"]);p.add_argument("--mapping-style",choices=["MANUAL","MAPSTRUCT","CUSTOM"]);p.add_argument("--test-client",choices=["MOCKMVC","WEBTESTCLIENT","CUSTOM"])
 for name in ("architecture-detail","web-stack-detail","dto-style-detail","mapping-style-detail","test-client-detail"):p.add_argument("--"+name)
 a=p.parse_args();written=[]
 try:
  root=a.target.resolve(strict=True); output=a.output.resolve(); view=a.view.resolve()
  if a.target.is_symlink() or root not in output.parents or root not in view.parents or output.exists() or view.exists() or view!=output.with_suffix(".md"):raise ValueError("mapping output paths are unsafe or occupied")
  paths={"featureSpec":a.feature,"technologyProfile":a.profile,"designRoute":a.route,"httpApiContract":a.http_api_contract};refs={k:reference(v,root) for k,v in paths.items()};feature,profile,route,metadata=map(load_object,paths.values());disposition=metadata.get("disposition")
  if disposition=="CREATE":approved,blockers,openapi=validate_http_contract(metadata,route,a.route,root,a.http_api_contract,feature,profile)
  elif disposition in {"EXTEND","REUSE"}:approved,blockers,openapi,_=validate_existing_contract(metadata,route,a.route,root,a.http_api_contract,feature,profile)
  else:raise ValueError("HTTP API contract disposition is unsupported")
  if not approved or blockers:raise ValueError("HTTP API contract is not semantically approved and current: "+"; ".join(blockers))
  artifact=root/metadata["artifact"]["path"];refs["openApi"]=reference(artifact,root)
  choices={"architecture":a.architecture,"webStack":a.web_stack,"dtoStyle":a.dto_style,"mappingStyle":a.mapping_style,"testClient":a.test_client}; choices={k:v for k,v in choices.items() if v}
  details={"architecture":a.architecture_detail,"webStack":a.web_stack_detail,"dtoStyle":a.dto_style_detail,"mappingStyle":a.mapping_style_detail,"testClient":a.test_client_detail};details={k:v.strip() for k,v in details.items() if isinstance(v,str) and v.strip()}
  value=build(feature,profile,openapi,root,a.module_path,a.package_name,choices,a.decision_source,refs,details); blockers=validate(value,root); payload=encoded(value); markdown=render(value,blockers).encode();output.parent.mkdir(parents=True,exist_ok=True)
  for path,content in ((output,payload),(view,markdown)):atomic_create(content,path);written.append((path,content))
 except (OSError,ValueError,KeyError,TypeError) as e:
  for path,content in reversed(written):
   if path.exists() and path.read_bytes()==content:path.unlink()
  print(f"HTTP_API_SPRING_MAPPING_CREATED: no\nERROR: {e}");return 1
 print(f"HTTP_API_SPRING_MAPPING_CREATED: yes\nMAPPING_STATUS: {value['status']}\nTARGET_SOURCE_CHANGED: no\nCODE_DRY_RUN_AUTHORIZED: no");return 0
if __name__=="__main__":sys.exit(main())
