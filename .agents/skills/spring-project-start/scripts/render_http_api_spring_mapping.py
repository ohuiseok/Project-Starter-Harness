#!/usr/bin/env python3
"""Render a progressive, user-first view of an HTTP API Spring mapping."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from http_api_spring_mapping import validate
from record_spec_approval import atomic_write_bytes
from validate_feature_specs import load_object

def render(value:dict,blockers:list[str])->str:
 s=value["summary"];d=value["decisions"]; lines=[f"# {value['featureId']} Spring 구현 매핑","",f"- 상태: {value['status']}",f"- API {s['operations']}개 · 생성 {s['create']} · 재사용 {s['reuse']} · 충돌 {s['conflict']} · 확인 필요 {s['unknown']}",f"- 계획된 테스트: {s['tests']}개","","## 추천 구현 구조","",f"- 구조: {d['architecture']['value']} · 웹: {d['webStack']['value']}",f"- DTO: {d['dtoStyle']['value']} · 변환: {d['mappingStyle']['value']} · 테스트: {d['testClient']['value']}",f"- 선택 근거: {d['architecture']['source']}"]
 for name,item in d.items():
  if item["detail"]:lines.append(f"- {name} 직접 구성: {item['detail']}")
 lines.extend(["","## 보호되는 경계","","- API DTO와 영속 Entity는 분리","- 데이터 계약 없이는 Entity·Repository를 추론하지 않음","- 쓰기 트랜잭션은 Application Service만 소유","- MSA 경계를 넘는 Repository 직접 접근 금지","","## API별 구현과 검증",""])
 for op in value["operationMappings"]:
  states=", ".join(f"{c['role']} {c['disposition']}" for c in op["components"]); tests=", ".join(t["kind"] for t in op["tests"])
  lines.extend([f"- **{op['method']} `{op['path']}`** · `{op['operationId']}`",f"  - 구현: {states}",f"  - 보안: {'필요' if op['security']['required'] else '없음'} ({op['security']['profileOption']})",f"  - 테스트: {tests}"])
 lines.extend(["","## 충돌과 확인 필요",""])
 if not value["conflicts"] and not value["unknowns"] and not blockers:lines.append("- 없음")
 for item in value["conflicts"]:lines.append(f"- 충돌 · {item['message']} (`{item['subject']}`)")
 for item in value["unknowns"]:lines.append(f"- 확인 필요 · {item['message']} (`{item['subject']}`)")
 for item in blockers:lines.append(f"- 입력 변경 · {item}")
 lines.extend(["","## 다음 선택","","- 추천안 승인 후 기존 Spring 구현 계획으로 변환","- 구조·DTO·매핑·테스트 방식을 항목별 수정","- 기타 요구를 자연어로 입력","- 현재 기능 구현 취소","","## 승인 효과","","- 구현 계획 준비만 허용","- 소스 변경, 테스트 실행, 코드 dry-run, commit, push는 허용하지 않음",""])
 return "\n".join(lines)
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--mapping",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--check",action="store_true");a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);value=load_object(a.mapping);content=render(value,validate(value,root)).encode()
  if a.check:
   if not a.output.is_file() or a.output.read_bytes()!=content:raise ValueError("mapping Markdown is stale")
  else:
   if a.output.exists():raise ValueError("mapping Markdown already exists")
   atomic_write_bytes(content,a.output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"HTTP_API_SPRING_MAPPING_MARKDOWN_VALID: no\nERROR: {e}");return 1
 print("HTTP_API_SPRING_MAPPING_MARKDOWN_VALID: yes");return 0
if __name__=="__main__":sys.exit(main())
