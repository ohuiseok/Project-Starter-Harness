#!/usr/bin/env python3
"""Assess build, schema, baseline, and target gates before code dry-run v2."""
from __future__ import annotations
import hashlib,json,re,subprocess,xml.etree.ElementTree as ET
from pathlib import Path,PurePosixPath
from validate_feature_specs import load_object

BASELINE=".starter-harness-implementation-v2.json";MAX_FILES=100;MAX_FILE_BYTES=1024*1024;MAX_TOTAL_BYTES=10*1024*1024
FORMATS={None,"date","date-time","uuid","int32","int64","float","double"};TYPES={"string","integer","number","boolean","object","array"}

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def git_state(root:Path,module_path:str)->dict:
 top=subprocess.run(["git","rev-parse","--show-toplevel"],cwd=root,capture_output=True,text=True,check=False);branch=subprocess.run(["git","branch","--show-current"],cwd=root,capture_output=True,text=True,check=False);status=subprocess.run(["git","status","--porcelain=v1","-z","--untracked-files=all"],cwd=root,capture_output=True,check=False)
 if any(i.returncode for i in (top,branch,status)) or Path(top.stdout.strip()).resolve()!=root:raise ValueError("target Git root, branch, or dirty state cannot be verified")
 entries=status.stdout.split(b"\0");paths=[];index=0
 while index<len(entries) and entries[index]:
  entry=entries[index].decode("utf-8","surrogateescape");code=entry[:2];paths.append(entry[3:]);index+=2 if "R" in code or "C" in code else 1
 module="" if module_path=="." else module_path.rstrip("/")+"/";build_names={"build.gradle","build.gradle.kts","pom.xml","settings.gradle","settings.gradle.kts","gradlew","mvnw"};relevant=sorted(i for i in paths if i.startswith(module+"src/") or i.startswith(module+"gradle/wrapper/") or Path(i).name in build_names and (not module or i.startswith(module) or "/" not in i))
 return {"root":str(root),"branch":branch.stdout.strip() or "DETACHED","dirtyPaths":relevant}
def gradle_artifacts(text:str)->set[str]:
 clean=re.sub(r"/\*.*?\*/","",text,flags=re.S);clean=re.sub(r"(?m)//.*$","",clean);pattern=r"\b(?:api|implementation|compileOnly|runtimeOnly|testImplementation|testCompileOnly|testRuntimeOnly)\s*\(?\s*['\"]([^'\"]+)['\"]"
 return {value.split(":")[1] for value in re.findall(pattern,clean) if value.count(":")>=1}
def maven_artifacts(path:Path)->set[str]:
 root=ET.parse(path).getroot();namespace=root.tag.partition("}")[0]+"}" if root.tag.startswith("{") else "";result=set()
 for dependencies in root.findall(f"{namespace}dependencies")+root.findall(f"{namespace}profiles/{namespace}profile/{namespace}dependencies"):
  for dependency in dependencies.findall(f"{namespace}dependency"):
   artifact=dependency.findtext(f"{namespace}artifactId")
   if artifact:result.add(artifact.strip())
 return result
def build_capability(root:Path,module_path:str)->dict:
 module=(root/module_path).resolve()
 if root not in (module,*module.parents):raise ValueError("build module escapes target")
 candidates=[]
 for base in (root,module):
  for name in ("build.gradle","build.gradle.kts","pom.xml"):
   if base/name not in candidates:candidates.append(base/name)
 files=[i for i in candidates if i.is_file() and not i.is_symlink()];artifacts=set();parse_errors=[]
 for path in files:
  try:artifacts.update(maven_artifacts(path) if path.name=="pom.xml" else gradle_artifacts(path.read_text(encoding="utf-8")))
  except (OSError,UnicodeError,ET.ParseError,ValueError) as e:parse_errors.append(f"{path.relative_to(root).as_posix()}: {type(e).__name__}")
 starter="spring-boot-starter-test" in artifacts;checks={"springMvc":"spring-boot-starter-web" in artifacts,"beanValidation":"spring-boot-starter-validation" in artifacts,"springTest":starter,"mockMvc":starter,"junit":starter or any(i.startswith("junit-jupiter") for i in artifacts),"mockito":starter or any(i.startswith("mockito") for i in artifacts)}
 return {"evidence":[{"path":i.relative_to(root).as_posix(),"sha256":sha(i)} for i in files],"artifacts":sorted(artifacts),"parseErrors":parse_errors,"checks":checks,"ready":bool(files) and not parse_errors and all(checks.values())}
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
  semantics=operation["implementationSemantics"]
  for parameter in semantics["parameters"]:
   if parameter["in"] not in {"path","query","header","cookie"}:blockers.append({"code":"PARAMETER_LOCATION_UNSUPPORTED","subject":f"{operation['operationId']}.{parameter['name']}"})
   defaults={"path":("simple",False),"query":("form",True),"header":("simple",False),"cookie":("form",True)}
   if parameter["in"] in defaults:
    style=parameter.get("style") or defaults[parameter["in"]][0];explode=parameter.get("explode") if parameter.get("explode") is not None else style=="form"
    if (style,explode)!=defaults[parameter["in"]]:blockers.append({"code":"PARAMETER_SERIALIZATION_UNSUPPORTED","subject":f"{operation['operationId']}.{parameter['name']}"})
   if parameter.get("unresolvedRef"):blockers.append({"code":"REFERENCE_UNRESOLVED","subject":parameter["unresolvedRef"]})
  request=semantics["requestBody"]
  if request:
   if request.get("unresolvedRef"):blockers.append({"code":"REFERENCE_UNRESOLVED","subject":request["unresolvedRef"]})
   for media in request["content"]:
    if media!="application/json":blockers.append({"code":"MEDIA_TYPE_UNSUPPORTED","subject":media})
  for code,response in semantics["responses"].items():
   if response.get("unresolvedRef"):blockers.append({"code":"REFERENCE_UNRESOLVED","subject":response["unresolvedRef"]})
   if code=="204" and response["content"]:blockers.append({"code":"NO_CONTENT_RESPONSE_HAS_BODY","subject":operation["operationId"]})
   for media in response["content"]:
    if media!="application/json":blockers.append({"code":"MEDIA_TYPE_UNSUPPORTED","subject":media})
   for header in response["headers"].values():
    if header.get("unresolvedRef"):blockers.append({"code":"REFERENCE_UNRESOLVED","subject":header["unresolvedRef"]})
 return [{"code":code,"subject":subject} for code,subject in sorted({(i["code"],i["subject"]) for i in blockers})]
