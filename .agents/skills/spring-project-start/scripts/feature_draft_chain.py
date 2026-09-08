#!/usr/bin/env python3
"""Shared validation for immutable continuation feature-draft chains."""
from __future__ import annotations
import json
from pathlib import Path
from create_feature_spec_from_intake import validate_intake
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object
def load_context(root:Path,intake_path:Path)->tuple[dict,dict,Path]:
 control=root/".starter-harness"; consumption=control/"continuation-consumptions"
 if control.is_symlink() or consumption.is_symlink(): raise ValueError("continuation evidence directory is unsafe")
 intake=load_object(intake_path); validate_intake(intake,intake_path,root); intake_hash=sha(intake_path)
 cancellation=root/".starter-harness/continuation-cancellations"/f"{intake_hash}.json"
 if cancellation.exists(): raise ValueError("continuation intake was cancelled")
 receipt_path=consumption/f"{intake_hash}.json"
 if receipt_path.is_symlink(): raise ValueError("continuation consumption receipt is unsafe")
 receipt=load_object(receipt_path)
 required={"continuationConsumptionVersion","intake","draft","view","featureId","state"}
 if set(receipt)!=required or receipt["continuationConsumptionVersion"]!=1 or receipt["state"]!="AWAITING_USER_DECISIONS" or receipt["intake"]!={"path":intake_path.relative_to(root).as_posix(),"sha256":intake_hash}: raise ValueError("continuation consumption receipt is invalid")
 return intake,receipt,receipt_path
def head(root:Path,receipt:dict)->tuple[Path,dict]:
 current=receipt["draft"]; intake_hash=receipt["intake"]["sha256"]; seen=set(); directory=root/".starter-harness/feature-draft-updates"
 if (root/".starter-harness").is_symlink() or directory.is_symlink(): raise ValueError("feature draft chain directory is unsafe")
 while True:
  if not isinstance(current,dict) or set(current)!={"path","sha256"}: raise ValueError("feature draft reference is invalid")
  path=target_path(root,current["path"],"feature draft")
  if not path.is_file() or sha(path)!=current["sha256"]: raise ValueError("feature draft chain evidence changed")
  if current["sha256"] in seen: raise ValueError("feature draft chain contains a cycle")
  seen.add(current["sha256"]); edge=directory/f"{current['sha256']}.json"
  if not edge.exists(): return path,current
  if edge.is_symlink(): raise ValueError("feature draft update evidence is unsafe")
  value=load_object(edge); required={"featureDraftUpdateVersion","previous","next","view","intakeSha256","changes","state"}
  if set(value)!=required or value["featureDraftUpdateVersion"]!=2 or value["state"]!="COMMITTED" or value["previous"]!=current or value["intakeSha256"]!=intake_hash or not isinstance(value["changes"],list) or not value["changes"]: raise ValueError("feature draft update evidence is invalid")
  view=value["view"]
  if not isinstance(view,dict) or set(view)!={"path","sha256"}: raise ValueError("feature draft update view reference is invalid")
  view_path=target_path(root,view["path"],"feature draft view")
  if not view_path.is_file() or sha(view_path)!=view["sha256"]: raise ValueError("feature draft update view evidence changed")
  current=value["next"]
def encoded(value:dict)->bytes: return (json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode()
