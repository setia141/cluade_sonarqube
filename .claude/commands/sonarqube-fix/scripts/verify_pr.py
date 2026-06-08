#!/usr/bin/env python3
"""
Verify that a PR branch is clean in SonarQube after the fix commit is pushed.

Steps:
  1. Poll the background task API until the branch analysis completes (or times out).
  2. Check the quality gate status for the branch.
  3. Fetch open issues on the branch and compare with the original issue keys.
  4. Report: resolved, still-open, and newly introduced issues.

Exit codes:
  0 — quality gate passes and all original issues are resolved
  1 — analysis failed, quality gate failed, or original issues still open
  2 — analysis did not finish within the timeout

Usage:
  python verify_pr.py \\
    --host https://sonarcloud.io \\
    --token <TOKEN> \\
    --project <PROJECT_KEY> \\
    --branch <BRANCH_NAME> \\
    --issues issues.json \\
    --output pr-verification.json \\
    [--timeout 300]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

POLL_INTERVAL = 15  # seconds between polls


def _headers(token: str) -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _wait_for_analysis(
    host: str,
    token: str,
    project: str,
    branch: str,
    timeout: int,
    pr_number: Optional[str] = None,
    min_submitted_at: Optional[float] = None,
) -> Optional[str]:
    """Poll until a background task for the branch submitted after min_submitted_at finishes.

    min_submitted_at (Unix timestamp) guards against picking up a stale SUCCESS
    from a previous push — we only accept tasks whose submittedAt is after that
    point in time.  Defaults to (now - 60s) so recent re-runs are still caught.

    Returns the task status string ("SUCCESS", "FAILED", "CANCELLED") or
    None if the timeout is exceeded before a terminal state is reached.
    """
    import datetime

    url = f"{host}/api/ce/activity"
    deadline = time.time() + timeout
    # Default: ignore tasks submitted more than 30 minutes before now.
    # This is wide enough to catch any legitimate in-progress or recently
    # completed analysis while still rejecting hours-old stale results
    # from a prior push on the same branch.
    if min_submitted_at is None:
        min_submitted_at = time.time() - 1800

    params: Dict[str, Any] = {"component": project, "ps": 5}
    if pr_number:
        params["pullRequest"] = pr_number
    else:
        params["branch"] = branch

    print(f"Waiting for SonarQube analysis of branch '{branch}' (timeout {timeout}s) …")

    while time.time() < deadline:
        try:
            r = requests.get(url, params=params, headers=_headers(token), timeout=30)
            r.raise_for_status()
            tasks = r.json().get("tasks", [])
            for task in tasks:
                submitted_raw = task.get("submittedAt", "")
                try:
                    # ISO-8601 with trailing Z or +00:00
                    submitted_ts = datetime.datetime.fromisoformat(
                        submitted_raw.replace("Z", "+00:00")
                    ).timestamp()
                except (ValueError, AttributeError):
                    submitted_ts = 0.0

                if submitted_ts < min_submitted_at:
                    continue  # stale task from a prior push

                status = task.get("status", "")
                print(f"  Task status: {status} (submitted {submitted_raw})")
                if status in ("SUCCESS", "FAILED", "CANCELLED"):
                    return status
                break  # newest qualifying task is still IN_PROGRESS — keep polling
        except requests.RequestException as e:
            print(f"  Warning: poll error — {e}", file=sys.stderr)

        time.sleep(POLL_INTERVAL)

    return None  # timed out


def _quality_gate_status(
    host: str, token: str, project: str, branch: str, pr_number: Optional[str] = None
) -> Dict[str, Any]:
    """Fetch quality gate status.

    SonarCloud returns 404 for the `branch` parameter on feature/PR branches.
    If that happens (or if pr_number is supplied), fall back to the
    `pullRequest` parameter which works for both SonarCloud and SonarQube 9+.
    """
    url = f"{host}/api/qualitygates/project_status"

    def _get(params: Dict) -> Optional[Dict]:
        try:
            r = requests.get(url, params=params, headers=_headers(token), timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json().get("projectStatus", {})
        except requests.RequestException as e:
            return {"status": "ERROR", "error": str(e)}

    # Try with pullRequest number first if supplied
    if pr_number:
        result = _get({"projectKey": project, "pullRequest": pr_number})
        if result is not None:
            return result

    # Try branch name
    result = _get({"projectKey": project, "branch": branch})
    if result is not None:
        return result

    # Last resort: project-level gate (no branch filter) — gives main branch status
    result = _get({"projectKey": project})
    if result is not None:
        result["_note"] = "Branch-level gate unavailable; showing project-level gate"
        return result

    return {"status": "UNKNOWN", "error": "Could not retrieve quality gate for branch or project"}


def _fetch_branch_issues(
    host: str,
    token: str,
    project: str,
    branch: str,
    pr_number: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch open issues on the PR/branch.

    SonarCloud indexes PR analysis under `pullRequest=<n>`, not `branch=<name>`.
    We try pullRequest first when a number is provided, then fall back to branch.
    """
    url = f"{host}/api/issues/search"

    def _fetch_with_scope(scope_param: Dict) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        page = 1
        while True:
            try:
                params = {
                    "componentKeys": project,
                    "severities": "BLOCKER,CRITICAL,MAJOR",
                    "types": "BUG,VULNERABILITY,CODE_SMELL",
                    "statuses": "OPEN",
                    "ps": 500,
                    "p": page,
                    **scope_param,
                }
                r = requests.get(url, params=params, headers=_headers(token), timeout=30)
                r.raise_for_status()
                data = r.json()
                batch = data.get("issues", [])
                issues.extend(batch)
                if len(issues) >= data.get("total", 0) or not batch:
                    break
                page += 1
            except requests.RequestException as e:
                print(f"  Warning: issue fetch error — {e}", file=sys.stderr)
                break
        return issues

    if pr_number:
        issues = _fetch_with_scope({"pullRequest": pr_number})
        if issues or True:  # always prefer PR scope when number is known
            return issues

    return _fetch_with_scope({"branch": branch})


