#!/usr/bin/env python3
"""
Enrich SonarQube issues with rule details from the Rules API.

Fetches name, description, severity, and type for every rule referenced in
issues.json and attaches them directly to each issue object. Claude Code
reads the enriched output and decides what to fix and how.

SonarCloud requires an --organization parameter for the rules API.
Self-hosted SonarQube does not need it.

Usage:
  # SonarCloud
  python analyze_issue.py --issues issues.json --output enriched.json \
    --host https://sonarcloud.io --token $TOKEN --organization my-org

  # Self-hosted SonarQube
  python analyze_issue.py --issues issues.json --output enriched.json \
    --host http://sonarqube.internal:9000 --token $TOKEN
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
    organization: Optional[str],
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
    failed_rules: List[str] = []

    for issue in issues:
        rule_key = issue.get("rule", "")
        if not rule_key:
            continue

        if rule_key not in rule_cache:
            result = _fetch_rule(session, host, rule_key, organization)
            rule_cache[rule_key] = result
            if not result:
                failed_rules.append(rule_key)

        issue["ruleDetails"] = rule_cache[rule_key]

    print(f"Enriched {len(issues)} issue(s) across {len(rule_cache)} rule(s)")

    if failed_rules:
        print(
            f"\nWARNING: Could not fetch rule details for: {', '.join(failed_rules)}",
            file=sys.stderr,
        )
        print(
            "These issues will have ruleDetails: {} in enriched.json.\n"
            "The agent MUST NOT proceed with fixing these issues until rule details\n"
            "are available. Check:\n"
            "  1. Is --organization set correctly for SonarCloud?\n"
            "  2. Is the rule key correct?\n"
            "  3. Does the token have rules:read permission?",
            file=sys.stderr,
        )
        sys.exit(1)

    return issues


def _fetch_rule(
    session: requests.Session,
    host: str,
    rule_key: str,
    organization: Optional[str],
) -> Dict[str, Any]:
    params: Dict[str, str] = {"key": rule_key}
    if organization:
        params["organization"] = organization

    try:
        resp = session.get(
            f"{host}/api/rules/show",
            params=params,
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
        print(f"  Error fetching rule {rule_key}: {exc}", file=sys.stderr)
        return {}


def _derive_organization(host: str, project_key: Optional[str]) -> Optional[str]:
    """
    SonarCloud project keys are typically formatted as 'org_project' or 'org:project'.
    Attempt to derive the organization from the project key as a fallback.
    Only applies to sonarcloud.io — self-hosted instances don't need organization.
    """
    if "sonarcloud.io" not in host:
        return None
    if not project_key:
        return None
    # Try splitting on underscore first (most common SonarCloud format)
    if "_" in project_key:
        return project_key.split("_")[0]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich SonarQube issues with rule details"
    )
    parser.add_argument("--issues",       required=True, help="issues.json from fetch_issues.py")
    parser.add_argument("--output",       default="enriched.json")
    parser.add_argument("--host",         default=os.getenv("SONARQUBE_HOST_URL", "https://sonarcloud.io"))
    parser.add_argument("--token",        default=os.getenv("SONARQUBE_TOKEN"))
    parser.add_argument("--organization", default=os.getenv("SONARQUBE_ORGANIZATION"),
                        help="SonarCloud organization key (required for sonarcloud.io, "
                             "not needed for self-hosted). If omitted, derived from project key.")
    parser.add_argument("--project",      default=os.getenv("SONARQUBE_PROJECT_KEY"),
                        help="Project key — used to derive organization if --organization is omitted")
    args = parser.parse_args()

    issues = json.loads(Path(args.issues).read_text())
    if not isinstance(issues, list):
        issues = issues.get("issues", [])

    # Derive organization from project key if not explicitly provided
    organization = args.organization
    if not organization:
        organization = _derive_organization(args.host, args.project)
        if organization:
            print(f"Derived organization '{organization}' from project key")

    enriched = enrich_issues(issues, args.host, args.token, organization)

    Path(args.output).write_text(json.dumps(enriched, indent=2), encoding="utf-8")
    print(f"Saved {len(enriched)} enriched issue(s) to {args.output}")


if __name__ == "__main__":
    main()
