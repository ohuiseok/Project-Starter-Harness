#!/usr/bin/env python3
"""Durably apply an exact CREATE/REUSE Spring code v2 review."""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,shutil,sys,tempfile
from pathlib import Path
from http_api_spring_mapping import reference
from spring_code_apply_v2 import BASELINE,MANAGED,ACTIVE,apply_lock,encoded,safe_path,sha,validate_approval
from validate_feature_specs import load_object
def fsync_dir(path:Path)->None:
 fd=os.open(path,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def managed_paths(root:Path,transaction_id:str)->tuple[Path,Path]:
 backup=root/MANAGED/"backups"/"spring-code-v2"/transaction_id
 journal=root/MANAGED/"transactions"/(transaction_id+".json")
 for path in (root/MANAGED,backup.parent,journal.parent):
  cursor=path
  while cursor!=root:
   if cursor.exists() and cursor.is_symlink():raise ValueError("managed transaction path is unsafe")
   cursor=cursor.parent
 return backup,journal
def durable_json(value:dict,path:Path)->None:
 path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix=".starter-harness-stage-",dir=path.parent)
 try:
  with os.fdopen(fd,"wb") as handle:handle.write(encoded(value));handle.flush();os.fsync(handle.fileno())
  os.replace(name,path);fsync_dir(path.parent)
 finally:
  if os.path.exists(name):os.unlink(name)
def atomic_file(content:bytes,mode:int,path:Path)->None:
 fd,name=tempfile.mkstemp(prefix=".starter-harness-stage-",dir=path.parent)
 try:
  with os.fdopen(fd,"wb") as handle:handle.write(content);handle.flush();os.fsync(handle.fileno())
  os.chmod(name,mode);os.replace(name,path);fsync_dir(path.parent)
 finally:
  if os.path.exists(name):os.unlink(name)
def backup_manifest(backup:Path)->dict:
 files={}
 for path in sorted(backup.rglob("*")):
  if path.is_symlink():raise ValueError("backup contains a symlink")
  if path.is_file() and path.name!="backup-manifest.json":files[path.relative_to(backup).as_posix()]={"sha256":sha(path),"mode":path.stat().st_mode&0o777}
 return {"springCodeBackupManifestV2Version":1,"files":files}
def verify_backup(backup:Path)->dict:
 path=backup/"backup-manifest.json";value=load_object(path)
 if value!=backup_manifest(backup):raise ValueError("backup manifest changed")
 return value
def result_document(record:dict)->dict:
 return {"springCodeApplyResultV2Version":1,"state":"APPLIED_PREVERIFIED","transactionId":record["transactionId"],"review":record["review"],"approval":record["approval"],"verification":record["verification"],"target":record["target"],"createsApplied":record["appliedFiles"],"reusesUnchanged":record["reuses"],"baseline":{"path":BASELINE,"sha256":record["baselineAfterSha256"]},"backup":{"path":record["backup"],"manifestSha256":record["backupManifestSha256"]},"postApplyVerification":"NOT_RUN","effects":{"testsExecuted":False,"network":"NOT_USED","docker":"NOT_USED","gitCommitOrPush":"NOT_RUN"},"committedAt":record["committedAt"]}
def validate_final(root:Path,record:dict)->None:
 for item in record["creates"]:
  path=root/item["path"]
  if path.is_symlink() or not path.is_file() or sha(path)!=item["sha256"] or path.stat().st_mode&0o777!=item["mode"]:raise ValueError("applied file evidence changed: "+item["path"])
 baseline=root/BASELINE
 if baseline.is_symlink() or not baseline.is_file() or sha(baseline)!=record["baselineAfterSha256"]:raise ValueError("applied baseline evidence changed")
def write_result(root:Path,record:dict)->None:
 path=root/record["resultPath"]
 if path.exists() or path.is_symlink():raise ValueError("apply result path is occupied")
 if not path.parent.is_dir() or path.parent.is_symlink():raise ValueError("apply result parent is unsafe")
 atomic_file(encoded(result_document(record)),0o644,path)
def rollback(root:Path,record:dict,journal:Path)->dict:
 record["state"]="ROLLING_BACK";durable_json(record,journal);errors=[];baseline=root/BASELINE
 try:
  if baseline.exists():
   if record.get("baselineAfterSha256") and sha(baseline)==record["baselineAfterSha256"]:
    if record["baselineBefore"]:
     source=root/record["backup"]/"previous-baseline.json";atomic_file(source.read_bytes(),source.stat().st_mode&0o777,baseline)
    else:baseline.unlink();fsync_dir(root)
   elif record["baselineBefore"] and sha(baseline)==record["baselineBefore"]["sha256"]:pass
   else:raise OSError("baseline drifted")
 except OSError as e:errors.append(f"baseline: {e}")
 for item in reversed(record["creates"]):
  path=root/item["path"]
  try:
   if not path.exists():continue
   if path.is_symlink() or not path.is_file() or sha(path)!=item["sha256"] or path.stat().st_mode&0o777!=item["mode"]:raise OSError("created file drifted")
   path.unlink();fsync_dir(path.parent)
  except OSError as e:errors.append(f"{item['path']}: {e}")
 parent_candidates=list(record["createdParents"])
 if record.get("currentParent") and record["currentParent"] not in parent_candidates:parent_candidates.append(record["currentParent"])
 for relative in reversed(parent_candidates):
  path=root/relative
  try:
   if path.exists():path.rmdir();fsync_dir(path.parent)
  except OSError as e:errors.append(f"{relative}: {e}")
 record["state"]="ROLLBACK_INCOMPLETE" if errors else "ROLLED_BACK";record["rollbackErrors"]=errors;durable_json(record,journal)
 return record
