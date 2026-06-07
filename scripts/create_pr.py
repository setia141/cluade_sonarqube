#!/usr/bin/env python3
"""
Create a GitHub PR with SonarQube fixes.
Usage: python3 create_pr.py --fixes fixes.json --validation validation.json --repo owner/repo
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List


CONFIDENCE_LABELS = {
    "HIGH":         ("auto-fix",           False),   # (label, is_draft)
    "MEDIUM":       ("needs-review",       True),
    "LOW":          ("regression-risk",    True),
    "NEEDS_HUMAN":  ("manual-review",      True),
}


def create_pr(
    fixes: List[Dict[str, Any]],
    validation: Dict[str, Any],
    repo: str,
    base_branch: str = "main",
    dry_run: bool = False,
) -> Dict[str, Any]:
    timestamp  = datetime.now().strftime("%Y%m%d-%H%M%S")
    confidence = validation.get("confidence", "MEDIUM")
    branch     = f"sonarqube/fixes-{timestamp}"

    print(f"Creating fix branch: {branch}")

    if not dry_run:
        _run_git(f"git checkout -b {branch}")
        _run_git(f"git add -A")

        commit_msg = _build_commit_message(fixes, validation)
        _run_git(f'git commit -m "{commit_msg}"')
        _run_git(f"git push origin {branch}")

    pr_title = _build_pr_title(fixes, confidence)
    pr_body  = _build_pr_body(fixes, validation, confidence)

    label, is_draft = CONFIDENCE_LABELS.get(confidence, ("needs-review", True))

    if dry_run:
        print("=== DRY RUN - PR would be created with ===")
        print(f"Title: {pr_title}")
        print(f"Branch: {branch}")
        print(f"Draft: {is_draft}")
        print(f"Label: {label}")
        print("\nBody preview:")
        print(pr_body[:1000])
        return {"dryRun": True, "branch": branch, "title": pr_title}

    cmd_parts = [
        "gh pr create",
        f"--title \"{pr_title}\"",
        f"--base {base_branch}",
        f"--head {branch}",
        f"--body \"{_escape(pr_body)}\"",
    ]
    if is_draft:
        cmd_parts.append("--draft")
    if label:
        cmd_parts.append(f"--label \"{label}\"")

    result = subprocess.run(" ".join(cmd_parts), shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"PR creation failed: {result.stderr}", file=sys.stderr)
        return {"success": False, "error": result.stderr, "branch": branch}

    pr_url = result.stdout.strip()
    print(f"Created PR: {pr_url}")
    return {"success": True, "prUrl": pr_url, "branch": branch, "confidence": confidence}


def _build_commit_message(fixes: List[Dict], validation: Dict) -> str:
    issue_count = len(fixes)
    rules = list({f.get("rule", "unknown") for f in fixes})[:3]
    rules_str = ", ".join(rules)
    confidence = validation.get("confidence", "MEDIUM")
    return (f"fix: resolve {issue_count} SonarQube issue(s) "
            f"[{rules_str}] — validation confidence: {confidence}")


def _build_pr_title(fixes: List[Dict], confidence: str) -> str:
    count   = len(fixes)
    severities = list({f.get("severity", "") for f in fixes if f.get("severity")})
    sev_str = "/".join(sorted(severities, key=lambda s: ["BLOCKER","CRITICAL","MAJOR"].index(s)
                               if s in ["BLOCKER","CRITICAL","MAJOR"] else 99))
    label = {"HIGH": "✅", "MEDIUM": "⚠️", "LOW": "🔴"}.get(confidence, "⚠️")
    return f"{label} Fix {count} SonarQube {sev_str} issue(s)"


def _build_pr_body(fixes: List[Dict], validation: Dict, confidence: str) -> str:
    layers  = validation.get("layers", {})
    summary = validation.get("summary", [])
    language= validation.get("language", "unknown")

    issues_table = "\n".join(
        f"| {f.get('rule','N/A')} | {f.get('file','N/A')}:{f.get('line','?')} "
        f"| {f.get('severity','?')} | {f.get('fixStrategy','see code')} |"
        for f in fixes
    )

    validation_rows = "\n".join(
        f"| {name.replace('_',' ').title()} | {'✅ Pass' if info.get('passed') else '❌ Fail'} "
        f"| {info.get('elapsed_sec','?')}s |"
        for name, info in layers.items()
        if isinstance(info, dict)
    )

    summary_block = "\n".join(f"- {s}" for s in summary)

    confidence_note = {
        "HIGH":        "All validation layers passed. Safe to merge after review.",
        "MEDIUM":      "Most layers passed. Marked as draft — please review the flagged items.",
        "LOW":         "Regression risk detected. Do NOT merge without thorough review.",
        "NEEDS_HUMAN": "Agent could not determine safety. Manual review required.",
    }.get(confidence, "Review required.")

    checklist_items = [
        "- [ ] Review each changed file for correctness",
        "- [ ] Run full test suite locally (`mvn test` / `pytest` / `dotnet test` / `npm test`)",
        "- [ ] Verify SonarQube Quality Gate passes",
        "- [ ] Check downstream service interactions are unchanged",
    ]
    if confidence in ("LOW", "NEEDS_HUMAN"):
        checklist_items.insert(0, "- [ ] ⚠️ High-risk change — pair review recommended")

    return f"""## SonarQube Auto-Fix — {confidence} Confidence

> {confidence_note}

### Issues Fixed ({len(fixes)})

| Rule | Location | Severity | Fix Applied |
|---|---|---|---|
{issues_table}

### Validation Report — {language}

| Layer | Result | Time |
|---|---|---|
{validation_rows}

**Validation summary:**
{summary_block}

### Reviewer Checklist

{chr(10).join(checklist_items)}

---
*Generated by SonarQube Fixer Agent — [SKILL.md](../SKILL.md)*
"""


def _escape(text: str) -> str:
    return text.replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')


def _run_git(cmd: str) -> None:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Git command failed: {cmd}\n{result.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Create GitHub PR with SonarQube fixes")
    parser.add_argument("--fixes",      required=True, help="fixes.json — list of applied fixes")
    parser.add_argument("--validation", required=True, help="validation_result.json")
    parser.add_argument("--repo",       default=os.getenv("GITHUB_REPOSITORY"), help="owner/repo")
    parser.add_argument("--base",       default="main", help="Base branch (default: main)")
    parser.add_argument("--dry-run",    action="store_true", help="Print PR details without creating")
    args = parser.parse_args()

    fixes      = json.loads(Path(args.fixes).read_text())
    validation = json.loads(Path(args.validation).read_text())

    result = create_pr(
        fixes=fixes,
        validation=validation,
        repo=args.repo,
        base_branch=args.base,
        dry_run=args.dry_run,
    )

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("success") or result.get("dryRun") else 1)


if __name__ == "__main__":
    main()
