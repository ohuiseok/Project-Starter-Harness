#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
from continuation_route import build_route,render,sanitize
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha
def reserve(root:Path,project:Path,request:str)->tuple[str,Path,bytes]:
 directory=root/".starter-harness/feature-reservations"; directory.mkdir(parents=True,exist_ok=True)
 used={p.stem for p in directory.glob("F[0-9][0-9][0-9].json")}
 data=json.loads(project.read_text()); used|={item["id"] for item in data["featureCandidates"]}; used|={p.name for p in (root/"docs/features").glob("F[0-9][0-9][0-9]")} if (root/"docs/features").exists() else set()
 number=max([int(x[1:]) for x in used] or [0])+1
 while True:
  feature_id=f"F{number:03d}"; path=directory/f"{feature_id}.json"; value={"featureReservationVersion":1,"featureId":feature_id,"requestSummary":sanitize(request),"state":"RESERVED"}; payload=(json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode()
  try:
   fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,"wb") as stream: stream.write(payload); stream.flush(); os.fsync(stream.fileno())
   return feature_id,path,payload
  except FileExistsError: number+=1
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--request",required=True); p.add_argument("--project-brief",required=True,type=Path); p.add_argument("--progress",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--view",required=True,type=Path); p.add_argument("--feature-id"); a=p.parse_args()
 reservation_path=None; reservation_bytes=None; output=None; route_bytes=None
 try:
  root=a.target.resolve(strict=True); project=a.project_brief.resolve(strict=True); progress=a.progress.resolve(strict=True); output=a.output.resolve(strict=False); view=a.view.resolve(strict=False)
  if a.target.is_symlink() or any(root not in path.parents for path in (project,progress,output,view)) or any(path.is_symlink() for path in (project,progress,output,view)) or output.exists() or view.exists(): raise ValueError("continuation paths are unsafe or already exist")
  route=build_route(root,a.request,project,progress,a.feature_id); reservation_path=None; reservation_bytes=None
  if route["route"]["proposedFeature"]:
   feature_id,reservation_path,reservation_bytes=reserve(root,project,a.request); reservation={"path":reservation_path.relative_to(root).as_posix(),"sha256":sha(reservation_path)}; route=build_route(root,a.request,project,progress,a.feature_id,feature_id,reservation)
  route_bytes=(json.dumps(route,ensure_ascii=False,indent=2)+"\n").encode(); view_bytes=render(route).encode(); output.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(route_bytes,output)
  try: atomic_write_bytes(view_bytes,view)
  except BaseException:
   if output.exists() and output.read_bytes()==route_bytes: output.unlink()
   if reservation_path and reservation_path.exists() and reservation_path.read_bytes()==reservation_bytes: reservation_path.unlink()
   raise
 except (OSError,ValueError,KeyError,TypeError) as e:
  if output and route_bytes and output.exists() and output.read_bytes()==route_bytes: output.unlink()
  if reservation_path and reservation_bytes and reservation_path.exists() and reservation_path.read_bytes()==reservation_bytes: reservation_path.unlink()
  print(f"CONTINUATION_ROUTE_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("CONTINUATION_ROUTE_VALID: yes"); print(f"ROUTE_TYPE: {route['route']['type']}"); print(f"NEXT_WORKFLOW: {route['route']['nextWorkflow']}"); print(f"CONFIRMATION_REQUIRED: {'yes' if route['route']['requiresConfirmation'] else 'no'}"); return 0
if __name__=="__main__": sys.exit(main())
