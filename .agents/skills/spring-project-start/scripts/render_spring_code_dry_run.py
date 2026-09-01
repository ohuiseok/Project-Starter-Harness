#!/usr/bin/env python3
"""Compare an exact Java candidate with a target without applying source."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from render_generation_dry_run import compare, write_report
from spring_code_dry_run import canonical_baseline, load_approved_plan, sha, validate_candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--rendered-source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        root = args.target.resolve(strict=True)
        harness = Path(__file__).resolve().parents[4]
        output = args.output.resolve(strict=False)
        if not root.is_dir() or args.target.is_symlink() or root == harness or root not in output.parents or args.output.is_symlink():
            raise ValueError("target or output is unsafe")
        plan = load_approved_plan(args.plan.resolve(strict=True), root)
        checks, candidate_conflicts = validate_candidate(plan, args.rendered_source)
        _, baseline_ref, baseline, modes = canonical_baseline(root)
        changes = compare(args.rendered_source, root, baseline, modes)
        changes["conflicts"].extend(candidate_conflicts)
        if changes["conflicts"]:
            changes["state"] = "CONFLICT"
        generated = []
        expected = {item["target"]["plannedPath"]: item for item in plan["components"]}
        for relative in sorted(expected):
            source = args.rendered_source / relative
            if source.is_file() and not source.is_symlink():
                generated.append({"componentRef": expected[relative]["componentId"], "kind": expected[relative]["kind"], "path": relative, "sha256": sha(source), "content": source.read_text(encoding="utf-8")})
        report = {
            "springCodeDryRunVersion": 1,
            "implementationPlan": {"path": args.plan.resolve().relative_to(root).as_posix(), "sha256": sha(args.plan)},
            "target": str(root),
            "baseline": baseline_ref,
            "userFlow": plan["userFlow"],
            "qualityChecks": checks,
            "generatedFiles": generated,
            "plannedChanges": changes,
            "verification": {"compilation": "NOT_RUN", "automatedTests": "NOT_RUN", "reason": "Dry run does not execute target code."},
            "targetSourceChanged": False,
            "readyForApproval": changes["state"] == "COMPUTED",
            "executionReady": False,
        }
        write_report(report, output, args.force)
    except (OSError, ValueError, KeyError) as error:
        print(f"SPRING_CODE_DRY_RUN_VALID: no\nERROR: {error}", file=sys.stderr)
        return 1
    print("SPRING_CODE_DRY_RUN_VALID: yes")
    print(f"CHANGE_RESULT: {report['plannedChanges']['state']}")
    print("TARGET_SOURCE_CHANGED: no")
    print(f"READY_FOR_APPROVAL: {'yes' if report['readyForApproval'] else 'no'}")
    print("EXECUTION_READY: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
