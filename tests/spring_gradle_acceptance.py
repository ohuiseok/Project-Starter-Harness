#!/usr/bin/env python3
"""Run an opt-in real Spring MVC/Gradle smoke in the production sandbox."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
DEFAULT_SCENARIO = Path(__file__).with_name("spring-gradle-acceptance-scenario.json")
sys.path.insert(0, str(SCRIPTS))

from run_spring_code_verification_v2 import copy_cache, sandbox
from spring_code_verification_v2 import PII, SECRET, cache, runtime_mounts
from run_post_apply_verification_v2 import classify


def outcome(state: str, stage: str, category: str, next_action: str, **details) -> dict:
    return {
        "acceptanceState": state,
        "stage": stage,
        "category": category,
        "nextAction": next_action,
        "evidenceScope": "REAL_SPRING_GRADLE_RUNTIME",
        "doesNotProve": ["NATURAL_LANGUAGE_INTERPRETATION", "PRODUCTION_APPLY_TRANSACTION", "FULL_UNMOCKED_CONTRACT_CHAIN", "DATABASE_RUNTIME"],
        "details": details,
    }


def safe_message(value: object) -> str:
    text = str(value)[:1000]
    return PII.sub("[REDACTED_PII]", SECRET.sub("[REDACTED]", text))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_scenario(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {"scenarioVersion", "id", "springBootVersion", "dependencyManagementVersion", "gradleVersion", "javaToolchain", "command", "expectedTest", "limits"}
    if set(value) != required or value["scenarioVersion"] != 1:
        raise ValueError("acceptance scenario structure is invalid")
    if not all(isinstance(value[key], str) and value[key] for key in ("id", "springBootVersion", "dependencyManagementVersion", "gradleVersion", "expectedTest")):
        raise ValueError("acceptance scenario identity or versions are invalid")
    version_pattern = r"\d+\.\d+(?:\.\d+)?(?:[-.][A-Za-z0-9]+)*"
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value["id"]) or any(not re.fullmatch(version_pattern, value[key]) for key in ("springBootVersion", "dependencyManagementVersion", "gradleVersion")):
        raise ValueError("acceptance scenario identity or versions are unsafe")
    if not isinstance(value["javaToolchain"], int) or value["javaToolchain"] < 17:
        raise ValueError("acceptance Java toolchain is invalid")
    expected = ["./gradlew", "--offline", "--no-daemon", "test"]
    if value["command"] != expected or value["limits"].keys() != {"timeoutSeconds", "maxLogCharacters"}:
        raise ValueError("acceptance command or limits are invalid")
    if not 30 <= value["limits"]["timeoutSeconds"] <= 1800 or not 10000 <= value["limits"]["maxLogCharacters"] <= 100000:
        raise ValueError("acceptance limits are out of range")
    return value


def prerequisites(scenario: dict | None = None) -> dict:
    scenario = scenario or load_scenario(DEFAULT_SCENARIO)
    missing = [name for name in ("java", "bwrap") if shutil.which(name) is None]
    if missing:
        return outcome("UNKNOWN", "ENVIRONMENT", "TOOL_MISSING", "필요한 실행 도구를 설치한 뒤 다시 검증", missing=missing)
    try:
        evidence = cache("GRADLE")
    except (OSError, ValueError) as error:
        return outcome("UNKNOWN", "ENVIRONMENT", "CACHE_UNREADABLE", "Gradle 캐시 상태를 확인한 뒤 다시 검증", error=safe_message(error))
    if evidence["status"] != "READY":
        return outcome("UNKNOWN", "ENVIRONMENT", "OFFLINE_CACHE_NOT_READY", "필요한 Gradle/Spring 의존성을 로컬 캐시에 준비", cacheStatus=evidence["status"])
    gradle_home = Path(os.environ.get("GRADLE_USER_HOME", Path.home() / ".gradle"))
    version = scenario["gradleVersion"]
    distributions = sorted((gradle_home / f"wrapper/dists/gradle-{version}-bin").glob(f"*/gradle-{version}/bin/gradle"))
    if not distributions or not distributions[0].is_file():
        return outcome("UNKNOWN", "ENVIRONMENT", "GRADLE_DISTRIBUTION_MISSING", f"Gradle {version} wrapper 배포본을 로컬 캐시에 준비")
    return outcome("RUNNABLE", "ENVIRONMENT", "READY", "격리된 실제 Spring 빌드 실행", cache=evidence, gradleExecutable=str(distributions[0]))


def write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def write_seed_files(root: Path, scenario: dict) -> None:
    write(root / "settings.gradle", "rootProject.name = 'starter-harness-acceptance'\n")
    write(root / "build.gradle", f"""plugins {{
    id 'java'
    id 'org.springframework.boot' version '{scenario["springBootVersion"]}'
    id 'io.spring.dependency-management' version '{scenario["dependencyManagementVersion"]}'
}}

