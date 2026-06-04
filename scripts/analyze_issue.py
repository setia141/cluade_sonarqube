#!/usr/bin/env python3
"""
Enrich SonarQube issues with rule details from the Rules API.

Fetches name, description, severity, and type for every rule referenced in
issues.json and attaches them directly to each issue object.  Claude Code
reads the enriched output and decides what to fix and how.

Usage:
  python3 analyze_issue.py --issues issues.json --output enriched.json
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests


def enrich_issues(
    issues: List[Dict[str, Any]],
    host: str,
    token: Optional[str],
) -> List[Dict[str, Any]]:
    """
    For each unique rule key in the issue list, fetch rule details from
    GET /api/rules/show and attach them to every issue that references that rule.
    """
    session = requests.Session()
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    session.headers["Content-Type"] = "application/json"

    rule_cache: Dict[str, Dict] = {}

    for issue in issues:
        rule_key = issue.get("rule", "")
        if not rule_key:
            continue

        if rule_key not in rule_cache:
            rule_cache[rule_key] = _fetch_rule(session, host, rule_key)

        issue["ruleDetails"] = rule_cache[rule_key]

    print(f"Enriched {len(issues)} issue(s) across {len(rule_cache)} rule(s)")
    return issues


def _fetch_rule(session: requests.Session, host: str, rule_key: str) -> Dict[str, Any]:
    try:
        resp = session.get(
            f"{host}/api/rules/show",
            params={"key": rule_key},
            timeout=15,
        )
        resp.raise_for_status()
        rule = resp.json().get("rule", {})
        return {
            "name":     rule.get("name", ""),
            "htmlDesc": rule.get("htmlDesc", ""),
            "severity": rule.get("severity", ""),
            "type":     rule.get("type", ""),
            "tags":     rule.get("tags", []),
        }
    except requests.RequestException as exc:
        print(f"  Warning: could not fetch rule {rule_key}: {exc}", file=sys.stderr)
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich SonarQube issues with rule details"
    )
    parser.add_argument("--issues",  required=True, help="issues.json from fetch_issues.py")
    parser.add_argument("--output",  default="enriched.json")
    parser.add_argument("--host",    default=os.getenv("SONARQUBE_HOST_URL", "https://sonarcloud.io"))
    parser.add_argument("--token",   default=os.getenv("SONARQUBE_TOKEN"))
    args = parser.parse_args()

    issues = json.loads(Path(args.issues).read_text())
    if not isinstance(issues, list):
        # fetch_issues.py can return {"issues": [...]} or a plain list
        issues = issues.get("issues", [])

    enriched = enrich_issues(issues, args.host, args.token)

    Path(args.output).write_text(json.dumps(enriched, indent=2), encoding="utf-8")
    print(f"Saved {len(enriched)} enriched issue(s) to {args.output}")


if __name__ == "__main__":
    main()