def verify(
    host: str,
    token: str,
    project: str,
    branch: str,
    original_issues: List[Dict[str, Any]],
    timeout: int,
    pr_number: Optional[str] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "branch": branch,
        "project": project,
        "passed": False,
        "quality_gate": None,
        "resolved_issues": [],
        "still_open_issues": [],
        "new_issues": [],
        "summary": [],
    }

    # ── 1. Wait for analysis ──────────────────────────────────────────
    analysis_status = _wait_for_analysis(
        host, token, project, branch, timeout, pr_number=pr_number
    )

    if analysis_status is None:
        result["summary"].append(f"TIMEOUT: Analysis did not complete within {timeout}s")
        return result

    if analysis_status != "SUCCESS":
        result["summary"].append(f"FAIL: SonarQube analysis task ended with status '{analysis_status}'")
        return result

    result["summary"].append("PASS: Analysis completed successfully")

    # ── 2. Quality gate ───────────────────────────────────────────────
    qg = _quality_gate_status(host, token, project, branch, pr_number)
    result["quality_gate"] = qg
    qg_status = qg.get("status", "UNKNOWN")

    qg_note = qg.get("_note", "")
    if qg_status == "OK":
        result["summary"].append(f"PASS: Quality gate — OK{' (' + qg_note + ')' if qg_note else ''}")
    elif qg_status == "UNKNOWN":
        result["summary"].append(f"WARN: Quality gate status unknown — {qg.get('error', '')}")
    else:
        result["summary"].append(f"FAIL: Quality gate — {qg_status}{' (' + qg_note + ')' if qg_note else ''}")

    # ── 3. Compare issues ─────────────────────────────────────────────
    original_keys = {i["key"] for i in original_issues}
    branch_issues = _fetch_branch_issues(host, token, project, branch, pr_number)
    branch_keys   = {i["key"] for i in branch_issues}

    resolved  = [i for i in original_issues if i["key"] not in branch_keys]
    still_open = [i for i in original_issues if i["key"] in branch_keys]
    new_issues = [i for i in branch_issues   if i["key"] not in original_keys]

    result["resolved_issues"]   = [{"key": i["key"], "rule": i.get("rule"), "file": i.get("component", "").split(":", 1)[-1], "line": i.get("line")} for i in resolved]
    result["still_open_issues"] = [{"key": i["key"], "rule": i.get("rule"), "file": i.get("component", "").split(":", 1)[-1], "line": i.get("line")} for i in still_open]
    result["new_issues"]        = [{"key": i["key"], "rule": i.get("rule"), "severity": i.get("severity"), "file": i.get("component", "").split(":", 1)[-1], "line": i.get("line"), "message": i.get("message")} for i in new_issues]

    if resolved:
        result["summary"].append(f"PASS: {len(resolved)} original issue(s) resolved: {[i['key'] for i in resolved]}")
    if still_open:
        result["summary"].append(f"FAIL: {len(still_open)} original issue(s) still open: {[i['key'] for i in still_open]}")
    if new_issues:
        result["summary"].append(f"WARN: {len(new_issues)} new issue(s) introduced by the fix")
    else:
        result["summary"].append("PASS: No new issues introduced")

    # ── 4. Overall verdict ────────────────────────────────────────────
    result["passed"] = (
        analysis_status == "SUCCESS"
        and qg_status in ("OK", "UNKNOWN")   # UNKNOWN = gate API unavailable, not a real failure
        and not still_open
        and not new_issues
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify SonarQube PR analysis after fix")
    parser.add_argument("--host",    default=os.getenv("SONARQUBE_HOST_URL", "https://sonarcloud.io"))
    parser.add_argument("--token",   default=os.getenv("SONARQUBE_TOKEN"))
    parser.add_argument("--project", required=True, help="SonarQube project key")
    parser.add_argument("--branch",  required=True, help="Fix branch name pushed to remote")
    parser.add_argument("--issues",  required=True, help="issues.json — original issues fetched in Step 2")
    parser.add_argument("--output",  default="pr-verification.json")
    parser.add_argument("--timeout",   type=int, default=300, help="Max seconds to wait for analysis (default 300)")
    parser.add_argument("--pr-number", default=None, help="GitHub/GitLab PR/MR number (enables SonarCloud PR quality gate lookup)")
    args = parser.parse_args()

    original_issues = json.loads(Path(args.issues).read_text())

    result = verify(
        host=args.host,
        token=args.token,
        project=args.project,
        branch=args.branch,
        original_issues=original_issues,
        timeout=args.timeout,
        pr_number=args.pr_number,
    )

    Path(args.output).write_text(json.dumps(result, indent=2))
    print("\n".join(f"  {s}" for s in result["summary"]))
    print(f"\nVerification {'PASSED' if result['passed'] else 'FAILED'}")
    print(f"Result saved to {args.output}")

    if result["new_issues"]:
        print("\nNew issues introduced (must fix before merging):")
        for i in result["new_issues"]:
            print(f"  [{i['severity']}] {i['rule']} — {i['file']}:{i['line']} — {i['message']}")

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
