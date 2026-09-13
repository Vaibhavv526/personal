#!/usr/bin/env python3
"""
aggregate_report.py — Deterministic findings aggregation and validation pipeline
for the brand AI-readiness audit orchestrator.

Implements strict validation, deduplication, sequential ID assignment,
and summary recalculation directly from the final findings array.
"""

import sys
import json
import re
import copy
from typing import Any, Optional

SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
}

VALID_TYPES = {"defect", "opportunity"}
VALID_SEVERITIES = {"critical", "high", "medium"}
VALID_PRIORITIES = {"high", "medium", "low"}
ID_REGEX = re.compile(r"^F-[0-9]{3}$")


class ReportIntegrityError(Exception):
    """Raised when report aggregation or validation fails integrity checks."""
    pass


def normalize_string(s: str) -> str:
    """Normalize string for deduplication comparison."""
    return re.sub(r"\s+", " ", s.strip().lower())


def deduplicate_findings(raw_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Deduplicate genuinely overlapping findings.
    
    Rules:
    - Never discard findings merely because they have different types or source skills.
    - Two findings are considered overlapping ONLY if they have the exact same normalized title
      and the same type.
    - Never merge fields (evidence, suggested_action) from different findings.
    - Keep the finding with the higher severity (critical > high > medium).
    - If equal, keep the first encountered finding.
    """
    deduped: list[dict[str, Any]] = []
    seen_keys: dict[tuple[str, str], int] = {}  # (type, normalized_title) -> index in deduped

    for f in raw_findings:
        finding = copy.deepcopy(f)
        f_type = finding.get("type", "defect")
        f_title = finding.get("title", "")
        key = (f_type, normalize_string(f_title))

        if key in seen_keys:
            existing_idx = seen_keys[key]
            existing_sev = deduped[existing_idx].get("severity", "medium")
            new_sev = finding.get("severity", "medium")

            # If incoming has strictly higher severity, replace entirely (no merging of fields)
            if SEVERITY_ORDER.get(new_sev, 99) < SEVERITY_ORDER.get(existing_sev, 99):
                deduped[existing_idx] = finding
            # Otherwise discard duplicate without touching the existing finding
        else:
            seen_keys[key] = len(deduped)
            deduped.append(finding)

    return deduped


def sort_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sort: defects first (critical -> high -> medium), then opportunities (medium only).
    Preserve original discovery order within each tier (stable sort).
    """
    def sort_key(item: dict[str, Any]) -> tuple[int, int]:
        f_type = item.get("type", "defect")
        f_sev = item.get("severity", "medium")
        type_rank = 0 if f_type == "defect" else 1
        sev_rank = SEVERITY_ORDER.get(f_sev, 99)
        return (type_rank, sev_rank)

    return sorted(findings, key=sort_key)


def validate_finding_object(finding: dict[str, Any], expected_id: Optional[str] = None) -> None:
    """Validate every finding object independently against all schema and integrity rules."""
    required_keys = {"id", "type", "title", "severity", "evidence", "suggested_action"}
    actual_keys = set(finding.keys())

    missing = required_keys - actual_keys
    if missing:
        raise ReportIntegrityError(f"Finding is missing required keys: {missing} in finding: {finding}")

    forbidden = actual_keys - required_keys
    if forbidden:
        raise ReportIntegrityError(f"Finding contains unallowed keys: {forbidden} in finding: {finding}")

    f_id = finding["id"]
    if not isinstance(f_id, str) or not ID_REGEX.match(f_id):
        raise ReportIntegrityError(f"Invalid finding id format: '{f_id}'")
    if expected_id and f_id != expected_id:
        raise ReportIntegrityError(f"Finding ID mismatch: expected '{expected_id}', got '{f_id}'")

    f_type = finding["type"]
    if f_type not in VALID_TYPES:
        raise ReportIntegrityError(f"Invalid finding type: '{f_type}'")

    f_title = finding["title"]
    if not isinstance(f_title, str) or not f_title.strip():
        raise ReportIntegrityError(f"Finding title must be a non-empty string in {f_id}")

    f_sev = finding["severity"]
    if f_sev not in VALID_SEVERITIES:
        raise ReportIntegrityError(f"Invalid finding severity: '{f_sev}' in {f_id}")
    if f_type == "opportunity" and f_sev != "medium":
        raise ReportIntegrityError(f"Opportunity finding must have severity 'medium', got '{f_sev}' in {f_id}")

    f_ev = finding["evidence"]
    if not isinstance(f_ev, str) or not f_ev.strip():
        raise ReportIntegrityError(f"Finding evidence must be a non-empty string in {f_id}")

    sa = finding["suggested_action"]
    if not isinstance(sa, dict):
        raise ReportIntegrityError(f"suggested_action must be a dictionary in {f_id}")

    sa_required_keys = {"summary", "priority"}
    sa_keys = set(sa.keys())
    if sa_keys != sa_required_keys:
        raise ReportIntegrityError(f"suggested_action keys must be exactly {sa_required_keys}, got {sa_keys} in {f_id}")

    sa_summary = sa["summary"]
    if not isinstance(sa_summary, str) or not sa_summary.strip():
        raise ReportIntegrityError(f"suggested_action.summary must be a non-empty string in {f_id}")

    sa_prio = sa["priority"]
    if sa_prio not in VALID_PRIORITIES:
        raise ReportIntegrityError(f"Invalid suggested_action.priority: '{sa_prio}' in {f_id}")


def log_debug_instrumentation(
    raw_findings: list[dict[str, Any]],
    final_findings: list[dict[str, Any]],
) -> None:
    """
    Log debug instrumentation to sys.stderr:
    - specialist name
    - number of raw findings returned
    - titles of raw findings
    - total number of findings passed to aggregate_and_validate
    - number of findings returned by aggregate_and_validate
    """
    specialists: dict[str, list[str]] = {}
    for f in raw_findings:
        skill = f.get("source_skill", "unknown-specialist")
        title = f.get("title", "<untitled>")
        specialists.setdefault(skill, []).append(title)

    print("=== AUDIT-ORCHESTRATOR DEBUG INSTRUMENTATION ===", file=sys.stderr)
    print("Specialist breakdown:", file=sys.stderr)
    for skill, titles in sorted(specialists.items()):
        print(f"  [{skill}]: {len(titles)} raw findings", file=sys.stderr)
        for t in titles:
            print(f"    - {t}", file=sys.stderr)
    print(f"Total raw findings passed to aggregate_and_validate: {len(raw_findings)}", file=sys.stderr)
    print(f"Total findings returned by aggregate_and_validate: {len(final_findings)}", file=sys.stderr)
    print("================================================", file=sys.stderr)


def aggregate_and_validate(
    site: str,
    audited_at: str,
    raw_findings: list[dict[str, Any]],
    debug: bool = True
) -> dict[str, Any]:
    """
    Compile and strictly validate final audit report.
    
    Requirements fulfilled:
    1. Preserve every valid finding returned by each specialist skill.
    2. Collect complete findings before assigning final IDs.
    3. Deduplicate only genuinely overlapping findings.
    4. Never discard findings merely because of different types or source skills.
    5. Never merge fields from different findings.
    6. Each final finding is an independent object with strict schema.
    7. suggested_action contains exactly summary and priority.
    8. No finding contains another finding's evidence or suggested_action.
    9. Assign IDs sequentially: F-001, F-002, ...
    10. Recalculate summary counts directly FROM the final findings array.
    11. Validate summary.total_findings == len(findings).
    12. Validate severity and opportunity counts.
    13. Validate no missing or non-sequential IDs.
    14. Validate every finding object independently.
    15. Repair/revalidate internally if needed.
    """
    # 1. Clean and isolate each finding
    isolated: list[dict[str, Any]] = []
    for raw in raw_findings:
        f = copy.deepcopy(raw)
        # Strip internal source_skill if present
        f.pop("source_skill", None)
        f.pop("id", None)  # orchestrator assigns final IDs

        # Ensure valid type
        f_type = f.get("type", "defect")
        if f_type not in VALID_TYPES:
            f_type = "defect"
        f["type"] = f_type

        # Ensure valid severity
        f_sev = f.get("severity", "medium")
        if f_sev not in VALID_SEVERITIES:
            f_sev = "medium"
        if f_type == "opportunity":
            f_sev = "medium"
        f["severity"] = f_sev

        # Ensure valid suggested_action
        sa = f.get("suggested_action")
        if not isinstance(sa, dict):
            sa = {"summary": str(sa or ""), "priority": "medium"}
        
        sa_summary = str(sa.get("summary", "")).strip()
        sa_priority = sa.get("priority")
        if sa_priority not in VALID_PRIORITIES:
            sa_priority = "high" if f_sev in ("critical", "high") else "medium"

        f["suggested_action"] = {
            "summary": sa_summary,
            "priority": sa_priority
        }

        # Ensure evidence and title are strings
        f["title"] = str(f.get("title", "")).strip()
        f["evidence"] = str(f.get("evidence", "")).strip()

        isolated.append(f)

    # 2. Deduplicate only genuinely overlapping findings
    deduped = deduplicate_findings(isolated)

    # 3. Sort: defects (critical -> high -> medium) then opportunities (medium)
    sorted_findings = sort_findings(deduped)

    # 4. Assign sequential IDs
    final_findings: list[dict[str, Any]] = []
    for idx, f in enumerate(sorted_findings):
        expected_id = f"F-{idx + 1:03d}"
        f_final = {
            "id": expected_id,
            "type": f["type"],
            "title": f["title"],
            "severity": f["severity"],
            "evidence": f["evidence"],
            "suggested_action": {
                "summary": f["suggested_action"]["summary"],
                "priority": f["suggested_action"]["priority"]
            }
        }
        # Validate individual finding object
        validate_finding_object(f_final, expected_id=expected_id)
        final_findings.append(f_final)

    # 5. Compute summary counts strictly from final_findings
    total_findings = len(final_findings)
    critical_count = sum(1 for f in final_findings if f["type"] == "defect" and f["severity"] == "critical")
    high_count = sum(1 for f in final_findings if f["type"] == "defect" and f["severity"] == "high")
    medium_count = sum(1 for f in final_findings if f["type"] == "defect" and f["severity"] == "medium")
    opportunity_count = sum(1 for f in final_findings if f["type"] == "opportunity")

    summary = {
        "total_findings": total_findings,
        "critical": critical_count,
        "high": high_count,
        "medium": medium_count,
        "opportunities": opportunity_count
    }

    # 6. Global report validation
    if summary["total_findings"] != len(final_findings):
        raise ReportIntegrityError("summary.total_findings does not match findings length")

    defect_sum = summary["critical"] + summary["high"] + summary["medium"]
    if defect_sum + summary["opportunities"] != summary["total_findings"]:
        raise ReportIntegrityError("Sum of summary severity counts does not match total_findings")

    # Validate ID continuity
    expected_ids = [f"F-{i+1:03d}" for i in range(len(final_findings))]
    actual_ids = [f["id"] for f in final_findings]
    if expected_ids != actual_ids:
        raise ReportIntegrityError(f"ID sequence broken: expected {expected_ids}, got {actual_ids}")

    clean_site = re.sub(r"^https?://", "", site).split("/")[0]
    clean_site = re.sub(r"^www\.", "", clean_site)

    if debug:
        log_debug_instrumentation(raw_findings, final_findings)

    return {
        "site": clean_site,
        "audited_at": audited_at,
        "summary": summary,
        "findings": final_findings
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: aggregate_report.py <raw_findings_json_file_or_stdin> [site] [audited_at]", file=sys.stderr)
        sys.exit(1)

    input_source = sys.argv[1]
    if input_source == "-":
        data = json.load(sys.stdin)
    else:
        with open(input_source, "r", encoding="utf-8") as f:
            data = json.load(f)

    site = sys.argv[2] if len(sys.argv) > 2 else data.get("site", "example.com")
    audited_at = sys.argv[3] if len(sys.argv) > 3 else data.get("audited_at", "2026-09-11T00:00:00Z")
    raw_findings = data.get("findings", data) if isinstance(data, dict) else data

    report = aggregate_and_validate(site, audited_at, raw_findings)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
