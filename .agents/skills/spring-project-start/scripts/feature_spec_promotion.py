#!/usr/bin/env python3
"""Contracts for promoting a ready continuation draft into official specifications."""
from __future__ import annotations
import copy,hashlib,json,subprocess
from pathlib import Path
from continuation_route import markdown
from feature_draft_chain import encoded,head,load_context
from prepare_feature_spec_approval import readiness,render as render_readiness
from record_spec_approval import approved_copy,synchronize_candidate
from render_spec_markdown import render_feature,render_project
from spring_milestone_completion import sha,target_path
from validate_feature_specs import load_object,validate_feature,validate_project
def file_ref(path:Path,root:Path)->dict: return {"path":path.relative_to(root).as_posix(),"sha256":sha(path)}
def git_overlap(root:Path,paths:list[Path])->list[str]:
 result=subprocess.run(["git","status","--porcelain","--untracked-files=all"],cwd=root,capture_output=True,text=True,check=False)
 if result.returncode: raise ValueError("target Git dirty state cannot be verified")
 dirty={line[3:].split(" -> ")[-1].strip('"') for line in result.stdout.splitlines() if len(line)>3}; relative={path.relative_to(root).as_posix() for path in paths}; return sorted(dirty&relative)
def bullets(values:list[str])->list[str]: return [f"- {markdown(item)}" for item in values] or ["- 없음"]
def validate_ready(root:Path,intake_path:Path,report_path:Path,view_path:Path)->tuple[dict,dict,dict,Path]:
 intake,receipt,_=load_context(root,intake_path); draft_path,draft_ref=head(root,receipt); spec=load_object(draft_path); blockers=readiness(spec)
 expected={"featureSpecApprovalReadinessVersion":1,"intake":file_ref(intake_path,root),"draft":draft_ref,"projectBrief":intake["projectBrief"],"progress":intake["progress"],"featureId":spec["feature"]["id"],"blockers":blockers,"state":"READY_FOR_SPEC_APPROVAL" if not blockers else "AWAITING_USER_DECISIONS"}
 if blockers or load_object(report_path)!=expected or view_path.read_text()!=render_readiness(spec,blockers): raise ValueError("current exact readiness report and view are required")
 return intake,receipt,spec,draft_path
def build(root:Path,intake_path:Path,report_path:Path,readiness_view:Path)->dict:
 intake,receipt,spec,draft_path=validate_ready(root,intake_path,report_path,readiness_view); project_path=target_path(root,intake["projectBrief"]["path"],"project brief"); project=load_object(project_path); validate_project(project); project_view=project_path.with_suffix(".md")
 if not project_view.is_file() or project_view.read_text()!=render_project(project): raise ValueError("project brief view is stale")
 proposed=copy.deepcopy(project); feature_id=spec["feature"]["id"]; matches=[item for item in proposed["featureCandidates"] if item["id"]==feature_id]
 if not matches:
  proposed["featureCandidates"].append({"id":feature_id,"name":spec["feature"]["name"],"userValue":spec["feature"]["userValue"],"recommendationReason":"사용자가 요청하고 검토한 다음 기능","dependsOn":spec["dependencies"],"blockingUnknownIds":[],"recommendedOrder":max([item["recommendedOrder"] for item in proposed["featureCandidates"]] or [0])+1,"status":"REVIEW_REQUIRED"}); proposed["approval"]={"status":"REVIEW_REQUIRED","approvedBy":None,"approvedAt":None,"approvedContentSha256":None}
 elif len(matches)!=1: raise ValueError("feature candidate must exist at most once")
 else:
  candidate=matches[0]
  if candidate["name"]!=spec["feature"]["name"] or candidate["userValue"]!=spec["feature"]["userValue"] or candidate["dependsOn"]!=spec["dependencies"]:
   candidate.update({"name":spec["feature"]["name"],"userValue":spec["feature"]["userValue"],"dependsOn":spec["dependencies"],"status":"REVIEW_REQUIRED"}); proposed["approval"]={"status":"REVIEW_REQUIRED","approvedBy":None,"approvedAt":None,"approvedContentSha256":None}
 base=receipt["baseFeature"]
 if base:
  official=target_path(root,base["path"],"base feature")
  if not official.is_file() or sha(official)!=base["sha256"]: raise ValueError("base feature changed")
  official_view=official.with_suffix(".md"); base_document=load_object(official)
  if not official_view.is_file() or official_view.read_text()!=render_feature(base_document,project): raise ValueError("base feature view is stale")
  base_view=file_ref(official_view,root)
 else: official=target_path(root,f"docs/features/{feature_id}/spec.json","official feature"); official_view=target_path(root,f"docs/features/{feature_id}/spec.md","official feature view"); base_view=None
 if not base and (official.exists() or official_view.exists()): raise ValueError("unowned official feature path or view already exists")
 official_paths=[project_path,project_view,official,official_view]
 return {"featureSpecPromotionVersion":2,"target":str(root),"intake":file_ref(intake_path,root),"readiness":file_ref(report_path,root),"readinessView":file_ref(readiness_view,root),"projectBrief":file_ref(project_path,root),"projectBriefView":file_ref(project_view,root),"baseFeature":base,"baseFeatureView":base_view,"reservation":intake["feature"].get("reservation"),"officialFeaturePath":official.relative_to(root).as_posix(),"gitOverlap":git_overlap(root,official_paths),"proposedProject":proposed,"proposedFeature":spec,"state":"READY_FOR_APPROVAL"}
