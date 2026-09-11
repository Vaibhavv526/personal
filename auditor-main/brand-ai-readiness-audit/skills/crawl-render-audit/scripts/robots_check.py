#!/usr/bin/env python3
"""
robots_check.py — Fetch and evaluate robots.txt for a target URL.

Usage:
    python robots_check.py <target_url>

Output: JSON to stdout. Exit 0 always (errors captured in output).
"""

import sys
import json
import re
import urllib.request
import urllib.error
import urllib.parse
from typing import Any

# Content-Type variants considered plain text
PLAIN_TEXT_MIMES = {
    "text/plain",
    "text/text",
    "text/x-plain",
    "text/x-text",
    "application/text",
    "application/plain",
}

# Regex pattern for recognized robots.txt directives
ROBOTS_DIRECTIVE_RE = re.compile(
    r"^\s*(user-agent|disallow|allow|sitemap|crawl-delay)\s*:",
    re.IGNORECASE,
)

# AI-specific and major crawl bots to check beyond the wildcard
TRACKED_AGENTS = [
    "*",
    "GPTBot",
    "Google-Extended",
    "anthropic-ai",
    "CCBot",
    "PerplexityBot",
    "Applebot-Extended",
    "Googlebot",
    "Bingbot",
]


def fetch_robots(robots_url: str, timeout: int = 10) -> dict[str, Any]:
    """Fetch robots.txt and return status + body + content_type."""
    try:
        req = urllib.request.Request(
            robots_url,
            headers={"User-Agent": "BrandAIReadinessAudit/1.0 (+https://github.com/brand-ai-readiness-audit)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "status": resp.status, "content_type": content_type, "body": body, "error": None}
    except urllib.error.HTTPError as exc:
        content_type = exc.headers.get("Content-Type", "") if exc.headers else None
        return {"ok": False, "status": exc.code, "content_type": content_type, "body": None, "error": str(exc)}
    except urllib.error.URLError as exc:
        return {"ok": False, "status": None, "content_type": None, "body": None, "error": str(exc.reason)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "content_type": None, "body": None, "error": str(exc)}


def parse_robots(body: str) -> dict[str, Any]:
    """
    Parse robots.txt into groups and sitemap directives.

    Returns:
        {
            "groups": {
                "User-agent value": {
                    "disallow": [paths],
                    "allow": [paths],
                    "crawl_delay": float | None,
                }
            },
            "sitemaps": [urls],
            "raw_line_count": int,
        }
    """
    groups: dict[str, dict[str, Any]] = {}
    sitemaps: list[str] = []
    current_agents: list[str] = []
    pending_rules: dict[str, Any] = {"disallow": [], "allow": [], "crawl_delay": None}

    def flush() -> None:
        for agent in current_agents:
            key = agent.strip()
            if key not in groups:
                groups[key] = {"disallow": [], "allow": [], "crawl_delay": None}
            groups[key]["disallow"].extend(pending_rules["disallow"])
            groups[key]["allow"].extend(pending_rules["allow"])
            if pending_rules["crawl_delay"] is not None:
                groups[key]["crawl_delay"] = pending_rules["crawl_delay"]

    lines = body.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if current_agents:
                flush()
                current_agents = []
                pending_rules = {"disallow": [], "allow": [], "crawl_delay": None}
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if pending_rules["disallow"] or pending_rules["allow"]:
                flush()
                current_agents = []
                pending_rules = {"disallow": [], "allow": [], "crawl_delay": None}
            current_agents.append(value)
        elif key == "disallow":
            pending_rules["disallow"].append(value)
        elif key == "allow":
            pending_rules["allow"].append(value)
        elif key == "crawl-delay":
            try:
                pending_rules["crawl_delay"] = float(value)
            except ValueError:
                pass
        elif key == "sitemap":
            sitemaps.append(value)

    if current_agents:
        flush()

    return {"groups": groups, "sitemaps": sitemaps, "raw_line_count": len(lines)}


def _path_matches(rule: str, path: str) -> bool:
    """
    Evaluate a single robots.txt Allow/Disallow rule against a path.
    Supports '*' wildcard and '$' end anchor per RFC standard.
    """
    if not rule:
        return False  # empty rule matches nothing meaningful
    anchored = rule.endswith("$")
    pattern = rule.rstrip("$")
    segments = pattern.split("*")
    pos = 0
    for i, seg in enumerate(segments):
        idx = path.find(seg, pos)
        if idx == -1:
            return False
        pos = idx + len(seg)
    if anchored:
        return pos == len(path)
    return True


def _longest_match_result(rules_allow: list[str], rules_disallow: list[str], path: str) -> str:
    """
    Return 'allow', 'disallow', or 'none' per longest-match wins spec.
    """
    best_len = -1
    best_result = "none"
    for rule in rules_allow:
        if _path_matches(rule, path):
            rl = len(rule.rstrip("$"))
            if rl > best_len:
                best_len = rl
                best_result = "allow"
    for rule in rules_disallow:
        if _path_matches(rule, path):
            rl = len(rule.rstrip("$"))
            if rl > best_len:
                best_len = rl
                best_result = "disallow"
    return best_result


def evaluate_path(parsed: dict[str, Any], target_path: str) -> dict[str, Any]:
    """
    Evaluate target_path against every tracked User-agent group.

    Returns a dict of {agent: {"result": "allow"|"disallow"|"none", "matched_rule": str|None}}
    """
    evaluation: dict[str, dict[str, Any]] = {}
    groups: dict[str, dict[str, Any]] = parsed["groups"]

    for agent in TRACKED_AGENTS:
        # Find exact match or fall back to wildcard
        candidates = [agent] if agent in groups else (["*"] if "*" in groups else [])
        if not candidates:
            evaluation[agent] = {"result": "none", "matched_rule": None, "note": "agent not in robots.txt"}
            continue

        group_key = candidates[0]
        g = groups[group_key]
        result = _longest_match_result(g["allow"], g["disallow"], target_path)

        # Find the winning rule string for evidence
        best_len = -1
        matched_rule = None
        matched_type = None
        for rule in g["allow"]:
            if _path_matches(rule, target_path) and len(rule.rstrip("$")) > best_len:
                best_len = len(rule.rstrip("$"))
                matched_rule = rule
                matched_type = "Allow"
        for rule in g["disallow"]:
            if _path_matches(rule, target_path) and len(rule.rstrip("$")) > best_len:
                best_len = len(rule.rstrip("$"))
                matched_rule = rule
                matched_type = "Disallow"

        evaluation[agent] = {
            "result": result,
            "matched_rule": f"{matched_type}: {matched_rule}" if matched_rule else None,
            "resolved_from_group": group_key,
        }

    return evaluation


def validate_robots_txt(
    body: str | None,
    content_type: str | None,
    status: int | None,
) -> tuple[bool, str | None]:
    """
    Validate whether the fetched response looks like a genuine robots.txt file.

    Returns (looks_like_valid, reason_if_invalid).
    """
    if status != 200 or body is None:
        return False, f"HTTP status is {status}, not 200"

    # 1. Content-Type must be text/plain or close to it
    raw_ct = (content_type or "").split(";")[0].strip().lower()
    if raw_ct not in PLAIN_TEXT_MIMES:
        return False, f"Content-Type '{content_type}' is not text/plain"

    # 2. Body must not contain HTML tags in the first 200 characters
    first_200 = body[:200].lower()
    if "<html" in first_200 or "<!doctype" in first_200:
        return False, "Response body contains HTML tag/doctype in the first 200 characters"

    # 3. Directives check: must have at least one valid directive if body is non-trivial
    non_comment_lines = [
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if non_comment_lines:
        directive_matches = [
            line for line in non_comment_lines
            if ROBOTS_DIRECTIVE_RE.match(line)
        ]
        if not directive_matches:
            return False, "Zero lines matched robots.txt directive pattern despite non-trivial body"

    return True, None


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: robots_check.py <target_url>"}))
        sys.exit(1)

    target_url = sys.argv[1].strip()
    parsed_url = urllib.parse.urlparse(target_url)
    origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
    robots_url = f"{origin}/robots.txt"
    target_path = parsed_url.path or "/"

    fetch_result = fetch_robots(robots_url)
    content_type = fetch_result.get("content_type")
    status = fetch_result.get("status")
    body = fetch_result.get("body")

    looks_like_valid, invalid_reason = validate_robots_txt(body, content_type, status)

    output: dict[str, Any] = {
        "target_url": target_url,
        "robots_url": robots_url,
        "target_path": target_path,
        "content_type": content_type,
        "looks_like_valid_robots_txt": looks_like_valid,
        "fetch": {
            "ok": fetch_result["ok"],
            "status": status,
            "content_type": content_type,
            "error": fetch_result["error"],
        },
        "parsed": None,
        "evaluation": None,
        "sitemaps": [],
        "sitewide_disallow": False,
    }

    if not fetch_result["ok"] or body is None:
        print(json.dumps(output, indent=2))
        return

    if not looks_like_valid:
        output["invalid_reason"] = invalid_reason
        output["body_excerpt"] = body[:200].strip()
        print(json.dumps(output, indent=2))
        return

    parsed = parse_robots(body)
    output["parsed"] = {
        "agent_groups_found": list(parsed["groups"].keys()),
        "sitemap_count": len(parsed["sitemaps"]),
        "raw_line_count": parsed["raw_line_count"],
    }
    output["sitemaps"] = parsed["sitemaps"]

    # Check for sitewide disallow
    wildcard = parsed["groups"].get("*", {})
    if "/" in wildcard.get("disallow", []) and "/" not in wildcard.get("allow", []):
        output["sitewide_disallow"] = True

    output["evaluation"] = evaluate_path(parsed, target_path)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
