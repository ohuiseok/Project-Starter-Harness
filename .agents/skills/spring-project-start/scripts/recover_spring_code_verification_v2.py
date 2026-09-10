#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,shutil,signal,sys,time
from pathlib import Path
from spring_code_verification_v2 import JOURNAL
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);path=root/JOURNAL;value=load_object(path)
  if set(value)!={"springCodeVerificationV2JournalVersion","state","plan","approval","temporaryRoot","pid","processStartTicks"} or value["springCodeVerificationV2JournalVersion"]!=2 or value["state"] not in {"PREPARED","RUNNING","CLEANED"}:raise ValueError("verification journal is invalid")
  temporary=Path(value["temporaryRoot"]);prefix="/var/tmp/spring-code-verification-v2-"
  if not str(temporary).startswith(prefix) or temporary.parent!=Path("/var/tmp"):raise ValueError("journal temporary root is unsafe")
  pid=value["pid"]
  if value["state"]=="RUNNING" and isinstance(pid,int) and (Path("/proc")/str(pid)).exists():
   command=(Path("/proc")/str(pid)/"cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace")
   ticks=(Path("/proc")/str(pid)/"stat").read_text().split()[21]
   if "bwrap" not in command or str(temporary/"workspace") not in command or ticks!=value["processStartTicks"]:raise ValueError("journal PID does not match the exact verification process")
   os.killpg(pid,signal.SIGKILL)
   for _ in range(40):
    if not (Path("/proc")/str(pid)).exists():break
    time.sleep(.05)
   if (Path("/proc")/str(pid)).exists():raise ValueError("verification process did not stop")
  if temporary.exists():
   if temporary.is_symlink() or not temporary.is_dir():raise ValueError("journal temporary root drifted")
   shutil.rmtree(temporary)
  path.unlink()
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_VERIFICATION_V2_RECOVERED: no\nERROR: {e}");return 1
 print("SPRING_CODE_VERIFICATION_V2_RECOVERED: yes\nTARGET_SOURCE_CHANGED: no");return 0
if __name__=="__main__":sys.exit(main())
