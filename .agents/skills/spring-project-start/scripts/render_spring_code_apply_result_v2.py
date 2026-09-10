#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
from http_api_spring_mapping import reference
from spring_code_apply_v2 import BASELINE,MANAGED,sha
from validate_feature_specs import load_object
def validate(value:dict,path:Path,root:Path)->None:
 if set(value)!={"springCodeApplyResultV2Version","state","transactionId","review","approval","verification","target","createsApplied","reusesUnchanged","baseline","backup","postApplyVerification","effects","committedAt"} or value["springCodeApplyResultV2Version"]!=1 or value["state"]!="APPLIED_PREVERIFIED" or Path(value["target"]).resolve()!=root:raise ValueError("Spring code apply result v2 is invalid")
 for key in ("review","approval","verification"):
  if reference(root/value[key]["path"],root)!=value[key]:raise ValueError(f"apply result {key} changed")
 baseline=root/BASELINE
 if value["baseline"]!={"path":BASELINE,"sha256":sha(baseline)}:raise ValueError("apply result baseline changed")
 transaction=root/MANAGED/"transactions"/(value["transactionId"]+".json");record=load_object(transaction)
 if record.get("state")!="COMMITTED" or record.get("appliedFiles")!=value["createsApplied"] or record.get("backup")!=value["backup"]["path"] or record.get("backupManifestSha256")!=value["backup"]["manifestSha256"]:raise ValueError("apply transaction is not committed")
 expected_backup=f"{MANAGED}/backups/spring-code-v2/{value['transactionId']}"
 if value["backup"]["path"]!=expected_backup:raise ValueError("apply backup path is invalid")
 manifest=root/expected_backup/"backup-manifest.json"
 if sha(manifest)!=value["backup"]["manifestSha256"]:raise ValueError("apply backup evidence changed")
 if path.is_symlink() or root not in path.resolve().parents:raise ValueError("apply result must be target-owned")
def render(value:dict)->str:
 return "\n".join(["# Spring 코드 v2 적용 결과","","## 결론","","- 상태: `APPLIED_PREVERIFIED`",f"- 생성 완료: {len(value['createsApplied'])}개",f"- 변경 없이 재사용: {len(value['reusesUnchanged'])}개","- baseline 병합: 완료","- 적용 후 테스트: 아직 실행하지 않음","- Git commit·push: 실행하지 않음","","## 생성 파일",""]+[f"- `{i}`" for i in value["createsApplied"]]+["","## 다음","","1. 추천: 실제 적용 상태 기반 격리 테스트","2. 적용 증거 상세 확인","3. 자연어로 다른 검증 요청",""])
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--result",required=True,type=Path);p.add_argument("--target",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--check",action="store_true");a=p.parse_args()
 try:
  root=a.target.resolve(strict=True);path=a.result.resolve(strict=True);value=load_object(path);validate(value,path,root);expected=render(value);output=a.output.resolve()
  if a.check:
   if not output.is_file() or output.read_text()!=expected:raise ValueError("apply result view is stale")
  else:
   if output.exists() or root not in output.parents:raise ValueError("apply result view output is unsafe or occupied")
   from apply_approved_spring_code_v2 import atomic_file
   output.parent.mkdir(parents=True,exist_ok=True);atomic_file(expected.encode(),0o644,output)
 except (OSError,ValueError,KeyError,TypeError) as e:print(f"SPRING_CODE_APPLY_RESULT_V2_VALID: no\nERROR: {e}");return 1
 print("SPRING_CODE_APPLY_RESULT_V2_VALID: yes\nAPPLICATION_STATE: APPLIED_PREVERIFIED");return 0
if __name__=="__main__":sys.exit(main())
