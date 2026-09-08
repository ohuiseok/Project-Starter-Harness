#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,json,shutil,subprocess,sys,tempfile
from pathlib import Path
from post_apply_verification import context_sha,validate_approval,validate_plan
from run_spring_code_verification import result_state
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--plan",required=True,type=Path); p.add_argument("--approval",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); plan_path=a.plan.resolve(strict=True); approval_path=a.approval.resolve(strict=True); output=a.output.resolve(strict=False)
  if a.target.is_symlink() or any(root not in p.parents for p in (plan_path,approval_path,output)) or output.exists(): raise ValueError("verification paths are unsafe or output exists")
  plan=load_object(plan_path); validate_plan(plan,plan_path,root); approval=load_object(approval_path)
  validate_approval(approval,plan_path,root)
  if shutil.which("bwrap") is None: raise ValueError("bubblewrap is required")
  with tempfile.TemporaryDirectory(prefix="post-apply-verification-",dir="/var/tmp") as temporary:
   workspace=Path(temporary)/"workspace"; shutil.copytree(root,workspace,symlinks=True,ignore=shutil.ignore_patterns(".git",".starter-harness",".gradle","build","target"))
   links=[p for p in workspace.rglob("*") if p.is_symlink()]
   if links: raise ValueError("symbolic links are not allowed in verification copy")
   before=context_sha(workspace)
   home=Path(temporary)/"home"; home.mkdir(); command=["bwrap","--die-with-parent","--unshare-net","--ro-bind","/","/","--dev","/dev","--proc","/proc","--tmpfs","/tmp","--tmpfs","/run","--bind",str(workspace),str(workspace),"--chdir",str(workspace),"--setenv","HOME",str(home),"--setenv","GRADLE_USER_HOME",str(home/".gradle"),"--setenv","DOCKER_HOST","unix:///run/no-docker.sock","--",*plan["command"]]
   try: done=subprocess.run(command,capture_output=True,text=True,timeout=plan["limits"]["timeoutSeconds"],check=False); exit_code=done.returncode; text=(done.stdout+done.stderr)[-plan["limits"]["maxOutputCharacters"]:]; state=result_state(exit_code,text)
   except subprocess.TimeoutExpired as e: exit_code=124; text=((e.stdout or "")+(e.stderr or ""))[-plan["limits"]["maxOutputCharacters"]:]; state="FAILED"
   if context_sha(workspace)!=before: raise ValueError("verification command changed source or build context in the temporary copy")
  if context_sha(root)!=plan["targetContextSha256"]: raise ValueError("target changed during verification")
  report={"postApplyVerificationReportVersion":1,"plan":{"path":plan_path.relative_to(root).as_posix(),"sha256":sha(plan_path)},"approval":{"path":approval_path.relative_to(root).as_posix(),"sha256":sha(approval_path)},"target":str(root),"targetContextSha256":plan["targetContextSha256"],"command":plan["command"],"isolation":plan["effects"],"result":{"state":state,"exitCode":exit_code,"output":text},"verifiedAt":dt.datetime.now(dt.timezone.utc).isoformat(),"readyForFinalization":state=="PASSED"}; output.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode(),output)
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"POST_APPLY_VERIFICATION_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("POST_APPLY_VERIFICATION_VALID: yes"); print(f"VERIFICATION_RESULT: {state}"); print(f"READY_FOR_FINALIZATION: {'yes' if state=='PASSED' else 'no'}"); return 0
if __name__=="__main__": sys.exit(main())
