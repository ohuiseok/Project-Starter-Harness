#!/usr/bin/env python3
"""Atomically apply exact approved relational artifacts without executing them."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from apply_approved_generation import atomic_json, non_empty, validate_sha
from relational_physical_contract import validate_physical_contract
from render_generation_dry_run import digest
from render_relational_artifact_dry_run import artifact_plan, compose, sql, testcontainers_java
from validate_feature_specs import load_object


MANAGED_DIR = ".starter-harness"
BASELINE_NAME = ".starter-harness-relational.json"


def safe_relative(value: Any) -> str:
    if not isinstance(value, str): raise ValueError("artifact path must be a string")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or path.as_posix() != value: raise ValueError(f"unsafe artifact path: {value!r}")
    if path.parts[0] in {MANAGED_DIR, BASELINE_NAME, ".git"}: raise ValueError(f"reserved artifact path: {value}")
    return value


def validate_report(report: dict, target: Path, require_approval: bool = True) -> dict:
    required = {"relationalArtifactDryRunVersion", "physicalContract", "physicalModelSha256", "artifactPlan", "baseline", "target", "generatedArtifacts", "plannedChanges", "recoveryAssessment", "targetSourceChanged", "databaseOrContainerChanged", "readyForApproval", "executionReady"}
    if not isinstance(report, dict) or set(report) != required or report["relationalArtifactDryRunVersion"] != 1: raise ValueError("relational dry-run report is invalid")
    if Path(str(report["target"])).resolve() != target.resolve(): raise ValueError("dry-run target does not match apply target")
    if report["targetSourceChanged"] is not False or report["databaseOrContainerChanged"] is not False: raise ValueError("dry run must prove no source, database, or container changes")
    baseline_ref = report["baseline"]
    if baseline_ref is not None:
        if not isinstance(baseline_ref, dict) or set(baseline_ref) != {"path", "sha256"} or baseline_ref["path"] != BASELINE_NAME: raise ValueError("dry-run baseline reference is invalid")
        validate_sha(baseline_ref["sha256"], "dry-run baseline hash")
    if report["executionReady"] is not False: raise ValueError("dry-run report must not be execution-ready")
    changes = report["plannedChanges"]
    if not isinstance(changes, dict) or changes.get("state") not in {"COMPUTED", "CONFLICT"} or not isinstance(changes.get("conflicts"), list): raise ValueError("dry-run change state is invalid")
    if require_approval and (changes["state"] != "COMPUTED" or changes["conflicts"] != [] or report["readyForApproval"] is not True): raise ValueError("dry-run changes must be conflict-free and approval-ready")
    if not require_approval and report["readyForApproval"] is not (changes["state"] == "COMPUTED"): raise ValueError("dry-run readiness does not match its change state")
    manifest = changes.get("desiredManifest")
    if not isinstance(manifest, dict) or manifest.get("manifestVersion") != 1 or not isinstance(manifest.get("files"), dict) or not isinstance(manifest.get("modes"), dict) or set(manifest["files"]) != set(manifest["modes"]): raise ValueError("dry-run desired manifest is invalid")
    previews = report["generatedArtifacts"]
    if not isinstance(previews, list) or not previews: raise ValueError("generated artifact previews are required")
    preview_paths = set()
    for index, item in enumerate(previews):
        if not isinstance(item, dict) or set(item) != {"kind", "path", "sha256", "content"}: raise ValueError(f"generatedArtifacts[{index}] is invalid")
        if item["kind"] not in {"FLYWAY_SQL", "DOCKER_COMPOSE", "TESTCONTAINERS_JAVA"}: raise ValueError(f"generated artifact kind is unsupported: {item['kind']}")
        path = safe_relative(item["path"])
        if path in preview_paths: raise ValueError(f"duplicate generated artifact path: {path}")
        preview_paths.add(path); validate_sha(item["sha256"], f"generated artifact hash for {path}")
        if not isinstance(item["content"], str) or digest_bytes(item["content"].encode()) != item["sha256"]: raise ValueError(f"generated artifact preview hash is stale: {path}")
        if manifest["files"].get(path) != item["sha256"]: raise ValueError(f"generated artifact preview disagrees with manifest: {path}")
    if preview_paths != set(manifest["files"]): raise ValueError("generated previews must exactly cover the desired manifest")
    for path, value in manifest["files"].items():
        safe_relative(path); validate_sha(value, f"manifest hash for {path}")
        mode = manifest["modes"][path]
        if not isinstance(mode, int) or isinstance(mode, bool) or not 0 <= mode <= 0o777: raise ValueError(f"manifest mode is invalid: {path}")
    categorized = set()
    for field in ("creates", "updates"):
        if not isinstance(changes.get(field), list): raise ValueError(f"plannedChanges.{field} must be an array")
        for item in changes[field]:
            path = safe_relative(item.get("path"))
            if path in categorized: raise ValueError(f"artifact categorized more than once: {path}")
            categorized.add(path)
            after = item.get("sha256") if field == "creates" else item.get("afterSha256")
            if after != manifest["files"].get(path): raise ValueError(f"{field} hash disagrees with manifest: {path}")
            if field == "updates":
                validate_sha(item.get("beforeSha256"), f"update before hash for {path}")
                if item.get("afterMode") != manifest["modes"][path]: raise ValueError(f"update mode disagrees with manifest: {path}")
                for key in ("beforeMode", "afterMode"):
                    if not isinstance(item.get(key), int) or isinstance(item.get(key), bool): raise ValueError(f"update mode is invalid: {path}")
    if not isinstance(changes.get("unchanged"), list): raise ValueError("plannedChanges.unchanged must be an array")
    for raw in changes["unchanged"]:
        path = safe_relative(raw)
        if path in categorized: raise ValueError(f"artifact categorized more than once: {path}")
        categorized.add(path)
    if changes["state"] == "COMPUTED" and categorized != set(manifest["files"]): raise ValueError("change categories must exactly cover the desired manifest")
    recovery = report["recoveryAssessment"]
    if not isinstance(recovery, dict) or recovery.get("renderedDdlClass") != "TRANSACTIONAL_CREATE_ONLY" or recovery.get("isolatedDatabaseVerified") is not False: raise ValueError("recovery assessment is unsupported or overclaims execution evidence")
    return changes


def digest_bytes(value: bytes) -> str:
    import hashlib
    return hashlib.sha256(value).hexdigest()


def validate_approval(approval: dict, report_hash: str, target: Path) -> None:
    required = {"relationalArtifactApprovalVersion", "approved", "dryRunReportSha256", "target", "approvedBy", "approvedAt"}
    if not isinstance(approval, dict) or set(approval) != required or approval["relationalArtifactApprovalVersion"] != 1 or approval["approved"] is not True: raise ValueError("explicit relational artifact approval is required")
    if approval["dryRunReportSha256"] != report_hash: raise ValueError("approval does not match the exact dry-run report SHA-256")
    if Path(str(approval["target"])).resolve() != target.resolve(): raise ValueError("approval target does not match apply target")
    if not non_empty(approval["approvedBy"]) or not non_empty(approval["approvedAt"]): raise ValueError("approval identity and time are required")
    try: timestamp = dt.datetime.fromisoformat(approval["approvedAt"].replace("Z", "+00:00"))
    except ValueError as error: raise ValueError("approval time must be ISO-8601") from error
    if timestamp.utcoffset() is None: raise ValueError("approval time must include a timezone")


def render_current(args: argparse.Namespace, root: Path) -> tuple[dict[str, bytes], dict]:
    metadata, physical = load_object(args.physical_contract), load_object(args.physical_model)
    route, feature, profile = load_object(args.route), load_object(args.feature), load_object(args.profile)
    approved, blockers, physical, _ = validate_physical_contract(metadata, args.physical_model, args.logical_contract, route, args.route, root, feature, profile)
    if not approved or blockers: raise ValueError("physical contract is no longer approved and current: " + "; ".join(blockers))
    plan = load_object(args.artifact_plan); artifact_plan(plan, physical, args.physical_contract, args.physical_model, args.profile, profile, root)
    artifacts = {physical["migrationPlan"]["plannedSourcePath"]: sql(physical, plan).encode()}
    if physical["provisioningPlan"]["compose"]: artifacts[physical["provisioningPlan"]["compose"]["plannedPath"]] = compose(physical, plan).encode()
    if plan["testcontainers"]: artifacts[plan["testcontainers"]["plannedPath"]] = testcontainers_java(physical, plan).encode()
    return artifacts, physical


def validate_existing_baseline(path: Path) -> None:
    baseline = load_object(path)
    if baseline.get("manifestVersion") != 1 or baseline.get("artifactKind") != "RELATIONAL": raise ValueError("existing relational baseline has an unsupported identity")
    files, modes = baseline.get("files"), baseline.get("modes")
    if not isinstance(files, dict) or not isinstance(modes, dict) or set(files) != set(modes): raise ValueError("existing relational baseline manifest is invalid")
    for name, value in files.items():
        safe_relative(name); validate_sha(value, f"existing baseline hash for {name}")
        if not isinstance(modes[name], int) or isinstance(modes[name], bool) or not 0 <= modes[name] <= 0o777: raise ValueError(f"existing baseline mode is invalid: {name}")


def prepared_transactions(managed_root: Path) -> list[str]:
    result = []
    transactions = managed_root / "transactions"
    if not transactions.exists(): return result
    if transactions.is_symlink() or not transactions.is_dir(): raise ValueError("transaction metadata path is unsafe")
    for path in sorted(transactions.glob("*/transaction.json")):
        if path.is_symlink(): raise ValueError("transaction record must not be a symbolic link")
        if load_object(path).get("state") == "PREPARED": result.append(path.parent.name)
    return result


def recover_transaction(target: Path, transaction_id: str) -> dict:
    if not transaction_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for character in transaction_id): raise ValueError("transaction ID is invalid")
    root = target.resolve(strict=True); managed = root / MANAGED_DIR; transaction = managed / "transactions" / transaction_id; record_path = transaction / "transaction.json"
    if target.is_symlink() or managed.is_symlink() or transaction.is_symlink() or record_path.is_symlink(): raise ValueError("recovery paths must not be symbolic links")
    record = load_object(record_path)
    required = {"relationalArtifactTransactionVersion", "transactionId", "state", "target", "dryRunReportSha256", "creates", "updates", "backup", "databaseOrContainerChanged", "desiredManifest", "beforeManifest", "baselineExisted", "baselineBeforeSha256"}
    if set(record) != required or record["relationalArtifactTransactionVersion"] != 1 or record["transactionId"] != transaction_id or record["state"] != "PREPARED" or Path(record["target"]).resolve() != root: raise ValueError("transaction is not a recoverable PREPARED relational apply")
    backup = managed / "backups" / transaction_id
    if Path(record["backup"]).resolve() != backup.resolve() or backup.is_symlink() or not backup.is_dir(): raise ValueError("transaction backup identity is invalid")
    manifest = record["desiredManifest"]; files, modes = manifest.get("files"), manifest.get("modes")
    if manifest.get("manifestVersion") != 1 or not isinstance(files, dict) or not isinstance(modes, dict) or set(files) != set(modes): raise ValueError("transaction desired manifest is invalid")
    creates, updates = record["creates"], record["updates"]
    if not isinstance(creates, list) or not isinstance(updates, list) or set(creates) | set(updates) != set(files) or set(creates) & set(updates): raise ValueError("transaction change sets are invalid")
    before_manifest = record["beforeManifest"]
    if not isinstance(before_manifest, dict) or set(before_manifest) != set(updates): raise ValueError("transaction before manifest is invalid")
    for relative in updates:
        safe_relative(relative); saved = backup / "files" / relative; destination = root / relative
        if saved.is_symlink() or not saved.is_file(): raise ValueError(f"UPDATE backup is missing: {relative}")
        if destination.is_symlink() or not destination.is_file(): raise ValueError(f"UPDATE target cannot be safely recovered: {relative}")
        expected_before = before_manifest[relative]
        if not isinstance(expected_before, dict) or set(expected_before) != {"sha256", "mode"}: raise ValueError(f"transaction before evidence is invalid: {relative}")
        if digest(saved) != expected_before["sha256"] or saved.stat().st_mode & 0o777 != expected_before["mode"]: raise ValueError(f"UPDATE backup evidence changed: {relative}")
        current, current_mode = digest(destination), destination.stat().st_mode & 0o777
        if current == files[relative] and current_mode == modes[relative]: shutil.copy2(saved, destination)
        elif current != expected_before["sha256"] or current_mode != expected_before["mode"]: raise ValueError(f"UPDATE target diverged during interrupted apply: {relative}")
    for relative in creates:
        safe_relative(relative); destination = root / relative
        if destination.is_symlink(): raise ValueError(f"CREATE target cannot be safely recovered: {relative}")
        if destination.exists():
            if not destination.is_file() or digest(destination) != files[relative] or destination.stat().st_mode & 0o777 != modes[relative]: raise ValueError(f"CREATE target diverged during interrupted apply: {relative}")
            destination.unlink()
    baseline_path = root / BASELINE_NAME
    if record["baselineExisted"] is True:
        saved = backup / BASELINE_NAME
        if saved.is_symlink() or not saved.is_file(): raise ValueError("prior relational baseline backup is missing")
        if digest(saved) != record["baselineBeforeSha256"]: raise ValueError("prior relational baseline backup evidence changed")
        if not baseline_path.exists() or baseline_path.is_symlink() or not baseline_path.is_file(): raise ValueError("relational baseline cannot be safely recovered")
        if digest(baseline_path) != record["baselineBeforeSha256"]:
            if load_object(baseline_path).get("appliedFromDryRunSha256") != record["dryRunReportSha256"]: raise ValueError("relational baseline diverged during interrupted apply")
            shutil.copy2(saved, baseline_path)
    elif record["baselineExisted"] is False:
        if baseline_path.exists():
            current = load_object(baseline_path)
            if current.get("appliedFromDryRunSha256") != record["dryRunReportSha256"]: raise ValueError("relational baseline diverged during interrupted apply")
            baseline_path.unlink()
    else: raise ValueError("transaction baselineExisted flag is invalid")
    for relative in sorted(creates, key=lambda item: len(PurePosixPath(item).parts), reverse=True):
        parent = (root / relative).parent
        while parent != root:
            try: parent.rmdir()
            except OSError: break
            parent = parent.parent
    record.update({"state": "RECOVERED", "recoveredAt": dt.datetime.now(dt.timezone.utc).isoformat()}); atomic_json(record, record_path)
    return {"transactionId": transaction_id, "state": "RECOVERED", "databaseOrContainerChanged": False}


def apply(args: argparse.Namespace) -> dict:
    target = args.target
    if target.is_symlink() or not target.is_dir(): raise ValueError("target must be an existing non-symlink directory")
    root = target.resolve(); harness_root = Path(__file__).resolve().parents[4]
    if root == harness_root: raise ValueError("the Harness repository cannot be used as the target")
    for path, label in ((args.report, "report"), (args.approval, "approval"), (args.physical_contract, "physical contract"), (args.physical_model, "physical model"), (args.logical_contract, "logical contract"), (args.route, "route"), (args.feature, "feature"), (args.profile, "profile"), (args.artifact_plan, "artifact plan")):
        if path.is_symlink(): raise ValueError(f"{label} must not be a symbolic link")
        resolved = path.resolve(strict=True)
        if root not in (resolved, *resolved.parents): raise ValueError(f"{label} escapes target")
    managed_root, baseline_path = root / MANAGED_DIR, root / BASELINE_NAME
    if managed_root.is_symlink() or baseline_path.is_symlink(): raise ValueError("managed paths must not be symbolic links")
    pending = prepared_transactions(managed_root)
    if pending: raise ValueError("unfinished PREPARED relational transaction requires recovery: " + ", ".join(pending))
    report = load_object(args.report); report_hash = digest(args.report); changes = validate_report(report, root)
    validate_approval(load_object(args.approval), report_hash, root)
    contract_ref = report["physicalContract"]
    if not isinstance(contract_ref, dict) or set(contract_ref) != {"path", "sha256"} or Path(str(contract_ref["path"])).resolve() != args.physical_contract.resolve() or contract_ref["sha256"] != digest(args.physical_contract): raise ValueError("report physical contract reference is stale or mismatched")
    if report["physicalModelSha256"] != digest(args.physical_model): raise ValueError("physical model changed after dry run")
    plan_ref = report["artifactPlan"]
    if not isinstance(plan_ref, dict) or set(plan_ref) != {"path", "sha256"} or Path(str(plan_ref["path"])).resolve() != args.artifact_plan.resolve() or plan_ref["sha256"] != digest(args.artifact_plan): raise ValueError("report artifact plan reference is stale or mismatched")
    baseline_ref = report["baseline"]
    if baseline_ref is None:
        if baseline_path.exists(): raise ValueError("relational baseline appeared after dry run")
    else:
        if not isinstance(baseline_ref, dict) or set(baseline_ref) != {"path", "sha256"} or baseline_ref["path"] != BASELINE_NAME: raise ValueError("dry-run baseline reference is invalid")
        if not baseline_path.is_file() or digest(baseline_path) != baseline_ref["sha256"]: raise ValueError("relational baseline changed after dry run")
        validate_existing_baseline(baseline_path)
    artifacts, physical = render_current(args, root); manifest = changes["desiredManifest"]
    if report["recoveryAssessment"].get("required") != physical["migrationPlan"]["requiredRecovery"]: raise ValueError("recovery requirement changed after dry run")
    if {path: digest_bytes(content) for path, content in artifacts.items()} != manifest["files"]: raise ValueError("re-rendered artifacts do not match the approved manifest")
    creates = {item["path"]: item for item in changes["creates"]}; updates = {item["path"]: item for item in changes["updates"]}
    for relative in artifacts:
        destination = root / relative; parent = destination.parent
        while parent != root:
            if parent.is_symlink(): raise ValueError(f"target parent became a symbolic link: {relative}")
            parent = parent.parent
        if relative in creates:
            if destination.exists() or destination.is_symlink(): raise ValueError(f"CREATE target changed after dry run: {relative}")
        else:
            if destination.is_symlink() or not destination.is_file(): raise ValueError(f"existing target changed type after dry run: {relative}")
            expected_hash = updates.get(relative, {}).get("beforeSha256", manifest["files"][relative]); expected_mode = updates.get(relative, {}).get("beforeMode", manifest["modes"][relative])
            if digest(destination) != expected_hash or destination.stat().st_mode & 0o777 != expected_mode: raise ValueError(f"target changed after dry run: {relative}")
    transaction_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(4)
    managed_root.mkdir(mode=0o700, exist_ok=True)
    if not managed_root.is_dir(): raise ValueError("managed metadata path is not a directory")
    transaction, backup = managed_root / "transactions" / transaction_id, managed_root / "backups" / transaction_id
    transaction.mkdir(parents=True); backup.mkdir(parents=True)
    shutil.copy2(args.report, backup / "relational-dry-run-report.json"); shutil.copy2(args.approval, backup / "relational-approval.json"); shutil.copy2(args.artifact_plan, backup / "relational-artifact-plan.json")
    baseline_existed = baseline_path.exists()
    if baseline_existed:
        shutil.copy2(baseline_path, backup / BASELINE_NAME)
    for relative in updates:
        destination = backup / "files" / relative; destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(root / relative, destination)
    before_manifest = {path: {"sha256": item["beforeSha256"], "mode": item["beforeMode"]} for path, item in updates.items()}
    record = {"relationalArtifactTransactionVersion": 1, "transactionId": transaction_id, "state": "PREPARED", "target": str(root), "dryRunReportSha256": report_hash, "creates": sorted(creates), "updates": sorted(updates), "backup": str(backup), "databaseOrContainerChanged": False, "desiredManifest": manifest, "beforeManifest": before_manifest, "baselineExisted": baseline_existed, "baselineBeforeSha256": digest(baseline_path) if baseline_existed else None}
    atomic_json(record, transaction / "transaction.json")
    written: list[str] = []; created_directories: list[Path] = []
    try:
        for relative in sorted(set(creates) | set(updates)):
            destination = root / relative
            parent_check = destination.parent
            while parent_check != root:
                if parent_check.is_symlink(): raise ValueError(f"target parent changed immediately before apply: {relative}")
                parent_check = parent_check.parent
            if relative in creates:
                if destination.exists() or destination.is_symlink(): raise ValueError(f"CREATE target changed immediately before apply: {relative}")
            else:
                item = updates[relative]
                if destination.is_symlink() or not destination.is_file() or digest(destination) != item["beforeSha256"] or destination.stat().st_mode & 0o777 != item["beforeMode"]: raise ValueError(f"UPDATE target changed immediately before apply: {relative}")
            missing = []; parent = destination.parent
            while parent != root and not parent.exists(): missing.append(parent); parent = parent.parent
            for directory in reversed(missing): directory.mkdir(); created_directories.append(directory)
            staged = transaction / "commit" / relative; staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(artifacts[relative]); staged.chmod(manifest["modes"][relative]); os.replace(staged, destination); written.append(relative)
        applied_at = dt.datetime.now(dt.timezone.utc).isoformat()
        baseline = {"manifestVersion": 1, "artifactKind": "RELATIONAL", "files": manifest["files"], "modes": manifest["modes"], "appliedFromDryRunSha256": report_hash, "appliedAt": applied_at}
        atomic_json(baseline, baseline_path); record.update({"state": "COMMITTED", "appliedAt": applied_at}); atomic_json(record, transaction / "transaction.json")
    except Exception as error:
        rollback_errors = []
        for relative in reversed(written):
            try:
                destination = root / relative
                if destination.is_symlink() or not destination.is_file() or digest(destination) != manifest["files"][relative] or destination.stat().st_mode & 0o777 != manifest["modes"][relative]: raise OSError("applied file changed externally; rollback overwrite refused")
                if relative in updates: shutil.copy2(backup / "files" / relative, destination)
                else: destination.unlink()
            except OSError as rollback_error: rollback_errors.append(f"{relative}: {rollback_error}")
        for directory in reversed(created_directories):
            try: directory.rmdir()
            except OSError as rollback_error: rollback_errors.append(f"{directory.relative_to(root)}: {rollback_error}")
        try:
            if baseline_existed: shutil.copy2(backup / BASELINE_NAME, baseline_path)
            elif baseline_path.exists() and baseline_path.is_file(): baseline_path.unlink()
        except OSError as rollback_error: rollback_errors.append(f"baseline: {rollback_error}")
        record.update({"state": "ROLLBACK_FAILED" if rollback_errors else "ROLLED_BACK", "error": str(error)})
        if rollback_errors: record["rollbackErrors"] = rollback_errors
        atomic_json(record, transaction / "transaction.json")
        if rollback_errors: raise RuntimeError(f"relational artifact apply failed and rollback was incomplete: {rollback_errors}") from error
        raise ValueError(f"relational artifact apply failed and was rolled back: {error}") from error
    return {"transactionId": transaction_id, "state": "COMMITTED", "createsApplied": sorted(creates), "updatesApplied": sorted(updates), "unchanged": changes["unchanged"], "backup": str(backup), "baseline": str(baseline_path), "databaseOrContainerChanged": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("report", "approval", "physical-contract", "physical-model", "logical-contract", "route", "feature", "profile", "artifact-plan", "target"): parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    try: result = apply(args)
    except (OSError, ValueError, RuntimeError) as error: print(f"RELATIONAL_ARTIFACT_APPLY_VALID: no\nERROR: {error}", file=sys.stderr); return 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2); print(); print("RELATIONAL_ARTIFACT_APPLY_VALID: yes", file=sys.stderr); print("APPLY_STATE: COMMITTED", file=sys.stderr); print("BASELINE_WRITTEN: yes", file=sys.stderr); print("DATABASE_OR_CONTAINER_CHANGED: no", file=sys.stderr); return 0


if __name__ == "__main__": sys.exit(main())
