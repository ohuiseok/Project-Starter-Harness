#!/usr/bin/env python3
"""Build and validate a source-free HTTP API to Spring symbol mapping plan."""
from __future__ import annotations
import hashlib,re,subprocess
from pathlib import Path,PurePosixPath
from typing import Any
from existing_http_api_contract import controller_mappings,normalize_path
from http_api_contract import operations,security_option

LANGUAGES={"JAVA","KOTLIN"}; WEB_STACKS={"SPRING_MVC","WEBFLUX"}; ARCHITECTURES={"LAYERED","HEXAGONAL","CLEAN","MODULAR","MICROSERVICE","CUSTOM"}; DTO_STYLES={"CLASS","RECORD","KOTLIN_DATA_CLASS","CUSTOM"}; MAPPING_STYLES={"MANUAL","MAPSTRUCT","CUSTOM"}; TEST_CLIENTS={"MOCKMVC","WEBTESTCLIENT","CUSTOM"}; SOURCES={"USER_CONFIRMED","PROJECT_EVIDENCE","RECOMMENDATION_ACCEPTED"}
TYPE=re.compile(r"\b(?:class|interface|record|object|data\s+class)\s+(\w+)")

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def reference(path:Path,root:Path)->dict:
 p=path.resolve(strict=True)
 if path.is_symlink() or root not in p.parents or not p.is_file():raise ValueError("mapping input must be a target-owned regular file")
 return {"path":p.relative_to(root).as_posix(),"sha256":sha(p)}
def option(profile:dict,key:str)->str:
 value=profile.get("decisions",{}).get(key,{})
 return value.get("option","UNKNOWN") if isinstance(value,dict) else "UNKNOWN"
def dirty(root:Path)->set[str]:
 r=subprocess.run(["git","status","--porcelain","--untracked-files=all"],cwd=root,capture_output=True,text=True,check=False)
 return {line[3:].split(" -> ")[-1] for line in r.stdout.splitlines() if len(line)>3} if r.returncode==0 else set()
def source_files(root:Path,module:str)->list[Path]:
 base=(root/module).resolve()
 if root not in (base,*base.parents):raise ValueError("module path escapes target")
 return sorted([*base.glob("src/main/java/**/*.java"),*base.glob("src/main/kotlin/**/*.kt")])
def decision(value:str,source:str,detail:str|None)->dict:return {"value":value,"detail":detail,"source":source,"confirmedByUser":source in {"USER_CONFIRMED","RECOMMENDATION_ACCEPTED"}}
def type_name(operation_id:str,suffix:str)->str:
 base="".join(part[:1].upper()+part[1:] for part in re.split(r"[^A-Za-z0-9]+",re.sub(r"([a-z0-9])([A-Z])",r"\1 \2",operation_id)) if part)
 return base+suffix
def package_path(package:str)->str:return package.replace(".","/")

