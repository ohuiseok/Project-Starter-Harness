#!/usr/bin/env python3
"""Bounded, read-only discovery of existing HTTP API evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from existing_http_api_contract import controller_mappings
from continuation_route import markdown
from http_api_contract import derived_traceability, operations, validate_openapi
from spring_milestone_completion import sha, target_path
from validate_feature_specs import load_object, validate_feature

VERSION = 1
EXCLUDED = {".git", ".gradle", ".idea", ".vscode", "build", "target", "out", "node_modules", "vendor", "generated", "logs"}
SOURCE_SUFFIXES = {".java", ".kt"}
OPENAPI_SUFFIXES = {".json", ".yaml", ".yml"}
WORD = re.compile(r"[0-9A-Za-z가-힣]+")


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def atomic_create(content: bytes, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        if temporary.exists(): temporary.unlink()


def words(value: str) -> set[str]:
    return {item.lower() for item in WORD.findall(value) if len(item) > 1}


def snapshot(path: Path) -> tuple[bytes, bool]:
    """Read once and report whether the path stayed identical during the read."""
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        content = stream.read()
        after = os.fstat(stream.fileno())
    current = path.stat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    return content, identity(before) == identity(after) == identity(current)


def evidence_for(relative: str, content: bytes, stable: bool) -> dict:
    return {
        "path": relative,
        "sha256": hashlib.sha256(content).hexdigest(),
        "sizeBytes": len(content),
        "stability": "STABLE" if stable else "UNSTABLE",
    }


def candidate_id(kind: str, relative: str, digest: str) -> str:
    value = f"{kind}\0{relative}\0{digest}".encode()
    return "api-" + hashlib.sha256(value).hexdigest()[:16]


def with_id(candidate: dict) -> dict:
    evidence = candidate["evidence"]
    return {"candidateId": candidate_id(candidate["kind"], evidence["path"], evidence["sha256"]), **candidate}


def feature_words(feature: dict) -> set[str]:
    values = [feature["feature"][key] for key in ("name", "goal", "userValue")]
    for item in feature["acceptanceCriteria"]:
        values.extend(item[key] for key in ("given", "when", "then"))
    return words(" ".join(values))


def git_context(root: Path) -> tuple[str, set[str]]:
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True, check=False)
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True, check=False)
    status = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=root, capture_output=True, check=False)
    if top.returncode or branch.returncode or status.returncode or Path(top.stdout.strip()).resolve() != root:
        raise ValueError("target Git root, branch, or dirty state cannot be verified")
    entries = status.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    dirty = set()
    index = 0
    while index < len(entries) and entries[index]:
        entry = entries[index]; path = entry[3:]; dirty.add(path)
        if entry[:2][0] in {"R", "C"} or entry[:2][1] in {"R", "C"}:
            index += 1
            if index < len(entries) and entries[index]: dirty.add(entries[index])
        index += 1
    return branch.stdout.strip() or "DETACHED", dirty


def scope_path(root: Path, value: str) -> Path:
    if value == ".":
        return root
    path = target_path(root, value, "discovery module")
    if not path.is_dir(): raise ValueError(f"discovery module is missing or not a directory: {value}")
    return path


def discover(root: Path, feature_path: Path, profile_path: Path, modules: list[str], max_files: int, max_file_bytes: int, max_total_bytes: int, excluded_paths: list[str] | None = None) -> dict:
    feature = load_object(feature_path); profile = load_object(profile_path)
    approved, blockers = validate_feature(feature, None)
    if not approved or blockers: raise ValueError("an approved feature specification is required")
    if profile.get("profileVersion") != 1: raise ValueError("technology profile version is unsupported")
    branch, dirty = git_context(root); scopes = [scope_path(root, item) for item in modules]; excluded_paths = excluded_paths or []
    seen: set[str] = set(); candidates = []; inspected = 0; content_bytes = 0; truncated = False; wanted = feature_words(feature)
    for scope in scopes:
        for directory, names, files in os.walk(scope, followlinks=False):
            base = Path(directory)
            names[:] = sorted(name for name in names if name not in EXCLUDED and not (base / name).is_symlink())
            for name in sorted(files):
                path = base / name
                if path.is_symlink(): continue
                relative = path.relative_to(root).as_posix()
                if relative in excluded_paths: continue
                if relative in seen: continue
                seen.add(relative); inspected += 1
                if inspected > max_files: truncated = True; break
                suffix = path.suffix.lower()
                if suffix not in OPENAPI_SUFFIXES | SOURCE_SUFFIXES: continue
                try: size = path.stat().st_size
                except OSError:
                    size = 0
                if size > max_file_bytes: continue
                if content_bytes + size > max_total_bytes: truncated = True; break
                try:
                    content, unchanged = snapshot(path)
                except OSError as error:
                    placeholder = hashlib.sha256(f"unreadable:{relative}".encode()).hexdigest()
                    candidates.append(with_id({"kind": "UNREADABLE_SOURCE" if suffix in SOURCE_SUFFIXES else "UNREADABLE_API", "evidence": {"path": relative, "sha256": placeholder, "sizeBytes": size, "stability": "UNSTABLE"}, "discovery": {"parseState": "UNREADABLE"}, "requirementMatches": [], "requirementCoverage": {"required": [], "covered": [], "missing": []}, "recommendedDisposition": "UNKNOWN", "confidence": "LOW", "decisionReasons": ["The file could not be read safely"], "ambiguities": [f"Evidence read failed: {error.strerror or type(error).__name__}"]}))
                    continue
                if content_bytes + len(content) > max_total_bytes:
                    truncated = True
                    break
                content_bytes += len(content)
                evidence = evidence_for(relative, content, unchanged and relative not in dirty)
                if suffix == ".json":
                    try: document = json.loads(content.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        if "openapi" not in name.lower() and "swagger" not in name.lower(): continue
                        candidates.append(with_id({"kind": "OPENAPI_JSON", "evidence": evidence, "discovery": {"operations": [], "parseState": "MALFORMED"}, "requirementMatches": [], "requirementCoverage": {"required": [], "covered": [], "missing": []}, "recommendedDisposition": "UNKNOWN", "confidence": "LOW", "decisionReasons": ["The possible OpenAPI document is malformed"], "ambiguities": [f"JSON could not be parsed at line {getattr(error, 'lineno', '?')}"]})); continue
                    if not isinstance(document, dict): continue
                    if not isinstance(document.get("openapi"), str) or not isinstance(document.get("paths"), dict):
                        if "openapi" not in document and "paths" not in document and "openapi" not in name.lower() and "swagger" not in name.lower(): continue
                        candidates.append(with_id({"kind": "OPENAPI_JSON", "evidence": evidence, "discovery": {"operations": [], "parseState": "MALFORMED"}, "requirementMatches": [], "requirementCoverage": {"required": [], "covered": [], "missing": []}, "recommendedDisposition": "UNKNOWN", "confidence": "LOW", "decisionReasons": ["The possible OpenAPI document is structurally incomplete"], "ambiguities": ["OpenAPI version and paths must have supported JSON types"]})); continue
                    found_ops = []
                    try:
                        for api_path, method, operation in operations(document):
                            description = " ".join(str(operation.get(key, "")) for key in ("operationId", "summary", "description")) + " " + api_path
                            refs = operation.get("x-harness-requirement-refs", [])
                            found_ops.append({"method": method.upper(), "path": api_path, "operationId": operation.get("operationId"), "requirementRefs": refs if isinstance(refs, list) else [], "matchTerms": sorted(wanted & words(description))})
                    except (TypeError, ValueError):
                        candidates.append(with_id({"kind": "OPENAPI_JSON", "evidence": evidence, "discovery": {"operations": [], "parseState": "UNKNOWN"}, "requirementMatches": [], "requirementCoverage": {"required": [], "covered": [], "missing": []}, "recommendedDisposition": "UNKNOWN", "confidence": "LOW", "decisionReasons": ["Operations could not be interpreted"], "ambiguities": ["OpenAPI operations could not be parsed safely"]})); continue
                    matched = [item for item in found_ops if item["matchTerms"]]
                    required_refs = {item["id"] for item in feature["acceptanceCriteria"]} | {item["id"] for item in feature["businessRules"]}
                    covered = {ref for item in matched for ref in item["requirementRefs"]}
                    coverage = {"required": sorted(required_refs), "covered": sorted(required_refs & covered), "missing": sorted(required_refs - covered)}
                    selected_ids = {item["operationId"] for item in matched if isinstance(item["operationId"], str)}
                    try:
                        semantic_blockers = validate_openapi(document, feature, profile, {"traceability": derived_traceability(document)}, selected_ids or None)
                    except (TypeError, ValueError) as error:
                        candidates.append(with_id({"kind": "OPENAPI_JSON", "evidence": evidence, "discovery": {"operations": found_ops, "parseState": "UNKNOWN"}, "requirementMatches": matched, "requirementCoverage": coverage, "recommendedDisposition": "UNKNOWN", "confidence": "LOW", "decisionReasons": ["Semantic validation could not complete"], "ambiguities": [f"OpenAPI semantic validation failed: {error}"]})); continue
                    if matched and required_refs and required_refs <= covered and not semantic_blockers:
                        disposition, confidence, reasons, ambiguities = "REUSE", "HIGH", ["Matched operations cover every feature requirement and pass semantic validation"], []
                    elif matched:
                        disposition, confidence, reasons, ambiguities = "EXTEND", "MEDIUM", ["Related operations exist but the contract needs changes or more evidence"], ["Existing operations are related but do not prove complete requirement coverage", *semantic_blockers]
                    else:
                        disposition, confidence, reasons, ambiguities = "UNKNOWN", "LOW", ["No operation could be tied deterministically to the feature"], ["No operation has a deterministic feature-term match"]
                    candidates.append(with_id({"kind": "OPENAPI_JSON", "evidence": evidence, "discovery": {"operations": found_ops, "parseState": "PARSED"}, "requirementMatches": matched, "requirementCoverage": coverage, "recommendedDisposition": disposition, "confidence": confidence, "decisionReasons": reasons, "ambiguities": ambiguities}))
                elif suffix in {".yaml", ".yml"}:
                    head = content.decode("utf-8", errors="replace")[:4096]
                    if re.search(r"(?m)^\s*openapi\s*:", head):
                        candidates.append(with_id({"kind": "OPENAPI_YAML", "evidence": evidence, "discovery": {"operations": [], "parseState": "UNSUPPORTED"}, "requirementMatches": [], "requirementCoverage": {"required": [], "covered": [], "missing": []}, "recommendedDisposition": "UNKNOWN", "confidence": "LOW", "decisionReasons": ["A possible contract exists but this adapter cannot validate YAML"], "ambiguities": ["YAML OpenAPI validation is not supported by the current adapter"]}))
                else:
                    text = content.decode("utf-8", errors="replace")
                    if "@RestController" not in text and "@Controller" not in text: continue
                    parsed = controller_mappings(path, text)
                    mappings = [{"method": method.upper(), "path": api_path} for method, api_path in sorted(parsed.mappings)]
                    matches = [item for item in mappings if wanted & words(item["path"])]
                    ambiguities = list(parsed.unknowns) + ["Controller evidence alone cannot prove the complete public API contract"]
                    candidates.append(with_id({"kind": "SPRING_CONTROLLER", "evidence": evidence, "discovery": {"mappings": mappings, "parseState": "PARSED" if not parsed.unknowns else "PARTIAL"}, "requirementMatches": matches, "requirementCoverage": {"required": [], "covered": [], "missing": []}, "recommendedDisposition": "UNKNOWN", "confidence": "LOW", "decisionReasons": ["Controller mappings are implementation evidence, not a complete public contract"], "ambiguities": ambiguities}))
            if truncated: break
        if truncated: break
    api_candidates = [item for item in candidates if item["kind"] in {"OPENAPI_JSON", "OPENAPI_YAML", "UNREADABLE_API"}]
    stable_openapi = [item for item in api_candidates if item["kind"] == "OPENAPI_JSON" and item["evidence"]["stability"] == "STABLE" and item["discovery"]["parseState"] == "PARSED"]
    overall = "CREATE" if not candidates else (stable_openapi[0]["recommendedDisposition"] if len(api_candidates) == 1 and len(stable_openapi) == 1 else "UNKNOWN")
    if truncated: overall = "UNKNOWN"
    return {"httpApiEvidenceDiscoveryVersion": VERSION, "target": str(root), "git": {"root": str(root), "branch": branch}, "inputs": {"feature": {"path": feature_path.relative_to(root).as_posix(), "sha256": sha(feature_path)}, "technologyProfile": {"path": profile_path.relative_to(root).as_posix(), "sha256": sha(profile_path)}}, "scope": {"modules": modules, "excludedDirectories": sorted(EXCLUDED), "excludedPaths": excluded_paths, "maxFiles": max_files, "maxFileBytes": max_file_bytes, "maxTotalBytes": max_total_bytes}, "summary": {"filesInspected": min(inspected, max_files), "contentBytesRead": content_bytes, "candidateCount": len(candidates), "truncated": truncated, "recommendedDisposition": overall}, "candidates": candidates, "effects": {"routeChanged": False, "sourceChanged": False, "runtimeExecuted": False, "gitCommitOrPush": "NOT_RUN"}}


def render(report: dict) -> str:
    lines = ["# 기존 HTTP API 근거 탐색", "", f"- 전체 추천: {report['summary']['recommendedDisposition']}", f"- 조사 파일: {report['summary']['filesInspected']}개 · 후보: {report['summary']['candidateCount']}개", f"- 범위 제한 도달: {'예' if report['summary']['truncated'] else '아니오'}", "", "## 발견한 기존 설계", ""]
    for item in report["candidates"]:
        lines.append(f"### {item['candidateId']}")
        lines.extend(["", f"- 파일: `{markdown(item['evidence']['path'])}`", f"- 판정: {item['kind']} · {item['recommendedDisposition']} · 신뢰도 {item['confidence']} · 상태 {item['evidence']['stability']}"])
        for reason in item.get("decisionReasons", []): lines.append(f"- 판단 이유: {markdown(reason)}")
        matches = item.get("requirementMatches", [])
        if matches:
            lines.append("- 기능과 연결된 API:")
            for match in matches:
                operation = match.get("operationId") or "operationId 없음"
                lines.append(f"  - {markdown(match['method'])} `{markdown(match['path'])}` · {markdown(operation)}")
        coverage = item.get("requirementCoverage", {})
        if coverage.get("required"):
            lines.append(f"- 요구사항: 충족 {len(coverage['covered'])}/{len(coverage['required'])}")
            if coverage["missing"]: lines.append(f"  - 미충족: {', '.join(markdown(value) for value in coverage['missing'])}")
        for ambiguity in item["ambiguities"]: lines.append(f"  - 확인 필요: {markdown(ambiguity)}")
        lines.append("")
    if not report["candidates"]: lines.append("- 기존 HTTP API 근거 없음 · 새 계약 생성 추천")
    lines.extend(["", "## 다음 선택", "", "- 추천 적용", "- 다른 후보 선택", "- 새로 생성", "- 기타 내용을 자연어로 입력", "- 취소", "", "이 보고서는 라우트·소스·런타임·Git 상태를 변경하지 않습니다.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature", required=True, type=Path); parser.add_argument("--profile", required=True, type=Path); parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--module", action="append", default=[]); parser.add_argument("--output", required=True, type=Path); parser.add_argument("--view", required=True, type=Path)
    parser.add_argument("--max-files", type=int, default=5000); parser.add_argument("--max-file-bytes", type=int, default=1_048_576); parser.add_argument("--max-total-bytes", type=int, default=20_971_520)
    args = parser.parse_args(); created = []
    try:
        root = args.target.resolve(strict=True)
        feature = target_path(root, args.feature.absolute().relative_to(root).as_posix(), "feature"); profile = target_path(root, args.profile.absolute().relative_to(root).as_posix(), "profile")
        output = target_path(root, args.output.absolute().relative_to(root).as_posix(), "discovery output"); view = target_path(root, args.view.absolute().relative_to(root).as_posix(), "discovery view")
        modules = args.module or ["."]
        if args.target.is_symlink() or view != output.with_suffix(".md") or output.exists() or view.exists() or min(args.max_files, args.max_file_bytes, args.max_total_bytes) < 1: raise ValueError("discovery target, outputs, or limits are unsafe")
        excluded = [output.relative_to(root).as_posix(), view.relative_to(root).as_posix()]
        report = discover(root, feature, profile, modules, args.max_files, args.max_file_bytes, args.max_total_bytes, excluded); report_bytes = encoded(report); view_bytes = render(report).encode()
        output.parent.mkdir(parents=True, exist_ok=True); atomic_create(report_bytes, output); created.append((output, report_bytes)); atomic_create(view_bytes, view); created.append((view, view_bytes))
    except (OSError, ValueError, KeyError, TypeError) as error:
        for path, content in reversed(created):
            if path.exists() and path.read_bytes() == content: path.unlink()
        print(f"HTTP_API_EVIDENCE_DISCOVERY_VALID: no\nERROR: {error}"); return 1
    print("HTTP_API_EVIDENCE_DISCOVERY_VALID: yes"); print("ROUTE_CHANGED: no"); print("SOURCE_CHANGED: no"); return 0


if __name__ == "__main__": sys.exit(main())
