#!/usr/bin/env python3
"""Run an opt-in real Spring MVC/Gradle smoke in the production sandbox."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
sys.path.insert(0, str(SCRIPTS))

from run_spring_code_verification_v2 import copy_cache, sandbox
from spring_code_verification_v2 import PII, SECRET, cache
from run_post_apply_verification_v2 import classify


def outcome(state: str, stage: str, category: str, next_action: str, **details) -> dict:
    return {
        "acceptanceState": state,
        "stage": stage,
        "category": category,
        "nextAction": next_action,
        "evidenceScope": "REAL_SPRING_GRADLE_RUNTIME",
        "doesNotProve": ["NATURAL_LANGUAGE_INTERPRETATION", "FULL_UNMOCKED_CONTRACT_CHAIN", "DATABASE_RUNTIME"],
        "details": details,
    }


def safe_message(value: object) -> str:
    text = str(value)[:1000]
    return PII.sub("[REDACTED_PII]", SECRET.sub("[REDACTED]", text))


def prerequisites() -> dict:
    missing = [name for name in ("java", "bwrap") if shutil.which(name) is None]
    if missing:
        return outcome("UNKNOWN", "ENVIRONMENT", "TOOL_MISSING", "필요한 실행 도구를 설치한 뒤 다시 검증", missing=missing)
    try:
        evidence = cache("GRADLE")
    except (OSError, ValueError) as error:
        return outcome("UNKNOWN", "ENVIRONMENT", "CACHE_UNREADABLE", "Gradle 캐시 상태를 확인한 뒤 다시 검증", error=safe_message(error))
    if evidence["status"] != "READY":
        return outcome("UNKNOWN", "ENVIRONMENT", "OFFLINE_CACHE_NOT_READY", "필요한 Gradle/Spring 의존성을 로컬 캐시에 준비", cacheStatus=evidence["status"])
    distributions = sorted((Path.home() / ".gradle/wrapper/dists/gradle-8.5-bin").glob("*/gradle-8.5/bin/gradle"))
    if not distributions or not distributions[0].is_file():
        return outcome("UNKNOWN", "ENVIRONMENT", "GRADLE_DISTRIBUTION_MISSING", "Gradle 8.5 wrapper 배포본을 로컬 캐시에 준비")
    return outcome("RUNNABLE", "ENVIRONMENT", "READY", "격리된 실제 Spring 빌드 실행", cache=evidence, gradleExecutable=str(distributions[0]))


def write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def write_target_files(root: Path) -> None:
    write(root / "settings.gradle", "rootProject.name = 'starter-harness-acceptance'\n")
    write(root / "build.gradle", """plugins {
    id 'java'
    id 'org.springframework.boot' version '3.2.0'
    id 'io.spring.dependency-management' version '1.1.4'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'
java { toolchain { languageVersion = JavaLanguageVersion.of(17) } }
repositories { mavenCentral() }
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
tasks.named('test') { useJUnitPlatform() }
""")
    write(root / "src/main/java/com/example/AcceptanceApplication.java", """package com.example;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
@SpringBootApplication
public class AcceptanceApplication {
  public static void main(String[] args) { SpringApplication.run(AcceptanceApplication.class, args); }
}
""")
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
def create_target(root: Path, gradle_executable: str) -> None:
    write_target_files(root)
    subprocess.run([gradle_executable, "--offline", "--no-daemon", "wrapper", "--gradle-version", "8.5", "--distribution-type", "bin"], cwd=root, check=True, timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "acceptance@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Harness Acceptance"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "acceptance fixture"], cwd=root, check=True)


def run(timeout: int = 300) -> dict:
    ready = prerequisites()
    if ready["acceptanceState"] != "RUNNABLE":
        return ready
    with tempfile.TemporaryDirectory(prefix="spring-gradle-acceptance-", dir="/var/tmp") as temporary:
        base = Path(temporary)
        target, home = base / "external-target", base / "home"
        target.mkdir(); home.mkdir()
        try:
            create_target(target, ready["details"]["gradleExecutable"])
            cache_evidence = cache("GRADLE")
            if cache_evidence["status"] != "READY":
                return outcome("UNKNOWN", "ENVIRONMENT", "OFFLINE_CACHE_NOT_READY", "wrapper 준비 후 Gradle 캐시를 다시 확인", cacheStatus=cache_evidence["status"])
            copy_cache("GRADLE", home, cache_evidence)
            process = subprocess.run(
                sandbox(target, home, ["./gradlew", "--offline", "--no-daemon", "test"]),
                cwd=target,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return outcome("UNKNOWN", "SPRING_TEST", "TIMEOUT", "제한 시간 또는 실행 환경을 검토한 뒤 새 시도로 재실행")
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return outcome("BLOCKED", "FIXTURE_OR_SANDBOX", "PRECONDITION_INVALID", "fixture 또는 sandbox 계약을 수정", error=safe_message(error))
        text = process.stdout.decode("utf-8", "replace")[-20000:]
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        redacted = bool(SECRET.search(text) or PII.search(text))
        text = PII.sub("[REDACTED_PII]", SECRET.sub("[REDACTED]", text))
        state, category = classify(process.returncode, text, False, redacted)
        if process.returncode and ("org.gradle" in text and ("NoClassDefFoundError" in text or "ClassNotFoundException" in text)):
            state, category = "UNKNOWN", "OFFLINE_DEPENDENCY_OR_INFRASTRUCTURE"
        if state == "VERIFIED":
            return outcome("PASSED", "SPRING_TEST", category, "실제 Spring 실행 증거를 v2 계약-chain acceptance와 함께 유지", exitCode=process.returncode, targetWasExternal=True)
        next_action = "Gradle 캐시·Java·sandbox 환경 확인" if state == "UNKNOWN" else "생성 코드 또는 Spring 테스트 수정"
        return outcome(state, "SPRING_TEST", category, next_action, exitCode=process.returncode, output=text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    result = run(args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"PASSED": 0, "FAILED": 1, "BLOCKED": 2, "UNKNOWN": 3}.get(result["acceptanceState"], 2)


if __name__ == "__main__":
    sys.exit(main())
