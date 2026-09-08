#!/usr/bin/env python3
"""Cancel an active feature-spec intake without deleting its evidence."""
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
from continuation_route import sanitize
from feature_draft_chain import head,load_context
from spring_milestone_completion import sha
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--intake",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--reason",required=True); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); intake=a.intake.resolve(strict=True)
  if root not in intake.parents or intake.is_symlink(): raise ValueError("cancellation path is unsafe")
  _,receipt,_=load_context(root,intake); current,current_ref=head(root,receipt); reason=sanitize(a.reason); directory=root/".starter-harness/continuation-cancellations"
  if (root/".starter-harness").is_symlink() or directory.is_symlink(): raise ValueError("cancellation evidence directory is unsafe")
  directory.mkdir(parents=True,exist_ok=True); output=directory/f"{sha(intake)}.json"; value={"featureSpecIntakeCancellationVersion":1,"intake":{"path":intake.relative_to(root).as_posix(),"sha256":sha(intake)},"latestDraft":current_ref,"reason":reason,"state":"CANCELLED"}; payload=(json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode(); fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,"wb") as stream: stream.write(payload); stream.flush(); os.fsync(stream.fileno())
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"FEATURE_SPEC_INTAKE_CANCELLATION_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("FEATURE_SPEC_INTAKE_CANCELLATION_VALID: yes"); print("STATE: CANCELLED"); print("EVIDENCE_DELETED: no"); return 0
if __name__=="__main__": sys.exit(main())