def build(feature:dict,profile:dict,openapi:dict,root:Path,module_path:str,package_name:str,choices:dict[str,str],decision_source:str,input_refs:dict,custom_details:dict[str,str]|None=None)->dict:
 if decision_source not in SOURCES:raise ValueError("decision source is invalid")
 language="KOTLIN" if option(profile,"language")=="language.kotlin" else "JAVA"
 defaults={"architecture":"LAYERED","webStack":"SPRING_MVC","dtoStyle":"KOTLIN_DATA_CLASS" if language=="KOTLIN" else "RECORD","mappingStyle":"MANUAL","testClient":"MOCKMVC"}
 resolved={key:choices.get(key) or value for key,value in defaults.items()}
 enums={"architecture":ARCHITECTURES,"webStack":WEB_STACKS,"dtoStyle":DTO_STYLES,"mappingStyle":MAPPING_STYLES,"testClient":TEST_CLIENTS}
 for key,allowed in enums.items():
  if resolved[key] not in allowed:raise ValueError(f"unsupported mapping decision: {key}={resolved[key]}")
  if resolved[key]=="CUSTOM" and not (custom_details or {}).get(key):raise ValueError(f"CUSTOM mapping decision requires a concise detail: {key}")
 conflicts=[]; unknowns=[]
 if resolved["webStack"]=="WEBFLUX" and resolved["testClient"]!="WEBTESTCLIENT":conflicts.append({"code":"TEST_STACK_MISMATCH","subject":"testClient","message":"WebFlux는 WebTestClient 검증이 필요합니다."})
 if resolved["webStack"]=="SPRING_MVC" and resolved["testClient"]=="WEBTESTCLIENT":conflicts.append({"code":"TEST_STACK_MISMATCH","subject":"testClient","message":"MVC 기본 검증에는 MockMvc가 권장됩니다."})
 if language=="JAVA" and resolved["dtoStyle"]=="KOTLIN_DATA_CLASS" or language=="KOTLIN" and resolved["dtoStyle"]=="RECORD":conflicts.append({"code":"DTO_LANGUAGE_MISMATCH","subject":"dtoStyle","message":"DTO 형식이 선택 언어와 맞지 않습니다."})
 files=source_files(root,module_path); dirty_set=dirty(root); observed=[]
 for path in files:
  rel=path.relative_to(root).as_posix(); text=path.read_text(encoding="utf-8",errors="replace"); types=TYPE.findall(text); result=controller_mappings(path,text)
  observed.append({"path":rel,"sha256":sha(path),"types":types,"mappings":sorted([{"method":m.upper(),"path":p} for m,p in result.mappings],key=lambda x:(x["path"],x["method"])),"unknowns":list(result.unknowns),"dirty":rel in dirty_set})
 operations_out=[]; required={i["id"] for i in feature.get("acceptanceCriteria",[])+feature.get("businessRules",[])}; covered=set()
 extension="kt" if language=="KOTLIN" else "java"; source_root="src/main/kotlin" if language=="KOTLIN" else "src/main/java"
 for path,method,operation in operations(openapi):
  oid=operation.get("operationId"); refs=sorted(operation.get("x-harness-requirement-refs",[])); covered.update(refs)
  exact=[item for item in observed if {"method":method.upper(),"path":normalize_path(path) or "/"} in item["mappings"]]
  uncertain=[item for item in observed if item["unknowns"]]
  controller_name=type_name(oid,"Controller"); planned=f"{module_path.rstrip('/')+'/' if module_path!='.' else ''}{source_root}/{package_path(package_name)}/api/{controller_name}.{extension}"
  disposition="REUSE" if len(exact)==1 else "UNKNOWN" if uncertain else "CONFLICT" if (root/planned).exists() else "CREATE"
  if len(exact)>1:disposition="CONFLICT"; conflicts.append({"code":"SYMBOL_OWNERSHIP_COLLISION","subject":oid,"message":"여러 Controller가 동일 endpoint를 소유합니다."})
  if disposition=="UNKNOWN":unknowns.append({"code":"CONTROLLER_MAPPING_UNKNOWN","subject":oid,"message":"커스텀 또는 비리터럴 매핑을 정적으로 확정할 수 없습니다.","evidencePaths":[i["path"] for i in uncertain]})
  security=operation.get("security",openapi.get("security",[])); secured=bool(security)
  components=[{"role":role,"typeName":type_name(oid,suffix),"disposition":disposition if role=="CONTROLLER" else "CREATE","plannedPath":planned if role=="CONTROLLER" else None,"candidateEvidence":[{"path":i["path"],"sha256":i["sha256"]} for i in exact]} for role,suffix in (("CONTROLLER","Controller"),("REQUEST_DTO","Request"),("RESPONSE_DTO","Response"),("APPLICATION_SERVICE","Service"))]
  tests=[{"kind":"CONTRACT","client":resolved["testClient"],"covers":[oid,*refs]},{"kind":"VALIDATION","client":resolved["testClient"],"covers":[oid]},{"kind":"SECURITY","client":resolved["testClient"],"covers":[oid]}] if secured else [{"kind":"CONTRACT","client":resolved["testClient"],"covers":[oid,*refs]},{"kind":"VALIDATION","client":resolved["testClient"],"covers":[oid]}]
  operations_out.append({"operationId":oid,"method":method.upper(),"path":path,"requirementRefs":refs,"security":{"required":secured,"profileOption":security_option(profile)},"components":components,"tests":tests})
 for ref in sorted(required-covered):conflicts.append({"code":"TRACEABILITY_GAP","subject":ref,"message":"어떤 API operation도 이 요구사항을 추적하지 않습니다."})
 if decision_source=="PROJECT_EVIDENCE" and any(resolved[k]!=defaults[k] for k in resolved):unknowns.append({"code":"DECISION_EVIDENCE_REQUIRED","subject":"mapping decisions","message":"프로젝트 증거 기반 선택의 정확한 근거가 필요합니다.","evidencePaths":[]})
 status="BLOCKED" if conflicts or unknowns else "REVIEW_READY"
 return {"httpApiSpringMappingVersion":1,"status":status,"featureId":feature["feature"]["id"],"target":{"root":str(root),"modulePath":module_path,"packageName":package_name,"language":language},"inputs":input_refs,"decisions":{k:decision(v,decision_source,(custom_details or {}).get(k)) for k,v in resolved.items()},"boundaries":{"apiDtoEntitySeparated":True,"persistence":"NOT_INFERRED_WITHOUT_DATA_CONTRACT","transactionOwner":"APPLICATION_SERVICE_IF_WRITE_CONTRACT","crossServiceRepositoryAccess":False},"operationMappings":operations_out,"sourceEvidence":observed,"conflicts":conflicts,"unknowns":unknowns,"summary":{"operations":len(operations_out),"create":sum(c["disposition"]=="CREATE" for o in operations_out for c in o["components"]),"reuse":sum(c["disposition"]=="REUSE" for o in operations_out for c in o["components"]),"conflict":len(conflicts),"unknown":len(unknowns),"tests":sum(len(o["tests"]) for o in operations_out)},"effects":{"sourceChanged":False,"testsExecuted":False,"codeDryRunAuthorized":False,"gitCommitOrPush":"NOT_RUN"}}

