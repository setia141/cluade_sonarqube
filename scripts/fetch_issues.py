#!/usr/bin/env python3
"""
Fetch critical/blocker SonarQube issues via API
Usage: python3 fetch_issues.py --host https://sonarcloud.io --token $TOKEN --project owner_repo
"""

import argparse
import json
import os
import sys
import requests
from typing import List, Dict, Any


def fetch_issues(
    host: str,
    project_key: str,
    severities: List[str] = None,
    issue_types: List[str] = None,
    page_size: int = 500,
    token: str = None,
) -> Dict[str, Any]:
    """
    Fetch issues from SonarQube API
    
    Args:
        host: SonarQube host URL
        project_key: Project key
        severities: List of severities (BLOCKER, CRITICAL, MAJOR, MINOR, INFO)
        issue_types: List of types (BUG, VULNERABILITY, CODE_SMELL)
        page_size: Results per page (max 500)
        token: API token (optional - only needed for external/cloud access)
    
    Returns:
        Dict with issues and metadata
    """
    
    if not severities:
        severities = ["BLOCKER", "CRITICAL"]
    if not issue_types:
        issue_types = ["BUG", "VULNERABILITY"]
    
    url = f"{host}/api/issues/search"
    headers = {"Content-Type": "application/json"}
    
    # Add token only if provided (for cloud or external access)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    params = {
        "componentKeys": project_key,
        "severities": ",".join(severities),
        "types": ",".join(issue_types),
        "statuses": "OPEN",
        "ps": page_size,
    }
    
    try:
        print(f"Fetching issues from {host} for project {project_key}...")
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        issues = data.get("issues", [])
        total = data.get("total", 0)
        
        print(f"OK: Found {total} critical/blocker issues")
        
        return {
            "success": True,
            "total": total,
            "issues": issues,
            "components": data.get("components", []),
            "rules": data.get("rules", []),
        }
        
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Error fetching issues: {e}", file=sys.stderr)
        return {
            "success": False,
            "error": str(e),
            "issues": []
        }


def get_rule_details(host: str, token: str, rule_key: str) -> Dict[str, Any]:
    """
    Get details about a specific rule
    """
    url = f"{host}/api/rules/show"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    params = {"key": rule_key}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json().get("rule", {})
    except requests.exceptions.RequestException as e:
        print(f"Warning: Could not fetch rule details for {rule_key}: {e}", file=sys.stderr)
        return {}


def get_source_code(
    host: str,
    token: str,
    component_key: str,
    from_line: int = None,
    to_line: int = None,
) -> str:
    """
    Get source code from SonarQube
    """
    url = f"{host}/api/sources/show"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    params = {"key": component_key}
    if from_line:
        params["from"] = from_line
    if to_line:
        params["to"] = to_line
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        sources = response.json().get("sources", [])
        # API returns [[lineNum, "code"], ...] arrays
        return "\n".join(s[1] for s in sources if len(s) >= 2)
        
    except requests.exceptions.RequestException as e:
        print(f"Warning: Could not fetch source code: {e}", file=sys.stderr)
        return ""


def enrich_issues_with_details(
    issues: List[Dict[str, Any]],
    host: str,
    token: str,
) -> List[Dict[str, Any]]:
    """
    Add rule details and source code snippets to issues
    """
    enriched = []
    
    for issue in issues:
        rule_key = issue.get("rule", "")
        component_key = issue.get("component", "")
        line_num = issue.get("line", 1)
        
        # Get context: 5 lines before and after
        from_line = max(1, line_num - 5)
        to_line = line_num + 5
        
        source_code = get_source_code(host, token, component_key, from_line, to_line)
        rule_details = get_rule_details(host, token, rule_key)
        
        issue["ruleDetails"] = rule_details
        issue["sourceCodeContext"] = {
            "fromLine": from_line,
            "toLine": to_line,
            "code": source_code
        }
        
        enriched.append(issue)
    
    return enriched


def main():
    parser = argparse.ArgumentParser(
        description="Fetch critical/blocker SonarQube issues"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("SONARQUBE_HOST_URL", "https://sonarcloud.io"),
        help="SonarQube host URL"
    )
    parser.add_argument(
        "--token",
        default=os.getenv("SONARQUBE_TOKEN"),
        help="SonarQube API token (optional - only needed for cloud/external access)"
    )
    parser.add_argument(
        "--project",
        default=os.getenv("SONARQUBE_PROJECT_KEY"),
        required=not os.getenv("SONARQUBE_PROJECT_KEY"),
        help="SonarQube project key"
    )
    parser.add_argument(
        "--severities",
        default="BLOCKER,CRITICAL",
        help="Comma-separated severities (BLOCKER, CRITICAL, MAJOR, MINOR, INFO)"
    )
    parser.add_argument(
        "--types",
        default="BUG,VULNERABILITY",
        help="Comma-separated issue types (BUG, VULNERABILITY, CODE_SMELL)"
    )
    parser.add_argument(
        "--output",
        default="issues.json",
        help="Output JSON file"
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Fetch additional details (rule info, source code)"
    )
    
    args = parser.parse_args()
    
    # Fetch issues
    result = fetch_issues(
        host=args.host,
        project_key=args.project,
        severities=args.severities.split(","),
        issue_types=args.types.split(","),
        token=args.token,  # Optional - only if provided
    )
    
    if not result["success"]:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)
    
    issues = result["issues"]
    
    # Optionally enrich with details
    if args.enrich:
        print("Fetching additional details...")
        issues = enrich_issues_with_details(issues, args.host, args.token)
    
    # Write output
    with open(args.output, "w") as f:
        json.dump(issues, f, indent=2)
    
    print(f"OK: Saved {len(issues)} issues to {args.output}")
    
    # Summary
    print("\n=== Summary ===")
    print(f"Total issues: {result['total']}")
    
    by_severity = {}
    by_type = {}
    by_rule = {}
    
    for issue in issues:
        sev = issue.get("severity", "UNKNOWN")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        
        issue_type = issue.get("type", "UNKNOWN")
        by_type[issue_type] = by_type.get(issue_type, 0) + 1
        
        rule = issue.get("rule", "UNKNOWN")
        by_rule[rule] = by_rule.get(rule, 0) + 1
    
    print("\nBy Severity:")
    for sev, count in sorted(by_severity.items()):
        print(f"  {sev}: {count}")
    
    print("\nBy Type:")
    for issue_type, count in sorted(by_type.items()):
        print(f"  {issue_type}: {count}")
    
    print("\nTop 5 Rules:")
    for rule, count in sorted(by_rule.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {rule}: {count}")


if __name__ == "__main__":
    main()