group = 'com.example'
version = '0.0.1-SNAPSHOT'
java {{ toolchain {{ languageVersion = JavaLanguageVersion.of({scenario["javaToolchain"]}) }} }}
repositories {{ mavenCentral() }}
dependencies {{
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}}
tasks.named('test') {{ useJUnitPlatform() }}
""")
    write(root / "src/main/java/com/example/AcceptanceApplication.java", """package com.example;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
@SpringBootApplication
public class AcceptanceApplication {
  public static void main(String[] args) { SpringApplication.run(AcceptanceApplication.class, args); }
}
""")


def write_feature_candidates(root: Path) -> list[dict]:
    paths = [root / "src/main/java/com/example/OrdersController.java", root / "src/test/java/com/example/OrdersControllerTest.java"]
    write(root / "src/main/java/com/example/OrdersController.java", """package com.example;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
@RestController
public class OrdersController {
  @GetMapping("/orders") public String orders() { return "[]"; }
}
""")
    write(root / "src/test/java/com/example/OrdersControllerTest.java", """package com.example;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
@SpringBootTest
@AutoConfigureMockMvc
class OrdersControllerTest {
  @Autowired MockMvc mvc;
  @Test void returnsOrders() throws Exception {
    mvc.perform(get("/orders")).andExpect(status().isOk()).andExpect(content().string("[]"));
  }
}
""")
    return [{"path": path.relative_to(root).as_posix(), "sha256": sha(path), "mode": path.stat().st_mode & 0o777} for path in paths]


def create_target(root: Path, gradle_executable: str, scenario: dict) -> str:
    write_seed_files(root, scenario)
    subprocess.run([gradle_executable, "--offline", "--no-daemon", "wrapper", "--gradle-version", scenario["gradleVersion"], "--distribution-type", "bin"], cwd=root, check=True, timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "acceptance@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Harness Acceptance"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "acceptance fixture"], cwd=root, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def run(timeout: int | None = None, scenario_path: Path = DEFAULT_SCENARIO, log_path: Path | None = None) -> dict:
    try:
        scenario = load_scenario(scenario_path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        return outcome("BLOCKED", "SCENARIO", "SCENARIO_INVALID", "acceptance scenario 계약을 수정", error=safe_message(error))
    timeout = scenario["limits"]["timeoutSeconds"] if timeout is None else timeout
    if not 30 <= timeout <= 1800:
        return outcome("BLOCKED", "SCENARIO", "TIMEOUT_INVALID", "30~1800초 범위로 제한 시간을 수정")
    ready = prerequisites(scenario)
    if ready["acceptanceState"] != "RUNNABLE":
        return ready
    with tempfile.TemporaryDirectory(prefix="spring-gradle-acceptance-", dir="/var/tmp") as temporary:
        base = Path(temporary)
        target, home = base / "external-target", base / "home"
        target.mkdir(); home.mkdir()
        try:
            initial_head = create_target(target, ready["details"]["gradleExecutable"], scenario)
        except subprocess.TimeoutExpired:
            return outcome("UNKNOWN", "WRAPPER_PROVISIONING", "TIMEOUT", "Gradle wrapper 준비 환경을 확인한 뒤 재실행")
        except (OSError, subprocess.SubprocessError) as error:
            return outcome("UNKNOWN", "WRAPPER_PROVISIONING", "GRADLE_UNAVAILABLE", "Gradle 배포본과 오프라인 plugin 캐시를 확인", error=safe_message(error))
        try:
            if (target / "src/main/java/com/example/OrdersController.java").exists():
                return outcome("BLOCKED", "SEED", "FEATURE_ALREADY_PRESENT", "초기 seed에서 F001 기능 코드를 제거")
            generated = write_feature_candidates(target)
            cache_evidence = cache("GRADLE")
            if cache_evidence["status"] != "READY":
                return outcome("UNKNOWN", "ENVIRONMENT", "OFFLINE_CACHE_NOT_READY", "wrapper 준비 후 Gradle 캐시를 다시 확인", cacheStatus=cache_evidence["status"])
            copy_cache("GRADLE", home, cache_evidence)
            process = subprocess.run(
                sandbox(target, home, scenario["command"], runtime_mounts()),
                cwd=target,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return outcome("UNKNOWN", "SPRING_TEST", "TIMEOUT", "제한 시간 또는 실행 환경을 검토한 뒤 새 시도로 재실행")
        except ValueError as error:
            return outcome("BLOCKED", "EVIDENCE", "EVIDENCE_STALE_OR_UNSAFE", "캐시 또는 sandbox 증거를 다시 준비하고 승인", error=safe_message(error))
        except (OSError, subprocess.SubprocessError) as error:
            return outcome("UNKNOWN", "ENVIRONMENT", "EXECUTION_UNAVAILABLE", "Java·Gradle·bubblewrap 실행 환경을 확인", error=safe_message(error))
        text = process.stdout.decode("utf-8", "replace")[-scenario["limits"]["maxLogCharacters"]:]
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        redacted = bool(SECRET.search(text) or PII.search(text))
        text = PII.sub("[REDACTED_PII]", SECRET.sub("[REDACTED]", text))
        if log_path is not None:
            atomic_output(log_path, text + ("\n" if text and not text.endswith("\n") else ""))
        state, category = classify(process.returncode, text, False, redacted)
        if process.returncode and ("org.gradle" in text and ("NoClassDefFoundError" in text or "ClassNotFoundException" in text)):
            state, category = "UNKNOWN", "OFFLINE_DEPENDENCY_OR_INFRASTRUCTURE"
        if state == "VERIFIED":
            return outcome("PASSED", "SPRING_TEST", category, "실제 Spring 실행 증거를 v2 계약-chain acceptance와 함께 유지", scenario={"path":str(scenario_path),"sha256":sha(scenario_path),"id":scenario["id"],"expectedTest":scenario["expectedTest"]},initialGitHead=initial_head,generatedFiles=generated,exitCode=process.returncode,targetWasExternal=True,featureAbsentFromInitialCommit=True,redactedLog=bool(log_path))
        next_action = "Gradle 캐시·Java·sandbox 환경 확인" if state == "UNKNOWN" else "생성 코드 또는 Spring 테스트 수정"
        return outcome(state, "SPRING_TEST", category, next_action, scenario={"path":str(scenario_path),"sha256":sha(scenario_path),"id":scenario["id"]},initialGitHead=initial_head,generatedFiles=generated,exitCode=process.returncode,output=text,redactedLog=bool(log_path))


def atomic_output(path: Path, content: str) -> None:
    path = path.absolute()
    if path.exists() or path.is_symlink():
        raise ValueError("acceptance output is occupied")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ValueError("acceptance output parent is unsafe")
    path = path.parent.resolve(strict=True) / path.name
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("acceptance output staging path is occupied")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    result = run(args.timeout, args.scenario.resolve(), args.log.resolve() if args.log else None)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try: atomic_output(args.output, rendered)
        except (OSError, ValueError) as error:
            result = outcome("BLOCKED", "EVIDENCE_OUTPUT", "OUTPUT_UNSAFE", "비어 있는 안전한 결과 경로를 선택", error=safe_message(error));rendered=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    print(rendered, end="")
    return {"PASSED": 0, "FAILED": 1, "BLOCKED": 2, "UNKNOWN": 3}.get(result["acceptanceState"], 2)


if __name__ == "__main__":
    sys.exit(main())
