#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,sys
from pathlib import Path
from continuation_route import render,validate_route
from record_spec_approval import atomic_write_bytes
from spring_milestone_completion import sha
from validate_feature_specs import load_object
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--route",required=True,type=Path); p.add_argument("--view",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--approval-output",required=True,type=Path); p.add_argument("--handoff-output",required=True,type=Path); p.add_argument("--expected-route-hash",required=True); p.add_argument("--approved-by",required=True); p.add_argument("--approved-at",required=True); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); route_path=a.route.resolve(strict=True); view=a.view.resolve(strict=True); approval_path=a.approval_output.resolve(strict=False); handoff_path=a.handoff_output.resolve(strict=False); paths=(route_path,view,approval_path,handoff_path)
  if a.target.is_symlink() or any(root not in path.parents for path in paths) or any(path.is_symlink() for path in paths) or approval_path.exists() or handoff_path.exists() or sha(route_path)!=a.expected_route_hash: raise ValueError("continuation approval paths or reviewed route are invalid")
  route=load_object(route_path); validate_route(route,route_path,root)
  if view.read_text()!=render(route): raise ValueError("reviewed continuation view is stale")
  timestamp=dt.datetime.fromisoformat(a.approved_at.replace("Z","+00:00"))
  if not a.approved_by.strip() or timestamp.utcoffset() is None or not route["readyForHandoff"]: raise ValueError("approval identity, time, and ready route are required")
  approval={"continuationRouteApprovalVersion":1,"approved":True,"routeSha256":sha(route_path),"viewSha256":sha(view),"target":str(root),"approvedBy":a.approved_by,"approvedAt":a.approved_at}
  handoff={"continuationHandoffVersion":1,"route":{"path":route_path.relative_to(root).as_posix(),"sha256":sha(route_path)},"approval":{"path":approval_path.relative_to(root).as_posix(),"sha256":hashlib.sha256((json.dumps(approval,ensure_ascii=False,indent=2)+"\n").encode()).hexdigest()},"target":str(root),"routeType":route["route"]["type"],"changeKind":route["route"]["changeKind"],"feature":route["route"]["selectedFeature"] or route["route"]["proposedFeature"],"nextWorkflow":route["route"]["nextWorkflow"],"state":"READY"}
  approval_bytes=(json.dumps(approval,ensure_ascii=False,indent=2)+"\n").encode(); handoff_bytes=(json.dumps(handoff,ensure_ascii=False,indent=2)+"\n").encode(); approval_path.parent.mkdir(parents=True,exist_ok=True); atomic_write_bytes(approval_bytes,approval_path)
  try: atomic_write_bytes(handoff_bytes,handoff_path)
  except BaseException:
   if approval_path.read_bytes()==approval_bytes: approval_path.unlink()
   raise
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"CONTINUATION_HANDOFF_VALID: no\nERROR: {e}",file=sys.stderr); return 1
 print("CONTINUATION_HANDOFF_VALID: yes"); print(f"NEXT_WORKFLOW: {handoff['nextWorkflow']}"); print("SOURCE_CHANGED: no"); print("GIT_COMMIT_OR_PUSH: NOT_RUN"); return 0
if __name__=="__main__": sys.exit(main())
