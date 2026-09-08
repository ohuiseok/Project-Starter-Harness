#!/usr/bin/env python3
"""Build and validate continuation-consumption v1 to v2 migrations."""
from __future__ import annotations
from pathlib import Path
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object,validate_feature
def build(root:Path,input_path:Path,base_path:Path|None)->dict:
 value=load_object(input_path); required={"continuationConsumptionVersion","intake","draft","view","featureId","state"}
 if set(value)!=required or value["continuationConsumptionVersion"]!=1 or value["state"]!="AWAITING_USER_DECISIONS": raise ValueError("a v1 continuation consumption is required")
 for key in ("intake","draft","view"):
  item=value[key]
  if not isinstance(item,dict) or set(item)!={"path","sha256"}: raise ValueError(f"v1 {key} reference is invalid")
  path=target_path(root,item["path"],f"v1 {key}")
  if not path.is_file() or sha(path)!=item["sha256"]: raise ValueError(f"v1 {key} evidence changed")
 intake=load_object(target_path(root,value["intake"]["path"],"intake")); route_type=intake.get("routeType")
 if route_type=="REVISE_FEATURE" or (route_type=="BUG_FIX" and intake.get("feature",{}).get("name")):
  if base_path is None: raise ValueError("base-feature is required for revision migration")
 if base_path:
  base=base_path.resolve(strict=True)
  if root not in base.parents or base.is_symlink(): raise ValueError("migration base feature is unsafe")
  document=load_object(base); approved,blockers=validate_feature(document,load_object(target_path(root,intake["projectBrief"]["path"],"project brief")))
  if not approved or blockers or document["feature"]["id"]!=value["featureId"]: raise ValueError("migration base feature is not the approved matching contract")
  base_ref={"path":base.relative_to(root).as_posix(),"sha256":sha(base)}
 else: base_ref=None
 return {"continuationConsumptionVersion":2,"intake":value["intake"],"draft":value["draft"],"view":value["view"],"baseFeature":base_ref,"featureId":value["featureId"],"state":value["state"]}
def render(old:dict,new:dict)->str:
 return "\n".join(["# continuation 소비 기록 마이그레이션","","- 버전: 1 → 2",f"- 기능: {new['featureId']}",f"- 기존 기능 기준 계약: {new['baseFeature']['path'] if new['baseFeature'] else '없음'}","- draft·view·intake 해시는 변경하지 않음","- 기능 명세와 프로젝트 계약은 변경하지 않음","","## 선택","","- 이 마이그레이션 적용","- 취소",""])
