#!/usr/bin/env python3
"""Approve and transactionally promote an exact reviewed feature specification."""
from __future__ import annotations
import argparse,datetime as dt,hashlib,sys
from pathlib import Path
from feature_draft_chain import encoded
from feature_spec_promotion import build,render
from record_spec_approval import approved_copy,atomic_write_bytes,synchronize_candidate
from render_spec_markdown import render_feature,render_project
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object,validate_feature,validate_project
ACTIVE={"PREPARED","APPLYING","ROLLBACK_INCOMPLETE"}
def transaction_id(plan_hash:str,actor:str,when:str)->str: return hashlib.sha256(f"{plan_hash}\0{actor}\0{when}".encode()).hexdigest()
def pending(root:Path)->list[Path]:
 directory=root/".starter-harness/feature-spec-promotion-transactions"
 if directory.is_symlink(): raise ValueError("promotion transaction directory is unsafe")
 result=[]
 if directory.is_dir():
  for journal in directory.glob("*/transaction.json"):
   if journal.is_symlink(): raise ValueError("promotion transaction journal is unsafe")
   value=load_object(journal)
   if value.get("featureSpecPromotionTransactionVersion")!=2 or value.get("state") not in ACTIVE|{"COMMITTED","ROLLED_BACK"}: raise ValueError(f"{journal}: promotion transaction journal is malformed or unsupported")
   if value["state"] in ACTIVE: result.append(journal)
 return result
def current_hash(path:Path)->str|None:
 if path.is_symlink() or (path.exists() and not path.is_file()): raise ValueError(f"{path}: target type is unsafe")
 return sha(path) if path.exists() else None
