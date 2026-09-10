#!/usr/bin/env python3
"""Build and revalidate an exact Java MVC API-only candidate report v2."""
from __future__ import annotations
import hashlib,re,tempfile
from pathlib import Path,PurePosixPath
from http_api_spring_mapping import reference
from spring_code_renderability_v2 import MAX_FILES,MAX_FILE_BYTES,MAX_TOTAL_BYTES,assess,sha
from validate_feature_specs import load_object
from validate_spring_implementation_plan_v2_approval import validate_approval

PACKAGE=re.compile(r"(?m)^\s*package\s+([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)\s*;")
PUBLIC_TYPE=re.compile(r"\bpublic\s+(?:final\s+)?(?:class|interface|record|enum)\s+([A-Z][A-Za-z0-9_]*)\b")
ASSERTION=re.compile(r"\b(?:assertThat|assertEquals|assertTrue|assertFalse|andExpect|verify)\s*\(")
SECRET=re.compile(r'''(?ix)\b(?:password|secret|api[_-]?key|access[_-]?token)\b\s*=\s*["'][^"'\n$]{4,}["']''')
ROLE_MARKERS={"CONTROLLER":["@RestController"],"APPLICATION_SERVICE":["@Service"],"TEST":["@Test"]}
MAPPINGS={"GET":"GetMapping","POST":"PostMapping","PUT":"PutMapping","PATCH":"PatchMapping","DELETE":"DeleteMapping"}
PARAMETERS={"path":"PathVariable","query":"RequestParam","header":"RequestHeader","cookie":"CookieValue"}

def package_for(component:dict)->str:
 path=component["target"]["path"].replace("\\","/")
 marker="/java/"
 if marker not in path:raise ValueError("component is not under a Java source root")
 tail=path.split(marker,1)[1].rsplit("/",1)[0]
 return tail.replace("/",".")
def safe_relative(value:str)->PurePosixPath:
 path=PurePosixPath(value)
 if path.is_absolute() or ".." in path.parts or path.suffix!=".java" or not path.parts:raise ValueError(f"unsafe Java candidate path: {value}")
 return path
def files(root:Path)->dict[str,Path]:
 if root.is_symlink() or not root.is_dir():raise ValueError("candidate root must be a non-symlink directory")
 found={}
 for path in root.rglob("*"):
  if path.is_symlink():raise ValueError("candidate contains a symlink")
  if path.is_file():
   rel=path.relative_to(root).as_posix();safe_relative(rel);found[rel]=path
 if len(found)>MAX_FILES:raise ValueError("candidate file count exceeds limit")
 if any(i.stat().st_size>MAX_FILE_BYTES for i in found.values()):raise ValueError("candidate file exceeds size limit")
 if sum(i.stat().st_size for i in found.values())>MAX_TOTAL_BYTES:raise ValueError("candidate total size exceeds limit")
 return found
def schema_value(plan:dict,schema:dict|None)->dict:
 value=schema or {}
 ref=value.get("$ref") if isinstance(value,dict) else None
 if isinstance(ref,str) and ref.startswith("#/components/schemas/"):return plan["schemaCatalog"].get(ref.rsplit("/",1)[-1],{})
 return value
def java_type(schema:dict)->str:
 kind=schema.get("type")
 if kind=="string":return {"uuid":"UUID","date":"LocalDate","date-time":"OffsetDateTime"}.get(schema.get("format"),"String")
 if kind=="integer":return "Long" if schema.get("format")=="int64" else "Integer"
 if kind=="number":return "Float" if schema.get("format")=="float" else "Double"
 if kind=="boolean":return "Boolean"
 if kind=="array":return "List"
 if kind=="object":return "Object"
 return "Object"
def dto_shape(plan:dict,component:dict)->dict[str,str]:
 shapes=[]
 for operation in plan["operationLinks"]:
  if component["componentId"] not in operation["componentRefs"]:continue
  semantics=operation["implementationSemantics"]
  if component["role"]=="REQUEST_DTO" and semantics["requestBody"]:
   for schema in semantics["requestBody"]["content"].values():shapes.append(schema_value(plan,schema))
  if component["role"]=="RESPONSE_DTO":
   for response in semantics["responses"].values():
    for schema in response["content"].values():shapes.append(schema_value(plan,schema))
 properties={}
 for shape in shapes:
  for name,value in shape.get("properties",{}).items():properties[name]=java_type(schema_value(plan,value))
 return properties
