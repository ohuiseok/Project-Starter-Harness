#!/usr/bin/env python3
"""Contracts for planning and validating isolated Spring code verification v2."""
from __future__ import annotations
import datetime as dt,hashlib,json,os,re,shutil,subprocess
from pathlib import Path,PurePosixPath
from http_api_spring_mapping import reference
from spring_code_dry_run_v2 import validate_report as validate_dry_run
from validate_feature_specs import load_object
from validate_spring_code_dry_run_v2_approval import validate_approval as validate_dry_run_approval
MAX_OUTPUT=20000;JOURNAL=".starter-harness/transactions/spring-code-verification-v2.json"
SECRET=re.compile(r"(?i)(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|(?:password|passwd|token|api[_-]?key|secret)\s*[:=]\s*\S+)")
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def source_context(root:Path,generated:set[str])->dict:
 names={"build.gradle","build.gradle.kts","settings.gradle","settings.gradle.kts","gradle.properties","pom.xml","gradlew","mvnw"};evidence={}
 for path in sorted(root.rglob("*")):
  if path.is_symlink():continue
  rel=path.relative_to(root).as_posix()
  if {"build","target",".gradle"}&set(PurePosixPath(rel).parts):continue
  build_aux=rel.startswith("buildSrc/") or "/buildSrc/" in rel or path.name in {"libs.versions.toml","lombok.config"}
  if path.is_file() and rel not in generated and (rel.startswith("src/main/java/") or rel.startswith("src/test/java/") or "/src/main/java/" in rel or "/src/test/java/" in rel or path.name in names or build_aux or rel.startswith("gradle/wrapper/") or "/gradle/wrapper/" in rel or rel.startswith(".mvn/wrapper/") or "/.mvn/wrapper/" in rel):evidence[rel]={"sha256":sha(path),"mode":path.stat().st_mode&0o777}
 return evidence
def context_hash(value:dict)->str:return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def wrapper(root:Path,module:str)->dict:
 bases=[root] if module=="." else [root,root/module]
 for base in bases:
  launcher=base/"gradlew"
  if launcher.is_file() and not launcher.is_symlink():
   required=[launcher,base/"gradle/wrapper/gradle-wrapper.jar",base/"gradle/wrapper/gradle-wrapper.properties"]
   if not all(i.is_file() and not i.is_symlink() for i in required):return {"kind":"GRADLE","status":"INCOMPLETE","files":[]}
   prefix=base.relative_to(root).as_posix();command=[("./" if prefix=="." else "./"+prefix+"/")+"gradlew","--offline","--no-daemon"]+(([":"+module.replace("/",":")+":test"] if module!="." and base==root else ["test"]))
   return {"kind":"GRADLE","status":"READY" if os.access(launcher,os.X_OK) else "NOT_EXECUTABLE","files":[reference(i,root)|{"mode":i.stat().st_mode&0o777} for i in required],"command":command}
  launcher=base/"mvnw"
  if launcher.is_file() and not launcher.is_symlink():
   props=base/".mvn/wrapper/maven-wrapper.properties";jar=base/".mvn/wrapper/maven-wrapper.jar";required=[launcher,props,jar]
   if not all(i.is_file() and not i.is_symlink() for i in required):return {"kind":"MAVEN","status":"INCOMPLETE","files":[]}
   prefix=base.relative_to(root).as_posix();command=[("./" if prefix=="." else "./"+prefix+"/")+"mvnw","-o"]+((["-pl",module,"-am","test"] if module!="." and base==root else ["test"]))
   return {"kind":"MAVEN","status":"READY" if os.access(launcher,os.X_OK) else "NOT_EXECUTABLE","files":[reference(i,root)|{"mode":i.stat().st_mode&0o777} for i in required],"command":command}
 raise ValueError("target has no supported Gradle or Maven wrapper")
def cache(kind:str)->dict:
 if kind=="GRADLE":
  base=Path(os.environ.get("GRADLE_USER_HOME",Path.home()/".gradle"));ready=(base/"caches").is_dir() and (base/"wrapper").is_dir()
 else:base=Path.home()/".m2/repository";ready=base.is_dir()
 return {"kind":kind,"status":"READY" if ready else "MISSING","copiedEntries":["caches","wrapper"] if kind=="GRADLE" else ["repository"],"credentialSettingsCopied":False}
