#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from post_apply_verification import cache_info,command,context_sha,render
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--completion",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--view",required=True,type=Path); p.add_argument("--timeout-seconds",type=int,default=600); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); completion=a.completion.resolve(strict=True); output=a.output.resolve(strict=False); view=a.view.resolve(strict=False)
  if a.target.is_symlink() or any(root not in p.parents for p in (completion,output,view)) or output.exists() or view.exists(): raise ValueError("plan paths are unsafe or already exist")
  report=load_object(completion)
  if report.get("state")!="APPLIED_PREVERIFIED" or not 30<=a.timeout_seconds<=1800: raise ValueError("completion or timeout is not ready")
  cache=cache_info(root); plan={"postApplyVerificationPlanVersion":1,"target":str(root),"completion":{"path":completion.relative_to(root).as_posix(),"sha256":sha(completion)},"targetContextSha256":context_sha(root),"command":command(root),"dependencyCache":cache,"effects":{"network":"DISABLED","dockerSocket":"HIDDEN","targetSource":"TEMP_COPY_MONITORED","buildOutputs":"TEMPORARY","database":"NOT_STARTED","ports":"NOT_PUBLISHED"},"limits":{"timeoutSeconds":a.timeout_seconds,"maxOutputCharacters":20000},"readyForApproval":cache["status"]=="READY"}
  plan_bytes=(json.dumps(plan,ensure_ascii=False,indent=2)+"\n").encode(); view_bytes=render(plan,report).encode(); output.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(plan_bytes,output)
  try: atomic_write_bytes(view_bytes,view)
  except BaseException:
   if output.read_bytes()==plan_bytes: output.unlink()
   raise
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"POST_APPLY_PLAN_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("POST_APPLY_PLAN_VALID: yes"); print(f"READY_FOR_APPROVAL: {'yes' if plan['readyForApproval'] else 'no'}"); return 0
if __name__=="__main__": sys.exit(main())
