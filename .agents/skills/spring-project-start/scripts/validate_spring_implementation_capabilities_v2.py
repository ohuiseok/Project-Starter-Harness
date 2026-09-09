#!/usr/bin/env python3
"""Validate the implementation-plan v2 capability catalog."""
from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path

ARCHITECTURES={"LAYERED","HEXAGONAL","CLEAN","MODULAR","MICROSERVICE","CUSTOM"}
ADAPTER_ID=re.compile(r"^[A-Z][A-Z0-9_]*$")

def load_and_validate(path:Path)->dict:
 value=json.loads(path.read_text())
 if set(value)!={"capabilityCatalogVersion","adapters"} or value["capabilityCatalogVersion"]!=2 or not isinstance(value["adapters"],list) or not value["adapters"]:raise ValueError("capability catalog v2 structure is invalid")
 ids=[];selectors=[]
 required={"id","language","webStack","architectures","securityProfiles","securedOperations","persistence","planning","codeDryRunRenderer"}
 for item in value["adapters"]:
  if not isinstance(item,dict) or set(item)!=required or not ADAPTER_ID.fullmatch(item["id"]):raise ValueError("capability adapter structure or ID is invalid")
  if item["language"] not in {"JAVA","KOTLIN"} or item["webStack"] not in {"SPRING_MVC","WEBFLUX"} or not set(item["architectures"])<=ARCHITECTURES or not item["architectures"]:raise ValueError(f"capability adapter selector is invalid: {item['id']}")
  if len(item["architectures"])!=len(set(item["architectures"])) or len(item["securityProfiles"])!=len(set(item["securityProfiles"])) or not all(isinstance(i,str) and i for i in item["securityProfiles"]):raise ValueError(f"capability adapter choices are duplicated or invalid: {item['id']}")
  if not isinstance(item["securedOperations"],bool) or item["persistence"] not in {"NOT_USED"} or item["planning"] not in {"SUPPORTED","UNSUPPORTED"}:raise ValueError(f"capability adapter claims are invalid: {item['id']}")
  if item["codeDryRunRenderer"]!="NOT_IMPLEMENTED":raise ValueError(f"unregistered code renderer claim: {item['id']}")
  ids.append(item["id"]);selectors.extend((item["language"],item["webStack"],arch) for arch in item["architectures"])
 if len(ids)!=len(set(ids)) or len(selectors)!=len(set(selectors)):raise ValueError("capability adapter IDs or selectors overlap")
 return value

def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--catalog",type=Path,default=Path(__file__).resolve().parent.parent/"references/spring-implementation-capabilities-v2.json");a=p.parse_args()
 try:value=load_and_validate(a.catalog)
 except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as e:print(f"SPRING_IMPLEMENTATION_CAPABILITIES_V2_VALID: no\nERROR: {e}");return 1
 print(f"SPRING_IMPLEMENTATION_CAPABILITIES_V2_VALID: yes\nADAPTERS: {len(value['adapters'])}");return 0
if __name__=="__main__":sys.exit(main())
