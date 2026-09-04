#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys
from pathlib import Path
from render_design_route import atomic_write
from validate_feature_specs import load_object
from run_spring_code_verification import validate_verification_report

def render(report: dict) -> str:
    result=report["result"]; isolation=report["isolation"]
    return "\n".join(["# Spring 코드 격리 검증 결과","","## 결론","",f"- 상태: {result['state']}",f"- apply 승인 준비: {'예' if report['readyForApplyApproval'] else '아니요'}","- 대상 source 변경: 없음","","## 격리 조건","",f"- 파일시스템: {isolation['filesystem']}",f"- 네트워크: {isolation['network']}",f"- Docker socket: {isolation['dockerSocket']}","","## 실행","",f"- 명령: `{' '.join(report['command'])}`",f"- exit code: {result['exitCode']}","","```text",result["output"].rstrip(),"```","","## 의미","","- PASSED는 임시 복사본에서 승인된 후보의 컴파일과 자동 테스트가 통과했다는 뜻","- 실제 target 적용이나 commit·push를 승인하지 않음",""])

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--report",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--check",action="store_true"); p.add_argument("--force",action="store_true"); a=p.parse_args()
    try:
        root=a.target.resolve(strict=True); report_path=a.report.resolve(strict=True); output=a.output.resolve(strict=False)
        if a.target.is_symlink() or root not in report_path.parents or root not in output.parents or a.report.is_symlink() or a.output.is_symlink(): raise ValueError("verification report or view is unsafe")
        report=load_object(report_path); validate_verification_report(report,report_path,root); expected=render(report)
        if a.check:
            if a.output.read_text(encoding="utf-8")!=expected: raise ValueError("verification Markdown is stale")
        else: atomic_write(expected,output,a.force)
    except (OSError,ValueError,KeyError) as error: print(f"SPRING_CODE_VERIFICATION_MARKDOWN_VALID: no\nERROR: {error}"); return 1
    print("SPRING_CODE_VERIFICATION_MARKDOWN_VALID: yes"); return 0
if __name__=="__main__": sys.exit(main())
