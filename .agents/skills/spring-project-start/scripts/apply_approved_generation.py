#!/usr/bin/env python3
"""Apply an approved dry run with preflight checks, backup, and rollback."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from render_generation_dry_run import (
    digest,
    download_initializr,
    files_under,
    load_object,
    safe_extract,
)
from validate_generation_plan import validate as validate_plan


MANAGED_DIR = ".starter-harness"
BASELINE_NAME = ".starter-harness-generation.json"


def non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value != "UNKNOWN"


def safe_relative(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("change path must be a string")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"unsafe change path: {value!r}")
    if path.parts[0] in {MANAGED_DIR, BASELINE_NAME, ".git"}:
        raise ValueError(f"reserved change path: {value}")
    return value


def validate_sha(value: Any, location: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{location} must be a lowercase SHA-256")
    return value


def validate_report(report: dict[str, Any], target: Path) -> dict[str, Any]:
    if report.get("dryRunVersion") != 1:
        raise ValueError("dryRunVersion must be 1")
    if Path(str(report.get("target", ""))).resolve() != target.resolve():
        raise ValueError("dry-run target does not match apply target")
    if report.get("targetSourceChanged") is not False:
        raise ValueError("dry-run report must confirm targetSourceChanged=false")
    if report.get("readyForApproval") is not True or report.get("executionReady") is not False:
        raise ValueError("dry-run report is not ready for approval")
    changes = report.get("plannedChanges")
    if not isinstance(changes, dict) or changes.get("state") != "COMPUTED":
        raise ValueError("dry-run changes must be COMPUTED")
    if changes.get("conflicts") != []:
        raise ValueError("dry-run report contains conflicts")
    manifest = changes.get("desiredManifest")
    if not isinstance(manifest, dict) or manifest.get("manifestVersion") != 1:
        raise ValueError("desired manifestVersion must be 1")
    files = manifest.get("files")
    modes = manifest.get("modes")
    if not isinstance(files, dict) or not isinstance(modes, dict) or set(files) != set(modes):
        raise ValueError("desired manifest files and modes must have identical paths")
    for path, file_hash in files.items():
        safe_relative(path)
        validate_sha(file_hash, f"desired manifest hash for {path}")
        mode = modes[path]
        if not isinstance(mode, int) or isinstance(mode, bool) or not 0 <= mode <= 0o777:
            raise ValueError(f"desired mode is invalid for {path}")

    categorized: set[str] = set()
    for field in ("creates", "updates"):
        entries = changes.get(field)
        if not isinstance(entries, list):
            raise ValueError(f"plannedChanges.{field} must be an array")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"plannedChanges.{field} entries must be objects")
            path = safe_relative(entry.get("path"))
            if path in categorized:
                raise ValueError(f"change path is categorized more than once: {path}")
            categorized.add(path)
            expected_after = entry.get("sha256") if field == "creates" else entry.get("afterSha256")
            if validate_sha(expected_after, f"{field} desired hash for {path}") != files.get(path):
                raise ValueError(f"{field} desired hash disagrees with manifest: {path}")
            if field == "updates":
                validate_sha(entry.get("beforeSha256"), f"update baseline hash for {path}")
                for mode_field in ("beforeMode", "afterMode"):
                    mode = entry.get(mode_field)
                    if not isinstance(mode, int) or isinstance(mode, bool) or not 0 <= mode <= 0o777:
                        raise ValueError(f"update {mode_field} is invalid for {path}")
                if entry["afterMode"] != modes[path]:
                    raise ValueError(f"update desired mode disagrees with manifest: {path}")
    unchanged = changes.get("unchanged")
    if not isinstance(unchanged, list):
        raise ValueError("plannedChanges.unchanged must be an array")
    for raw_path in unchanged:
        path = safe_relative(raw_path)
        if path in categorized:
            raise ValueError(f"change path is categorized more than once: {path}")
        categorized.add(path)
    if categorized != set(files):
        raise ValueError("change categories must exactly cover the desired manifest")
    return changes


def validate_approval(approval: dict[str, Any], report_hash: str, target: Path) -> None:
    if approval.get("approvalVersion") != 1 or approval.get("approved") is not True:
        raise ValueError("explicit approvalVersion=1 and approved=true are required")
    if approval.get("dryRunReportSha256") != report_hash:
        raise ValueError("approval does not match the exact dry-run report SHA-256")
    if Path(str(approval.get("target", ""))).resolve() != target.resolve():
        raise ValueError("approval target does not match apply target")
    if not non_empty(approval.get("approvedBy")) or not non_empty(approval.get("approvedAt")):
        raise ValueError("approval requires approvedBy and approvedAt")


def atomic_json(document: dict[str, Any], destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def stage_rendered(args: argparse.Namespace, plan: dict[str, Any], rendered: Path) -> None:
    if args.rendered_source:
        if not args.rendered_source.is_dir():
            raise ValueError("rendered source must be a directory")
        for relative, source in files_under(args.rendered_source).items():
            destination = rendered / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return
    archive = args.rendered_archive
    if archive is None:
        archive = rendered.parent / "starter.zip"
        download_initializr(plan, archive)
    safe_extract(archive, rendered)


def apply(args: argparse.Namespace) -> dict[str, Any]:
    target = args.target
    if target.is_symlink() or not target.is_dir():
        raise ValueError("target must be an existing non-symlink directory")
    harness_root = Path(__file__).resolve().parents[4]
    if target.resolve() == harness_root:
        raise ValueError("the Harness repository cannot be used as the target")
    managed_root = target / MANAGED_DIR
    baseline_path = target / BASELINE_NAME
    if managed_root.is_symlink() or baseline_path.is_symlink():
        raise ValueError("managed metadata paths must not be symbolic links")
    if baseline_path.exists() and not baseline_path.is_file():
        raise ValueError("baseline path is not a regular file")

    report = load_object(args.report)
    report_hash = digest(args.report)
    changes = validate_report(report, target)
    approval = load_object(args.approval)
    validate_approval(approval, report_hash, target)
    plan = load_object(args.plan)
    validate_plan(plan)
    if str(args.plan) != report.get("sourcePlan"):
        raise ValueError("apply plan path does not match the dry-run report")

    render_context = tempfile.TemporaryDirectory(prefix="spring-generation-apply-preflight-")
    rendered = Path(render_context.name) / "rendered"
    rendered.mkdir()
    stage_rendered(args, plan, rendered)
    desired_files = files_under(rendered)
    desired_hashes = {path: digest(file) for path, file in desired_files.items()}
    desired_modes = {path: file.stat().st_mode & 0o777 for path, file in desired_files.items()}
    manifest = changes["desiredManifest"]
    if desired_hashes != manifest["files"] or desired_modes != manifest["modes"]:
        raise ValueError("re-rendered files do not match the approved desired manifest")

    creates = {entry["path"]: entry for entry in changes["creates"]}
    updates = {entry["path"]: entry for entry in changes["updates"]}
    for relative in desired_files:
        destination = target / relative
        parent = destination.parent
        while parent != target:
            if parent.is_symlink():
                raise ValueError(f"target parent became a symbolic link: {relative}")
            parent = parent.parent
        if relative in creates:
            if destination.exists() or destination.is_symlink():
                raise ValueError(f"CREATE target changed after dry run: {relative}")
        else:
            if destination.is_symlink() or not destination.is_file():
                raise ValueError(f"existing target changed type after dry run: {relative}")
            expected = updates.get(relative, {}).get("beforeSha256", desired_hashes[relative])
            if digest(destination) != expected:
                raise ValueError(f"target content changed after dry run: {relative}")
            expected_mode = updates.get(relative, {}).get("beforeMode", desired_modes[relative])
            if destination.stat().st_mode & 0o777 != expected_mode:
                raise ValueError(f"target permissions changed after dry run: {relative}")

    transaction_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(4)
    managed_root.mkdir(mode=0o700, exist_ok=True)
    if not managed_root.is_dir():
        raise ValueError("managed metadata path is not a directory")
    transaction = managed_root / "transactions" / transaction_id
    backup = managed_root / "backups" / transaction_id
    transaction.mkdir(parents=True)
    backup.mkdir(parents=True)

    shutil.copy2(args.report, backup / "dry-run-report.json")
    shutil.copy2(args.approval, backup / "approval.json")
    if baseline_path.exists():
        shutil.copy2(baseline_path, backup / BASELINE_NAME)
    for relative in updates:
        source = target / relative
        destination = backup / "files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    record = {
        "transactionVersion": 1,
        "transactionId": transaction_id,
        "state": "PREPARED",
        "target": str(target.resolve()),
        "dryRunReportSha256": report_hash,
        "creates": sorted(creates),
        "updates": sorted(updates),
        "backup": str(backup),
    }
    atomic_json(record, transaction / "transaction.json")
    written: list[str] = []
    created_directories: list[Path] = []
    baseline_existed = baseline_path.exists()
    try:
        for relative in sorted(set(creates) | set(updates)):
            destination = target / relative
            parent_check = destination.parent
            while parent_check != target:
                if parent_check.is_symlink():
                    raise ValueError(f"target parent changed to a symbolic link: {relative}")
                parent_check = parent_check.parent
            if relative in creates:
                if destination.exists() or destination.is_symlink():
                    raise ValueError(f"CREATE target changed immediately before apply: {relative}")
            else:
                entry = updates[relative]
                if destination.is_symlink() or not destination.is_file():
                    raise ValueError(f"UPDATE target changed type immediately before apply: {relative}")
                if digest(destination) != entry["beforeSha256"] or destination.stat().st_mode & 0o777 != entry["beforeMode"]:
                    raise ValueError(f"UPDATE target changed immediately before apply: {relative}")
            missing_parents: list[Path] = []
            parent = destination.parent
            while parent != target and not parent.exists():
                missing_parents.append(parent)
                parent = parent.parent
            for directory in reversed(missing_parents):
                directory.mkdir()
                created_directories.append(directory)
            staged = transaction / "commit" / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rendered / relative, staged)
            os.replace(staged, destination)
            destination.chmod(manifest["modes"][relative])
            written.append(relative)
        applied_at = dt.datetime.now(dt.timezone.utc).isoformat()
        baseline = {
            "manifestVersion": 1,
            "files": manifest["files"],
            "modes": manifest["modes"],
            "appliedFromDryRunSha256": report_hash,
            "appliedAt": applied_at,
        }
        atomic_json(baseline, baseline_path)
        record.update({"state": "COMMITTED", "appliedAt": applied_at})
        atomic_json(record, transaction / "transaction.json")
    except Exception as error:
        rollback_errors: list[str] = []
        for relative in reversed(written):
            try:
                destination = target / relative
                if (
                    destination.is_symlink()
                    or not destination.is_file()
                    or digest(destination) != desired_hashes[relative]
                    or destination.stat().st_mode & 0o777 != desired_modes[relative]
                ):
                    raise OSError("applied file changed externally; refusing to overwrite during rollback")
                if relative in updates:
                    shutil.copy2(backup / "files" / relative, destination)
                else:
                    destination.unlink()
            except OSError as rollback_error:
                rollback_errors.append(f"{relative}: {rollback_error}")
        for directory in reversed(created_directories):
            try:
                directory.rmdir()
            except OSError as rollback_error:
                rollback_errors.append(f"{directory.relative_to(target)}: {rollback_error}")
        try:
            if baseline_existed:
                shutil.copy2(backup / BASELINE_NAME, baseline_path)
            elif baseline_path.exists() and baseline_path.is_file():
                baseline_path.unlink()
        except OSError as rollback_error:
            rollback_errors.append(f"baseline: {rollback_error}")
        record.update({"state": "ROLLBACK_FAILED" if rollback_errors else "ROLLED_BACK", "error": str(error)})
        if rollback_errors:
            record["rollbackErrors"] = rollback_errors
        atomic_json(record, transaction / "transaction.json")
        if rollback_errors:
            render_context.cleanup()
            raise RuntimeError(f"apply failed and rollback was incomplete: {rollback_errors}") from error
        render_context.cleanup()
        raise ValueError(f"apply failed and was rolled back: {error}") from error

    result = {
        "transactionId": transaction_id,
        "state": "COMMITTED",
        "createsApplied": sorted(creates),
        "updatesApplied": sorted(updates),
        "unchanged": changes["unchanged"],
        "backup": str(backup),
        "baseline": str(baseline_path),
    }
    render_context.cleanup()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--rendered-source", type=Path)
    source.add_argument("--rendered-archive", type=Path)
    args = parser.parse_args()
    try:
        result = apply(args)
    except (ValueError, RuntimeError, OSError) as error:
        print(f"APPLY_VALID: no\nERROR: {error}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    print("APPLY_VALID: yes", file=sys.stderr)
    print("APPLY_STATE: COMMITTED", file=sys.stderr)
    print("BASELINE_WRITTEN: yes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
