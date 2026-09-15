#!/usr/bin/env python3
"""Execute real local wrapper processes through the v2 post-apply runner."""
from __future__ import annotations
import contextlib,io,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parent.parent;SCRIPTS=ROOT/".agents/skills/spring-project-start/scripts";sys.path[:0]=[str(SCRIPTS),str(ROOT)]
from http_api_spring_mapping import reference
from post_apply_verification_v2 import manifest
import run_post_apply_verification_v2 as runner
class ExecutionLoopV2Tests(unittest.TestCase):
 def fixture(self,root:Path,kind:str,attempt:str):
  subprocess.run(["git","init","-q"],cwd=root,check=True);subprocess.run(["git","config","user.email","test@example.com"],cwd=root,check=True);subprocess.run(["git","config","user.name","Test"],cwd=root,check=True);docs=root/"docs";docs.mkdir();wrapper=root/("gradlew" if kind=="GRADLE" else "mvnw");wrapper.write_text("#!/bin/sh\necho TESTS-PASSED\nexit 0\n");wrapper.chmod(0o755);(root/"src/main/java").mkdir(parents=True);(root/"src/main/java/A.java").write_text("class A {}\n");subprocess.run(["git","add","."],cwd=root,check=True);subprocess.run(["git","commit","-qm","fixture"],cwd=root,check=True);plan_path=docs/(attempt+"-plan.json");approval=docs/(attempt+"-approval.json");approval.write_text("{}");command={"executable":"./"+wrapper.name,"arguments":["test"],"workingDirectory":"."};plan={"attemptId":attempt,"applyResult":reference(approval,root),"applyTransactionId":"spring-code-v2-test","dependencyCache":{"kind":kind},"command":command,"limits":{"timeoutSeconds":30,"maxLogBytes":10000,"termGraceSeconds":1},"git":runner.git_state(root,set(manifest(root)["files"]))};plan_path.write_text(json.dumps(plan));return plan_path,approval,plan,docs/(attempt+"-result.json")
 def run_attempt(self,root:Path,kind:str,attempt:str):
  plan_path,approval,plan,output=self.fixture(root,kind,attempt) if not (root/".git").exists() else self.additional(root,kind,attempt)
  argv=["run","--plan",str(plan_path),"--approval",str(approval),"--target",str(root),"--output",str(output)];sandbox=lambda workspace,home,command:[str(workspace/command[0][2:]),*command[1:]]
  with mock.patch.object(sys,"argv",argv),mock.patch.object(runner,"validate_plan"),mock.patch.object(runner,"validate_approval"),mock.patch.object(runner,"copy_cache"),mock.patch.object(runner,"sandbox",side_effect=sandbox),contextlib.redirect_stdout(io.StringIO()):code=runner.main()
  return code,plan,output
 def additional(self,root:Path,kind:str,attempt:str):
  docs=root/"docs";plan_path=docs/(attempt+"-plan.json");approval=docs/(attempt+"-approval.json");approval.write_text("{}");wrapper="gradlew" if kind=="GRADLE" else "mvnw";plan={"attemptId":attempt,"applyResult":reference(approval,root),"applyTransactionId":"spring-code-v2-test","dependencyCache":{"kind":kind},"command":{"executable":"./"+wrapper,"arguments":["test"],"workingDirectory":"."},"limits":{"timeoutSeconds":30,"maxLogBytes":10000,"termGraceSeconds":1},"git":runner.git_state(root,set(manifest(root)["files"]))};plan_path.write_text(json.dumps(plan));return plan_path,approval,plan,docs/(attempt+"-result.json")
 def test_gradle_wrapper_process_reaches_verified(self):
  with tempfile.TemporaryDirectory() as d:
   code,_,output=self.run_attempt(Path(d),"GRADLE","post-apply-v2-gradle");self.assertEqual(0,code);self.assertEqual("VERIFIED",json.loads(output.read_text())["state"])
 def test_maven_wrapper_process_reaches_verified(self):
  with tempfile.TemporaryDirectory() as d:
   code,_,output=self.run_attempt(Path(d),"MAVEN","post-apply-v2-maven");self.assertEqual(0,code);self.assertEqual("VERIFIED",json.loads(output.read_text())["state"])
 def test_retry_requires_new_attempt_and_preserves_first_log(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.assertEqual(0,self.run_attempt(root,"GRADLE","post-apply-v2-one")[0]);first=root/".starter-harness/logs/post-apply-v2/post-apply-v2-one.log";(root/"docs/post-apply-v2-one-result.json").unlink();self.assertEqual(1,self.run_attempt(root,"GRADLE","post-apply-v2-one")[0]);self.assertEqual(0,self.run_attempt(root,"GRADLE","post-apply-v2-two")[0]);self.assertTrue(first.is_file());self.assertTrue((root/".starter-harness/logs/post-apply-v2/post-apply-v2-two.log").is_file())
if __name__=="__main__":unittest.main()