def environment()->dict:
 java=shutil.which("java");bwrap=shutil.which("bwrap");version="UNKNOWN"
 if java:
  done=subprocess.run([java,"-version"],capture_output=True,text=True,timeout=10,check=False);version=(done.stderr or done.stdout).splitlines()[0] if done.returncode==0 else "UNKNOWN"
 sandbox="MISSING"
 if bwrap:
  try:
   done=subprocess.run([bwrap,"--die-with-parent","--unshare-all","--ro-bind","/","/","--dev","/dev","--proc","/proc","--tmpfs","/tmp","--tmpfs","/run","--","/bin/true"],capture_output=True,text=True,timeout=15,check=False);sandbox="READY" if done.returncode==0 else "UNAVAILABLE"
  except (OSError,subprocess.SubprocessError):sandbox="UNAVAILABLE"
 return {"java":{"status":"READY" if java and version!="UNKNOWN" else "UNKNOWN","version":version},"bubblewrap":{"status":sandbox}}
def java_compatibility(root:Path,environment_value:dict)->dict:
 required=None;source="NOT_DECLARED"
 for path in list(root.rglob("build.gradle"))+list(root.rglob("build.gradle.kts"))+list(root.rglob("pom.xml")):
  if path.is_symlink() or not path.is_file():continue
  text=path.read_text(encoding="utf-8",errors="replace")
  patterns=[r"JavaLanguageVersion\.of\s*\(\s*(\d+)\s*\)",r"JavaVersion\.VERSION_(\d+)",r"<java\.version>\s*(\d+)\s*</java\.version>",r"<maven\.compiler\.release>\s*(\d+)\s*</maven\.compiler\.release>"]
  for pattern in patterns:
   match=re.search(pattern,text)
   if match:required=int(match.group(1));source=path.relative_to(root).as_posix();break
  if required is not None:break
 current_match=re.search(r'\b(?:version\s+)?"?(\d+)',environment_value["java"]["version"]);current=int(current_match.group(1)) if current_match else None
 status="NOT_DECLARED" if required is None else "UNKNOWN" if current is None else "COMPATIBLE" if current>=required else "INCOMPATIBLE"
 return {"status":status,"requiredMajor":required,"currentMajor":current,"source":source}
def build_plan(root:Path,approval_path:Path,timeout:int=600)->dict:
 receipt=validate_dry_run_approval(root,approval_path);dry_path=root/receipt["dryRun"]["path"];dry=load_object(dry_path);validate_dry_run(dry,root);plan_receipt=load_object(root/dry["implementationPlanApproval"]["path"]);implementation=load_object(root/plan_receipt["implementationPlan"]["path"]);tool=wrapper(root,implementation["target"]["modulePath"]);dep=cache(tool["kind"]);env=environment();compat=java_compatibility(root,env);generated={i["path"] for i in dry["generatedFiles"]};context=source_context(root,generated);blockers=[]
 if tool["status"]!="READY":blockers.append({"code":"WRAPPER_NOT_READY","subject":tool["status"]})
 if dep["status"]!="READY":blockers.append({"code":"OFFLINE_CACHE_MISSING","subject":tool["kind"]})
 if env["java"]["status"]!="READY":blockers.append({"code":"JAVA_UNAVAILABLE","subject":"java"})
 if env["bubblewrap"]["status"]!="READY":blockers.append({"code":"SANDBOX_UNAVAILABLE","subject":"bubblewrap"})
 if compat["status"]=="INCOMPATIBLE":blockers.append({"code":"JAVA_VERSION_INCOMPATIBLE","subject":f"requires {compat['requiredMajor']}, current {compat['currentMajor']}"})
 for rel in context:
  path=root/rel
  if path.stat().st_size<=1024*1024:
   try:contains=bool(SECRET.search(path.read_text(encoding="utf-8")))
   except UnicodeDecodeError:contains=False
   if contains:blockers.append({"code":"SECRET_LIKE_BUILD_INPUT","subject":rel})
 return {"springCodeVerificationPlanV2Version":1,"target":str(root),"dryRunApproval":reference(approval_path,root),"dryRun":reference(dry_path,root),"targetContext":{"sha256":context_hash(context),"files":context},"wrapper":tool,"dependencyCache":dep,"environment":env,"javaCompatibility":compat,"command":tool.get("command",[]),"effects":{"network":"DISABLED","dockerSocket":"HIDDEN","database":"NOT_STARTED","ports":"NOT_PUBLISHED","targetSource":"READ_ONLY_AND_MONITORED","workspace":"TEMPORARY_ALLOWLIST_COPY","hostEnvironment":"CLEARED","credentialSettings":"NOT_COPIED"},"limits":{"timeoutSeconds":timeout,"maxOutputCharacters":MAX_OUTPUT},"blockers":blockers,"readyForApproval":not blockers}
