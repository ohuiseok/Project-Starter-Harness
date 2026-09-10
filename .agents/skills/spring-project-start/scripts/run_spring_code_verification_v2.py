#!/usr/bin/env python3
"""Run an approved v2 candidate in a networkless temporary workspace."""
from __future__ import annotations
import argparse,datetime as dt,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from discover_http_api_evidence import atomic_create
from http_api_spring_mapping import reference
from spring_code_verification_v2 import JOURNAL,SECRET,context_hash,sha,source_context,validate_approval,validate_plan
from validate_feature_specs import load_object
def atomic_json(value:dict,path:Path)->None:
 data=(json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode();path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+".tmp")
 if temporary.exists():raise ValueError("verification journal staging path exists")
 temporary.write_bytes(data);os.replace(temporary,path)
def copy_files(root:Path,workspace:Path,paths:list[str])->None:
 for rel in paths:
  source=root/rel;destination=workspace/rel
  if root not in source.resolve().parents or source.is_symlink() or any(i.is_symlink() for i in source.parents if i!=root and root in i.parents) or not source.is_file():raise ValueError("allowlisted target evidence is missing or unsafe: "+rel)
  destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
def copy_cache(kind:str,home:Path)->None:
 if kind=="GRADLE":
  source=Path(os.environ.get("GRADLE_USER_HOME",Path.home()/".gradle"));destination=home/".gradle";destination.mkdir()
  for name in ("caches","wrapper"):shutil.copytree(source/name,destination/name,symlinks=False)
 else:shutil.copytree(Path.home()/".m2/repository",home/".m2/repository",symlinks=False)
def tree_hash(root:Path)->str:
 evidence={}
 for path in sorted(root.rglob("*")):
  if path.is_symlink():raise ValueError("verification workspace contains a symlink")
  if path.is_file():evidence[path.relative_to(root).as_posix()]={"sha256":sha(path),"mode":path.stat().st_mode&0o777}
 return context_hash(evidence)
def input_hash(workspace:Path,generated:list[dict])->str:
 evidence=source_context(workspace,set())
 for item in generated:
  path=workspace/item["path"]
  if not path.is_file() or path.is_symlink():raise ValueError("generated verification input is missing or unsafe")
  evidence[item["path"]]={"sha256":sha(path),"mode":path.stat().st_mode&0o777}
 return context_hash(evidence)
def sandbox(workspace:Path,home:Path,command:list[str])->list[str]:
 java=shutil.which("java")
 if not java or not shutil.which("bwrap"):raise ValueError("Java and bubblewrap are required")
 java_home=Path(java).resolve().parent.parent;path=f"{java_home}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
 return ["bwrap","--die-with-parent","--unshare-all","--new-session","--ro-bind","/","/","--tmpfs","/root","--tmpfs","/home","--tmpfs","/etc","--tmpfs","/var/lib","--tmpfs","/var/tmp","--tmpfs","/var/log","--tmpfs","/var/spool","--tmpfs","/var/cache","--tmpfs","/opt","--tmpfs","/srv","--tmpfs","/mnt","--tmpfs","/media","--tmpfs","/tmp","--tmpfs","/run","--dir","/run/workspace","--dir","/run/workhome","--dev","/dev","--proc","/proc","--bind",str(workspace),"/run/workspace","--bind",str(home),"/run/workhome","--chdir","/run/workspace","--clearenv","--setenv","PATH",path,"--setenv","JAVA_HOME",str(java_home),"--setenv","HOME","/run/workhome","--setenv","GRADLE_USER_HOME","/run/workhome/.gradle","--setenv","LANG","C.UTF-8","--setenv","DOCKER_HOST","unix:///run/starter-harness-no-docker.sock","--",*command]
