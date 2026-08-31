#!/usr/bin/env python3
"""Render an Initializr plan in temporary storage and compare it safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from validate_generation_plan import load_object, validate


MANIFEST_VERSION = 1
IGNORED_NAMES = {".git", ".starter-harness-generation.json"}
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def files_under(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in IGNORED_NAMES for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"symbolic links are not allowed in rendered output: {relative}")
        if path.is_file():
            result[relative.as_posix()] = path
    return result


def safe_extract(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            if sum(member.file_size for member in bundle.infolist()) > MAX_EXTRACTED_BYTES:
                raise ValueError("rendered archive exceeds the extraction size limit")
            for member in bundle.infolist():
                name = PurePosixPath(member.filename)
                if name.is_absolute() or ".." in name.parts:
                    raise ValueError(f"unsafe archive path: {member.filename}")
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"archive symbolic link is not allowed: {member.filename}")
            bundle.extractall(destination)
            for member in bundle.infolist():
                extracted = destination / member.filename
                mode = (member.external_attr >> 16) & 0o777
                if mode and extracted.is_file():
                    extracted.chmod(mode)
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError(f"cannot read rendered archive: {error}") from error


def initializr_request(plan: dict[str, Any]) -> dict[str, Any]:
    initializr = plan["initializr"]
    request = initializr.get("request")
    if request is None:
        raise ValueError("multi-project plans require compiled child plans before dry run")
    return request


def download_initializr(plan: dict[str, Any], output: Path) -> None:
    request = dict(initializr_request(plan))
    request["dependencies"] = ",".join(request["dependencies"])
    url = plan["initializr"]["service"].rstrip("/") + "/starter.zip?" + urllib.parse.urlencode(request)
    try:
        with urllib.request.urlopen(url, timeout=30) as response, output.open("wb") as handle:
            if response.status != 200:
                raise ValueError(f"Initializr returned HTTP {response.status}")
            remaining = MAX_ARCHIVE_BYTES + 1
            while remaining:
                chunk = response.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                handle.write(chunk)
                remaining -= len(chunk)
            if remaining == 0:
                raise ValueError("Initializr archive exceeds the download size limit")
    except (OSError, urllib.error.URLError) as error:
        raise ValueError(f"cannot render from Spring Initializr: {error}") from error


def load_baseline(path: Path | None) -> tuple[dict[str, str], dict[str, int]]:
    if path is None or not path.exists():
        return {}, {}
    document = load_object(path)
    if document.get("manifestVersion") != MANIFEST_VERSION:
        raise ValueError("baseline manifestVersion must be 1")
    files = document.get("files")
    if not isinstance(files, dict) or not all(
        isinstance(name, str)
        and isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
        for name, value in files.items()
    ):
        raise ValueError("baseline manifest files must map paths to SHA-256 strings")
    modes = document.get("modes", {})
    if not isinstance(modes, dict) or not all(
        name in files
        and isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= 0o777
        for name, value in modes.items()
    ):
        raise ValueError("baseline manifest modes must map managed paths to permission integers")
    return files, modes


def compare(
    rendered: Path,
    target: Path,
    baseline: dict[str, str],
    baseline_modes: dict[str, int],
) -> dict[str, Any]:
    creates: list[dict[str, str]] = []
    updates: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    unchanged: list[str] = []
    desired_files = files_under(rendered)
    desired_manifest = {relative: digest(path) for relative, path in desired_files.items()}
    desired_modes = {
        relative: path.stat().st_mode & 0o777 for relative, path in desired_files.items()
    }
    for relative, desired in desired_files.items():
        destination = target / relative
        desired_hash = desired_manifest[relative]
        relative_path = Path(relative)
        has_symlink_parent = any(
            (target / Path(*relative_path.parts[:index])).is_symlink()
            for index in range(1, len(relative_path.parts))
        )
        if has_symlink_parent or destination.is_symlink() or (destination.exists() and not destination.is_file()):
            conflicts.append({"path": relative, "reason": "target-path-is-not-a-regular-file"})
            continue
        if not destination.exists():
            creates.append({"path": relative, "sha256": desired_hash})
            continue
        current_hash = digest(destination)
        current_mode = destination.stat().st_mode & 0o777
        desired_mode = desired_modes[relative]
        if current_hash == desired_hash and current_mode == desired_mode:
            unchanged.append(relative)
        elif baseline.get(relative) == current_hash and baseline_modes.get(relative, current_mode) == current_mode:
            updates.append({
                "path": relative,
                "beforeSha256": current_hash,
                "afterSha256": desired_hash,
                "beforeMode": current_mode,
                "afterMode": desired_mode,
            })
        else:
            conflicts.append({"path": relative, "reason": "existing-content-has-no-matching-baseline"})
    return {
        "state": "CONFLICT" if conflicts else "COMPUTED",
        "creates": creates,
        "updates": updates,
        "conflicts": conflicts,
        "unchanged": unchanged,
        "desiredManifest": {
            "manifestVersion": MANIFEST_VERSION,
            "files": desired_manifest,
            "modes": desired_modes,
        },
    }


def write_report(report: dict[str, Any], output: Path, force: bool) -> None:
    if output.exists() and not force:
        raise ValueError(f"output already exists; use --force to replace it: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--rendered-source", type=Path)
    source.add_argument("--rendered-archive", type=Path)
    parser.add_argument("--baseline-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        plan = load_object(args.plan)
        validate(plan)
        if plan["planStatus"] != "READY_FOR_DRY_RUN":
            raise ValueError("plan reviews must be resolved before dry run")
        if args.target.is_symlink() or not args.target.is_dir():
            raise ValueError("target must be an existing directory")
        harness_root = Path(__file__).resolve().parents[4]
        if args.target.resolve() == harness_root:
            raise ValueError("the Harness repository cannot be used as the target")
        mappings = load_object(
            Path(__file__).resolve().parent.parent / "references" / "generation-mappings.json"
        )
        strategies = mappings["contributorStrategies"]
        unresolved = [
            name
            for name in plan["projectStructure"].get("contributors", [])
            if strategies.get(name) != "initializr-covered"
        ]
        with tempfile.TemporaryDirectory(prefix="spring-generation-dry-run-") as temporary_name:
            temporary = Path(temporary_name)
            rendered = temporary / "rendered"
            rendered.mkdir()
            if args.rendered_source:
                if not args.rendered_source.is_dir():
                    raise ValueError("rendered source must be a directory")
                for relative, source_file in files_under(args.rendered_source).items():
                    destination = rendered / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, destination)
            else:
                archive = args.rendered_archive
                if archive is None:
                    archive = temporary / "starter.zip"
                    download_initializr(plan, archive)
                safe_extract(archive, rendered)
            baseline, baseline_modes = load_baseline(args.baseline_manifest)
            changes = compare(rendered, args.target, baseline, baseline_modes)
        contributor_conflicts = [
            {"path": None, "reason": f"contributor-not-yet-rendered:{name}"}
            for name in unresolved
        ]
        changes["conflicts"].extend(contributor_conflicts)
        if changes["conflicts"]:
            changes["state"] = "CONFLICT"
        report = {
            "dryRunVersion": 1,
            "sourcePlan": str(args.plan),
            "target": str(args.target.resolve()),
            "plannedChanges": changes,
            "targetSourceChanged": False,
            "readyForApproval": changes["state"] == "COMPUTED",
            "executionReady": False,
            "nextStep": (
                "Resolve conflicts and repeat the dry run."
                if changes["state"] == "CONFLICT"
                else "Review the report and obtain explicit approval before applying files."
            ),
        }
        if args.output:
            write_report(report, args.output, args.force)
        else:
            json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
            print()
    except ValueError as error:
        print(f"DRY_RUN_VALID: no\nERROR: {error}", file=sys.stderr)
        return 1
    print("DRY_RUN_VALID: yes", file=sys.stderr)
    print(f"CHANGE_RESULT: {report['plannedChanges']['state']}", file=sys.stderr)
    print("TARGET_SOURCE_CHANGED: no", file=sys.stderr)
    print(f"READY_FOR_APPROVAL: {'yes' if report['readyForApproval'] else 'no'}", file=sys.stderr)
    print("EXECUTION_READY: no", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