def baseline(root:Path)->dict:
 path=root/BASELINE
 if path.is_symlink() or path.exists() and not path.is_file():raise ValueError("code baseline v2 is unsafe")
 if not path.exists():return {"state":"ABSENT","reference":None,"files":{},"drift":[]}
 value=load_object(path)
 if set(value)!={"manifestVersion","artifactKind","files","modes"} or value["manifestVersion"]!=2 or value["artifactKind"]!="SPRING_IMPLEMENTATION_V2" or not isinstance(value["files"],dict) or not isinstance(value["modes"],dict) or set(value["files"])!=set(value["modes"]):raise ValueError("code baseline v2 is invalid")
 for name,digest in value["files"].items():
  pure=PurePosixPath(name)
  mode=value["modes"][name]
  if pure.is_absolute() or ".." in pure.parts or not isinstance(digest,str) or len(digest)!=64 or any(i not in "0123456789abcdef" for i in digest) or not isinstance(mode,int) or isinstance(mode,bool) or not 0<=mode<=0o777:raise ValueError("code baseline v2 file entry is invalid")
 drift=[]
 for name,digest in value["files"].items():
  target=root/name;mode=value["modes"][name]
  if target.is_symlink() or not target.is_file():drift.append({"path":name,"reason":"MISSING_OR_UNSAFE"})
  elif sha(target)!=digest or target.stat().st_mode&0o777!=mode:drift.append({"path":name,"reason":"CONTENT_OR_MODE_CHANGED"})
 return {"state":"DRIFTED" if drift else "CURRENT","reference":{"path":BASELINE,"sha256":sha(path)},"files":value["files"],"drift":drift}
def assess(plan:dict,root:Path,approval_ref:dict|None=None)->dict:
 build=build_capability(root,plan["target"]["modulePath"]);schemas=schema_blockers(plan);git=git_state(root,plan["target"]["modulePath"]);base=baseline(root);blockers=[]
 if not build["ready"]:blockers.append({"code":"BUILD_CAPABILITY_MISSING","subject":"build"})
 blockers.extend(schemas)
 if base["state"]=="DRIFTED":blockers.append({"code":"BASELINE_DRIFT","subject":", ".join(i["path"] for i in base["drift"])})
 if any(i["fileAction"]=="UPDATE_FILE" for i in plan["components"]):blockers.append({"code":"UPDATE_RENDERER_NOT_IMPLEMENTED","subject":"existing source"})
 renderer=plan["capability"]["codeDryRunRenderer"]
 if renderer=="NOT_IMPLEMENTED":blockers.append({"code":"RENDERER_NOT_IMPLEMENTED","subject":"capability"})
 return {"springCodeRenderabilityVersion":2,"target":str(root),"planId":plan["planId"],"implementationPlanApproval":approval_ref,"git":git,"buildCapability":build,"schemaBlockers":schemas,"baseline":base,"limits":{"maxFiles":MAX_FILES,"maxFileBytes":MAX_FILE_BYTES,"maxTotalBytes":MAX_TOTAL_BYTES},"coverageLevel":"API_CONTRACT_ONLY","blockers":blockers,"renderer":renderer,"readyForCodeDryRun":not blockers,"effects":{"sourceChanged":False,"testsExecuted":False,"network":"NOT_USED","docker":"NOT_USED","gitCommitOrPush":"NOT_RUN"}}
