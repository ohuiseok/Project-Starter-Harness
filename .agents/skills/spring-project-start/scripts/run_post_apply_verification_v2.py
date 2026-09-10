#!/usr/bin/env python3
"""Run one approved post-apply command in a networkless disposable workspace."""
from __future__ import annotations
import argparse,datetime as dt,json,os,re,shutil,signal,subprocess,sys,tempfile,time
from pathlib import Path
from apply_approved_spring_code_v2 import durable_json,fsync_dir
from discover_http_api_evidence import atomic_create
from http_api_spring_mapping import reference
from post_apply_verification_v2 import JOURNAL,manifest,validate_approval,validate_plan
from run_spring_code_verification_v2 import PII,SECRET,copy_cache,process_start_ticks,sandbox
from spring_code_apply_v2 import MANAGED,apply_lock,sha
from spring_code_verification_v2 import git_state
from validate_feature_specs import load_object
def terminate(process:subprocess.Popen,grace:int)->bool:
 if process.poll() is not None:return True
 os.killpg(process.pid,signal.SIGTERM)
 try:process.wait(timeout=grace);return True
 except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait();return process.poll() is not None
def classify(code:int,text:str,timed_out:bool,redacted:bool)->tuple[str,str]:
 if redacted:return "UNKNOWN","SENSITIVE_OUTPUT"
 if timed_out:return "UNKNOWN","TIMEOUT"
 if code==0:return "VERIFIED","TESTS_PASSED"
 if any(i in text for i in ("Could not resolve","Unknown host","No cached version")):return "UNKNOWN","OFFLINE_DEPENDENCY_OR_INFRASTRUCTURE"
 if any(i in text for i in ("Compilation failed","cannot find symbol",":compileJava FAILED")):return "FAILED","COMPILATION_FAILURE"
 if "ApplicationContext" in text:return "FAILED","SPRING_CONTEXT_FAILURE"
 return "FAILED","TEST_OR_BUILD_FAILURE"
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan",required=True,type=Path);p.add_argument("--approval",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args();journal_path=None;temporary=None
 try:
  root=a.target.resolve(strict=True);plan_path=a.plan.resolve(strict=True);approval_path=a.approval.resolve(strict=True);output=a.output.resolve();journal_path=root/JOURNAL
  with apply_lock(root):
   if output.exists() or root not in output.parents or output.relative_to(root).parts[0]!="docs" or journal_path.exists():raise ValueError("verification output is occupied or recovery is required")
   plan=load_object(plan_path);validate_plan(plan,plan_path,root);validate_approval(root,approval_path,plan_path);snapshot=manifest(root);paths=set(snapshot["files"])
   temporary=Path(tempfile.mkdtemp(prefix="post-apply-v2-",dir="/var/tmp"));workspace=temporary/"workspace";home=temporary/"home";workspace.mkdir();home.mkdir();marker=temporary/".starter-harness-post-apply-v2.json";marker.write_text(json.dumps({"target":str(root),"planSha256":sha(plan_path)}))
   shutil.copytree(root,workspace,dirs_exist_ok=True,symlinks=True,ignore=shutil.ignore_patterns(".git",MANAGED,".gradle","build","target"))
   if any(i.is_symlink() for i in workspace.rglob("*")):raise ValueError("symbolic links are not allowed in verification copy")
   copy_cache(plan["dependencyCache"]["kind"],home,plan["dependencyCache"]);cmd=plan["command"];argv=[cmd["executable"],*cmd["arguments"]];started=dt.datetime.now(dt.timezone.utc).isoformat();journal={"postApplyVerificationV2JournalVersion":1,"state":"PREPARED","plan":reference(plan_path,root),"approval":reference(approval_path,root),"output":output.relative_to(root).as_posix(),"temporaryRoot":str(temporary),"temporaryMarkerSha256":sha(marker),"pid":None,"processStartTicks":None};durable_json(journal,journal_path)
   process=subprocess.Popen(sandbox(workspace,home,argv),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
   try:journal.update(state="RUNNING",pid=process.pid,processStartTicks=process_start_ticks(process.pid));durable_json(journal,journal_path)
   except BaseException:terminate(process,plan["limits"]["termGraceSeconds"]);process.communicate();raise
   timed_out=False
   try:raw,_=process.communicate(timeout=plan["limits"]["timeoutSeconds"])
   except subprocess.TimeoutExpired:timed_out=True;terminate(process,plan["limits"]["termGraceSeconds"]);raw,_=process.communicate()
   code=124 if timed_out else process.returncode;text=raw.decode("utf-8","replace");text=re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]","",text);redacted=bool(SECRET.search(text) or PII.search(text));text=SECRET.sub("[REDACTED]",text);text=PII.sub("[REDACTED_PII]",text);raw_bytes=text.encode();truncated=len(raw_bytes)>plan["limits"]["maxLogBytes"]
   if truncated:raw_bytes=raw_bytes[:plan["limits"]["maxLogBytes"]//2]+b"\n...[TRUNCATED]...\n"+raw_bytes[-plan["limits"]["maxLogBytes"]//2:]
   result,category=classify(code,text,timed_out,redacted);after_workspace=manifest(workspace);unexpected=after_workspace!=snapshot
   if unexpected:result,category="UNKNOWN","UNEXPECTED_INPUT_MUTATION"
   if manifest(root)!=snapshot or git_state(root,paths)!=plan["git"]:raise ValueError("target drifted during verification")
   log_dir=root/MANAGED/"logs"/"post-apply-v2";log_dir.mkdir(parents=True,exist_ok=True);log_path=log_dir/(plan["applyTransactionId"]+"-"+sha(plan_path)[:12]+".log")
   if log_path.exists():raise ValueError("verification log path is occupied")
   atomic_create(raw_bytes,log_path);journal["state"]="COMMAND_FINISHED";durable_json(journal,journal_path);shutil.rmtree(temporary);temporary=None
   report={"postApplyVerificationReportV2Version":1,"state":result,"category":category,"verificationLevel":"APPLIED_TEST_ISOLATED","plan":reference(plan_path,root),"approval":reference(approval_path,root),"applyResult":plan["applyResult"],"target":str(root),"preRunSnapshotSha256":snapshot["sha256"],"postRunSnapshotSha256":manifest(root)["sha256"],"command":cmd,"result":{"exitCode":code,"timedOut":timed_out,"unexpectedMutation":unexpected},"log":{"path":log_path.relative_to(root).as_posix(),"sha256":sha(log_path),"sizeBytes":log_path.stat().st_size,"truncated":truncated,"redacted":redacted},"startedAt":started,"finishedAt":dt.datetime.now(dt.timezone.utc).isoformat(),"readyForMilestoneCompletion":result=="VERIFIED","milestoneCompletionAuthorized":False};output.parent.mkdir(parents=True,exist_ok=True);atomic_create((json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode(),output);journal_path.unlink();fsync_dir(journal_path.parent)
 except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as e:
  if temporary and temporary.exists() and (journal_path is None or not journal_path.exists()):shutil.rmtree(temporary,ignore_errors=True)
  print(f"POST_APPLY_VERIFICATION_V2_VALID: no\nERROR: {e}",file=sys.stderr);return 1
 print(f"POST_APPLY_VERIFICATION_V2_VALID: yes\nVERIFICATION_RESULT: {result}\nREADY_FOR_MILESTONE_COMPLETION: {'yes' if result=='VERIFIED' else 'no'}\nMILESTONE_COMPLETION_AUTHORIZED: no");return 0
if __name__=="__main__":sys.exit(main())