def validate_plan(plan:dict,path:Path,root:Path)->dict:
 if not isinstance(plan,dict) or plan.get("springCodeVerificationPlanV2Version")!=1 or set(plan)!={"springCodeVerificationPlanV2Version","target","dryRunApproval","dryRun","targetContext","wrapper","dependencyCache","environment","javaCompatibility","command","effects","limits","blockers","readyForApproval"}:raise ValueError("Spring code verification plan v2 is invalid")
 if Path(plan["target"]).resolve()!=root or not 30<=plan["limits"]["timeoutSeconds"]<=1800 or plan["limits"]["maxOutputCharacters"]!=MAX_OUTPUT:raise ValueError("verification target or limits are invalid")
 approval=root/plan["dryRunApproval"]["path"]
 if reference(approval,root)!=plan["dryRunApproval"]:raise ValueError("dry-run approval changed")
 expected=build_plan(root,approval,plan["limits"]["timeoutSeconds"])
 if plan!=expected:raise ValueError("verification plan is stale")
 if path.is_symlink() or root not in path.resolve().parents:raise ValueError("verification plan must be target-owned")
 return load_object(root/plan["dryRun"]["path"])
def render_plan(plan:dict)->str:
 return "\n".join(["# Spring 코드 v2 격리 검증 계획","","## 검토 결론","",f"- 실행 준비: {'예' if plan['readyForApproval'] else '아니요'}",f"- 명령: `{' '.join(plan['command']) or '결정 불가'}`",f"- Java: {plan['environment']['java']['version']}",f"- Java 호환성: {plan['javaCompatibility']['status']}",f"- 로컬 {plan['dependencyCache']['kind']} cache: {plan['dependencyCache']['status']}",f"- 차단 항목: {len(plan['blockers'])}개","","## 실제 효과","","- 네트워크·Docker·DB·포트: 차단 또는 사용하지 않음","- target: 읽기 전용으로 감시하며 변경하지 않음","- source/build/wrapper allowlist만 임시 복사","- 호스트 환경변수 초기화, credential 설정 복사 안 함","- 컴파일·테스트 출력은 임시 공간에만 생성","","## 차단 항목",""]+[f"- `{i['code']}` · {i['subject']}" for i in plan["blockers"]] + ["- 없음" if not plan["blockers"] else "","","## 검증 의미","","- 통과 시 승인된 API 계약 후보가 임시 복사본에서 컴파일되고 테스트됐음을 의미","- 비즈니스 행동 완료, source 적용, commit, push를 의미하지 않음","","## 선택","","1. 추천: 이 검증 계획 승인","2. 제한 시간 등 항목 수정","3. 자연어로 다른 검증 요청","4. 취소",""])
def validate_approval(root:Path,path:Path,plan_path:Path)->dict:
 reference(path,root);value=load_object(path)
 if set(value)!={"springCodeVerificationPlanV2ApprovalVersion","state","plan","view","approvedBy","approvedAt","effects"} or value["springCodeVerificationPlanV2ApprovalVersion"]!=1 or value["state"]!="APPROVED":raise ValueError("verification plan approval is invalid")
 if reference(plan_path,root)!=value["plan"]:raise ValueError("approved verification plan changed")
 view=root/value["view"]["path"];plan=load_object(plan_path);validate_plan(plan,plan_path,root)
 if reference(view,root)!=value["view"] or view.read_text()!=render_plan(plan):raise ValueError("approved verification view changed")
 if not value["approvedBy"].strip() or dt.datetime.fromisoformat(value["approvedAt"].replace("Z","+00:00")).utcoffset() is None:raise ValueError("approval identity or time is invalid")
 if value["effects"]!={"verificationExecutionAuthorized":True,"sourceChanged":False,"applyAuthorized":False,"gitCommitOrPush":"NOT_RUN"}:raise ValueError("approval effects are invalid")
 return value
