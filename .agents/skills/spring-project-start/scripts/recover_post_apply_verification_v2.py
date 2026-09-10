#!/usr/bin/env python3
from __future__ import annotations
import argparse,os,shutil,signal,sys
from pathlib import Path
from apply_approved_spring_code_v2 import fsync_dir
from post_apply_verification_v2 import JOURNAL
from spring_code_apply_v2 import apply_lock,sha
from validate_feature_specs import load_object
def alive(record:dict)->bool:
 try:return (Path("/proc")/str(record["pid"])/"stat").read_text().split()[21]==record["processStartTicks"]
 except (OSError,KeyError,TypeError):return False
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--target",required=True,type=Path);a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);path=root/JOURNAL
  with apply_lock(root):
   record=load_object(path)
   if record.get("postApplyVerificationV2JournalVersion")!=1:raise ValueError("verification journal is invalid")
   if alive(record):os.killpg(record["pid"],signal.SIGTERM);raise ValueError("verification process was alive and received TERM; run recovery again after it exits")
   temporary=Path(record["temporaryRoot"])
   marker=temporary/".starter-harness-post-apply-v2.json"
   if temporary.parent!=Path("/var/tmp") or not temporary.name.startswith("post-apply-v2-") or temporary.is_symlink() or not marker.is_file() or marker.is_symlink() or sha(marker)!=record.get("temporaryMarkerSha256"):raise ValueError("temporary path is unsafe")
   if temporary.exists():shutil.rmtree(temporary)
   path.unlink();fsync_dir(path.parent)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"POST_APPLY_VERIFICATION_V2_RECOVERED: no\nERROR: {e}");return 1
 print("POST_APPLY_VERIFICATION_V2_RECOVERED: yes\nSTATE: CLEANED\nCOMMAND_REEXECUTED: no");return 0
if __name__=="__main__":sys.exit(main())
