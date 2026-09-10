#!/usr/bin/env python3
"""Review and validation contracts for CREATE/REUSE Spring code apply v2."""
from __future__ import annotations
import datetime as dt,fcntl,hashlib,json,os,subprocess
from contextlib import contextmanager
from pathlib import Path,PurePosixPath
from http_api_spring_mapping import reference
from spring_code_renderability_v2 import baseline as current_baseline
from spring_code_verification_v2 import git_state,sha,validate_apply_readiness,validate_report as validate_verification
from validate_feature_specs import load_object
BASELINE=".starter-harness-implementation-v2.json";MANAGED=".starter-harness";LOCK=f"{MANAGED}/locks/spring-code-v2-apply.lock";ACTIVE={"PREPARED","APPLYING","BASELINE_WRITTEN","ROLLING_BACK","ROLLBACK_INCOMPLETE","COMMITTED_REPORT_PENDING"}
def encoded(value:dict)->bytes:return (json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode()
def safe_path(value:str,suffix:str|None=None)->PurePosixPath:
 path=PurePosixPath(value)
 if not isinstance(value,str) or not value or path.is_absolute() or ".." in path.parts or path.parts[0] in {".git",MANAGED} or suffix and path.suffix!=suffix:raise ValueError(f"unsafe target path: {value!r}")
 return path
def nearest_parent(root:Path,relative:str)->tuple[Path,list[str]]:
 target=root/safe_path(relative,".java");missing=[];parent=target.parent
 while parent!=root and not parent.exists():missing.append(parent.relative_to(root).as_posix());parent=parent.parent
 if parent.is_symlink() or not parent.is_dir() or root not in target.resolve().parents:raise ValueError(f"unsafe target parent: {relative}")
 for item in target.parents:
  if item==root:break
  if item.exists() and item.is_symlink():raise ValueError(f"target parent is symlink: {relative}")
 return parent,list(reversed(missing))
def git_extra(root:Path,paths:list[str])->dict:
 ignored=[]
 for path in paths:
  done=subprocess.run(["git","check-ignore","--no-index","-q","--",path],cwd=root,check=False)
  if done.returncode==0:ignored.append(path)
  elif done.returncode not in {1}:raise ValueError("Git ignore state cannot be verified")
 submodules=[];done=subprocess.run(["git","submodule","status","--recursive"],cwd=root,capture_output=True,text=True,check=False)
 if done.returncode==0:
  for line in done.stdout.splitlines():
   parts=line.strip().split()
   if len(parts)>=2:submodules.append(parts[1])
 elif (root/".gitmodules").exists():raise ValueError("Git submodule state cannot be verified")
 overlaps=sorted(path for path in paths for module in submodules if path==module or path.startswith(module+"/"))
 sparse=(root/".git/info/sparse-checkout").exists()
 return {"ignoredTargets":sorted(ignored),"submoduleOverlaps":overlaps,"sparseCheckout":sparse}
def pending(root:Path)->list[str]:
 directory=root/MANAGED/"transactions"
 if directory.is_symlink():raise ValueError("transaction directory is unsafe")
 found=[]
 for path in directory.glob("spring-code-v2-*.json") if directory.is_dir() else []:
  try:state=load_object(path).get("state")
  except (OSError,ValueError):raise ValueError(f"transaction cannot be inspected: {path}")
  if state in ACTIVE:found.append(path.relative_to(root).as_posix())
 return sorted(found)
def build_review(root:Path,verification_path:Path,result_path:str)->dict:
 verification=load_object(verification_path);validate_apply_readiness(verification,verification_path,root);plan=load_object(root/verification["plan"]["path"]);dry_path=root/verification["dryRun"]["path"];dry=load_object(dry_path)
 if dry["renderer"]!="JAVA_MVC_API_ONLY_V1" or dry["summary"]["updates"]!=0:raise ValueError("apply v2 supports CREATE_FILE and REUSE_FILE only")
 creates=sorted(({k:item[k] for k in ("componentRef","path","mode","sha256")} for item in dry["generatedFiles"]),key=lambda i:i["path"]);reuses=sorted(dry["reusedFiles"],key=lambda i:i["path"]);paths=[i["path"] for i in creates];blockers=[];warnings=[];parents=[]
 existing_case={path.relative_to(root).as_posix().casefold():path.relative_to(root).as_posix() for path in root.rglob("*") if not path.is_symlink()}
 seen={}
 for item in creates:
  relative=item["path"];target=root/safe_path(relative,".java");_,missing=nearest_parent(root,relative);parents.extend(missing);fold=relative.casefold()
  if target.exists() or target.is_symlink():blockers.append({"code":"CREATE_TARGET_OCCUPIED","subject":relative})
  if fold in seen or fold in existing_case:blockers.append({"code":"CASE_COLLISION","subject":relative})
  seen[fold]=relative
 base=current_baseline(root);existing_files=base["files"]
 for item in creates:
  if item["path"] in existing_files:blockers.append({"code":"BASELINE_ALREADY_OWNS_CREATE","subject":item["path"]})
 for item in reuses:
  target=root/item["path"]
  if target.is_symlink() or not target.is_file() or sha(target)!=item["sha256"] or target.stat().st_mode&0o777!=item["mode"]:blockers.append({"code":"REUSE_EVIDENCE_CHANGED","subject":item["path"]})
 extra=git_extra(root,paths);blockers.extend({"code":"GIT_IGNORED_TARGET","subject":i} for i in extra["ignoredTargets"]);blockers.extend({"code":"SUBMODULE_TARGET","subject":i} for i in extra["submoduleOverlaps"])
 if extra["sparseCheckout"]:warnings.append({"code":"SPARSE_CHECKOUT_ACTIVE","subject":"target"})
 desired_files=dict(existing_files);desired_modes={}
 if base["reference"]:desired_modes.update(load_object(root/BASELINE)["modes"])
 for item in creates:desired_files[item["path"]]=item["sha256"];desired_modes[item["path"]]=item["mode"]
 desired={"manifestVersion":2,"artifactKind":"SPRING_IMPLEMENTATION_V2","files":desired_files,"modes":desired_modes};desired_sha=hashlib.sha256(encoded(desired)).hexdigest()
 candidate_bytes=sum(len(next(x["content"].encode() for x in dry["generatedFiles"] if x["path"]==i["path"])) for i in creates)
 evidence_refs=[reference(verification_path,root),reference(dry_path,root)]+([base["reference"]] if base["reference"] else [])
 evidence_bytes=sum((root/ref["path"]).stat().st_size for ref in evidence_refs)
 required=max((candidate_bytes+evidence_bytes+len(encoded(desired)))*3+1024*1024,2*1024*1024);stat=os.statvfs(root);available=stat.f_bavail*stat.f_frsize
 if available<required:blockers.append({"code":"INSUFFICIENT_DISK_SPACE","subject":f"requires {required}, available {available}"})
 if pending(root):blockers.append({"code":"RECOVERY_REQUIRED","subject":pending(root)[0]})
 result=safe_path(result_path,".json")
 if result.parts[0]!="docs":raise ValueError("apply result must be a JSON file under docs/")
 if (root/result).exists() or (root/result).is_symlink():blockers.append({"code":"RESULT_PATH_OCCUPIED","subject":result.as_posix()})
 identity=hashlib.sha256(json.dumps({"verification":reference(verification_path,root),"desired":desired_sha,"result":result.as_posix()},sort_keys=True,separators=(",",":")).encode()).hexdigest()[:24]
 return {"springCodeApplyReviewV2Version":1,"state":"REVIEW_READY" if not blockers else "BLOCKED","transactionId":"spring-code-v2-"+identity,"target":str(root),"verification":reference(verification_path,root),"dryRun":reference(dry_path,root),"git":plan["git"],"baseline":{"before":base["reference"],"existingFiles":len(existing_files),"ownershipRule":"RETAIN_EXISTING_ADD_CREATES_ONLY_REUSE_UNOWNED"},"fileActions":{"creates":creates,"reuses":reuses,"updates":[],"deletes":[]},"parentDirectories":sorted(set(parents),key=lambda i:(len(PurePosixPath(i).parts),i)),"filesystem":{"device":root.stat().st_dev,"requiredBytes":required,"availableBytesAtReview":available},"backup":{"path":f"{MANAGED}/backups/spring-code-v2/spring-code-v2-{identity}","manifest":"backup-manifest.json"},"journal":{"path":f"{MANAGED}/transactions/spring-code-v2-{identity}.json","states":["PREPARED","APPLYING","BASELINE_WRITTEN","COMMITTED","COMMITTED_REPORT_PENDING","ROLLING_BACK","ROLLED_BACK","ROLLBACK_INCOMPLETE"]},"result":{"path":result.as_posix()},"desiredBaseline":{"sha256":desired_sha,"document":desired},"warnings":warnings,"blockers":blockers,"effects":{"sourceFiles":"CREATE_ONLY","reuseFiles":"UNCHANGED","baseline":"MERGED_LAST","tests":"NOT_RUN","network":"NOT_USED","docker":"NOT_USED","gitCommitOrPush":"NOT_RUN"},"readyForApproval":not blockers}
def validate_review(review:dict,path:Path,root:Path,current:bool=True)->dict:
 required={"springCodeApplyReviewV2Version","state","transactionId","target","verification","dryRun","git","baseline","fileActions","parentDirectories","filesystem","backup","journal","result","desiredBaseline","warnings","blockers","effects","readyForApproval"}
 if not isinstance(review,dict) or set(review)!=required or review["springCodeApplyReviewV2Version"]!=1 or Path(review["target"]).resolve()!=root:raise ValueError("Spring code apply review v2 is invalid")
 verification=root/review["verification"]["path"]
 if reference(verification,root)!=review["verification"]:raise ValueError("verification evidence changed")
 if current:
  expected=build_review(root,verification,review["result"]["path"])
  expected["filesystem"]["availableBytesAtReview"]=review["filesystem"]["availableBytesAtReview"]
  if os.statvfs(root).f_bavail*os.statvfs(root).f_frsize<review["filesystem"]["requiredBytes"]:raise ValueError("disk space is no longer sufficient")
  if review!=expected:raise ValueError("apply review is stale")
 if path.is_symlink() or root not in path.resolve().parents:raise ValueError("apply review must be target-owned")
 return load_object(root/review["dryRun"]["path"])
def render_review(review:dict)->str:
 actions=review["fileActions"];lines=["# Spring 코드 v2 적용 검토","","## 결론","",f"- 적용 준비: {'예' if review['readyForApproval'] else '아니요'}",f"- 신규 파일 {len(actions['creates'])} · 재사용 {len(actions['reuses'])} · 수정 0 · 삭제 0",f"- 새 부모 디렉터리 {len(review['parentDirectories'])}개",f"- 차단 {len(review['blockers'])} · 경고 {len(review['warnings'])}","- 적용 전 격리 검증: PASSED","","## 안전 장치","","- 파일 단위 atomic replace + durable journal + 검증 가능한 rollback","- 기존 baseline 소유권 유지, CREATE만 추가, REUSE는 소유권에 편입하지 않음",f"- backup: `{review['backup']['path']}`",f"- journal: `{review['journal']['path']}`",f"- 결과 보고서: `{review['result']['path']}`","- OS non-blocking lock으로 apply/recovery 동시 실행 차단","","## 파일",""]
 lines.extend(f"- CREATE `{i['path']}`" for i in actions["creates"]);lines.extend(f"- REUSE `{i['path']}` · 변경 없음" for i in actions["reuses"])
 lines += ["","## 차단과 경고",""]+[f"- 차단 `{i['code']}` · {i['subject']}" for i in review["blockers"]]+[f"- 경고 `{i['code']}` · {i['subject']}" for i in review["warnings"]]
 if not review["blockers"] and not review["warnings"]:lines.append("- 없음")
 lines += ["","## 승인 효과","","- 승인된 신규 Java 파일과 v2 baseline만 transaction으로 적용","- 테스트·Docker·DB·네트워크·Git commit/push는 실행하지 않음","- 성공 상태는 `APPLIED_PREVERIFIED`; 적용 후 검증은 별도 단계","","## 선택","","1. 추천: 이 적용안 승인","2. 항목별 수정","3. 자연어로 다른 적용 범위 요청","4. 취소",""]
 return "\n".join(lines)
def validate_approval(root:Path,path:Path,review_path:Path,current:bool=True)->dict:
 reference(path,root);value=load_object(path)
 if set(value)!={"springCodeApplyApprovalV2Version","state","review","view","approvedBy","approvedAt","effects"} or value["springCodeApplyApprovalV2Version"]!=1 or value["state"]!="APPROVED":raise ValueError("Spring code apply approval v2 is invalid")
 if reference(review_path,root)!=value["review"]:raise ValueError("approved apply review changed")
 review=load_object(review_path);validate_review(review,review_path,root,current);view=root/value["view"]["path"]
 if reference(view,root)!=value["view"] or view.read_text()!=render_review(review):raise ValueError("approved apply review view changed")
 if not value["approvedBy"].strip() or dt.datetime.fromisoformat(value["approvedAt"].replace("Z","+00:00")).utcoffset() is None:raise ValueError("apply approval identity or time is invalid")
 if value["effects"]!={"applyAuthorized":True,"testsExecuted":False,"gitCommitOrPush":"NOT_RUN"}:raise ValueError("apply approval effects are invalid")
 return value
@contextmanager
def apply_lock(root:Path):
 directory=root/MANAGED/"locks"
 if directory.exists() and (directory.is_symlink() or not directory.is_dir()):raise ValueError("apply lock directory is unsafe")
 directory.mkdir(parents=True,exist_ok=True);path=root/LOCK
 if path.is_symlink():raise ValueError("apply lock is unsafe")
 with path.open("a+b") as handle:
  try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise ValueError("BUSY: another apply or recovery owns the target lock")
  yield
