#!/usr/bin/env python3
"""Build and validate a source-free HTTP API to Spring symbol mapping plan."""
from __future__ import annotations
import hashlib,re,subprocess,json
from pathlib import Path,PurePosixPath
from typing import Any
from existing_http_api_contract import controller_mappings,normalize_path
from http_api_contract import operations,security_option

LANGUAGES={"JAVA","KOTLIN"}; WEB_STACKS={"SPRING_MVC","WEBFLUX"}; ARCHITECTURES={"LAYERED","HEXAGONAL","CLEAN","MODULAR","MICROSERVICE","CUSTOM"}; DTO_STYLES={"CLASS","RECORD","KOTLIN_DATA_CLASS","CUSTOM"}; MAPPING_STYLES={"MANUAL","MAPSTRUCT","CUSTOM"}; TEST_CLIENTS={"MOCKMVC","WEBTESTCLIENT","CUSTOM"}; SOURCES={"USER_CONFIRMED","PROJECT_EVIDENCE","RECOMMENDATION_ACCEPTED"}
TYPE=re.compile(r"\b(?:class|interface|record|object|data\s+class)\s+(\w+)")
PACKAGE=re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"); SECRET=re.compile(r"(?i)(password|secret|token|api[_-]?key|private[_-]?key)"); PII=re.compile(r"(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b)")

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
def child_mappings(root:Path,mapping_path:Path)->list[Path]:
 expected=reference(mapping_path,root);found=[]
 for path in (root/"docs").glob("**/*.json") if (root/"docs").is_dir() else []:
  try:value=json.loads(path.read_text())
  except (OSError,json.JSONDecodeError):continue
  if value.get("httpApiSpringMappingVersion")==2 and value.get("revision",{}).get("previous")==expected:found.append(path)
 return found
def mapping_cancellations(root:Path,mapping_path:Path)->list[Path]:
 expected=reference(mapping_path,root);found=[]
 for path in (root/"docs").glob("**/*.json") if (root/"docs").is_dir() else []:
  try:value=json.loads(path.read_text())
  except (OSError,json.JSONDecodeError):continue
  if value.get("httpApiSpringMappingCancellationVersion")==1 and value.get("mapping")==expected:found.append(path)
 return found
def validate_contract_current(value:dict,root:Path)->None:
 from validate_feature_specs import load_object
 from http_api_contract import validate_http_contract
 from existing_http_api_contract import validate_existing_contract
 inputs=value["inputs"];feature=load_object(root/inputs["featureSpec"]["path"]);profile=load_object(root/inputs["technologyProfile"]["path"]);route_path=root/inputs["designRoute"]["path"];route=load_object(route_path);contract_path=root/inputs["httpApiContract"]["path"];metadata=load_object(contract_path)
 if metadata.get("disposition")=="CREATE":approved,blockers,openapi=validate_http_contract(metadata,route,route_path,root,contract_path,feature,profile)
 elif metadata.get("disposition") in {"EXTEND","REUSE"}:approved,blockers,openapi,_=validate_existing_contract(metadata,route,route_path,root,contract_path,feature,profile)
 else:raise ValueError("HTTP API contract disposition is unsupported")
 if not approved or blockers:raise ValueError("HTTP API contract is no longer approved and current: "+"; ".join(blockers))
 if openapi!=load_object(root/inputs["openApi"]["path"]):raise ValueError("mapped OpenAPI is not the approved contract artifact")

