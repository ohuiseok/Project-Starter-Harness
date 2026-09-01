#!/usr/bin/env python3
"""Create physical relational design metadata without rendering or applying files."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from http_api_contract import encoded
from record_spec_approval import atomic_write_bytes
from relational_physical_contract import derived_traceability, load_adapters, validate_physical_contract
from validate_feature_specs import load_object


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logical-contract", required=True, type=Path); parser.add_argument("--physical-model-source", required=True, type=Path)
    parser.add_argument("--physical-contract-output", required=True, type=Path); parser.add_argument("--physical-model-output", required=True, type=Path)
    parser.add_argument("--route", required=True, type=Path); parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path); parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args(); created = []
    try:
        root = args.target.resolve(strict=True); contract_output, model_output = args.physical_contract_output.resolve(), args.physical_model_output.resolve()
        for path, label in ((contract_output, "physical contract output"), (model_output, "physical model output")):
            if root not in (path, *path.parents): raise ValueError(f"{label} escapes target")
            if path.exists(): raise ValueError(f"{label} already exists; implicit overwrite is not allowed")
        if contract_output.parent != model_output.parent: raise ValueError("physical metadata and model must be siblings")
        logical_metadata = load_object(args.logical_contract); logical_model = load_object(root / logical_metadata["artifact"]["path"])
        physical = load_object(args.physical_model_source); physical_content = encoded(physical)
        adapter = load_adapters().get(physical.get("adapterId"))
        if adapter is None: raise ValueError("physical model references an unknown adapter")
        metadata = {
            "physicalContractVersion": 1, "contractId": f"{logical_metadata['contractId']}-physical",
            "logicalContract": {"path": args.logical_contract.resolve().relative_to(root).as_posix(), "sha256": hashlib.sha256(args.logical_contract.read_bytes()).hexdigest()},
            "logicalModel": {"path": logical_metadata["artifact"]["path"], "sha256": logical_metadata["modelSha256"]},
            "target": logical_metadata["target"], "artifact": {"format": "PHYSICAL_DATA_MODEL", "path": model_output.relative_to(root).as_posix()},
            "physicalModelSha256": hashlib.sha256(physical_content).hexdigest(), "adapter": {"id": adapter["id"], "status": adapter["status"]},
            "traceability": derived_traceability(physical, logical_model),
            "approval": {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None},
        }
        metadata_content = encoded(metadata)
        for path, content in ((model_output, physical_content), (contract_output, metadata_content)):
            path.parent.mkdir(parents=True, exist_ok=True); atomic_write_bytes(content, path); created.append((path, content))
        _, blockers, _, _ = validate_physical_contract(metadata, model_output, args.logical_contract, load_object(args.route), args.route, root, load_object(args.feature), load_object(args.profile))
    except (OSError, ValueError) as error:
        rollback_errors = []
        for path, expected in reversed(created):
            try:
                if path.read_bytes() != expected: raise OSError("created artifact changed externally; refusing rollback deletion")
                path.unlink()
            except OSError as rollback_error: rollback_errors.append(f"{path}: {rollback_error}")
        suffix = f"; rollback incomplete: {rollback_errors}" if rollback_errors else ""
        print(f"RELATIONAL_PHYSICAL_CONTRACT_CREATED: no\nERROR: {error}{suffix}"); return 1
    print("RELATIONAL_PHYSICAL_CONTRACT_CREATED: yes")
    print(f"CONTRACT_DRAFT_READY: {'yes' if not blockers else 'no'}")
    for blocker in blockers: print(f"BLOCKER: {blocker}")
    print("TARGET_SOURCE_CHANGED: no"); print("MIGRATION_RENDERED: no"); print("DATABASE_OR_CONTAINER_CHANGED: no")
    return 0


if __name__ == "__main__": sys.exit(main())
