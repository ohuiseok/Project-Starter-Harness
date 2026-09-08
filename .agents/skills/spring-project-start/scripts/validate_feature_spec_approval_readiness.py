#!/usr/bin/env python3
"""Revalidate an exact feature-spec approval readiness report and view."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from feature_draft_chain import head,load_context
from prepare_feature_spec_approval import readiness,render
from spring_milestone_completion import sha
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--intake",required=True,type=Path); p.add_argument("--report",required=True,type=Path); p.add_argument("--view",required=True,type=Path); p.add_argument("--target",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); intake=a.intake.resolve(strict=True); report=a.report.resolve(strict=True); view=a.view.resolve(strict=True)
  if any(root not in path.parents or path.is_symlink() for path in (intake,report,view)): raise ValueError("readiness validation paths are unsafe")
  intake_value,receipt,_=load_context(root,intake); draft_path,draft_ref=head(root,receipt); spec=load_object(draft_path); blockers=readiness(spec); expected={"featureSpecApprovalReadinessVersion":1,"intake":{"path":intake.relative_to(root).as_posix(),"sha256":sha(intake)},"draft":draft_ref,"projectBrief":intake_value["projectBrief"],"progress":intake_value["progress"],"featureId":spec["feature"]["id"],"blockers":blockers,"state":"READY_FOR_SPEC_APPROVAL" if not blockers else "AWAITING_USER_DECISIONS"}
  if load_object(report)!=expected or view.read_text()!=render(spec,blockers): raise ValueError("readiness report or view is stale or inconsistent")
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"FEATURE_SPEC_APPROVAL_READINESS_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_SPEC_APPROVAL_READINESS_VALID: yes"); print(f"STATE: {expected['state']}"); return 0 if not blockers else 1
if __name__=="__main__": sys.exit(main())
