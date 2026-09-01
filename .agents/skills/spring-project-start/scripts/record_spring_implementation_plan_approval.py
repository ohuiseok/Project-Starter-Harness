#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt, json, sys
from pathlib import Path
from record_spec_approval import atomic_write_bytes, encoded_json, read_expected
from render_spring_implementation_plan import render
from spring_implementation_plan import validate
from validate_feature_specs import approval_content_hash, load_object

def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--plan",required=True,type=Path); parser.add_argument("--target",required=True,type=Path); parser.add_argument("--expected-plan-hash",required=True); parser.add_argument("--approved-by",required=True); parser.add_argument("--approved-at",required=True); args=parser.parse_args()
    try:
        root=args.target.resolve(strict=True); plan_path=args.plan.resolve(strict=True)
        if not root.is_dir() or args.target.is_symlink() or root not in plan_path.parents or args.plan.is_symlink(): raise ValueError("target or plan is unsafe")
        if not args.approved_by.strip(): raise ValueError("approved-by is required")
        dt.datetime.fromisoformat(args.approved_at.replace("Z","+00:00")); original=args.plan.read_bytes(); source=load_object(args.plan)
        if source["status"]!="REVIEW_READY": raise ValueError("only a REVIEW_READY plan can be approved")
        blockers=validate(source,root)
        if blockers: raise ValueError("implementation plan is blocked: "+"; ".join(blockers))
        if approval_content_hash(source)!=args.expected_plan_hash: raise ValueError("implementation plan changed after user review")
        markdown=args.plan.with_suffix(".md"); markdown_original=render(source,blockers).encode(); read_expected(markdown,markdown_original,"implementation plan Markdown")
        approved=json.loads(json.dumps(source)); approved["status"]="APPROVED"; approved["approval"]={"status":"APPROVED","approvedBy":args.approved_by,"approvedAt":args.approved_at,"approvedContentSha256":None}; approved["approval"]["approvedContentSha256"]=approval_content_hash(approved)
        if validate(approved,root): raise ValueError("approved implementation plan is invalid")
        artifacts=[(args.plan,original,encoded_json(approved)),(markdown,markdown_original,render(approved,[]).encode())]; written=[]
        try:
            for path,before,after in artifacts: read_expected(path,before,str(path)); atomic_write_bytes(after,path); written.append((path,before,after))
        except (OSError,ValueError) as error:
            for path,before,after in reversed(written):
                if path.read_bytes()!=after: raise RuntimeError("approval rollback refused after external drift") from error
                atomic_write_bytes(before,path)
            raise
    except (OSError,ValueError,RuntimeError,KeyError) as error: print(f"SPRING_IMPLEMENTATION_PLAN_APPROVAL_VALID: no\nERROR: {error}"); return 1
    print("SPRING_IMPLEMENTATION_PLAN_APPROVAL_VALID: yes"); print("CODE_DRY_RUN_AUTHORIZED: yes"); print("TARGET_SOURCE_CHANGED: no"); return 0
if __name__=="__main__": sys.exit(main())
