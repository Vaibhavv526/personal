#!/usr/bin/env python3
"""Validates an audit report JSON against the marketplace's own documented schema."""
import json
import re
import sys

ID_RE = re.compile(r"^F-\d{3}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
VALID_SEVERITIES = {"critical", "high", "medium"}
VALID_TYPES = {"defect", "opportunity"}
VALID_PRIORITIES = {"high", "medium", "low"}

def validate(report_path):
    errors = []
    try:
        with open(report_path, encoding="utf-8") as fh:
            raw = fh.read()
    except FileNotFoundError:
        return [f"Report file not found: {report_path}"]

    try:
        report = json.loads(raw)
    except json.JSONDecodeError as e:
        return [f"Output is not valid JSON: {e}. First 300 chars: {raw[:300]!r}"]

    for key in ("site", "audited_at", "summary", "findings"):
        if key not in report:
            errors.append(f"Missing top-level key: {key}")
    if errors:
        return errors

    site = report["site"]
    if "://" in site or site.startswith("/") or site.endswith("/"):
        errors.append(f"site should be bare hostname, got: {site!r}")

    if not ISO_RE.match(report["audited_at"]):
        errors.append(f"audited_at not in expected UTC ISO-8601 Z format: {report['audited_at']!r}")

    findings = report["findings"]
    summary = report["summary"]

    if summary.get("total_findings") != len(findings):
        errors.append(f"summary.total_findings ({summary.get('total_findings')}) != len(findings) ({len(findings)})")

    seen_ids = []
    sev_counts = {"critical": 0, "high": 0, "medium": 0}
    opportunity_count = 0

    for i, f in enumerate(findings):
        loc = f"findings[{i}] (id={f.get('id')})"
        for key in ("id", "title", "severity", "evidence", "suggested_action"):
            if key not in f:
                errors.append(f"{loc}: missing key '{key}'")
        fid = f.get("id", "")
        if not ID_RE.match(fid):
            errors.append(f"{loc}: id '{fid}' doesn't match ^F-[0-9]{{3}}$")
        seen_ids.append(fid)

        ftype = f.get("type")
        if ftype not in VALID_TYPES:
            errors.append(f"{loc}: type '{ftype}' not in {VALID_TYPES}")

        sev = f.get("severity")
        if sev not in VALID_SEVERITIES:
            errors.append(f"{loc}: severity '{sev}' not in {VALID_SEVERITIES} (no low/info allowed)")
        elif ftype == "defect":
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
        elif ftype == "opportunity":
            if sev != "medium":
                errors.append(f"{loc}: opportunity severity must be 'medium', got '{sev}'")
            opportunity_count += 1

        if not f.get("evidence", "").strip():
            errors.append(f"{loc}: evidence is empty")

        sa = f.get("suggested_action", {})
        if not isinstance(sa, dict) or not sa.get("summary", "").strip():
            errors.append(f"{loc}: suggested_action.summary missing/empty")
        if sa.get("priority") not in VALID_PRIORITIES:
            errors.append(f"{loc}: suggested_action.priority '{sa.get('priority')}' invalid")

    expected_ids = [f"F-{i+1:03d}" for i in range(len(findings))]
    if seen_ids != expected_ids:
        errors.append(f"IDs not sequential from F-001: got {seen_ids}, expected {expected_ids}")

    if summary.get("critical") != sev_counts["critical"]:
        errors.append(f"summary.critical ({summary.get('critical')}) != actual critical defects ({sev_counts['critical']})")
    if summary.get("high") != sev_counts["high"]:
        errors.append(f"summary.high ({summary.get('high')}) != actual high defects ({sev_counts['high']})")
    if summary.get("medium") != sev_counts["medium"]:
        errors.append(f"summary.medium ({summary.get('medium')}) != actual medium defects ({sev_counts['medium']})")
    if summary.get("opportunities", 0) != opportunity_count:
        errors.append(f"summary.opportunities ({summary.get('opportunities')}) != actual opportunities ({opportunity_count})")

    return errors

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: validate_report.py <report.json>")
        sys.exit(2)
    errs = validate(sys.argv[1])
    if errs:
        print(f"FAIL — {len(errs)} issue(s):")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    print("PASS — schema valid")
    sys.exit(0)