def validate_report(report:dict,path:Path,root:Path)->dict:
 required={"springCodeVerificationReportV2Version","verificationLevel","plan","approval","dryRun","target","targetContextSha256","command","isolation","startedAt","finishedAt","result","targetSourceChanged","readyForApplyReview"}
 if not isinstance(report,dict) or set(report)!=required or report["springCodeVerificationReportV2Version"]!=1 or report["verificationLevel"]!="CANDIDATE_TEST_ISOLATED" or Path(report["target"]).resolve()!=root or report["targetSourceChanged"] is not False:raise ValueError("Spring code verification report v2 is invalid")
 plan_path=root/report["plan"]["path"];approval_path=root/report["approval"]["path"]
 if reference(plan_path,root)!=report["plan"] or reference(approval_path,root)!=report["approval"]:raise ValueError("verification evidence changed")
 plan=load_object(plan_path);dry=validate_plan(plan,plan_path,root);validate_approval(root,approval_path,plan_path)
 if report["dryRun"]!=plan["dryRun"] or report["targetContextSha256"]!=plan["targetContext"]["sha256"] or report["command"]!=plan["command"] or report["isolation"]!=plan["effects"]:raise ValueError("verification report input evidence is inconsistent")
 result=report["result"]
 if set(result)!={"state","exitCode","output","redacted","timedOut"} or result["state"] not in {"PASSED","FAILED","UNKNOWN"} or not isinstance(result["exitCode"],int) or not isinstance(result["output"],str) or len(result["output"])>plan["limits"]["maxOutputCharacters"]:raise ValueError("verification result is invalid")
 if result["timedOut"] is not (result["exitCode"]==124) or result["redacted"] and result["state"]!="UNKNOWN" or SECRET.search(result["output"]):raise ValueError("verification timeout or redaction evidence is invalid")
 if report["readyForApplyReview"] is not (result["state"]=="PASSED" and result["exitCode"]==0):raise ValueError("apply review readiness is inconsistent")
 for stamp in (report["startedAt"],report["finishedAt"]):
  if dt.datetime.fromisoformat(stamp.replace("Z","+00:00")).utcoffset() is None:raise ValueError("verification timestamps need timezone")
 if context_hash(source_context(root,{i["path"] for i in dry["generatedFiles"]}))!=plan["targetContext"]["sha256"]:raise ValueError("target context changed after verification")
 if path.is_symlink() or root not in path.resolve().parents:raise ValueError("verification report must be target-owned")
 return plan
def render_report(report:dict)->str:
 result=report["result"]
 return "\n".join(["# Spring 코드 v2 격리 검증 결과","","## 결론","",f"- 상태: {result['state']}",f"- apply 검토 준비: {'예' if report['readyForApplyReview'] else '아니요'}","- 실제 target source 변경: 없음",f"- timeout: {'예' if result['timedOut'] else '아니요'}",f"- 민감 출력 redaction: {'예 · 결과는 UNKNOWN' if result['redacted'] else '없음'}","","## 실행과 격리","",f"- 명령: `{' '.join(report['command'])}`","- 네트워크·Docker·DB·포트: 차단 또는 사용하지 않음","- 호스트 환경변수·credential 설정: 노출하지 않음","- 작업공간: allowlist 임시 복사 후 삭제",f"- exit code: {result['exitCode']}","","## 출력","","```text",result["output"].rstrip(),"```","","## 의미","","- PASSED는 승인 후보의 격리 컴파일·테스트 통과 증거","- 비즈니스 행동 완료나 실제 source 적용 증거는 아님","- apply에는 별도 영향 검토와 승인이 필요",""])
