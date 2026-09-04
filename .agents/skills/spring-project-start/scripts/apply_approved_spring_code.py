#!/usr/bin/env python3
"""Apply exactly approved, isolated-verified Spring code with recovery evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from apply_approved_generation import atomic_json, non_empty, validate_sha
from render_generation_dry_run import digest
from run_spring_code_verification import target_context_hash, validate_verification_report
from spring_code_dry_run import BASELINE, canonical_baseline, sha, validate_report
from validate_feature_specs import load_object


MANAGED = ".starter-harness"
ACTIVE_STATES = {"PREPARED", "APPLYING"}


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if not isinstance(value, str) or not value or path.is_absolute() or ".." in path.parts or path.suffix != ".java" or path.parts[0] in {".git", MANAGED}:
        raise ValueError(f"unsafe Spring code path: {value!r}")
    return value


def pending_transactions(root: Path) -> list[Path]:
    directory = root / MANAGED / "implementation-transactions"
    if directory.is_symlink():
        raise ValueError("implementation transaction directory is unsafe")
    result = []
    if directory.is_dir():
        for record in directory.glob("*/transaction.json"):
            try:
                if load_object(record).get("state") in ACTIVE_STATES:
                    result.append(record)
            except (OSError, ValueError):
                raise ValueError(f"cannot inspect implementation transaction: {record}")
    return result


def dirty_paths(root: Path) -> set[str]:
    result = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError("target Git dirty state cannot be verified")
    paths = set()
    for line in result.stdout.splitlines():
        if len(line) > 3:
            value = line[3:].split(" -> ")[-1]
            paths.add(value.strip('"'))
    return paths


def validate_approval(value: dict, verification_path: Path, verification: dict, dry_path: Path, dry: dict, root: Path, baseline_ref: dict | None) -> None:
    required = {"springCodeApplyApprovalVersion", "approved", "verificationReportSha256", "dryRunReportSha256", "target", "targetContextSha256", "baselineSha256", "files", "approvedBy", "approvedAt"}
    if not isinstance(value, dict) or set(value) != required or value["springCodeApplyApprovalVersion"] != 1 or value["approved"] is not True:
        raise ValueError("explicit Spring code apply approval is required")
    expected = {
        "verificationReportSha256": sha(verification_path), "dryRunReportSha256": sha(dry_path),
        "targetContextSha256": verification["targetContextSha256"],
        "baselineSha256": baseline_ref["sha256"] if baseline_ref else None,
        "files": sorted(dry["plannedChanges"]["desiredManifest"]["files"]),
    }
    if any(value[name] != expected[name] for name in expected) or Path(str(value["target"])).resolve() != root:
        raise ValueError("apply approval does not match the exact verified code, target context, baseline, and files")
    if not non_empty(value["approvedBy"]) or not non_empty(value["approvedAt"]):
        raise ValueError("apply approval identity and time are required")
    timestamp = dt.datetime.fromisoformat(value["approvedAt"].replace("Z", "+00:00"))
    if timestamp.utcoffset() is None:
        raise ValueError("apply approval time must include a timezone")


def validate_target_changes(root: Path, changes: dict) -> None:
    creates = {item["path"]: item for item in changes["creates"]}
    updates = {item["path"]: item for item in changes["updates"]}
    manifest = changes["desiredManifest"]
    for relative in manifest["files"]:
        safe_path(relative)
        destination = root / relative
        parent = destination.parent
        while parent != root:
            if parent.is_symlink():
                raise ValueError(f"target parent is a symbolic link: {relative}")
            parent = parent.parent
        if relative in creates:
            if destination.exists() or destination.is_symlink():
                raise ValueError(f"CREATE target changed after verification: {relative}")
        else:
            if destination.is_symlink() or not destination.is_file():
                raise ValueError(f"existing target changed type after verification: {relative}")
            expected_hash = updates.get(relative, {}).get("beforeSha256", manifest["files"][relative])
            expected_mode = updates.get(relative, {}).get("beforeMode", manifest["modes"][relative])
            if digest(destination) != expected_hash or destination.stat().st_mode & 0o777 != expected_mode:
                raise ValueError(f"target changed after verification: {relative}")


def merged_baseline(existing: dict | None, manifest: dict, dry_hash: str, verification_hash: str) -> dict:
    files = dict(existing.get("files", {}) if existing else {})
    modes = dict(existing.get("modes", {}) if existing else {})
    files.update(manifest["files"]); modes.update(manifest["modes"])
    history = list(existing.get("appliedSlices", []) if existing else [])
    history.append({"dryRunSha256": dry_hash, "verificationSha256": verification_hash, "appliedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "files": sorted(manifest["files"])})
    return {"manifestVersion": 1, "artifactKind": "SPRING_IMPLEMENTATION", "files": files, "modes": modes, "appliedSlices": history}


def replace_file(content: bytes, mode: int, staged: Path, destination: Path) -> None:
    staged.parent.mkdir(parents=True, exist_ok=True)
    with staged.open("wb") as handle:
        handle.write(content); handle.flush(); os.fsync(handle.fileno())
    staged.chmod(mode); os.replace(staged, destination)
    directory = os.open(destination.parent, os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)


def recover_transaction(target: Path, transaction_id: str) -> dict:
    root = target.resolve(strict=True)
    if not transaction_id or "/" in transaction_id or transaction_id in {".", ".."}:
        raise ValueError("transaction ID is invalid")
    record_path = root / MANAGED / "implementation-transactions" / transaction_id / "transaction.json"
    record = load_object(record_path)
    required = {"springCodeTransactionVersion", "transactionId", "state", "target", "creates", "updates", "desiredManifest", "beforeManifest", "backup", "baselineExisted", "baselineBeforeSha256", "baselineAfterSha256"}
    allowed = required | {"appliedAt", "recoveryErrors"}
    if not isinstance(record, dict) or not required <= set(record) <= allowed or record.get("springCodeTransactionVersion") != 1 or record.get("transactionId") != transaction_id or record.get("state") not in ACTIVE_STATES or Path(str(record.get("target", ""))).resolve() != root:
        raise ValueError("transaction is not recoverable")
    manifest = record["desiredManifest"]; backup = Path(record["backup"]); expected_backup = root / MANAGED / "implementation-backups" / transaction_id
    if backup.resolve() != expected_backup.resolve() or backup.is_symlink() or not backup.is_dir(): raise ValueError("transaction backup path is invalid")
    if not isinstance(record["creates"], list) or not isinstance(record["updates"], list) or set(record["creates"]) & set(record["updates"]): raise ValueError("transaction file sets are invalid")
    for relative in record["creates"] + record["updates"]: safe_path(relative)
    if not isinstance(manifest, dict) or set(manifest) != {"manifestVersion", "files", "modes"} or manifest["manifestVersion"] != 1 or set(manifest["files"]) != set(manifest["modes"]) or set(manifest["files"]) != set(record["creates"] + record["updates"]): raise ValueError("transaction desired manifest is invalid")
    if not isinstance(record["beforeManifest"], dict) or set(record["beforeManifest"]) != set(record["updates"]): raise ValueError("transaction before manifest is invalid")
    errors = []
    for relative in reversed(sorted(set(record["creates"] + record["updates"]))):
        destination = root / safe_path(relative)
        try:
            if not destination.exists():
                continue
            if destination.is_symlink() or not destination.is_file() or digest(destination) != manifest["files"][relative]:
                if relative in record["creates"]: raise OSError("created file drifted; overwrite refused")
                before = record["beforeManifest"][relative]
                if digest(destination) == before["sha256"]: continue
                raise OSError("updated file drifted; overwrite refused")
            if relative in record["updates"]:
                source = backup / "files" / relative; before = record["beforeManifest"][relative]
                if source.is_symlink() or not source.is_file() or digest(source) != before["sha256"] or source.stat().st_mode & 0o777 != before["mode"]: raise OSError("backup evidence changed; restore refused")
                shutil.copy2(source, destination)
            else:
                destination.unlink()
        except OSError as error: errors.append(f"{relative}: {error}")
    baseline = root / BASELINE
    try:
        if record["baselineExisted"]:
            if baseline.exists() and digest(baseline) not in {record.get("baselineAfterSha256"), record["baselineBeforeSha256"]}: raise OSError("baseline drifted; overwrite refused")
            shutil.copy2(backup / BASELINE, baseline)
        elif baseline.exists():
            if record.get("baselineAfterSha256") and digest(baseline) != record["baselineAfterSha256"]: raise OSError("new baseline drifted; removal refused")
            baseline.unlink()
    except OSError as error: errors.append(f"baseline: {error}")
    record["state"] = "RECOVERY_FAILED" if errors else "RECOVERED"
    if errors: record["recoveryErrors"] = errors
    atomic_json(record, record_path)
    if errors: raise ValueError("implementation recovery was incomplete: " + "; ".join(errors))
    return {"transactionId": transaction_id, "state": "RECOVERED"}


def apply(args: argparse.Namespace) -> dict:
    root = args.target.resolve(strict=True)
    harness = Path(__file__).resolve().parents[4]
    if args.target.is_symlink() or not root.is_dir() or root == harness:
        raise ValueError("target must be an external non-symlink directory")
    pending = pending_transactions(root)
    if pending: raise ValueError(f"interrupted implementation transaction requires recovery: {pending[0].parent.name}")
    verification_path = args.verification_report.resolve(strict=True); dry_path = args.dry_run.resolve(strict=True); approval_path = args.approval.resolve(strict=True)
    if any(root not in path.parents or path.is_symlink() for path in (verification_path, dry_path, approval_path)):
        raise ValueError("apply evidence must be target-owned regular files")
    verification = load_object(verification_path); validate_verification_report(verification, verification_path, root)
    if verification["result"]["state"] != "PASSED" or verification["readyForApplyApproval"] is not True:
        raise ValueError("only a passing isolated verification may be applied")
    if verification["dryRun"]["path"] != dry_path.relative_to(root).as_posix() or verification["dryRun"]["sha256"] != sha(dry_path):
        raise ValueError("verification does not reference the supplied dry run")
    dry = load_object(dry_path); validate_report(dry, root)
    baseline_path, baseline_ref, _, _ = canonical_baseline(root)
    existing_baseline = load_object(baseline_path) if baseline_ref else None
    validate_approval(load_object(approval_path), verification_path, verification, dry_path, dry, root, baseline_ref)
    generated = {item["path"]: item["content"].encode() for item in dry["generatedFiles"]}
    manifest = dry["plannedChanges"]["desiredManifest"]
    if {path: __import__("hashlib").sha256(content).hexdigest() for path, content in generated.items()} != manifest["files"]:
        raise ValueError("dry-run content no longer matches its desired manifest")
    if target_context_hash(root, set(generated)) != verification["targetContextSha256"]:
        raise ValueError("target build/source context changed after isolated verification")
    validate_target_changes(root, dry["plannedChanges"])
    dirty = dirty_paths(root); relevant = set(generated) | {path for path in dirty if path.startswith("src/") or Path(path).name in {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "gradle.properties", "pom.xml", "gradlew", "mvnw"}}
    overlap = sorted(dirty & relevant)
    if overlap: raise ValueError("relevant Git changes overlap the approved apply: " + ", ".join(overlap))
    warnings = sorted(dirty - relevant)
    transaction_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(4)
    transaction = root / MANAGED / "implementation-transactions" / transaction_id
    backup = root / MANAGED / "implementation-backups" / transaction_id
    for managed_path in (root / MANAGED, transaction.parent, backup.parent):
        if managed_path.exists() and (managed_path.is_symlink() or not managed_path.is_dir()): raise ValueError(f"managed apply path is unsafe: {managed_path}")
    transaction.mkdir(parents=True); backup.mkdir(parents=True)
    for source, name in ((dry_path, "code-dry-run.json"), (verification_path, "verification-report.json"), (approval_path, "apply-approval.json")): shutil.copy2(source, backup / name)
    baseline_existed = baseline_path.exists()
    if baseline_existed: shutil.copy2(baseline_path, backup / BASELINE)
    creates = [item["path"] for item in dry["plannedChanges"]["creates"]]; updates = [item["path"] for item in dry["plannedChanges"]["updates"]]
    before_manifest = {}
    for item in dry["plannedChanges"]["updates"]:
        before_manifest[item["path"]] = {"sha256": item["beforeSha256"], "mode": item["beforeMode"]}
        destination = backup / "files" / item["path"]; destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(root / item["path"], destination)
    record = {"springCodeTransactionVersion": 1, "transactionId": transaction_id, "state": "PREPARED", "target": str(root), "creates": creates, "updates": updates, "desiredManifest": manifest, "beforeManifest": before_manifest, "backup": str(backup), "baselineExisted": baseline_existed, "baselineBeforeSha256": sha(baseline_path) if baseline_existed else None, "baselineAfterSha256": None}
    atomic_json(record, transaction / "transaction.json")
    written = []
    try:
        record["state"] = "APPLYING"; atomic_json(record, transaction / "transaction.json")
        for relative in sorted(creates + updates):
            validate_target_changes(root, {**dry["plannedChanges"], "desiredManifest": {"manifestVersion": 1, "files": {relative: manifest["files"][relative]}, "modes": {relative: manifest["modes"][relative]}}, "creates": [item for item in dry["plannedChanges"]["creates"] if item["path"] == relative], "updates": [item for item in dry["plannedChanges"]["updates"] if item["path"] == relative], "unchanged": [], "conflicts": [], "state": "COMPUTED"})
            destination = root / relative; destination.parent.mkdir(parents=True, exist_ok=True)
            staged = transaction / "commit" / relative; replace_file(generated[relative], manifest["modes"][relative], staged, destination); written.append(relative)
        baseline = merged_baseline(existing_baseline, manifest, sha(dry_path), sha(verification_path))
        baseline_bytes = (json.dumps(baseline, ensure_ascii=False, indent=2) + "\n").encode()
        record["baselineAfterSha256"] = __import__("hashlib").sha256(baseline_bytes).hexdigest(); atomic_json(record, transaction / "transaction.json")
        atomic_json(baseline, baseline_path)
        record["state"] = "COMMITTED"; record["appliedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(); atomic_json(record, transaction / "transaction.json")
    except Exception as error:
        try: recover_transaction(root, transaction_id)
        except ValueError as recovery_error: raise RuntimeError(f"apply failed and recovery was incomplete: {recovery_error}") from error
        raise ValueError(f"apply failed and was rolled back: {error}") from error
    return {"transactionId": transaction_id, "state": "COMMITTED", "applicationState": "APPLIED_PREVERIFIED", "createsApplied": sorted(creates), "updatesApplied": sorted(updates), "unrelatedDirtyWarnings": warnings, "baseline": str(baseline_path), "backup": str(backup), "postApplyVerification": "NOT_RUN", "gitCommitOrPush": "NOT_RUN"}


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("dry-run", "verification-report", "approval", "target"): parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    try: result = apply(args)
    except (OSError, ValueError, RuntimeError, KeyError) as error: print(f"SPRING_CODE_APPLY_VALID: no\nERROR: {error}", file=sys.stderr); return 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2); print(); print("SPRING_CODE_APPLY_VALID: yes", file=sys.stderr); print("APPLY_STATE: COMMITTED", file=sys.stderr); print("POST_APPLY_VERIFICATION: NOT_RUN", file=sys.stderr); print("GIT_COMMIT_OR_PUSH: NOT_RUN", file=sys.stderr); return 0


if __name__ == "__main__": sys.exit(main())