def state(returncode:int,text:str)->str:
 if returncode==0:return "PASSED"
 markers=("Could not resolve","Could not install Gradle","PluginResolutionException","Unknown host","Network is unreachable","No cached version")
 return "UNKNOWN" if any(i in text for i in markers) else "FAILED"
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--plan",required=True,type=Path);p.add_argument("--approval",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args();journal_path=None
 try:
  root=a.target.resolve(strict=True);plan_path=a.plan.resolve(strict=True);approval_path=a.approval.resolve(strict=True);output=a.output.resolve();journal_path=root/JOURNAL
  if output.exists() or root not in output.parents or output.relative_to(root).parts[0]!="docs" or journal_path.exists():raise ValueError("verification output is occupied or an unfinished journal exists")
  plan=load_object(plan_path);dry=validate_plan(plan,plan_path,root);validate_approval(root,approval_path,plan_path)
  if not plan["readyForApproval"]:raise ValueError("verification plan has blockers")
  temporary=Path(tempfile.mkdtemp(prefix="spring-code-verification-v2-",dir="/var/tmp"));workspace=temporary/"workspace";home=temporary/"home";workspace.mkdir();home.mkdir();journal={"springCodeVerificationV2JournalVersion":1,"state":"PREPARED","plan":reference(plan_path,root),"approval":reference(approval_path,root),"temporaryRoot":str(temporary),"pid":None};atomic_json(journal,journal_path)
  copy_files(root,workspace,list(plan["targetContext"]["files"]));
  for item in dry["generatedFiles"]:
   destination=workspace/item["path"];destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(item["content"],encoding="utf-8");destination.chmod(item["mode"])
  copy_cache(plan["dependencyCache"]["kind"],home);before=input_hash(workspace,dry["generatedFiles"]);started=dt.datetime.now(dt.timezone.utc).isoformat();process=subprocess.Popen(sandbox(workspace,home,plan["command"]),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);journal["state"]="RUNNING";journal["pid"]=process.pid;atomic_json(journal,journal_path)
  try:text,_=process.communicate(timeout=plan["limits"]["timeoutSeconds"]);code=process.returncode;result=state(code,text)
  except subprocess.TimeoutExpired:
   process.kill();text,_=process.communicate();code=124;result="UNKNOWN"
  text=text[-plan["limits"]["maxOutputCharacters"]:];redacted=bool(SECRET.search(text));text=SECRET.sub("[REDACTED]",text)
  if redacted:result="UNKNOWN"
  if input_hash(workspace,dry["generatedFiles"])!=before:raise ValueError("verification changed source or build inputs in its temporary workspace")
  if context_hash(source_context(root,{i["path"] for i in dry["generatedFiles"]}))!=plan["targetContext"]["sha256"]:raise ValueError("target changed during verification")
  shutil.rmtree(temporary);journal["state"]="CLEANED";journal["pid"]=None;atomic_json(journal,journal_path)
  report={"springCodeVerificationReportV2Version":1,"verificationLevel":"CANDIDATE_TEST_ISOLATED","plan":reference(plan_path,root),"approval":reference(approval_path,root),"dryRun":plan["dryRun"],"target":str(root),"targetContextSha256":plan["targetContext"]["sha256"],"command":plan["command"],"isolation":plan["effects"],"startedAt":started,"finishedAt":dt.datetime.now(dt.timezone.utc).isoformat(),"result":{"state":result,"exitCode":code,"output":text,"redacted":redacted,"timedOut":code==124},"targetSourceChanged":False,"readyForApplyReview":result=="PASSED"};output.parent.mkdir(parents=True,exist_ok=True);atomic_create((json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode(),output);journal_path.unlink()
 except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as e:
  print(f"SPRING_CODE_VERIFICATION_V2_VALID: no\nERROR: {e}",file=sys.stderr);return 1
 print(f"SPRING_CODE_VERIFICATION_V2_VALID: yes\nVERIFICATION_RESULT: {result}\nTARGET_SOURCE_CHANGED: no\nREADY_FOR_APPLY_REVIEW: {'yes' if result=='PASSED' else 'no'}");return 0
if __name__=="__main__":sys.exit(main())
