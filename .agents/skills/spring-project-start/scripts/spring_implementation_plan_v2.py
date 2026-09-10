#!/usr/bin/env python3
"""Deterministic implementation-plan core v2 with capability adapters."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path,PurePosixPath
from http_api_spring_mapping import reference
from validate_feature_specs import load_object
from validate_http_api_spring_mapping_approval import validate_approval as validate_mapping_approval
from validate_spring_implementation_capabilities_v2 import load_and_validate as load_capabilities

CATALOG=Path(__file__).resolve().parent.parent/"references/spring-implementation-capabilities-v2.json"
ID=re.compile(r"^[a-z][a-z0-9-]*$")
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+"\n").encode()
def cid(role:str,path:str,type_name:str)->str:
 raw=f"{role}-{type_name}-{path}".lower();prefix=re.sub(r"[^a-z0-9]+","-",raw).strip("-")[:72].rstrip("-");return f"{prefix}-{hashlib.sha256(raw.encode()).hexdigest()[:10]}"
def test_path(target:dict,controller_path:str,operation_id:str,kind:str)->str:
 marker="src/main/java/";prefix,remainder=controller_path.split(marker,1) if marker in controller_path else (f"{target['modulePath'].rstrip('/')+'/' if target['modulePath']!='.' else ''}",target["packageName"].replace(".","/")+"/api/Controller.java")
 package=PurePosixPath(remainder).parent.as_posix();name="".join(p[:1].upper()+p[1:] for p in re.split(r"[^A-Za-z0-9]+",re.sub(r"([a-z])([A-Z])",r"\1 \2",operation_id)) if p)
 return f"{prefix}src/test/java/{package}/{name}{kind.title()}Test.java"
def adapter(mapping:dict)->dict:
 catalog=load_capabilities(CATALOG);matches=[a for a in catalog["adapters"] if a["language"]==mapping["target"]["language"] and a["webStack"]==mapping["decisions"]["webStack"]["value"] and mapping["decisions"]["architecture"]["value"] in a["architectures"]]
 return matches[0] if len(matches)==1 else {"id":"NONE","planning":"UNSUPPORTED","codeDryRunRenderer":"NOT_IMPLEMENTED"}
def file_action(disposition:str)->str:return {"CREATE":"CREATE_FILE","EXTEND":"UPDATE_FILE","REUSE":"REUSE_FILE","CONFLICT":"CONFLICT","UNKNOWN":"UNKNOWN"}.get(disposition,"UNKNOWN")
def related_documents(root:Path,key:str,expected:dict)->list[Path]:
 found=[]
 for path in (root/"docs").glob("**/*.json") if (root/"docs").is_dir() else []:
  try:value=json.loads(path.read_text())
  except (OSError,json.JSONDecodeError):continue
  if value.get(key)==expected:found.append(path)
 return found
def plans_for_mapping(root:Path,mapping_ref:dict)->list[Path]:
 found=[]
 for path in (root/"docs").glob("**/*.json") if (root/"docs").is_dir() else []:
  try:value=json.loads(path.read_text())
  except (OSError,json.JSONDecodeError):continue
  if value.get("implementationPlanVersion")==2 and value.get("inputs",{}).get("springMapping")==mapping_ref:found.append(path)
 return found
def plan_approvals(root:Path,plan_ref:dict)->list[Path]:return related_documents(root,"implementationPlan",plan_ref)
def plan_cancellations(root:Path,plan_ref:dict)->list[Path]:return related_documents(root,"cancelledPlan",plan_ref)
def build(mapping:dict,mapping_ref:dict,approval_ref:dict,root:Path)->dict:
 capability=adapter(mapping);conflicts=[{"code":i["code"],"subject":i["subject"],"message":i["message"],"source":"SPRING_MAPPING"} for i in mapping["conflicts"]];unknowns=[{"code":i["code"],"subject":i["subject"],"message":i["message"],"source":"SPRING_MAPPING"} for i in mapping["unknowns"]]
 if capability["planning"]!="SUPPORTED":conflicts.append({"code":"PLANNING_ADAPTER_UNAVAILABLE","subject":f"{mapping['target']['language']}/{mapping['decisions']['webStack']['value']}","message":"이 기술 조합의 구현 계획 adapter가 없습니다.","source":"CAPABILITY_CATALOG"})
 secured_operations=[op for op in mapping["operationMappings"] if op["security"]["required"]];security_profiles=sorted({op["security"]["profileOption"] for op in secured_operations})
 unsupported_security=sorted(set(security_profiles)-set(capability.get("securityProfiles",[])))
 if unsupported_security or secured_operations and not capability.get("securedOperations",False):conflicts.append({"code":"SECURITY_CAPABILITY_UNAVAILABLE","subject":", ".join(unsupported_security or security_profiles),"message":"현재 adapter는 이 보안 구성을 구현 계획에 포함하지 못합니다.","source":"CAPABILITY_CATALOG"})
 grouped={};operation_links=[]
 for op in mapping["operationMappings"]:
  op_components=[];controller_refs=[]
  for raw in op["components"]:
   key=(raw["role"],raw["plannedPath"],raw["typeName"]);identity=cid(*key)
   symbol={"operationId":op["operationId"],"kind":"HTTP_HANDLER" if raw["role"]=="CONTROLLER" else "USE_CASE_METHOD" if raw["role"]=="APPLICATION_SERVICE" else "DATA_TYPE","action":"REUSE_METHOD" if raw["disposition"]=="REUSE" else "ADD_METHOD" if raw["disposition"]=="EXTEND" else "CREATE_TYPE","httpMethod":op["method"] if raw["role"]=="CONTROLLER" else None,"httpPath":op["path"] if raw["role"]=="CONTROLLER" else None}
   if key not in grouped:grouped[key]={"componentId":identity,"role":raw["role"],"disposition":raw["disposition"],"fileAction":file_action(raw["disposition"]),"sourceEvidence":raw["candidateEvidence"],"owner":{"contractId":mapping["contractId"],"modulePath":mapping["target"]["modulePath"]},"target":{"path":raw["plannedPath"],"typeName":raw["typeName"]},"symbols":[],"operationRefs":[],"requirementRefs":[],"dependsOn":[]}
   elif grouped[key]["disposition"]!=raw["disposition"]:
    item=grouped[key];states={item["disposition"],raw["disposition"]}
    if raw["role"] in {"CONTROLLER","APPLICATION_SERVICE"} and states<={"CREATE","EXTEND","REUSE"}:
     item["disposition"]="EXTEND";item["fileAction"]="UPDATE_FILE";evidence={i["path"]:i for i in [*item["sourceEvidence"],*raw["candidateEvidence"]]};item["sourceEvidence"]=[evidence[i] for i in sorted(evidence)]
    else:conflicts.append({"code":"SHARED_COMPONENT_DISPOSITION_CONFLICT","subject":raw["plannedPath"],"message":"공유 컴포넌트에 호환되지 않는 생성·확장·재사용 판단이 지정됐습니다.","source":"PLAN_CORE"})
   item=grouped[key];item["symbols"].append(symbol);item["operationRefs"].append(op["operationId"]);item["requirementRefs"].extend(op["requirementRefs"]);op_components.append(identity)
   if raw["role"]=="CONTROLLER":controller_refs.append(identity)
  test_ids=[];controller_path=next(raw["plannedPath"] for raw in op["components"] if raw["role"]=="CONTROLLER")
  for test in op["tests"]:
   path=test_path(mapping["target"],controller_path,op["operationId"],test["kind"]);key=("TEST",path,Path(path).stem);identity=cid(*key);occupied=(root/path).exists()
   if occupied:conflicts.append({"code":"TEST_PATH_OCCUPIED","subject":path,"message":"계획된 테스트 경로에 기존 파일이 있어 자동 생성을 확정할 수 없습니다.","source":"PLAN_CORE"})
   disposition="CONFLICT" if occupied else "CREATE";grouped[key]={"componentId":identity,"role":"TEST","disposition":disposition,"fileAction":file_action(disposition),"sourceEvidence":[],"owner":{"contractId":mapping["contractId"],"modulePath":mapping["target"]["modulePath"]},"target":{"path":path,"typeName":Path(path).stem},"symbols":[{"operationId":op["operationId"],"kind":test["kind"],"action":"CREATE_TYPE","httpMethod":None,"httpPath":None}],"operationRefs":[op["operationId"]],"requirementRefs":list(dict.fromkeys(test["covers"][1:])),"dependsOn":sorted(set(controller_refs))};test_ids.append(identity)
  operation_links.append({"operationId":op["operationId"],"method":op["method"],"path":op["path"],"componentRefs":op_components,"testRefs":test_ids,"requirementRefs":op["requirementRefs"],"implementationSemantics":op["implementationSemantics"],"security":op["security"]})
 components=[]
 for item in grouped.values():
  if item["fileAction"]=="UPDATE_FILE" and item["role"] in {"CONTROLLER","APPLICATION_SERVICE"}:
   for symbol in item["symbols"]:
    if symbol["action"]=="CREATE_TYPE":symbol["action"]="ADD_METHOD"
  if item["fileAction"]=="UPDATE_FILE" and not item["sourceEvidence"]:conflicts.append({"code":"UPDATE_SOURCE_EVIDENCE_REQUIRED","subject":item["target"]["path"],"message":"기존 파일 확장에는 현재 파일 해시 증거가 필요합니다.","source":"PLAN_CORE"})
  item["operationRefs"]=sorted(set(item["operationRefs"]));item["requirementRefs"]=sorted(set(item["requirementRefs"]));item["symbols"]=sorted(item["symbols"],key=lambda x:(x["operationId"],x["kind"]));components.append(item)
 roles={i["componentId"]:i["role"] for i in components};services={op["operationId"]:next((i for i in op["componentRefs"] if roles.get(i)=="APPLICATION_SERVICE"),None) for op in operation_links}
 for item in components:
  if item["role"]=="CONTROLLER":item["dependsOn"]=sorted({services[o] for o in item["operationRefs"] if services.get(o)})
 coverage=[]
 for requirement in sorted({r for op in operation_links for r in op["requirementRefs"]}):coverage.append({"requirementRef":requirement,"verificationLevel":"API_CONTRACT_ONLY","operationRefs":[op["operationId"] for op in operation_links if requirement in op["requirementRefs"]],"implementationRefs":sorted({c["componentId"] for c in components if requirement in c["requirementRefs"] and c["role"]!="TEST"}),"testRefs":sorted({c["componentId"] for c in components if requirement in c["requirementRefs"] and c["role"]=="TEST"})})
 for item in coverage:
  if not item["implementationRefs"] or not item["testRefs"]:conflicts.append({"code":"REQUIREMENT_COVERAGE_INCOMPLETE","subject":item["requirementRef"],"message":"요구사항의 구현 또는 자동화 테스트 연결이 비어 있습니다.","source":"PLAN_CORE"})
 path_owners={}
 for component in components:path_owners.setdefault(component["target"]["path"],[]).append(component["componentId"])
 for path,owners in path_owners.items():
  if len(owners)>1:conflicts.append({"code":"TARGET_PATH_OWNERSHIP_COLLISION","subject":path,"message":"서로 다른 컴포넌트가 같은 파일 경로를 소유하려 합니다.","source":"PLAN_CORE"})
 status="BLOCKED" if conflicts or unknowns else "REVIEW_READY";renderer=capability.get("codeDryRunRenderer","NOT_IMPLEMENTED")
 plan_id=re.sub(r"[^a-z0-9]+","-",f"{mapping['featureId']}-{mapping['contractId']}-implementation-v2".lower()).strip("-")
 return {"implementationPlanVersion":2,"status":status,"planId":plan_id,"featureId":mapping["featureId"],"contractId":mapping["contractId"],"target":mapping["target"],"inputs":{"springMapping":mapping_ref,"springMappingApproval":approval_ref,"capabilityCatalog":{"path":"HARNESS:.agents/skills/spring-project-start/references/spring-implementation-capabilities-v2.json","sha256":hashlib.sha256(CATALOG.read_bytes()).hexdigest()}},"capability":{"adapterId":capability["id"],"planning":capability["planning"],"codeDryRunRenderer":renderer},"scope":{"security":"UNSUPPORTED" if secured_operations else "NOT_USED","persistence":"NOT_USED","externalClients":"NOT_USED","buildChanges":"NONE_PLANNED"},"buildRequirements":{"main":["spring-boot-starter-web","spring-boot-starter-validation"],"test":["spring-boot-starter-test","mockmvc","junit","mockito"],"changesAllowed":False},"baseline":{"artifactKind":"SPRING_IMPLEMENTATION_V2","path":".starter-harness-implementation-v2.json","manifestVersion":2},"schemaCatalog":mapping["schemaCatalog"],"operationLinks":operation_links,"components":sorted(components,key=lambda x:x["componentId"]),"coverage":coverage,"conflicts":conflicts,"unknowns":unknowns,"summary":{"operations":len(operation_links),"components":len(components),"create":sum(i["disposition"]=="CREATE" for i in components),"extend":sum(i["disposition"]=="EXTEND" for i in components),"reuse":sum(i["disposition"]=="REUSE" for i in components),"tests":sum(i["role"]=="TEST" for i in components)},"advancement":{"implementationPlanApproval":status=="REVIEW_READY","codeDryRun":False,"reason":"v2 code dry-run renderer is not implemented" if renderer=="NOT_IMPLEMENTED" else "separate approval required"},"effects":{"sourceChanged":False,"testsExecuted":False,"gitCommitOrPush":"NOT_RUN"}}
def validate(plan:dict,root:Path,verify_approval:bool=True)->list[str]:
 required={"implementationPlanVersion","status","planId","featureId","contractId","target","inputs","capability","scope","buildRequirements","baseline","schemaCatalog","operationLinks","components","coverage","conflicts","unknowns","summary","advancement","effects"}
 if set(plan)!=required or plan.get("implementationPlanVersion")!=2 or not ID.fullmatch(plan["planId"]):raise ValueError("implementation plan v2 identity is invalid")
 blockers=[]
 for name in ("springMapping","springMappingApproval"):
  ref=plan["inputs"][name];path=root/ref["path"]
  if reference(path,root)!=ref:blockers.append(f"input changed: {name}")
 if not blockers and verify_approval:
  receipt=validate_mapping_approval(root,root/plan["inputs"]["springMappingApproval"]["path"])
  if receipt["mapping"]!=plan["inputs"]["springMapping"]:blockers.append("mapping approval does not authorize this mapping")
 ids=[i["componentId"] for i in plan["components"]]
 if len(ids)!=len(set(ids)):raise ValueError("component IDs must be unique")
 idset=set(ids)
 for item in plan["components"]:
  path=PurePosixPath(item["target"]["path"])
  if path.is_absolute() or ".." in path.parts or set(item["dependsOn"])-idset:raise ValueError("component graph contains unsafe path or missing dependency")
  if item["fileAction"]!=file_action(item["disposition"]):raise ValueError("component file action is inconsistent")
  for evidence in item["sourceEvidence"]:
   if reference(root/evidence["path"],root)!=evidence:blockers.append(f"component source evidence changed: {evidence['path']}")
 visiting=set();visited=set();graph={i["componentId"]:i["dependsOn"] for i in plan["components"]}
 def cycle(node):
  if node in visiting:return True
  if node in visited:return False
  visiting.add(node);found=any(cycle(i) for i in graph[node]);visiting.remove(node);visited.add(node);return found
 if any(cycle(i) for i in graph):blockers.append("component dependency cycle exists")
 if any(not i["implementationRefs"] or not i["testRefs"] for i in plan["coverage"]):blockers.append("requirement coverage is incomplete")
 mapping=load_object(root/plan["inputs"]["springMapping"]["path"]);expected=build(mapping,plan["inputs"]["springMapping"],plan["inputs"]["springMappingApproval"],root)
 if expected!=plan:blockers.append("plan does not match deterministic reconstruction")
 if plan["status"]!="BLOCKED" and blockers:blockers.append("plan status does not reflect validation blockers")
 return blockers
