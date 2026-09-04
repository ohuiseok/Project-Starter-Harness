#!/usr/bin/env python3
"""Record exact Spring code apply approval without asking users to handle hashes."""
from __future__ import annotations
import argparse,datetime as dt,sys
from pathlib import Path
from apply_approved_generation import atomic_json
from apply_approved_spring_code import dirty_paths, validate_target_changes
from run_spring_code_verification import target_context_hash, validate_verification_report
from spring_code_dry_run import canonical_baseline, sha, validate_report
from validate_feature_specs import load_object

def main()->int:
    p=argparse.ArgumentParser()
    for name in ("dry-run","verification-report","target","output"): p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--expected-verification-hash",required=True); p.add_argument("--approved-by",required=True); p.add_argument("--approved-at",required=True); a=p.parse_args()
    try:
        root=a.target.resolve(strict=True); dry_path=a.dry_run.resolve(strict=True); verification_path=a.verification_report.resolve(strict=True); output=a.output.resolve(strict=False)
        if a.target.is_symlink() or any(root not in path.parents for path in (dry_path,verification_path,output)) or a.dry_run.is_symlink() or a.verification_report.is_symlink() or a.output.is_symlink() or output.exists(): raise ValueError("apply approval paths are unsafe or output exists")
        if sha(verification_path)!=a.expected_verification_hash: raise ValueError("verification report changed after user review")
        dry=load_object(dry_path); validate_report(dry,root); verification=load_object(verification_path); validate_verification_report(verification,verification_path,root)
        if verification["result"]["state"]!="PASSED" or verification["readyForApplyApproval"] is not True: raise ValueError("verification is not ready for apply approval")
        if verification["dryRun"]!={"path":dry_path.relative_to(root).as_posix(),"sha256":sha(dry_path)}: raise ValueError("verification and dry run do not match")
        generated=set(dry["plannedChanges"]["desiredManifest"]["files"])
        if target_context_hash(root,generated)!=verification["targetContextSha256"]: raise ValueError("target context changed after verification")
        validate_target_changes(root,dry["plannedChanges"]); dirty=dirty_paths(root); build_names={"build.gradle","build.gradle.kts","settings.gradle","settings.gradle.kts","gradle.properties","pom.xml","gradlew","mvnw"}
        overlap=sorted(path for path in dirty if path in generated or path.startswith("src/") or Path(path).name in build_names)
        if overlap: raise ValueError("relevant Git changes block apply approval: "+", ".join(overlap))
        _,baseline_ref,_,_=canonical_baseline(root); timestamp=dt.datetime.fromisoformat(a.approved_at.replace("Z","+00:00"))
        if not a.approved_by.strip() or timestamp.utcoffset() is None: raise ValueError("approval identity and timezone-aware time are required")
        approval={"springCodeApplyApprovalVersion":1,"approved":True,"verificationReportSha256":sha(verification_path),"dryRunReportSha256":sha(dry_path),"target":str(root),"targetContextSha256":verification["targetContextSha256"],"baselineSha256":baseline_ref["sha256"] if baseline_ref else None,"files":sorted(generated),"approvedBy":a.approved_by,"approvedAt":a.approved_at}
        output.parent.mkdir(parents=True,exist_ok=True); atomic_json(approval,output)
    except (OSError,ValueError,KeyError) as error: print(f"SPRING_CODE_APPLY_APPROVAL_VALID: no\nERROR: {error}",file=sys.stderr); return 1
    print("SPRING_CODE_APPLY_APPROVAL_VALID: yes"); print("SOURCE_APPLIED: no"); print("GIT_COMMIT_OR_PUSH: NOT_RUN"); return 0
if __name__=="__main__": sys.exit(main())
