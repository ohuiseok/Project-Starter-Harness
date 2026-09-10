#!/usr/bin/env python3
from __future__ import annotations
import json,tempfile,unittest
from pathlib import Path
from unittest import mock
import sys
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
from http_api_spring_mapping import reference
import apply_approved_spring_code_v2 as apply_script
import spring_code_apply_v2 as core
import recover_spring_code_apply_v2 as recover_script

class ApplyV2Tests(unittest.TestCase):
 def fixture(self,root:Path,two=False):
  docs=root/"docs";docs.mkdir();verification=docs/"verification.json";verification.write_text("{}");dry=docs/"dry.json";files=[{"componentRef":"c1","role":"CONTROLLER","path":"src/main/java/a/A.java","mode":0o644,"sha256":__import__("hashlib").sha256(b"class A {}\n").hexdigest(),"content":"class A {}\n"}]
  if two:files.append({"componentRef":"c2","role":"TEST","path":"src/test/java/a/ATest.java","mode":0o644,"sha256":__import__("hashlib").sha256(b"class ATest {}\n").hexdigest(),"content":"class ATest {}\n"})
  parents=set()
  for item in files:
   parent=Path(item["path"]).parent
   while str(parent)!=".":parents.add(parent.as_posix());parent=parent.parent
  dry.write_text(json.dumps({"generatedFiles":files}));review_path=docs/"review.json";view=docs/"review.md";view.write_text("view");approval=docs/"approval.json";approval.write_text("{}");desired={"manifestVersion":2,"artifactKind":"SPRING_IMPLEMENTATION_V2","files":{i["path"]:i["sha256"] for i in files},"modes":{i["path"]:i["mode"] for i in files}};tx="spring-code-v2-test123";review={"transactionId":tx,"verification":reference(verification,root),"dryRun":reference(dry,root),"fileActions":{"creates":[{k:i[k] for k in ("componentRef","path","mode","sha256")} for i in files],"reuses":[],"updates":[],"deletes":[]},"parentDirectories":sorted(parents,key=lambda p:(len(Path(p).parts),p)),"desiredBaseline":{"sha256":__import__("hashlib").sha256(apply_script.encoded(desired)).hexdigest(),"document":desired},"backup":{"path":f".starter-harness/backups/spring-code-v2/{tx}"},"journal":{"path":f".starter-harness/transactions/{tx}.json"},"result":{"path":"docs/apply-result.json"}};review_path.write_text(json.dumps(review));return review_path,approval,review,files
 def test_create_apply_commits_baseline_and_separate_result(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);review,approval,value,files=self.fixture(root)
   with mock.patch.object(apply_script,"validate_approval"):record=apply_script.apply(root,review,approval)
   self.assertEqual("COMMITTED",record["state"]);self.assertTrue((root/files[0]["path"]).is_file());self.assertTrue((root/core.BASELINE).is_file());self.assertTrue((root/value["result"]["path"]).is_file())
 def test_partial_failure_removes_exact_created_files_and_parents(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);review,approval,_,files=self.fixture(root,True);real=apply_script.atomic_file;calls=0
   def fail_second(content,mode,path):
    nonlocal calls
    if path.suffix==".java":
     calls+=1
     if calls==2:raise OSError("injected")
    return real(content,mode,path)
   with mock.patch.object(apply_script,"validate_approval"),mock.patch.object(apply_script,"atomic_file",side_effect=fail_second),self.assertRaisesRegex(ValueError,"rolled back"):apply_script.apply(root,review,approval)
   self.assertFalse(any((root/i["path"]).exists() for i in files));journal=load(root/".starter-harness/transactions/spring-code-v2-test123.json");self.assertEqual("ROLLED_BACK",journal["state"])
 def test_report_failure_keeps_committed_source_for_recovery(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);review,approval,value,files=self.fixture(root)
   with mock.patch.object(apply_script,"validate_approval"),mock.patch.object(apply_script,"write_result",side_effect=OSError("report")):record=apply_script.apply(root,review,approval)
   self.assertEqual("COMMITTED_REPORT_PENDING",record["state"]);self.assertTrue((root/files[0]["path"]).exists());self.assertTrue((root/core.BASELINE).exists())
 def test_os_lock_rejects_concurrent_apply(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   with core.apply_lock(root):
    with self.assertRaisesRegex(ValueError,"BUSY"):
     with core.apply_lock(root):pass
 def test_review_rejects_existing_case_collision_and_baseline_owner(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);review,_,_,files=self.fixture(root);existing=root/"src/main/java/a/a.java";existing.parent.mkdir(parents=True);existing.write_text("x");baseline=root/core.BASELINE;baseline.write_text(json.dumps({"manifestVersion":2,"artifactKind":"SPRING_IMPLEMENTATION_V2","files":{files[0]["path"]:"0"*64},"modes":{files[0]["path"]:420}}));verification=root/"docs/verification.json";plan=root/"docs/plan.json";dry=root/"docs/dry.json";plan.write_text(json.dumps({"git":{}}));verification.write_text(json.dumps({"plan":reference(plan,root),"dryRun":reference(dry,root)}));dry.write_text(json.dumps({"renderer":"JAVA_MVC_API_ONLY_V1","summary":{"updates":0},"generatedFiles":files,"reusedFiles":[]}))
   with mock.patch.object(core,"validate_apply_readiness"),mock.patch.object(core,"current_baseline",return_value={"reference":reference(baseline,root),"files":{files[0]["path"]:"0"*64}}),mock.patch.object(core,"git_extra",return_value={"ignoredTargets":[],"submoduleOverlaps":[],"sparseCheckout":False}),mock.patch.object(core,"pending",return_value=[]):result=core.build_review(root,verification,"docs/result.json")
   codes={i["code"] for i in result["blockers"]};self.assertIn("CASE_COLLISION",codes);self.assertIn("BASELINE_ALREADY_OWNS_CREATE",codes)
 def test_recovery_rejects_tampered_backup_path(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);transaction="spring-code-v2-test123";journal=root/".starter-harness/transactions"/(transaction+".json");journal.parent.mkdir(parents=True);journal.write_text(json.dumps({"springCodeTransactionV2Version":1,"transactionId":transaction,"target":str(root),"backup":"../outside","state":"PREPARED"}))
   with mock.patch.object(sys,"argv",["recover","--target",str(root),"--transaction-id",transaction]):self.assertEqual(1,recover_script.main())
def load(path):return json.loads(path.read_text())
if __name__=="__main__":unittest.main()
