#!/usr/bin/env python3
"""Journal and atomically replace verified milestone progress artifacts."""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,secrets,sys
from pathlib import Path
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import build_completion,build_progress,render_progress,target_path,validate_progress
from validate_feature_specs import load_object

MANAGED=".starter-harness/milestone-completion-transactions"
ACTIVE={"PREPARED","APPLYING"}

def encoded(value:dict)->bytes: return (json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode()
def digest_bytes(value:bytes)->str: return hashlib.sha256(value).hexdigest()

def migrate_progress(value:dict)->dict:
    if isinstance(value,dict) and value.get("progressVersion")==1 and "blockedCandidates" not in value:
        value=dict(value); value["blockedCandidates"]=[]
    return value

def journal_path(root:Path,transaction_id:str)->Path:
    if not transaction_id or "/" in transaction_id or transaction_id in {".",".."}: raise ValueError("completion transaction ID is invalid")
    return target_path(root,f"{MANAGED}/{transaction_id}/transaction.json","completion transaction")

def pending_transactions(root:Path)->list[Path]:
    directory=target_path(root,MANAGED,"completion transaction directory")
    if not directory.exists(): return []
    if not directory.is_dir(): raise ValueError("completion transaction directory is unsafe")
    pending=[]
    for record in directory.glob("*/transaction.json"):
        if record.is_symlink(): raise ValueError("completion transaction record is unsafe")
        if load_object(record).get("state") in ACTIVE: pending.append(record)
    return pending

def recover(root:Path,transaction_id:str)->dict:
    record_path=journal_path(root,transaction_id); record=load_object(record_path)
    if not isinstance(record,dict) or record.get("version")!=1 or record.get("transactionId")!=transaction_id or record.get("state") not in ACTIVE or Path(str(record.get("target",""))).resolve()!=root: raise ValueError("completion transaction is not recoverable")
    backup=record_path.parent/"before"; errors=[]
    for item in reversed(record.get("artifacts",[])):
        try:
            destination=target_path(root,item["path"],"completion artifact"); current=destination.read_bytes() if destination.exists() else None
            current_sha=digest_bytes(current) if current is not None else None
            if current_sha==item["beforeSha256"]: continue
            if current_sha!=item["afterSha256"]: raise OSError("artifact drifted; recovery overwrite refused")
            if item["beforeSha256"] is None: destination.unlink()
            else:
                source=backup/item["path"]
                if source.is_symlink() or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=item["beforeSha256"]: raise OSError("backup evidence changed")
                atomic_write_bytes(source.read_bytes(),destination)
        except (OSError,ValueError,KeyError) as error: errors.append(f"{item.get('path','UNKNOWN')}: {error}")
    record["state"]="RECOVERY_FAILED" if errors else "RECOVERED"; record["recoveryErrors"]=errors
    atomic_write_bytes(encoded(record),record_path)
    if errors: raise ValueError("completion recovery was incomplete: "+"; ".join(errors))
    return record

def main()->int:
    p=argparse.ArgumentParser()
    for name in ("project-brief","feature","dry-run","verification-report","target","output"): p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--transaction-id",required=True); p.add_argument("--completed-at",required=True); a=p.parse_args()
    try:
        root=a.target.resolve(strict=True)
        if a.target.is_symlink() or not root.is_dir(): raise ValueError("target is unsafe")
        pending=pending_transactions(root)
        if pending: raise ValueError(f"interrupted completion transaction requires recovery: {pending[0].parent.name}")
        output=a.output.resolve(strict=False); canonical_json=target_path(root,"docs/progress.json","progress ledger"); canonical_md=target_path(root,"docs/progress.md","progress view")
        paths=(a.project_brief.resolve(strict=True),a.feature.resolve(strict=True),a.dry_run.resolve(strict=True),a.verification_report.resolve(strict=True),output)
        if any(root not in path.parents for path in paths) or any(path.is_symlink() for path in paths) or output.exists(): raise ValueError("completion paths are unsafe or output exists")
        timestamp=dt.datetime.fromisoformat(a.completed_at.replace("Z","+00:00"))
        if timestamp.utcoffset() is None: raise ValueError("completed-at must include a timezone")
        completion=build_completion(root,a.transaction_id,a.project_brief,a.feature,a.dry_run,a.verification_report,a.completed_at); completion_bytes=encoded(completion)
        completion_ref={"path":output.relative_to(root).as_posix(),"sha256":digest_bytes(completion_bytes)}
        previous_json=canonical_json.read_bytes() if canonical_json.exists() else None; previous_md=canonical_md.read_bytes() if canonical_md.exists() else None; existing=None
        if previous_json is not None:
            existing=migrate_progress(load_object(canonical_json)); validate_progress(existing,root)
            if previous_md is None or previous_md.decode()!=render_progress(existing): raise ValueError("existing progress Markdown is missing or independently changed")
        elif previous_md is not None: raise ValueError("progress Markdown exists without its structured ledger")
        project=load_object(a.project_brief); progress=build_progress(existing,project,completion,completion_ref,root)
        artifacts=[(output,None,completion_bytes),(canonical_json,previous_json,encoded(progress)),(canonical_md,previous_md,render_progress(progress).encode())]
        transaction_id=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-")+secrets.token_hex(4); record_path=journal_path(root,transaction_id); backup=record_path.parent/"before"
        artifact_records=[]
        for path,before,after in artifacts:
            relative=path.relative_to(root).as_posix(); artifact_records.append({"path":relative,"beforeSha256":digest_bytes(before) if before is not None else None,"afterSha256":digest_bytes(after)})
            if before is not None:
                destination=backup/relative; destination.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(before,destination)
        record={"version":1,"transactionId":transaction_id,"state":"PREPARED","target":str(root),"artifacts":artifact_records}
        record_path.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(encoded(record),record_path); record["state"]="APPLYING"; atomic_write_bytes(encoded(record),record_path)
        try:
            for path,before,after in artifacts:
                if (path.read_bytes() if path.exists() else None)!=before: raise ValueError(f"completion output changed before write: {path}")
                path.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(after,path)
            record["state"]="COMMITTED"; record["completedAt"]=a.completed_at; atomic_write_bytes(encoded(record),record_path)
        except Exception as error:
            try: recover(root,transaction_id)
            except ValueError as recovery_error: raise RuntimeError(f"completion failed and recovery was incomplete: {recovery_error}") from error
            raise ValueError(f"completion failed and was rolled back: {error}") from error
    except (OSError,ValueError,RuntimeError,KeyError,TypeError) as error: print(f"SPRING_MILESTONE_COMPLETION_VALID: no\nERROR: {error}",file=sys.stderr); return 1
    print("SPRING_MILESTONE_COMPLETION_VALID: yes"); print("MILESTONE_STATE: APPLIED_PREVERIFIED"); print(f"NEXT_FEATURE: {progress['current']['recommendedFeatureId'] or 'NONE'}"); print("GIT_COMMIT_OR_PUSH: NOT_RUN"); return 0
if __name__=="__main__": sys.exit(main())
