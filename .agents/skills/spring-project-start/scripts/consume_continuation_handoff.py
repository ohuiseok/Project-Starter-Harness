#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,sys
from pathlib import Path
from continuation_route import validate_handoff
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha
from validate_feature_specs import load_object
def fsync_dir(path:Path)->None:
 fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--handoff",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args()
 claim_path=None;claim_bytes=None;output_bytes=None
 try:
  root=a.target.resolve(strict=True); handoff=a.handoff.resolve(strict=True); output=a.output.resolve(strict=False)
  if a.target.is_symlink() or root not in handoff.parents or root not in output.parents or handoff.is_symlink() or output.is_symlink() or output.exists(): raise ValueError("workflow intake paths are unsafe or already exist")
  value=load_object(handoff); validate_handoff(value,handoff,root)
  route_path=root/value["route"]["path"]; route=load_object(route_path)
  intake={"continuationWorkflowIntakeVersion":2,"handoff":{"path":handoff.relative_to(root).as_posix(),"sha256":sha(handoff)},"projectBrief":route["projectBrief"],"progress":route["progress"],"requestSummary":route["request"]["summary"],"target":str(root),"workflow":value["nextWorkflow"],"routeType":value["routeType"],"changeKind":value["changeKind"],"feature":value["feature"],"state":"READY_FOR_WORKFLOW"}
  output_bytes=(json.dumps(intake,ensure_ascii=False,indent=2)+"\n").encode();directory=root/".starter-harness/continuation-handoff-consumptions"
  if (root/".starter-harness").is_symlink() or directory.is_symlink():raise ValueError("continuation consumption claim path is unsafe")
  directory.mkdir(parents=True,exist_ok=True);claim_path=directory/f"{sha(handoff)}.json";claim={"continuationHandoffConsumptionVersion":1,"handoff":{"path":handoff.relative_to(root).as_posix(),"sha256":sha(handoff)},"intake":{"path":output.relative_to(root).as_posix(),"sha256":hashlib.sha256(output_bytes).hexdigest()},"state":"PREPARED"};claim_bytes=(json.dumps(claim,ensure_ascii=False,indent=2)+"\n").encode()
  fd=os.open(claim_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,"wb") as stream:stream.write(claim_bytes);stream.flush();os.fsync(stream.fileno())
  fsync_dir(directory)
  try:
   output.parent.mkdir(parents=True,exist_ok=True);atomic_write_bytes(output_bytes,output);fsync_dir(output.parent);claim["state"]="COMMITTED";atomic_write_bytes((json.dumps(claim,ensure_ascii=False,indent=2)+"\n").encode(),claim_path);fsync_dir(directory)
  except Exception:
   if output.exists() and output.read_bytes()==output_bytes:output.unlink();fsync_dir(output.parent)
   if claim_path.exists() and claim_path.read_bytes()==claim_bytes:claim_path.unlink();fsync_dir(directory)
   raise
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"CONTINUATION_INTAKE_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("CONTINUATION_INTAKE_VALID: yes"); print(f"NEXT_WORKFLOW: {value['nextWorkflow']}"); return 0
if __name__=="__main__": sys.exit(main())