def declared_fields(content:str)->dict[str,str]:
 record=re.search(r"\brecord\s+[A-Z][A-Za-z0-9_]*\s*\((.*?)\)\s*\{",content,re.S)
 body=record.group(1) if record else content
 pairs=re.findall(r"\b(String|Integer|Long|Float|Double|Boolean|UUID|LocalDate|OffsetDateTime|List(?:<[^>]+>)?|Object)\s+([a-z][A-Za-z0-9_]*)\b",body)
 return {name:"List" if kind.startswith("List") else kind for kind,name in pairs}
def annotation_has(content:str,annotation:str,name:str)->bool:
 return any(re.search(r"[\"']"+re.escape(name)+r"[\"']",body) for body in re.findall(r"@"+annotation+r"\s*\(([^)]*)\)",content))
def field_has_annotation(content:str,name:str,annotations:set[str])->bool:
 match=re.search(r"((?:@\w+(?:\([^)]*\))?\s*)*)\b(?:String|Integer|Long|Float|Double|Boolean|UUID|LocalDate|OffsetDateTime|List(?:<[^>]+>)?|Object)\s+"+re.escape(name)+r"\b",content)
 return bool(match and any("@"+item in match.group(1) for item in annotations))
def component_checks(plan:dict,component:dict,content:str)->tuple[list[dict],list[dict]]:
 cid=component["componentId"];path=component["target"]["path"];checks=[];conflicts=[]
 def check(name:str,ok:bool,reason:str):
  checks.append({"check":name,"componentRef":cid,"state":"PASSED" if ok else "FAILED"})
  if not ok:conflicts.append({"path":path,"reason":reason})
 package=PACKAGE.search(content);public=PUBLIC_TYPE.search(content)
 check("JAVA_IDENTITY",bool(package and package.group(1)==package_for(component) and public and public.group(1)==component["target"]["typeName"]),"package-or-public-type-mismatch")
 markers=ROLE_MARKERS.get(component["role"],[]);check("SPRING_ROLE",all(i in content for i in markers),"missing-role-marker")
 check("NO_SECRET_LITERAL",not SECRET.search(content),"hardcoded-secret-like-literal")
 if component["role"]=="CONTROLLER":
  for symbol in component["symbols"]:
   annotation=MAPPINGS.get(symbol["httpMethod"],"");ok=bool(annotation and re.search(r"@"+annotation+r"\s*\(\s*(?:(?:path|value)\s*=\s*)?[\"']"+re.escape(symbol["httpPath"])+r"[\"']",content))
   check("HTTP_MAPPING:"+symbol["operationId"],ok,"http-mapping-mismatch:"+symbol["operationId"])
  for operation in plan["operationLinks"]:
   if cid not in operation["componentRefs"]:continue
   for parameter in operation["implementationSemantics"]["parameters"]:
    annotation=PARAMETERS.get(parameter["in"],"");ok=bool(annotation and annotation_has(content,annotation,parameter["name"]))
    check("HTTP_PARAMETER:"+operation["operationId"]+":"+parameter["name"],ok,"http-parameter-mismatch:"+parameter["name"])
   body=operation["implementationSemantics"]["requestBody"]
   if body:
    media_ok="application/json" not in body["content"] or "application/json" in content or "APPLICATION_JSON_VALUE" in content
    check("REQUEST_BODY:"+operation["operationId"],"@RequestBody" in content and (not body["required"] or "@Valid" in content) and media_ok,"request-body-media-or-validation-mismatch:"+operation["operationId"])
   for status in operation["implementationSemantics"]["responses"]:
    ok=status=="default" or status=="200" or status in content or {"201":"CREATED","204":"NO_CONTENT"}.get(status,"") in content
    check("RESPONSE_STATUS:"+operation["operationId"]+":"+status,ok,"response-status-mismatch:"+status)
    response=operation["implementationSemantics"]["responses"][status]
    media_ok="application/json" not in response["content"] or "application/json" in content or "APPLICATION_JSON_VALUE" in content
    check("RESPONSE_MEDIA:"+operation["operationId"]+":"+status,media_ok,"response-media-mismatch:"+status)
    for header in response["headers"]:check("RESPONSE_HEADER:"+operation["operationId"]+":"+header,header in content,"response-header-missing:"+header)
 elif component["role"] in {"REQUEST_DTO","RESPONSE_DTO"}:
  expected=dto_shape(plan,component);actual=declared_fields(content)
  check("DTO_SHAPE",actual==expected,"dto-shape-mismatch")
  if component["role"]=="REQUEST_DTO":
   required=set()
   for operation in plan["operationLinks"]:
    if cid in operation["componentRefs"] and operation["implementationSemantics"]["requestBody"]:
     for raw in operation["implementationSemantics"]["requestBody"]["content"].values():required.update(schema_value(plan,raw).get("required",[]))
   check("DTO_REQUIRED_VALIDATION",all(field_has_annotation(content,name,{"NotNull","NotBlank","NotEmpty"}) for name in required),"dto-required-validation-missing")
 elif component["role"]=="APPLICATION_SERVICE":
  check("SERVICE_OPERATIONS",all(re.search(r"\b"+re.escape(i)+r"\s*\(",content) for i in component["operationRefs"]),"service-operation-missing")
 elif component["role"]=="TEST":
  check("EXECUTABLE_ASSERTION",bool(ASSERTION.search(content)),"test-has-no-executable-assertion")
  check("REQUIREMENT_TRACEABILITY",all(i in content for i in component["requirementRefs"]),"test-requirement-traceability-missing")
  for operation in plan["operationLinks"]:
   if cid in operation["testRefs"]:check("TEST_API_CONTRACT:"+operation["operationId"],operation["method"] in content and operation["path"] in content,"test-api-contract-missing:"+operation["operationId"])
 return checks,conflicts
