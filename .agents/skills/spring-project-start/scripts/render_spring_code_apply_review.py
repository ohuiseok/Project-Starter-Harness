#!/usr/bin/env python3
"""Render a user-first review immediately before Spring code apply approval."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from apply_approved_spring_code import dirty_paths, validate_target_changes
from render_design_route import atomic_write
from run_spring_code_verification import target_context_hash, validate_verification_report
from spring_code_dry_run import canonical_baseline, validate_report
from validate_feature_specs import load_object

def render(dry:dict,verification:dict,dirty:set[str])->str:
    changes=dry["plannedChanges"]; generated=set(changes["desiredManifest"]["files"])
    build_names={"build.gradle","build.gradle.kts","settings.gradle","settings.gradle.kts","gradle.properties","pom.xml","gradlew","mvnw"}
    relevant=sorted(path for path in dirty if path in generated or path.startswith("src/") or Path(path).name in build_names); unrelated=sorted(dirty-set(relevant)); flow=dry["userFlow"]
    lines=[f"# {flow['name']} 코드 적용 검토","","## 적용 준비","",f"- 상태: {'가능' if not relevant else '차단'}",f"- 생성 {len(changes['creates'])} · 수정 {len(changes['updates'])} · 삭제 0",f"- 관련 Git 변경: {len(relevant)}",f"- 관련 없는 Git 경고: {len(unrelated)}","- 격리 컴파일·자동 테스트: 통과","- 입력·target context 변경: 없음","","## 사용자 기능","",f"- 시작: {flow['trigger']}"]
    lines.extend(f"- {index}. {step}" for index,step in enumerate(flow["steps"],1)); lines.extend([f"- 결과: {flow['outcome']}","","## 실행 효과","","- 승인된 Java 파일만 생성 또는 baseline 기반 수정","- 적용 전 백업과 복구 journal 생성","- 누적 implementation baseline 갱신","- DB·Docker 실행 안 함","- post-apply 테스트·Git commit·push 실행 안 함","","## Git 상태"," "])
    if relevant:
        lines.extend(f"- 차단: `{path}`" for path in relevant)
    if unrelated:
        lines.extend(f"- 경고(적용 범위 밖): `{path}`" for path in unrelated)
    if not dirty: lines.append("- 변경 없음")
    lines.extend(["","## 파일 상세",""])
    for item in changes["creates"]: lines.append(f"- CREATE `{item['path']}`")
    for item in changes["updates"]: lines.append(f"- UPDATE `{item['path']}`")
    lines.extend(["","## 승인 의미","","- 이 화면의 정확한 검증 결과와 파일 범위만 apply 승인","- 적용 후 테스트 실패 시 자동 삭제하지 않고 별도 상태로 보고",""])
    return "\n".join(lines)

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--dry-run",required=True,type=Path); p.add_argument("--verification-report",required=True,type=Path); p.add_argument("--target",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--check",action="store_true"); p.add_argument("--force",action="store_true"); a=p.parse_args()
    try:
        root=a.target.resolve(strict=True); dry_path=a.dry_run.resolve(strict=True); verification_path=a.verification_report.resolve(strict=True); output=a.output.resolve(strict=False)
        if a.target.is_symlink() or any(root not in path.parents for path in (dry_path,verification_path,output)) or a.dry_run.is_symlink() or a.verification_report.is_symlink() or a.output.is_symlink(): raise ValueError("apply review paths are unsafe")
        dry=load_object(dry_path); validate_report(dry,root); verification=load_object(verification_path); validate_verification_report(verification,verification_path,root)
        if verification["result"]["state"]!="PASSED": raise ValueError("isolated verification did not pass")
        if target_context_hash(root,{item["path"] for item in dry["generatedFiles"]})!=verification["targetContextSha256"]: raise ValueError("target context changed")
        canonical_baseline(root); validate_target_changes(root,dry["plannedChanges"]); dirty=dirty_paths(root); expected=render(dry,verification,dirty)
        if a.check:
            if output.read_text(encoding="utf-8")!=expected: raise ValueError("apply review Markdown is stale")
        else: atomic_write(expected,output,a.force)
    except (OSError,ValueError,KeyError) as error: print(f"SPRING_CODE_APPLY_REVIEW_VALID: no\nERROR: {error}"); return 1
    print("SPRING_CODE_APPLY_REVIEW_VALID: yes"); return 0
if __name__=="__main__": sys.exit(main())
