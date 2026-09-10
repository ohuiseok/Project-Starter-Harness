#!/usr/bin/env python3
"""Assess build, schema, baseline, and target gates before code dry-run v2."""
from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path,PurePosixPath
from validate_feature_specs import load_object

BASELINE=".starter-harness-implementation-v2.json";MAX_FILES=100;MAX_FILE_BYTES=1024*1024;MAX_TOTAL_BYTES=10*1024*1024
FORMATS={None,"date","date-time","uuid","int32","int64","float","double"};TYPES={"string","integer","number","boolean","object","array"}

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def git_state(root:Path)->dict:
 top=subprocess.run(["git","rev-parse","--show-toplevel"],cwd=root,capture_output=True,text=True,check=False);branch=subprocess.run(["git","branch","--show-current"],cwd=root,capture_output=True,text=True,check=False);status=subprocess.run(["git","status","--porcelain","--untracked-files=all"],cwd=root,capture_output=True,text=True,check=False)
 if any(i.returncode for i in (top,branch,status)) or Path(top.stdout.strip()).resolve()!=root:raise ValueError("target Git root, branch, or dirty state cannot be verified")
 paths=[line[3:].split(" -> ")[-1] for line in status.stdout.splitlines() if len(line)>3];relevant=sorted(i for i in paths if i.startswith("src/") or Path(i).name in {"build.gradle","build.gradle.kts","pom.xml","settings.gradle","settings.gradle.kts","gradlew","mvnw"})
 return {"root":str(root),"branch":branch.stdout.strip() or "DETACHED","dirtyPaths":relevant}
def build_capability(root:Path,module_path:str)->dict:
 module=(root/module_path).resolve();candidates=[module/i for i in ("build.gradle","build.gradle.kts","pom.xml")];files=[i for i in candidates if i.is_file() and not i.is_symlink()];text="\n".join(i.read_text(encoding="utf-8",errors="replace") for i in files)
 checks={"springMvc":"spring-boot-starter-web" in text,"beanValidation":"spring-boot-starter-validation" in text,"springTest":"spring-boot-starter-test" in text,"mockMvc":"spring-boot-starter-test" in text,"junit":"spring-boot-starter-test" in text or "junit-jupiter" in text,"mockito":"spring-boot-starter-test" in text or "mockito" in text.lower()}
 return {"evidence":[{"path":i.relative_to(root).as_posix(),"sha256":sha(i)} for i in files],"checks":checks,"ready":bool(files) and all(checks.values())}
def schema_blockers(plan:dict)->list[dict]:
 catalog=plan["schemaCatalog"];blockers=[]
 def walk(value,subject,stack):
  if not isinstance(value,dict):return
  if any(key in value for key in ("oneOf","anyOf","allOf")):blockers.append({"code":"SCHEMA_COMPOSITION_UNSUPPORTED","subject":subject})
  if "additionalProperties" in value:blockers.append({"code":"SCHEMA_MAP_UNSUPPORTED","subject":subject})
  if value.get("type") is not None and value.get("type") not in TYPES:blockers.append({"code":"SCHEMA_TYPE_UNSUPPORTED","subject":subject})
  if value.get("format") not in FORMATS:blockers.append({"code":"SCHEMA_FORMAT_UNSUPPORTED","subject":subject})
  ref=value.get("$ref")
  if isinstance(ref,str) and ref.startswith("#/components/schemas/"):
   name=ref.rsplit("/",1)[-1]
   if name not in catalog:blockers.append({"code":"SCHEMA_REF_MISSING","subject":name})
   elif name in stack:blockers.append({"code":"SCHEMA_REF_CYCLE","subject":name})
   else:walk(catalog[name],name,stack|{name})
  for name,item in value.get("properties",{}).items():walk(item,f"{subject}.{name}",stack)
  if isinstance(value.get("items"),dict):walk(value["items"],subject+"[]",stack)
  for key,item in value.items():
   if key in {"$ref","properties","items"}:continue
   if isinstance(item,dict):walk(item,f"{subject}.{key}",stack)
   elif isinstance(item,list):
    for index,child in enumerate(item):walk(child,f"{subject}.{key}[{index}]",stack)
 for operation in plan["operationLinks"]:
  walk(operation["implementationSemantics"],operation["operationId"],set())
 return [{"code":code,"subject":subject} for code,subject in sorted({(i["code"],i["subject"]) for i in blockers})]
def baseline(root:Path)->dict:
 path=root/BASELINE
 if path.is_symlink() or path.exists() and not path.is_file():raise ValueError("code baseline v2 is unsafe")
 if not path.exists():return {"state":"ABSENT","reference":None,"files":{}}
 value=load_object(path)
 if set(value)!={"manifestVersion","artifactKind","files","modes"} or value["manifestVersion"]!=2 or value["artifactKind"]!="SPRING_IMPLEMENTATION_V2" or not isinstance(value["files"],dict) or not isinstance(value["modes"],dict) or set(value["files"])!=set(value["modes"]):raise ValueError("code baseline v2 is invalid")
 for name,digest in value["files"].items():
  pure=PurePosixPath(name)
  mode=value["modes"][name]
  if pure.is_absolute() or ".." in pure.parts or not isinstance(digest,str) or len(digest)!=64 or any(i not in "0123456789abcdef" for i in digest) or not isinstance(mode,int) or isinstance(mode,bool) or not 0<=mode<=0o777:raise ValueError("code baseline v2 file entry is invalid")
 return {"state":"CURRENT","reference":{"path":BASELINE,"sha256":sha(path)},"files":value["files"]}
def assess(plan:dict,root:Path,approval_ref:dict|None=None)->dict:
 build=build_capability(root,plan["target"]["modulePath"]);schemas=schema_blockers(plan);git=git_state(root);base=baseline(root);blockers=[]
 if not build["ready"]:blockers.append({"code":"BUILD_CAPABILITY_MISSING","subject":"build"})
 blockers.extend(schemas)
 if any(i["fileAction"]=="UPDATE_FILE" for i in plan["components"]):blockers.append({"code":"UPDATE_RENDERER_NOT_IMPLEMENTED","subject":"existing source"})
 return {"springCodeRenderabilityVersion":2,"target":str(root),"planId":plan["planId"],"implementationPlanApproval":approval_ref,"git":git,"buildCapability":build,"schemaBlockers":schemas,"baseline":base,"limits":{"maxFiles":MAX_FILES,"maxFileBytes":MAX_FILE_BYTES,"maxTotalBytes":MAX_TOTAL_BYTES},"coverageLevel":"API_CONTRACT_ONLY","blockers":blockers,"renderer":"NOT_IMPLEMENTED","readyForCodeDryRun":False,"effects":{"sourceChanged":False,"testsExecuted":False,"network":"NOT_USED","docker":"NOT_USED","gitCommitOrPush":"NOT_RUN"}}
