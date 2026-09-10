#!/usr/bin/env python3
"""Render the user-first Spring code dry-run v2 review."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from spring_code_dry_run_v2 import validate_report
from validate_feature_specs import load_object

def render(report:dict)->str:
 s=report["summary"];ready=report["readyForVerificationApproval"]
 lines=["# Spring API 코드 dry-run v2","","## 검토 결론","",f"- API operation: {s['operations']}개",f"- 신규 파일: {s['creates']}개 · 기존 그대로 재사용: {s['reuses']}개 · 기존 파일 수정: {s['updates']}개",f"- 차단 항목: {s['blockers']}개",f"- 격리 검증 승인 준비: {'예' if ready else '아니요'}","- 구현 범위: `API_CONTRACT_ONLY` — API 골격과 계약 테스트이며 비즈니스 행동 완료를 의미하지 않습니다.","- 대상 source 변경·컴파일·테스트·네트워크·Docker·commit·push: 없음","","## 변경 개요",""]
 for item in report["generatedFiles"]:lines.append(f"- 생성 `{item['path']}` ({item['role']})")
 for item in report["reusedFiles"]:lines.append(f"- 재사용 `{item['path']}` (내용 변경 없음)")
 if not report["generatedFiles"] and not report["reusedFiles"]:lines.append("- 없음")
 lines += ["","## 차단 항목과 해결",""]
 if report["blockers"]:
  for item in report["blockers"]:lines.append(f"- `{item['path']}`: {item['reason']}")
 else:lines.append("- 없음")
 lines += ["","## 생성 코드 상세","","필요할 때만 펼쳐 확인합니다.",""]
 for item in report["generatedFiles"]:lines += ["<details>",f"<summary><code>{item['path']}</code></summary>","","```java",item["content"].rstrip(),"```","","</details>",""]
 lines += ["## 다음 선택","","1. 추천: 현재 dry-run을 승인하여 향후 격리 컴파일·테스트만 허용","2. 항목별 수정","3. 자연어로 다른 구현 요청","4. 취소","","승인해도 파일 적용은 허용되지 않습니다.",""]
 return "\n".join(lines)
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--report",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--check",action="store_true");a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);report=load_object(a.report);validate_report(report,root);expected=render(report)
  if a.output.resolve()!=a.report.resolve().with_suffix(".md") or not a.output.is_file() or a.output.read_text()!=expected:raise ValueError("Spring code dry-run v2 view is stale")
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_DRY_RUN_V2_MARKDOWN_VALID: no\nERROR: {e}");return 1
 print("SPRING_CODE_DRY_RUN_V2_MARKDOWN_VALID: yes");return 0
if __name__=="__main__":sys.exit(main())