def build(feature:dict,profile:dict,openapi:dict,root:Path,module_path:str,package_name:str,choices:dict[str,str],decision_source:str,input_refs:dict,custom_details:dict[str,str]|None=None,max_files:int=2000,max_bytes:int=20_000_000,revision:dict|None=None,custom_layout:dict[str,str]|None=None)->dict:
 if decision_source not in SOURCES:raise ValueError("decision source is invalid")
 metadata=json.loads((root/input_refs["httpApiContract"]["path"]).read_text()); route=json.loads((root/input_refs["designRoute"]["path"]).read_text())
 language="KOTLIN" if option(profile,"language")=="language.kotlin" else "JAVA"
 defaults={"architecture":"LAYERED","webStack":"SPRING_MVC","dtoStyle":"KOTLIN_DATA_CLASS" if language=="KOTLIN" else "RECORD","mappingStyle":"MANUAL","testClient":"MOCKMVC"}
 resolved={key:choices.get(key) or value for key,value in defaults.items()}
 enums={"architecture":ARCHITECTURES,"webStack":WEB_STACKS,"dtoStyle":DTO_STYLES,"mappingStyle":MAPPING_STYLES,"testClient":TEST_CLIENTS}
 for key,allowed in enums.items():
  if resolved[key] not in allowed:raise ValueError(f"unsupported mapping decision: {key}={resolved[key]}")
  if resolved[key]=="CUSTOM" and not (custom_details or {}).get(key):raise ValueError(f"CUSTOM mapping decision requires a concise detail: {key}")
 for detail in (custom_details or {}).values():
  if SECRET.search(detail) or PII.search(detail):raise ValueError("custom mapping detail contains secret-like or personal data")
 if custom_layout:
  if set(custom_layout)!={"controller","service","dto"} or any(not re.fullmatch(r"[a-z][a-z0-9_/]*",path) or "//" in path for path in custom_layout.values()):raise ValueError("custom architecture role paths are invalid")
 conflicts=[]; unknowns=[]
 if metadata.get("target",{}).get("modulePath") not in {None,module_path}:conflicts.append({"code":"MODULE_TARGET_MISMATCH","subject":module_path,"message":"선택 모듈이 승인된 API 계약 대상과 다릅니다."})
 route_matches=[i for i in route.get("routes",[]) if i.get("contractId")==metadata.get("contractId")]
 if route_matches and (route_matches[0].get("target",{}).get("projectId")!=metadata.get("target",{}).get("projectId") or route_matches[0].get("target",{}).get("modulePath")!=module_path):conflicts.append({"code":"ROUTE_TARGET_MISMATCH","subject":module_path,"message":"선택 모듈이 최신 route 대상과 다릅니다."})
 if resolved["webStack"]=="WEBFLUX" and resolved["testClient"]!="WEBTESTCLIENT":conflicts.append({"code":"TEST_STACK_MISMATCH","subject":"testClient","message":"WebFlux는 WebTestClient 검증이 필요합니다."})
 if resolved["webStack"]=="SPRING_MVC" and resolved["testClient"]=="WEBTESTCLIENT":conflicts.append({"code":"TEST_STACK_MISMATCH","subject":"testClient","message":"MVC 기본 검증에는 MockMvc가 권장됩니다."})
 if language=="JAVA" and resolved["dtoStyle"]=="KOTLIN_DATA_CLASS" or language=="KOTLIN" and resolved["dtoStyle"]=="RECORD":conflicts.append({"code":"DTO_LANGUAGE_MISMATCH","subject":"dtoStyle","message":"DTO 형식이 선택 언어와 맞지 않습니다."})
 files=source_files(root,module_path); dirty_set=dirty(root); observed=[]; scanned_bytes=0
 if len(files)>max_files:unknowns.append({"code":"SOURCE_SCAN_LIMIT","subject":"source files","message":"소스 파일 수가 분석 한도를 초과했습니다.","evidencePaths":[]})
 for path in files[:max_files]:
  size=path.stat().st_size
  if scanned_bytes+size>max_bytes:unknowns.append({"code":"SOURCE_SCAN_LIMIT","subject":"source bytes","message":"소스 크기가 분석 한도를 초과했습니다.","evidencePaths":[]});break
  scanned_bytes+=size
  rel=path.relative_to(root).as_posix(); text=path.read_text(encoding="utf-8",errors="replace"); types=TYPE.findall(text); result=controller_mappings(path,text)
  observed.append({"path":rel,"sha256":sha(path),"types":types,"mappings":sorted([{"method":m.upper(),"path":p} for m,p in result.mappings],key=lambda x:(x["path"],x["method"])),"unknowns":list(result.unknowns),"dirty":rel in dirty_set})
 operations_out=[]; required={i["id"] for i in feature.get("acceptanceCriteria",[])+feature.get("businessRules",[])}; covered=set(); relevant_paths=set()
 extension="kt" if language=="KOTLIN" else "java"; source_root="src/main/kotlin" if language=="KOTLIN" else "src/main/java"
 for path,method,operation in operations(openapi):
  oid=operation.get("operationId"); refs=sorted(operation.get("x-harness-requirement-refs",[])); covered.update(refs)
  exact=[item for item in observed if {"method":method.upper(),"path":normalize_path(path) or "/"} in item["mappings"]]
  controller_tokens={type_name(oid,"Controller"),"Controller"}; uncertain=[item for item in observed if item["unknowns"] and (set(item["types"])&controller_tokens or item["path"].endswith("Controller.java") or item["path"].endswith("Controller.kt"))]
  controller_name=type_name(oid,"Controller"); planned=f"{module_path.rstrip('/')+'/' if module_path!='.' else ''}{source_root}/{package_path(package_name)}/api/{controller_name}.{extension}"
  disposition="REUSE" if len(exact)==1 else "UNKNOWN" if uncertain else "CONFLICT" if (root/planned).exists() else "CREATE"
  if len(exact)>1:disposition="CONFLICT"; conflicts.append({"code":"SYMBOL_OWNERSHIP_COLLISION","subject":oid,"message":"여러 Controller가 동일 endpoint를 소유합니다."})
  for item in exact+uncertain:relevant_paths.add(item["path"])
  if any(item["dirty"] for item in exact):conflicts.append({"code":"DIRTY_REUSE_EVIDENCE","subject":oid,"message":"재사용할 Controller 증거에 미커밋 변경이 있습니다."})
  if disposition=="UNKNOWN":unknowns.append({"code":"CONTROLLER_MAPPING_UNKNOWN","subject":oid,"message":"커스텀 또는 비리터럴 매핑을 정적으로 확정할 수 없습니다.","evidencePaths":[i["path"] for i in uncertain]})
  security=operation.get("security",openapi.get("security",[])); secured=bool(security)
  request_needed=isinstance(operation.get("requestBody"),dict); success=[(str(code),value) for code,value in operation.get("responses",{}).items() if str(code).startswith("2")]; response_needed=any(isinstance(v,dict) and v.get("content") for _,v in success)
  role_defs=[("CONTROLLER","Controller","api"),("APPLICATION_SERVICE","Service","application")]+([("REQUEST_DTO","Request","api")] if request_needed else [])+([("RESPONSE_DTO","Response","api")] if response_needed else [])
  feature_key=re.sub(r"[^a-z0-9_]","",oid.lower());custom_dirs={"CONTROLLER":(custom_layout or {}).get("controller","custom"),"APPLICATION_SERVICE":(custom_layout or {}).get("service","custom"),"REQUEST_DTO":(custom_layout or {}).get("dto","custom"),"RESPONSE_DTO":(custom_layout or {}).get("dto","custom")};arch_dirs={"LAYERED":{"CONTROLLER":"api","APPLICATION_SERVICE":"application","REQUEST_DTO":"api","RESPONSE_DTO":"api"},"HEXAGONAL":{"CONTROLLER":"adapter/in/web","APPLICATION_SERVICE":"application/port/in","REQUEST_DTO":"adapter/in/web","RESPONSE_DTO":"adapter/in/web"},"CLEAN":{"CONTROLLER":"interfaceadapter/web","APPLICATION_SERVICE":"usecase","REQUEST_DTO":"interfaceadapter/web","RESPONSE_DTO":"interfaceadapter/web"},"MODULAR":{"CONTROLLER":f"feature/{feature_key}/api","APPLICATION_SERVICE":f"feature/{feature_key}/application","REQUEST_DTO":f"feature/{feature_key}/api","RESPONSE_DTO":f"feature/{feature_key}/api"},"MICROSERVICE":{"CONTROLLER":"api","APPLICATION_SERVICE":"application","REQUEST_DTO":"api","RESPONSE_DTO":"api"},"CUSTOM":custom_dirs}[resolved["architecture"]]
  components=[]
  for role,suffix,_ in role_defs:
   name=type_name(oid,suffix); component_path=f"{module_path.rstrip('/')+'/' if module_path!='.' else ''}{source_root}/{package_path(package_name)}/{arch_dirs[role]}/{name}.{extension}"; candidates=[item for item in observed if name in item["types"]]
   if role=="CONTROLLER" and len(exact)==1:
    component_path=exact[0]["path"]
    if len(exact[0]["types"])==1:name=exact[0]["types"][0]
   for item in candidates:relevant_paths.add(item["path"])
   exact_symbol=[item for item in candidates if item["path"]==component_path]
   state=disposition if role=="CONTROLLER" else "CONFLICT" if len(candidates)>1 else "EXTEND" if len(exact_symbol)==1 else "UNKNOWN" if candidates else "CONFLICT" if (root/component_path).exists() else "CREATE"
   if role!="CONTROLLER" and state=="UNKNOWN":unknowns.append({"code":"SYMBOL_LOCATION_REVIEW","subject":name,"message":"같은 이름의 심볼이 다른 위치에 있어 재사용 또는 확장을 확정할 수 없습니다.","evidencePaths":[i["path"] for i in candidates]})
   evidence=exact if role=="CONTROLLER" and exact else candidates
   components.append({"role":role,"typeName":name,"disposition":state,"plannedPath":component_path,"candidateEvidence":[{"path":i["path"],"sha256":i["sha256"]} for i in evidence]})
  schemes=[];scopes=[]
  for requirement in security if isinstance(security,list) else []:
   if isinstance(requirement,dict):
    schemes.extend(requirement);scopes.extend(scope for values in requirement.values() if isinstance(values,list) for scope in values)
  response_codes=sorted(str(i) for i in operation.get("responses",{})); tests=[{"kind":"CONTRACT","client":resolved["testClient"],"covers":[oid,*refs],"cases":response_codes},{"kind":"VALIDATION","client":resolved["testClient"],"covers":[oid],"cases":["request-validation"] if request_needed else ["path-query-validation"]}]
  if secured:tests.append({"kind":"SECURITY","client":resolved["testClient"],"covers":[oid],"cases":["unauthenticated-401","forbidden-403",*sorted(set(scopes))]})
  operations_out.append({"operationId":oid,"method":method.upper(),"path":path,"requirementRefs":refs,"security":{"required":secured,"profileOption":security_option(profile),"schemes":sorted(set(schemes)),"scopes":sorted(set(scopes)),"csrf":"REQUIRED" if security_option(profile)=="security.session" and method.lower() not in {"get","head","options"} else "NOT_REQUIRED","methodSecurity":bool(scopes)},"components":components,"tests":tests})
 for ref in sorted(required-covered):conflicts.append({"code":"TRACEABILITY_GAP","subject":ref,"message":"어떤 API operation도 이 요구사항을 추적하지 않습니다."})
 evidence_candidates=[root/module_path/name for name in ("build.gradle","build.gradle.kts","pom.xml","settings.gradle","settings.gradle.kts")]+list((root/module_path/"src/main/resources").glob("application*")) if (root/module_path/"src/main/resources").is_dir() else [root/module_path/name for name in ("build.gradle","build.gradle.kts","pom.xml","settings.gradle","settings.gradle.kts")]
 decision_evidence=[reference(path,root) for path in evidence_candidates if path.is_file() and not path.is_symlink()]
 if decision_source=="PROJECT_EVIDENCE" and not decision_evidence:unknowns.append({"code":"DECISION_EVIDENCE_REQUIRED","subject":"mapping decisions","message":"프로젝트 기반 선택을 증명할 build/config 파일이 없습니다.","evidencePaths":[]})
 if decision_source=="PROJECT_EVIDENCE" and decision_evidence:
  evidence_text="\n".join((root/i["path"]).read_text(encoding="utf-8",errors="replace") for i in decision_evidence)
  if resolved["webStack"]=="WEBFLUX" and "spring-boot-starter-webflux" not in evidence_text:unknowns.append({"code":"DECISION_EVIDENCE_MISMATCH","subject":"webStack","message":"build 증거가 WebFlux 선택을 증명하지 않습니다.","evidencePaths":[i["path"] for i in decision_evidence]})
  if resolved["mappingStyle"]=="MAPSTRUCT" and "mapstruct" not in evidence_text.lower():unknowns.append({"code":"DECISION_EVIDENCE_MISMATCH","subject":"mappingStyle","message":"build 증거가 MapStruct 선택을 증명하지 않습니다.","evidencePaths":[i["path"] for i in decision_evidence]})
 if resolved["architecture"]=="MICROSERVICE" and module_path==".":conflicts.append({"code":"SERVICE_BOUNDARY_MISSING","subject":"modulePath","message":"MSA 매핑에는 명시적인 서비스 모듈이 필요합니다."})
 if resolved["architecture"]=="CUSTOM" and not custom_layout:unknowns.append({"code":"CUSTOM_ARCHITECTURE_PATHS_REQUIRED","subject":"architecture","message":"사용자 구조의 역할별 package 경로를 확정해야 합니다.","evidencePaths":[]})
 status="BLOCKED" if conflicts or unknowns else "REVIEW_READY"
 return {"httpApiSpringMappingVersion":2,"status":status,"contractId":metadata.get("contractId","UNKNOWN"),"featureId":feature["feature"]["id"],"target":{"root":str(root),"projectId":metadata.get("target",{}).get("projectId","UNKNOWN"),"modulePath":module_path,"packageName":package_name,"language":language},"inputs":input_refs,"scan":{"maxFiles":max_files,"maxBytes":max_bytes,"scannedFiles":min(len(files),max_files),"scannedBytes":scanned_bytes},"decisions":{k:decision(v,decision_source,(custom_details or {}).get(k)) for k,v in resolved.items()},"customLayout":custom_layout,"decisionEvidence":decision_evidence,"boundaries":{"apiDtoEntitySeparated":True,"persistence":"NOT_INFERRED_WITHOUT_DATA_CONTRACT","transactionOwner":"APPLICATION_SERVICE_IF_WRITE_CONTRACT","crossServiceRepositoryAccess":False},"operationMappings":operations_out,"sourceEvidence":[i for i in observed if i["path"] in relevant_paths],"revision":revision or {"previous":None,"changeSummary":"INITIAL"},"conflicts":conflicts,"unknowns":unknowns,"summary":{"operations":len(operations_out),"create":sum(c["disposition"]=="CREATE" for o in operations_out for c in o["components"]),"reuse":sum(c["disposition"] in {"REUSE","EXTEND"} for o in operations_out for c in o["components"]),"conflict":len(conflicts),"unknown":len(unknowns),"tests":sum(len(o["tests"]) for o in operations_out)},"effects":{"sourceChanged":False,"testsExecuted":False,"codeDryRunAuthorized":False,"gitCommitOrPush":"NOT_RUN"}}

