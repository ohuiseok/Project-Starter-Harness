#!/usr/bin/env python3
"""Run an exactly approved code candidate in a read-only, networkless sandbox."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from apply_approved_generation import non_empty
from render_generation_dry_run import write_report
from spring_code_dry_run import sha, validate_report
from validate_feature_specs import load_object


MAX_OUTPUT = 20000


def target_context_hash(target: Path, generated_paths: set[str]) -> str:
    names = {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "gradle.properties", "pom.xml", "gradlew", "mvnw"}
    evidence = {}
    for path in sorted(target.rglob("*")):
        if path.is_symlink():
            continue
        relative = path.relative_to(target).as_posix()
        relevant = path.is_file() and (path.name in names or relative.startswith("gradle/wrapper/") or (relative.startswith("src/") and relative not in generated_paths))
        if relevant:
            evidence[relative] = sha(path)
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_approval(value: dict, report_path: Path, target: Path) -> None:
    required = {"springCodeVerificationApprovalVersion", "approved", "dryRunReportSha256", "target", "approvedBy", "approvedAt"}
    if not isinstance(value, dict) or set(value) != required or value["springCodeVerificationApprovalVersion"] != 1 or value["approved"] is not True:
        raise ValueError("explicit Spring code verification approval is required")
    if value["dryRunReportSha256"] != sha(report_path) or Path(str(value["target"])).resolve() != target.resolve():
        raise ValueError("verification approval does not match the exact dry-run report and target")
    if not non_empty(value["approvedBy"]) or not non_empty(value["approvedAt"]):
        raise ValueError("verification approval identity and time are required")
    timestamp = dt.datetime.fromisoformat(value["approvedAt"].replace("Z", "+00:00"))
    if timestamp.utcoffset() is None:
        raise ValueError("verification approval time must include a timezone")


def copy_target(target: Path, workspace: Path) -> None:
    ignored = shutil.ignore_patterns(".git", ".gradle", "build", "target", ".starter-harness")
    shutil.copytree(target, workspace, dirs_exist_ok=True, symlinks=True, ignore=ignored)
    links = [path.relative_to(workspace).as_posix() for path in workspace.rglob("*") if path.is_symlink()]
    if links:
        raise ValueError("symbolic links are not allowed in the isolated verification copy: " + ", ".join(links[:10]))


def overlay(report: dict, workspace: Path) -> None:
    for item in report["generatedFiles"]:
        destination = workspace / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(item["content"], encoding="utf-8")


def build_command(workspace: Path) -> list[str]:
    if (workspace / "gradlew").is_file():
        return ["./gradlew", "--offline", "--no-daemon", "test"]
    if (workspace / "mvnw").is_file():
        return ["./mvnw", "-o", "test"]
    raise ValueError("target has no Gradle or Maven wrapper for isolated verification")


def sandbox_command(workspace: Path, command: list[str]) -> list[str]:
    if shutil.which("bwrap") is None:
        raise ValueError("bubblewrap is required for filesystem and network isolation")
    home = workspace / ".verification-home"
    home.mkdir()
    return [
        "bwrap", "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/",
        "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", "/run",
        "--bind", str(workspace), str(workspace), "--chdir", str(workspace),
        "--setenv", "HOME", str(home), "--setenv", "GRADLE_USER_HOME", str(home / ".gradle"),
        "--setenv", "DOCKER_HOST", "unix:///run/starter-harness-no-docker.sock", "--", *command,
    ]


def isolation_preflight() -> None:
    completed = subprocess.run(["bwrap", "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", "/run", "--", "/bin/true"], capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode:
        raise ValueError("bubblewrap network/filesystem isolation is unavailable: " + (completed.stderr or completed.stdout)[-1000:])


def result_state(returncode: int, output: str) -> str:
    if returncode == 0:
        return "PASSED"
    infrastructure = ("Could not resolve", "distributionUrl", "Could not install Gradle", "PluginResolutionException", "Unknown host", "Network is unreachable")
    return "UNKNOWN" if any(marker in output for marker in infrastructure) else "FAILED"


def validate_verification_report(report: dict, report_path: Path, target: Path) -> None:
    required = {"springCodeVerificationReportVersion", "dryRun", "approval", "target", "targetContextSha256", "isolation", "command", "result", "targetSourceChanged", "readyForApplyApproval"}
    if not isinstance(report, dict) or set(report) != required or report["springCodeVerificationReportVersion"] != 1:
        raise ValueError("Spring code verification report is invalid")
    if Path(str(report["target"])).resolve() != target.resolve() or report["targetSourceChanged"] is not False:
        raise ValueError("verification target safety evidence is invalid")
    if report["isolation"] != {"filesystem": "READ_ONLY_EXCEPT_TEMP_COPY", "network": "DISABLED", "dockerSocket": "HIDDEN"}:
        raise ValueError("verification isolation evidence is invalid")
    for name in ("dryRun", "approval"):
        ref = report[name]
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
            raise ValueError(f"verification {name} evidence is invalid")
        path = target / ref["path"]
        if path.is_symlink() or not path.is_file() or sha(path) != ref["sha256"]:
            raise ValueError(f"verification {name} evidence changed")
    dry_run_path = target / report["dryRun"]["path"]
    dry_run = load_object(dry_run_path)
    validate_report(dry_run, target)
    generated_paths = {item["path"] for item in dry_run["generatedFiles"]}
    if report["targetContextSha256"] != target_context_hash(target, generated_paths):
        raise ValueError("target build/source context changed after verification")
    validate_approval(load_object(target / report["approval"]["path"]), dry_run_path, target)
    expected_command = build_command(target)
    if report["command"] != expected_command:
        raise ValueError("verification command evidence changed")
    result = report["result"]
    if not isinstance(result, dict) or set(result) != {"state", "exitCode", "output"} or result["state"] not in {"PASSED", "FAILED", "UNKNOWN"} or not isinstance(result["exitCode"], int) or not isinstance(result["output"], str):
        raise ValueError("verification result evidence is invalid")
    if (result["state"] == "PASSED") != (result["exitCode"] == 0) or report["readyForApplyApproval"] is not (result["state"] == "PASSED"):
        raise ValueError("verification readiness does not match the result")
    if report_path.is_symlink() or target.resolve() not in report_path.resolve().parents:
        raise ValueError("verification report must be target-owned")


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("report", "approval", "target", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        root = args.target.resolve(strict=True)
        report_path = args.report.resolve(strict=True)
        approval_path = args.approval.resolve(strict=True)
        output = args.output.resolve(strict=False)
        if not 30 <= args.timeout_seconds <= 1800 or args.target.is_symlink() or root not in report_path.parents or root not in approval_path.parents or root not in output.parents or args.report.is_symlink() or args.approval.is_symlink() or args.output.is_symlink():
            raise ValueError("verification paths or timeout are unsafe")
        report = load_object(report_path)
        validate_report(report, root)
        if report["readyForApproval"] is not True:
            raise ValueError("code dry-run is not ready for isolated verification")
        validate_approval(load_object(approval_path), report_path, root)
        isolation_preflight()
        generated_paths = {item["path"] for item in report["generatedFiles"]}
        context_hash = target_context_hash(root, generated_paths)
        before = {item["path"]: (root / item["path"]).read_bytes() if (root / item["path"]).is_file() else None for item in report["generatedFiles"]}
        with tempfile.TemporaryDirectory(prefix="spring-code-verification-", dir="/var/tmp") as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            copy_target(root, workspace)
            overlay(report, workspace)
            command = build_command(workspace)
            try:
                completed = subprocess.run(sandbox_command(workspace, command), capture_output=True, text=True, timeout=args.timeout_seconds, check=False)
                output_text = (completed.stdout + completed.stderr)[-MAX_OUTPUT:]
                exit_code = completed.returncode
                state = result_state(exit_code, output_text)
            except subprocess.TimeoutExpired as error:
                state, exit_code = "FAILED", 124
                output_text = ((error.stdout or "") + (error.stderr or ""))[-MAX_OUTPUT:]
        after = {path: (root / path).read_bytes() if (root / path).is_file() else None for path in before}
        if before != after:
            raise RuntimeError("target source changed during isolated verification")
        result = {
            "springCodeVerificationReportVersion": 1,
            "dryRun": {"path": report_path.relative_to(root).as_posix(), "sha256": sha(report_path)},
            "approval": {"path": approval_path.relative_to(root).as_posix(), "sha256": sha(approval_path)},
            "target": str(root),
            "targetContextSha256": context_hash,
            "isolation": {"filesystem": "READ_ONLY_EXCEPT_TEMP_COPY", "network": "DISABLED", "dockerSocket": "HIDDEN"},
            "command": command,
            "result": {"state": state, "exitCode": exit_code, "output": output_text},
            "targetSourceChanged": False,
            "readyForApplyApproval": state == "PASSED",
        }
        write_report(result, output, args.force)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"SPRING_CODE_VERIFICATION_VALID: no\nERROR: {error}", file=sys.stderr)
        return 1
    print("SPRING_CODE_VERIFICATION_VALID: yes")
    print(f"VERIFICATION_RESULT: {result['result']['state']}")
    print("TARGET_SOURCE_CHANGED: no")
    print(f"READY_FOR_APPLY_APPROVAL: {'yes' if result['readyForApplyApproval'] else 'no'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