def build_report(plan:dict,approval_ref:dict,renderability_ref:dict,renderability:dict,candidate:Path,root:Path)->dict:
 if plan["capability"]["codeDryRunRenderer"]!="JAVA_MVC_API_ONLY_V1":raise ValueError("approved plan has no supported v2 renderer")
 if not renderability["readyForCodeDryRun"] or renderability["renderer"]!="JAVA_MVC_API_ONLY_V1":raise ValueError("renderability gate is not ready")
 expected_create={i["target"]["path"]:i for i in plan["components"] if i["fileAction"]=="CREATE_FILE"};reuse=[i for i in plan["components"] if i["fileAction"]=="REUSE_FILE"]
 unsupported=[i for i in plan["components"] if i["fileAction"] not in {"CREATE_FILE","REUSE_FILE"}]
 found=files(candidate);conflicts=[];checks=[];generated=[];reused=[]
 for path in sorted(set(expected_create)-set(found)):conflicts.append({"path":path,"reason":"planned-create-file-missing"})
 for path in sorted(set(found)-set(expected_create)):conflicts.append({"path":path,"reason":"candidate-file-not-in-create-plan"})
 for component in unsupported:conflicts.append({"path":component["target"]["path"],"reason":"file-action-not-renderable:"+component["fileAction"]})
 for path,component in sorted(expected_create.items()):
  target=root/path
  escaped=root not in target.resolve().parents;parent_symlink=any(i.is_symlink() for i in target.parents if i!=root and root in i.resolve().parents)
  if escaped or parent_symlink:conflicts.append({"path":path,"reason":"create-target-path-is-unsafe"})
  elif target.exists() or target.is_symlink():conflicts.append({"path":path,"reason":"create-target-is-occupied"})
  if path in found:
   try:content=found[path].read_text(encoding="utf-8")
   except UnicodeDecodeError:conflicts.append({"path":path,"reason":"candidate-is-not-utf8"});continue
   item_checks,item_conflicts=component_checks(plan,component,content);checks+=item_checks;conflicts+=item_conflicts
   generated.append({"componentRef":component["componentId"],"role":component["role"],"path":path,"mode":0o644,"sha256":hashlib.sha256(content.encode()).hexdigest(),"content":content})
 for component in reuse:
  path=component["target"]["path"];target=root/path;evidence=component["sourceEvidence"]
  ok=target.is_file() and not target.is_symlink() and len(evidence)==1 and reference(target,root)==evidence[0]
  checks.append({"check":"REUSE_EVIDENCE","componentRef":component["componentId"],"state":"PASSED" if ok else "FAILED"})
  if not ok:conflicts.append({"path":path,"reason":"reuse-source-evidence-changed"})
  else:reused.append({"componentRef":component["componentId"],"path":path,"sha256":sha(target),"mode":target.stat().st_mode&0o777})
 manifest={"manifestVersion":2,"artifactKind":"SPRING_IMPLEMENTATION_V2","files":dict(renderability["baseline"]["files"]),"modes":{}}
 if renderability["baseline"]["reference"]:
  from validate_feature_specs import load_object
  manifest["modes"].update(load_object(root/renderability["baseline"]["reference"]["path"])["modes"])
 for item in generated:manifest["files"][item["path"]]=item["sha256"];manifest["modes"][item["path"]]=item["mode"]
 blockers=sorted(conflicts,key=lambda i:(i["path"],i["reason"]));ready=not blockers and all(i["state"]=="PASSED" for i in checks) and len(generated)==len(expected_create)
 return {"springCodeDryRunVersion":2,"target":str(root),"planId":plan["planId"],"implementationPlanApproval":approval_ref,"renderability":renderability_ref,"renderer":"JAVA_MVC_API_ONLY_V1","coverageLevel":"API_CONTRACT_ONLY","summary":{"operations":len(plan["operationLinks"]),"creates":len(generated),"reuses":len(reused),"updates":0,"blockers":len(blockers)},"qualityChecks":checks,"generatedFiles":generated,"reusedFiles":reused,"desiredManifest":manifest,"blockers":blockers,"verification":{"compilation":"NOT_RUN","tests":"NOT_RUN","businessBehavior":"NOT_PROVEN"},"readyForVerificationApproval":ready,"effects":{"sourceChanged":False,"testsExecuted":False,"network":"NOT_USED","docker":"NOT_USED","gitCommitOrPush":"NOT_RUN"}}