def argument_path(root:Path,value:Path,label:str)->Path:
 try: relative=value.absolute().relative_to(root).as_posix()
 except ValueError as error: raise ValueError(f"{label} must be inside the target") from error
 return target_path(root,relative,label)
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--plan",required=True,type=Path); p.add_argument("--view",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--expected-plan-hash",required=True); p.add_argument("--approved-by",required=True); p.add_argument("--approved-at",required=True); a=p.parse_args(); transaction=None; journal=None; txdir=None
 try:
  root=a.target.resolve(strict=True); plan_path=argument_path(root,a.plan,"promotion plan"); view_path=argument_path(root,a.view,"promotion view")
  if a.target.is_symlink() or any(not path.is_file() for path in (plan_path,view_path)) or sha(plan_path)!=a.expected_plan_hash or not a.approved_by.strip(): raise ValueError("promotion approval inputs are unsafe or stale")
  timestamp=dt.datetime.fromisoformat(a.approved_at.replace("Z","+00:00"))
  if timestamp.utcoffset() is None: raise ValueError("approved-at must include a timezone")
  if pending(root): raise ValueError("an unresolved feature-spec promotion transaction requires recovery")
  saved=load_object(plan_path); expected=build(root,target_path(root,saved["intake"]["path"],"promotion intake"),target_path(root,saved["readiness"]["path"],"promotion readiness"),target_path(root,saved["readinessView"]["path"],"promotion readiness view"))
  if saved!=expected or view_path.read_text()!=render(saved): raise ValueError("promotion plan or reviewed view is stale")
  project=approved_copy(saved["proposedProject"],a.approved_by,a.approved_at); feature=approved_copy(saved["proposedFeature"],a.approved_by,a.approved_at); synchronize_candidate(project,feature); project=approved_copy(project,a.approved_by,a.approved_at); approved,blockers=validate_feature(feature,project); project_ok,project_blockers=validate_project(project)
  if not approved or blockers or not project_ok or project_blockers: raise ValueError("approved promotion documents are not advancement-ready")
  project_path=target_path(root,saved["projectBrief"]["path"],"project brief"); project_view=target_path(root,saved["projectBriefView"]["path"],"project brief view"); feature_path=target_path(root,saved["officialFeaturePath"],"official feature"); feature_view=target_path(root,str(Path(saved["officialFeaturePath"]).with_suffix(".md")),"official feature view"); intake_hash=saved["intake"]["sha256"]; completion=target_path(root,f".starter-harness/continuation-completions/{intake_hash}.json","continuation completion")
  completion_value={"continuationCompletionVersion":1,"intake":saved["intake"],"promotionPlan":{"path":plan_path.relative_to(root).as_posix(),"sha256":sha(plan_path)},"reservation":saved["reservation"],"featureId":feature["feature"]["id"],"approvedBy":a.approved_by,"approvedAt":a.approved_at,"state":"CONSUMED"}; targets=[(project_path,encoded(project)),(project_view,render_project(project).encode()),(feature_path,encoded(feature)),(feature_view,render_feature(feature,project).encode()),(completion,encoded(completion_value))]
  if len({path for path,_ in targets})!=len(targets) or completion.exists(): raise ValueError("promotion target collision or already-consumed intake")
  plan_hash=sha(plan_path); txid=transaction_id(plan_hash,a.approved_by,a.approved_at); txroot=root/".starter-harness/feature-spec-promotion-transactions"; txdir=target_path(root,f".starter-harness/feature-spec-promotion-transactions/{txid}","promotion transaction"); journal=txdir/"transaction.json"
  if txroot.is_symlink() or txdir.exists(): raise ValueError("promotion transaction already exists or is unsafe")
  txdir.mkdir(parents=True); records=[]
  for index,(path,after) in enumerate(targets):
   before_hash=current_hash(path); backup=None
   if before_hash is not None: backup=f"backup-{index}"; atomic_write_bytes(path.read_bytes(),txdir/backup)
   records.append({"path":path.relative_to(root).as_posix(),"beforeSha256":before_hash,"backup":backup,"afterSha256":hashlib.sha256(after).hexdigest()})
  # Close the backup-to-journal race before declaring the transaction prepared.
  if any(current_hash(path)!=record["beforeSha256"] for (path,_),record in zip(targets,records)): raise ValueError("promotion target changed while preparing backups")
  transaction={"featureSpecPromotionTransactionVersion":2,"transactionId":txid,"target":str(root),"plan":{"path":plan_path.relative_to(root).as_posix(),"sha256":plan_hash},"approval":{"approvedBy":a.approved_by,"approvedAt":a.approved_at},"targets":records,"state":"PREPARED","rollbackErrors":[]}; atomic_write_bytes(encoded(transaction),journal); transaction["state"]="APPLYING"; atomic_write_bytes(encoded(transaction),journal)
  try:
   for (path,after),record in zip(targets,records):
    if current_hash(path)!=record["beforeSha256"]: raise OSError(f"{path}: changed immediately before promotion write")
    path.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(after,path)
  except BaseException as write_error:
   rollback_errors=[]
   for record in reversed(records):
    try:
     path=target_path(root,record["path"],"rollback target"); current=current_hash(path)
     if current==record["afterSha256"]:
      if record["backup"]: atomic_write_bytes((txdir/record["backup"]).read_bytes(),path)
      else: path.unlink()
     elif current!=record["beforeSha256"]: raise OSError("target drifted during rollback")
    except (OSError,ValueError) as error: rollback_errors.append(f"{record['path']}: {error}")
   transaction["state"]="ROLLBACK_INCOMPLETE" if rollback_errors else "ROLLED_BACK"; transaction["rollbackErrors"]=rollback_errors; atomic_write_bytes(encoded(transaction),journal)
   if rollback_errors: raise RuntimeError("promotion failed and rollback is incomplete: "+"; ".join(rollback_errors)) from write_error
   raise OSError(f"promotion failed and was rolled back: {write_error}") from write_error
  transaction["state"]="COMMITTED"; transaction["rollbackErrors"]=[]; atomic_write_bytes(encoded(transaction),journal)
 except (OSError,ValueError,KeyError,TypeError,RuntimeError) as e: print(f"FEATURE_SPEC_PROMOTION_APPLIED: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_SPEC_PROMOTION_APPLIED: yes"); print("TRANSACTION_STATE: COMMITTED"); print("NEXT_WORKFLOW: DESIGN_ROUTING"); print("GIT_COMMIT_OR_PUSH: NOT_RUN"); return 0
if __name__=="__main__": sys.exit(main())