def render(plan:dict)->str:
 root=Path(plan["target"]); old_project=load_object(root/plan["projectBrief"]["path"]); project=plan["proposedProject"]; spec=plan["proposedFeature"]; feature_id=spec["feature"]["id"]; old=next((item for item in old_project["featureCandidates"] if item["id"]==feature_id),None); new=next(item for item in project["featureCandidates"] if item["id"]==feature_id); existing=plan["baseFeature"] is not None
 delta=[]
 if old is None: delta.append(f"새 후보 추가: {new['name']} · 순서 {new['recommendedOrder']}")
 else:
  for label,key in (("이름","name"),("사용자 가치","userValue"),("의존 기능","dependsOn")):
   if old[key]!=new[key]: delta.append(f"{label}: {old[key]} → {new[key]}")
 if not delta: delta=["기존 후보 내용 변경 없음 · 승인 상태만 동기화"]
 scenario=spec["scenario"]; design=[f"{key}: {value['status']} · {value['reason']}" for key,value in spec["designRequirements"].items()]; criteria=[f"{item['given']} / {item['when']} / {item['then']}" for item in spec["acceptanceCriteria"]]; rules=[item["description"] for item in spec["businessRules"]]
 lines=["# 공식 기능 명세 승격 검토","",f"- 기능: {feature_id} · {markdown(spec['feature']['name'])}",f"- 작업: {'기존 공식 명세 교체' if existing else '새 공식 명세 생성'}","","## 프로젝트 로드맵 변경","",*bullets(delta),"","## 사용자 가치","",markdown(spec["feature"]["userValue"]),"","## 사용자와 흐름","",*bullets(["주요 사용자: "+", ".join(spec["actors"]),"시작: "+scenario["trigger"]]+[f"{index}. {item}" for index,item in enumerate(scenario["mainFlow"],1)]),"","## 업무 규칙","",*bullets(rules),"","## 권한","",*bullets(spec["authorization"]),"","## 데이터와 상태","",*bullets(spec["dataAndState"]),"","## 실패 사례","",*bullets(spec["failureCases"]),"","## 검증 가능한 완료 조건","",*bullets(criteria),"","## 설계 필요성","",*bullets(design),"","## Git 작업 상태","",*bullets(["승격 대상과 겹치는 미커밋 변경: "+item for item in plan["gitOverlap"]] or ["승격 대상과 겹치는 미커밋 변경 없음"]),"","## 적용 시 변경되는 공식 파일","",f"- {markdown(plan['projectBrief']['path'])}","- "+markdown(str(Path(plan['projectBrief']['path']).with_suffix('.md'))),f"- {markdown(plan['officialFeaturePath'])}","- "+markdown(str(Path(plan['officialFeaturePath']).with_suffix('.md'))),"","## 적용하지 않는 것","","- API·ERD·소스 코드 생성 안 함","- 런타임·DB·Docker 실행 안 함","- Git commit·push 안 함","","## 선택","","- 이 내용으로 공식 명세 승인 및 승격","- 자연어로 draft 수정","- 취소",""]; return "\n".join(lines)