def current_context(root:Path,approval_path:Path,renderability_path:Path)->tuple[dict,dict,dict,dict]:
 receipt=validate_approval(root,approval_path);approval_ref=reference(approval_path,root);plan=load_object(root/receipt["implementationPlan"]["path"])
 renderability=load_object(renderability_path);renderability_ref=reference(renderability_path,root)
 if renderability.get("implementationPlanApproval")!=approval_ref:raise ValueError("renderability is for another plan approval")
 expected=assess(plan,root,approval_ref)
 if renderability!=expected:raise ValueError("renderability report is stale")
 if not renderability["readyForCodeDryRun"]:raise ValueError("renderability gate has blockers")
 return plan,approval_ref,renderability,renderability_ref
def validate_report(report:dict,root:Path)->None:
 required={"springCodeDryRunVersion","target","planId","implementationPlanApproval","renderability","renderer","coverageLevel","summary","qualityChecks","generatedFiles","reusedFiles","desiredManifest","blockers","verification","readyForVerificationApproval","effects"}
 if not isinstance(report,dict) or set(report)!=required or report["springCodeDryRunVersion"]!=2 or Path(report["target"]).resolve()!=root:raise ValueError("Spring code dry-run v2 structure is invalid")
 approval=root/report["implementationPlanApproval"]["path"];renderability=root/report["renderability"]["path"]
 if reference(approval,root)!=report["implementationPlanApproval"] or reference(renderability,root)!=report["renderability"]:raise ValueError("dry-run input evidence changed")
 plan,approval_ref,gate,gate_ref=current_context(root,approval,renderability)
 with tempfile.TemporaryDirectory(prefix="spring-code-v2-recheck-") as temporary:
  candidate=Path(temporary)
  for item in report["generatedFiles"]:
   if set(item)!={"componentRef","role","path","mode","sha256","content"} or hashlib.sha256(item["content"].encode()).hexdigest()!=item["sha256"]:raise ValueError("generated file evidence is invalid")
   path=candidate/safe_relative(item["path"]);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(item["content"],encoding="utf-8")
  expected=build_report(plan,approval_ref,gate_ref,gate,candidate,root)
 if report!=expected:raise ValueError("Spring code dry-run v2 is stale or was modified")
