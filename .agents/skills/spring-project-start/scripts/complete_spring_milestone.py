#!/usr/bin/env python3
"""Atomically record verified milestone completion and update project progress."""
from __future__ import annotations
import argparse,datetime as dt,json,sys
from pathlib import Path
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import build_completion,build_progress,render_progress,validate_progress
from validate_feature_specs import load_object

def encoded(value:dict)->bytes: return (json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode()

def main()->int:
    p=argparse.ArgumentParser()
    for name in ("project-brief","feature","dry-run","verification-report","target","output"): p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--transaction-id",required=True); p.add_argument("--completed-at",required=True); a=p.parse_args()
    try:
        root=a.target.resolve(strict=True); output=a.output.resolve(strict=False); canonical_json=root/"docs/progress.json"; canonical_md=root/"docs/progress.md"
        paths=(a.project_brief.resolve(strict=True),a.feature.resolve(strict=True),a.dry_run.resolve(strict=True),a.verification_report.resolve(strict=True),output,canonical_json,canonical_md)
        if a.target.is_symlink() or any(root not in path.parents for path in paths) or any(path.is_symlink() for path in paths) or output.exists(): raise ValueError("completion paths are unsafe or output exists")
        timestamp=dt.datetime.fromisoformat(a.completed_at.replace("Z","+00:00"))
        if timestamp.utcoffset() is None: raise ValueError("completed-at must include a timezone")
        completion=build_completion(root,a.transaction_id,a.project_brief,a.feature,a.dry_run,a.verification_report,a.completed_at); completion_bytes=encoded(completion)
        completion_ref={"path":output.relative_to(root).as_posix(),"sha256":__import__("hashlib").sha256(completion_bytes).hexdigest()}
        previous_json=canonical_json.read_bytes() if canonical_json.exists() else None; previous_md=canonical_md.read_bytes() if canonical_md.exists() else None
        existing=None
        if previous_json is not None:
            existing=load_object(canonical_json); validate_progress(existing,root)
            if previous_md is None or previous_md.decode()!=render_progress(existing): raise ValueError("existing progress Markdown is missing or independently changed")
        elif previous_md is not None: raise ValueError("progress Markdown exists without its structured ledger")
        project=load_object(a.project_brief); progress=build_progress(existing,project,completion,completion_ref,root); progress_bytes=encoded(progress); markdown_bytes=render_progress(progress).encode()
        artifacts=[(output,None,completion_bytes),(canonical_json,previous_json,progress_bytes),(canonical_md,previous_md,markdown_bytes)]; written=[]
        try:
            for path,before,after in artifacts:
                if (path.read_bytes() if path.exists() else None)!=before: raise ValueError(f"completion output changed before write: {path}")
                path.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(after,path); written.append((path,before,after))
        except (OSError,ValueError) as error:
            for path,before,after in reversed(written):
                if path.read_bytes()!=after: raise RuntimeError("completion rollback refused after external drift") from error
                if before is None: path.unlink()
                else: atomic_write_bytes(before,path)
            raise
    except (OSError,ValueError,RuntimeError,KeyError) as error: print(f"SPRING_MILESTONE_COMPLETION_VALID: no\nERROR: {error}",file=sys.stderr); return 1
    print("SPRING_MILESTONE_COMPLETION_VALID: yes"); print("MILESTONE_STATE: APPLIED_AND_VERIFIED"); print(f"NEXT_FEATURE: {progress['current']['recommendedFeatureId'] or 'NONE'}"); print("GIT_COMMIT_OR_PUSH: NOT_RUN"); return 0
if __name__=="__main__": sys.exit(main())