def apply(root:Path,review_path:Path,approval_path:Path)->dict:
 with apply_lock(root):
  validate_approval(root,approval_path,review_path,True);review=load_object(review_path);dry=load_object(root/review["dryRun"]["path"]);transaction_id=review["transactionId"]
  backup,journal=managed_paths(root,transaction_id)
  if backup.relative_to(root).as_posix()!=review["backup"]["path"] or journal.relative_to(root).as_posix()!=review["journal"]["path"]:raise ValueError("managed transaction paths are invalid")
  if journal.exists() or backup.exists():raise ValueError("transaction journal or backup already exists")
  result_path=root/review["result"]["path"]
  if result_path.exists() or result_path.is_symlink():raise ValueError("apply result path is occupied")
  creates=review["fileActions"]["creates"];content={i["path"]:i["content"].encode() for i in dry["generatedFiles"]}
  for item in creates:
   if hashlib.sha256(content[item["path"]]).hexdigest()!=item["sha256"]:raise ValueError("approved candidate content changed")
  backup.mkdir(parents=True);fsync_dir(backup.parent)
  try:
   evidence=[review_path,review_path.with_suffix(".md"),approval_path,root/review["verification"]["path"],root/review["dryRun"]["path"]]
   for source in evidence:shutil.copy2(source,backup/source.name)
   baseline=root/BASELINE;before=reference(baseline,root) if baseline.exists() else None
   if baseline.exists():shutil.copy2(baseline,backup/"previous-baseline.json")
   manifest=backup_manifest(backup);durable_json(manifest,backup/"backup-manifest.json");manifest_sha=sha(backup/"backup-manifest.json")
  except Exception:
   shutil.rmtree(backup);fsync_dir(backup.parent);raise
  record={"springCodeTransactionV2Version":1,"transactionId":transaction_id,"state":"PREPARED","target":str(root),"review":reference(review_path,root),"approval":reference(approval_path,root),"verification":review["verification"],"dryRun":review["dryRun"],"creates":creates,"reuses":review["fileActions"]["reuses"],"createdParents":[],"currentParent":None,"currentFile":None,"appliedFiles":[],"baselineBefore":before,"baselineAfterSha256":review["desiredBaseline"]["sha256"],"backup":review["backup"]["path"],"backupManifestSha256":manifest_sha,"resultPath":review["result"]["path"],"committedAt":None,"rollbackErrors":[]};journal.parent.mkdir(parents=True,exist_ok=True);durable_json(record,journal)
  try:
   verify_backup(backup);record["state"]="APPLYING";durable_json(record,journal)
   for relative in review["parentDirectories"]:
    path=root/relative
    if not path.exists():
     record["currentParent"]=relative;durable_json(record,journal);path.mkdir();fsync_dir(path.parent)
     record["createdParents"].append(relative);record["currentParent"]=None;durable_json(record,journal)
   for item in creates:
    path=root/safe_path(item["path"],".java");record["currentFile"]=item["path"];durable_json(record,journal)
    if path.exists() or path.is_symlink():raise ValueError("CREATE target became occupied: "+item["path"])
    atomic_file(content[item["path"]],item["mode"],path)
    if sha(path)!=item["sha256"] or path.stat().st_mode&0o777!=item["mode"]:raise ValueError("CREATE verification failed: "+item["path"])
    record["appliedFiles"].append(item["path"]);record["currentFile"]=None;durable_json(record,journal)
   if before:
    if not baseline.is_file() or baseline.is_symlink() or reference(baseline,root)!=before:raise ValueError("baseline changed before replacement")
   elif baseline.exists() or baseline.is_symlink():raise ValueError("baseline appeared before replacement")
   atomic_file(encoded(review["desiredBaseline"]["document"]),0o644,baseline);record["state"]="BASELINE_WRITTEN";durable_json(record,journal);validate_final(root,record);record["state"]="COMMITTED";record["committedAt"]=dt.datetime.now(dt.timezone.utc).isoformat();durable_json(record,journal)
  except Exception as error:
   rolled=rollback(root,record,journal)
   if rolled["state"]=="ROLLBACK_INCOMPLETE":raise RuntimeError("apply failed and rollback is incomplete: "+str(error))
   raise ValueError("apply failed and was rolled back: "+str(error))
  try:write_result(root,record)
  except Exception:
   record["state"]="COMMITTED_REPORT_PENDING";durable_json(record,journal);return record
  return record
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--review",required=True,type=Path);p.add_argument("--approval",required=True,type=Path);p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:record=apply(a.target.resolve(strict=True),a.review.resolve(strict=True),a.approval.resolve(strict=True))
 except (OSError,ValueError,RuntimeError,KeyError,TypeError) as e:print(f"SPRING_CODE_APPLY_V2_VALID: no\nERROR: {e}",file=sys.stderr);return 1
 print(f"SPRING_CODE_APPLY_V2_VALID: yes\nTRANSACTION_STATE: {record['state']}\nAPPLICATION_STATE: {'APPLIED_PREVERIFIED' if record['state'] in {'COMMITTED','COMMITTED_REPORT_PENDING'} else 'UNKNOWN'}\nPOST_APPLY_VERIFICATION: NOT_RUN\nGIT_COMMIT_OR_PUSH: NOT_RUN");return 0
if __name__=="__main__":sys.exit(main())
