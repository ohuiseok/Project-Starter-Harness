#!/usr/bin/env python3
"""Approve and atomically promote an exact reviewed feature specification."""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,sys
from pathlib import Path
from feature_draft_chain import encoded
from feature_spec_promotion import build,render
from record_spec_approval import approved_copy,atomic_write_bytes,synchronize_candidate
from render_spec_markdown import render_feature,render_project
from spring_milestone_completion import sha
from validate_feature_specs import load_object,validate_feature,validate_project
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--plan",required=True,type=Path); p.add_argument("--view",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--expected-plan-hash",required=True); p.add_argument("--approved-by",required=True); p.add_argument("--approved-at",required=True); a=p.parse_args(); written=[]
 try:
  root=a.target.resolve(strict=True); plan_path=a.plan.resolve(strict=True); view_path=a.view.resolve(strict=True)
  if a.target.is_symlink() or any(root not in path.parents or path.is_symlink() for path in (plan_path,view_path)) or sha(plan_path)!=a.expected_plan_hash or not a.approved_by.strip(): raise ValueError("promotion approval inputs are unsafe or stale")
  timestamp=dt.datetime.fromisoformat(a.approved_at.replace("Z","+00:00"))
  if timestamp.utcoffset() is None: raise ValueError("approved-at must include a timezone")
  saved=load_object(plan_path); expected=build(root,root/saved["intake"]["path"],root/saved["readiness"]["path"],root/saved["readinessView"]["path"])
  if saved!=expected or view_path.read_text()!=render(saved): raise ValueError("promotion plan or reviewed view is stale")
  project=approved_copy(saved["proposedProject"],a.approved_by,a.approved_at); feature=approved_copy(saved["proposedFeature"],a.approved_by,a.approved_at); synchronize_candidate(project,feature); project=approved_copy(project,a.approved_by,a.approved_at); approved,blockers=validate_feature(feature,project); project_ok,project_blockers=validate_project(project)
  if not approved or blockers or not project_ok or project_blockers: raise ValueError("approved promotion documents are not advancement-ready")
  project_path=root/saved["projectBrief"]["path"]; feature_path=root/saved["officialFeaturePath"]; targets=[(project_path,encoded(project)),(project_path.with_suffix(".md"),render_project(project).encode()),(feature_path,encoded(feature)),(feature_path.with_suffix(".md"),render_feature(feature,project).encode())]; intake_hash=saved["intake"]["sha256"]; completion=root/".starter-harness/continuation-completions"/f"{intake_hash}.json"; completion_value={"continuationCompletionVersion":1,"intake":saved["intake"],"promotionPlan":{"path":plan_path.relative_to(root).as_posix(),"sha256":sha(plan_path)},"reservation":saved["reservation"],"featureId":feature["feature"]["id"],"approvedBy":a.approved_by,"approvedAt":a.approved_at,"state":"CONSUMED"}; targets.append((completion,encoded(completion_value)))
  if completion.exists(): raise ValueError("continuation intake is already consumed")
  txid=hashlib.sha256(f"{sha(plan_path)}\0{a.approved_by}\0{a.approved_at}".encode()).hexdigest(); txdir=root/".starter-harness/feature-spec-promotion-transactions"/txid; journal=txdir/"transaction.json"
  if (root/".starter-harness").is_symlink() or txdir.parent.is_symlink() or txdir.exists(): raise ValueError("promotion transaction already exists or is unsafe")
  txdir.mkdir(parents=True); records=[]
  for index,(path,after) in enumerate(targets):
   before=path.read_bytes() if path.exists() else None; backup=None
   if before is not None: backup=f"backup-{index}"; atomic_write_bytes(before,txdir/backup)
   records.append({"path":path.relative_to(root).as_posix(),"beforeSha256":hashlib.sha256(before).hexdigest() if before is not None else None,"backup":backup,"afterSha256":hashlib.sha256(after).hexdigest()})
  transaction={"featureSpecPromotionTransactionVersion":1,"plan":{"path":plan_path.relative_to(root).as_posix(),"sha256":sha(plan_path)},"targets":records,"state":"PREPARED"}; atomic_write_bytes(encoded(transaction),journal); transaction["state"]="APPLYING"; atomic_write_bytes(encoded(transaction),journal)
  try:
   for path,after in targets:
    path.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(after,path); written.append((path,after))
  except BaseException:
   for record in reversed(records):
    path=root/record["path"]
    if path.exists() and sha(path)==record["afterSha256"]:
     if record["backup"]: atomic_write_bytes((txdir/record["backup"]).read_bytes(),path)
     else: path.unlink()
   transaction["state"]="ROLLED_BACK"; atomic_write_bytes(encoded(transaction),journal); raise
  transaction["state"]="COMMITTED"; atomic_write_bytes(encoded(transaction),journal)
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"FEATURE_SPEC_PROMOTION_APPLIED: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_SPEC_PROMOTION_APPLIED: yes"); print("TRANSACTION_STATE: COMMITTED"); print("NEXT_WORKFLOW: DESIGN_ROUTING"); print("GIT_COMMIT_OR_PUSH: NOT_RUN"); return 0
if __name__=="__main__": sys.exit(main())