def validate(value:dict,root:Path)->list[str]:
 required={"httpApiSpringMappingVersion","status","featureId","target","inputs","decisions","boundaries","operationMappings","sourceEvidence","conflicts","unknowns","summary","effects"}
 if not isinstance(value,dict) or set(value)!=required or value.get("httpApiSpringMappingVersion")!=1:raise ValueError("HTTP API Spring mapping is invalid")
 blockers=[]
 if value["status"] not in {"BLOCKED","REVIEW_READY"}:raise ValueError("mapping status is invalid")
 if Path(value["target"]["root"]).resolve()!=root.resolve() or value["target"]["language"] not in LANGUAGES:raise ValueError("mapping target is invalid")
 module=PurePosixPath(value["target"]["modulePath"])
 if module.is_absolute() or ".." in module.parts or not value["target"]["packageName"]:raise ValueError("mapping module or package is unsafe")
 if value["boundaries"]!={"apiDtoEntitySeparated":True,"persistence":"NOT_INFERRED_WITHOUT_DATA_CONTRACT","transactionOwner":"APPLICATION_SERVICE_IF_WRITE_CONTRACT","crossServiceRepositoryAccess":False}:raise ValueError("mapping boundaries are invalid")
 if set(value["decisions"])!={"architecture","webStack","dtoStyle","mappingStyle","testClient"}:raise ValueError("mapping decisions are incomplete")
 allowed_by_decision={"architecture":ARCHITECTURES,"webStack":WEB_STACKS,"dtoStyle":DTO_STYLES,"mappingStyle":MAPPING_STYLES,"testClient":TEST_CLIENTS}
 for name,item in value["decisions"].items():
  if set(item)!={"value","detail","source","confirmedByUser"} or item["source"] not in SOURCES or item["confirmedByUser"]!=(item["source"] in {"USER_CONFIRMED","RECOMMENDATION_ACCEPTED"}):raise ValueError(f"mapping decision is invalid: {name}")
  if item["value"] not in allowed_by_decision[name]:raise ValueError(f"mapping decision value is invalid: {name}")
  if item["value"]=="CUSTOM" and not isinstance(item["detail"],str):raise ValueError(f"custom mapping decision detail is missing: {name}")
 for name,item in value["inputs"].items():
  path=root/item["path"]; pure=PurePosixPath(item["path"])
  if set(item)!={"path","sha256"} or pure.is_absolute() or ".." in pure.parts or path.is_symlink() or not path.is_file() or sha(path)!=item["sha256"]:blockers.append(f"input changed: {name}")
 for item in value["sourceEvidence"]:
  path=root/item["path"]
  if not path.is_file() or path.is_symlink() or sha(path)!=item["sha256"]:blockers.append(f"source evidence changed: {item['path']}")
 operation_ids=[i["operationId"] for i in value["operationMappings"]]
 if not operation_ids or len(operation_ids)!=len(set(operation_ids)):raise ValueError("operation mappings must be non-empty and unique")
 for operation in value["operationMappings"]:
  if set(operation)!={"operationId","method","path","requirementRefs","security","components","tests"} or not operation["path"].startswith("/"):raise ValueError("operation mapping structure is invalid")
  roles=[item.get("role") for item in operation["components"]]
  if roles!=["CONTROLLER","REQUEST_DTO","RESPONSE_DTO","APPLICATION_SERVICE"]:raise ValueError("operation component roles are invalid")
  for component in operation["components"]:
   if set(component)!={"role","typeName","disposition","plannedPath","candidateEvidence"} or component["disposition"] not in {"CREATE","REUSE","CONFLICT","UNKNOWN"}:raise ValueError("operation component is invalid")
   if component["plannedPath"] is not None:
    planned=PurePosixPath(component["plannedPath"])
    if planned.is_absolute() or ".." in planned.parts:raise ValueError("planned component path is unsafe")
  for test in operation["tests"]:
   if set(test)!={"kind","client","covers"} or test["kind"] not in {"CONTRACT","VALIDATION","SECURITY"} or test["client"] not in TEST_CLIENTS or operation["operationId"] not in test["covers"]:raise ValueError("operation test mapping is invalid")
  if operation["security"]["required"] and not any(test["kind"]=="SECURITY" for test in operation["tests"]):blockers.append(f"secured operation lacks security test: {operation['operationId']}")
 if value["status"]=="REVIEW_READY" and (value["conflicts"] or value["unknowns"]):blockers.append("REVIEW_READY mapping has unresolved items")
 expected={"operations":len(value["operationMappings"]),"create":sum(c["disposition"]=="CREATE" for o in value["operationMappings"] for c in o["components"]),"reuse":sum(c["disposition"]=="REUSE" for o in value["operationMappings"] for c in o["components"]),"conflict":len(value["conflicts"]),"unknown":len(value["unknowns"]),"tests":sum(len(o["tests"]) for o in value["operationMappings"])}
 if value["summary"]!=expected:raise ValueError("mapping summary is inconsistent")
 return blockers