def validate(value:dict,root:Path)->list[str]:
 required={"httpApiSpringMappingVersion","status","contractId","featureId","target","inputs","scan","decisions","customLayout","decisionEvidence","boundaries","operationMappings","sourceEvidence","revision","conflicts","unknowns","summary","effects"}
 if not isinstance(value,dict) or set(value)!=required or value.get("httpApiSpringMappingVersion")!=2:raise ValueError("HTTP API Spring mapping is invalid")
 blockers=[]
 if value["status"] not in {"BLOCKED","REVIEW_READY"}:raise ValueError("mapping status is invalid")
 if set(value["scan"])!={"maxFiles","maxBytes","scannedFiles","scannedBytes"} or any(not isinstance(value["scan"][key],int) or value["scan"][key]<0 for key in value["scan"]):raise ValueError("mapping scan record is invalid")
 if set(value["target"])!={"root","projectId","modulePath","packageName","language"} or Path(value["target"]["root"]).resolve()!=root.resolve() or value["target"]["language"] not in LANGUAGES:raise ValueError("mapping target is invalid")
 module=PurePosixPath(value["target"]["modulePath"])
 if module.is_absolute() or ".." in module.parts or not PACKAGE.fullmatch(value["target"]["packageName"]):raise ValueError("mapping module or package is unsafe")
 if value["boundaries"]!={"apiDtoEntitySeparated":True,"persistence":"NOT_INFERRED_WITHOUT_DATA_CONTRACT","transactionOwner":"APPLICATION_SERVICE_IF_WRITE_CONTRACT","crossServiceRepositoryAccess":False}:raise ValueError("mapping boundaries are invalid")
 if set(value["decisions"])!={"architecture","webStack","dtoStyle","mappingStyle","testClient"}:raise ValueError("mapping decisions are incomplete")
 allowed_by_decision={"architecture":ARCHITECTURES,"webStack":WEB_STACKS,"dtoStyle":DTO_STYLES,"mappingStyle":MAPPING_STYLES,"testClient":TEST_CLIENTS}
 for name,item in value["decisions"].items():
  if set(item)!={"value","detail","source","confirmedByUser"} or item["source"] not in SOURCES or item["confirmedByUser"]!=(item["source"] in {"USER_CONFIRMED","RECOMMENDATION_ACCEPTED"}):raise ValueError(f"mapping decision is invalid: {name}")
  if item["value"] not in allowed_by_decision[name]:raise ValueError(f"mapping decision value is invalid: {name}")
  if item["value"]=="CUSTOM" and not isinstance(item["detail"],str):raise ValueError(f"custom mapping decision detail is missing: {name}")
 if set(value["inputs"])!={"featureSpec","technologyProfile","designRoute","httpApiContract","openApi"}:raise ValueError("mapping inputs are incomplete")
 for name,item in value["inputs"].items():
  path=root/item["path"]; pure=PurePosixPath(item["path"])
  if set(item)!={"path","sha256"} or pure.is_absolute() or ".." in pure.parts or path.is_symlink() or not path.is_file() or sha(path)!=item["sha256"]:blockers.append(f"input changed: {name}")
 for item in value["sourceEvidence"]:
  path=root/item["path"]
  if not path.is_file() or path.is_symlink() or sha(path)!=item["sha256"]:blockers.append(f"source evidence changed: {item['path']}")
 for item in value["decisionEvidence"]:
  path=root/item["path"]
  if reference(path,root)!=item:blockers.append(f"decision evidence changed: {item['path']}")
 previous=value["revision"].get("previous")
 if set(value["revision"])!={"previous","changeSummary"} or not isinstance(value["revision"]["changeSummary"],str) or SECRET.search(value["revision"]["changeSummary"]) or PII.search(value["revision"]["changeSummary"]):raise ValueError("mapping revision is invalid")
 if previous is not None:
  path=root/previous["path"]
  if reference(path,root)!=previous:blockers.append("previous mapping revision changed")
  else:
   old=json.loads(path.read_text())
   if old.get("contractId")!=value["contractId"] or old.get("featureId")!=value["featureId"]:blockers.append("previous mapping belongs to another contract or feature")
 operation_ids=[i["operationId"] for i in value["operationMappings"]]
 if not operation_ids or len(operation_ids)!=len(set(operation_ids)):raise ValueError("operation mappings must be non-empty and unique")
 for operation in value["operationMappings"]:
  if set(operation)!={"operationId","method","path","requirementRefs","security","components","tests"} or not operation["path"].startswith("/"):raise ValueError("operation mapping structure is invalid")
  roles=[item.get("role") for item in operation["components"]]
  if roles[:2]!=["CONTROLLER","APPLICATION_SERVICE"] or len(roles)!=len(set(roles)) or not set(roles)<={"CONTROLLER","APPLICATION_SERVICE","REQUEST_DTO","RESPONSE_DTO"}:raise ValueError("operation component roles are invalid")
  for component in operation["components"]:
   if set(component)!={"role","typeName","disposition","plannedPath","candidateEvidence"} or component["disposition"] not in {"CREATE","REUSE","CONFLICT","UNKNOWN"}:raise ValueError("operation component is invalid")
   if component["plannedPath"] is not None:
    planned=PurePosixPath(component["plannedPath"])
    if planned.is_absolute() or ".." in planned.parts:raise ValueError("planned component path is unsafe")
  for test in operation["tests"]:
   if set(test)!={"kind","client","covers","cases"} or test["kind"] not in {"CONTRACT","VALIDATION","SECURITY"} or test["client"] not in TEST_CLIENTS or operation["operationId"] not in test["covers"] or not test["cases"]:raise ValueError("operation test mapping is invalid")
  if operation["security"]["required"] and not any(test["kind"]=="SECURITY" for test in operation["tests"]):blockers.append(f"secured operation lacks security test: {operation['operationId']}")
 if value["status"]=="REVIEW_READY" and (value["conflicts"] or value["unknowns"]):blockers.append("REVIEW_READY mapping has unresolved items")
 expected={"operations":len(value["operationMappings"]),"create":sum(c["disposition"]=="CREATE" for o in value["operationMappings"] for c in o["components"]),"reuse":sum(c["disposition"] in {"REUSE","EXTEND"} for o in value["operationMappings"] for c in o["components"]),"conflict":len(value["conflicts"]),"unknown":len(value["unknowns"]),"tests":sum(len(o["tests"]) for o in value["operationMappings"])}
 if value["summary"]!=expected:raise ValueError("mapping summary is inconsistent")
 if blockers:return blockers
 from validate_feature_specs import load_object
 feature=load_object(root/value["inputs"]["featureSpec"]["path"]);profile=load_object(root/value["inputs"]["technologyProfile"]["path"]);openapi=load_object(root/value["inputs"]["openApi"]["path"])
 choices={key:item["value"] for key,item in value["decisions"].items()};details={key:item["detail"] for key,item in value["decisions"].items() if item["detail"]};sources={item["source"] for item in value["decisions"].values()}
 if len(sources)!=1:raise ValueError("mapping decision sources must be uniform")
 rebuilt=build(feature,profile,openapi,root,value["target"]["modulePath"],value["target"]["packageName"],choices,next(iter(sources)),value["inputs"],details,value["scan"]["maxFiles"],value["scan"]["maxBytes"],value["revision"],value["customLayout"])
 rebuilt["scan"]["scannedFiles"]=value["scan"]["scannedFiles"];rebuilt["scan"]["scannedBytes"]=value["scan"]["scannedBytes"]
 if rebuilt!=value:blockers.append("mapping does not match deterministic reconstruction")
 return blockers
