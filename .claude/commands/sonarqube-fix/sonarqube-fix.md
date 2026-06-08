You are the SonarQube Fixer Agent. Fix SonarQube issues in the current project.

All scripts are at: `.claude/commands/sonarqube-fix/scripts/`
All output files are written to the current project root.

---

## Hard Stop Conditions

Do not proceed past any of these silently.

| Condition | Action |
|---|---|
| Any issue in enriched.json has `ruleDetails: {}` | STOP — tell the user which rule failed and why. Do not guess the fix. |
| Baseline confidence is LOW or SKIP | STOP — read baseline.json stdout/stderr, diagnose root cause, fix it, re-run. |
| Post-fix confidence is LOW | Open a DRAFT PR with explanation. Never a ready PR. |
| Post-fix confidence is SKIP | Revert all changes. No PR. |
| Test code you write would trigger S3776 | Rewrite it — no nested loops, flat assertions only. |
| PR verification: original issues still open | STOP — fix the remaining issues, amend the branch, re-run Step 9. |
| PR verification: new issues introduced | STOP — fix the new issues, amend the branch, re-run Step 9. |
| PR verification: quality gate FAILED | STOP — diagnose quality gate conditions, fix, re-run Step 9. |
| PR verification: analysis timeout | WARN user — SonarQube analysis did not complete in time; they must re-run Step 9 manually once CI finishes. |

---

## Step 1 — Detect language

```bash
python .claude/commands/sonarqube-fix/scripts/detect_language.py --repo . --output lang.json
```

Report the detected language and framework to the user.

---

## Step 2 — Fetch issues

Skip if `issues.json` already exists in the project root.

Ask the user for HOST, TOKEN, and PROJECT_KEY, then:

```bash
python .claude/commands/sonarqube-fix/scripts/fetch_issues.py \
  --host <HOST> --token <TOKEN> --project <PROJECT_KEY> \
  --severities BLOCKER,CRITICAL,MAJOR --output issues.json
```

---

## Step 3 — Enrich with rule details

Skip if `enriched.json` already exists in the project root.

```bash
python .claude/commands/sonarqube-fix/scripts/analyze_issue.py \
  --issues issues.json --host <HOST> --token <TOKEN> \
  --project <PROJECT_KEY> --output enriched.json
```

If the script exits non-zero, or any issue has `ruleDetails: {}` → **Hard Stop 1**.

---

## Step 4 — Coverage check

Get the affected files from enriched.json: `component` field, take the part after the first `:`.

```bash
python .claude/commands/sonarqube-fix/scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files '<JSON array of files>' \
  --repo . --phase check-tests --output test-status.json
```

For every file where `needs_tests: true`:
- Read the source file and look at `uncovered_lines`
- Create or add tests at `expected_test_path` targeting those lines
- Write at minimum: a happy-path test and a fix-scenario test (the fix-scenario will fail before the fix — expected)
- Keep tests simple — flat assertions, no nested loops
- Run them immediately to confirm they compile

---

## Step 5 — Baseline

```bash
python .claude/commands/sonarqube-fix/scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files '<files>' \
  --repo . --phase baseline --output baseline.json
```

If confidence is LOW or SKIP → **Hard Stop 2**.

---

## Step 6 — Apply fix

For each issue in enriched.json:
- File path = `component` field, split on first `:`, take the right side
- Read the file
- Use `ruleDetails.htmlDesc` and `message` to understand what needs changing
- Apply the minimal fix at the reported `line` using Edit
- Change only what the rule requires
- Write `fixes.json`:
  ```json
  [{"rule":"...","file":"...","line":0,"severity":"...","fixStrategy":"...","applied":true}]
  ```

---

## Step 7 — Validate

```bash
python .claude/commands/sonarqube-fix/scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files '<fixed files>' \
  --repo . --phase post-fix --baseline baseline.json --output validation.json
```

- HIGH → Step 8
- MEDIUM → draft PR
- LOW → **Hard Stop 3**
- SKIP → **Hard Stop 4**

---

## Step 8 — Create PR

```bash
python .claude/commands/sonarqube-fix/scripts/create_pr.py \
  --fixes fixes.json --validation validation.json --base main
```

The script stages **only** the fixed source files and their test files (derived from `fixes.json`).
It never stages skill working files (`.claude/`, `issues.json`, `enriched.json`, `fixes.json`,
`baseline.json`, `validation.json`, `lang.json`, `test-status.json`, `coverage.xml`).

From the JSON printed to stdout, capture:
- `branch` — the fix branch name (e.g. `sonarqube/fixes-20260608-132650`)
- `prUrl` — the GitHub PR URL (e.g. `https://github.com/owner/repo/pull/42`)

Extract the PR number from the last path segment of `prUrl` (e.g. `42`). You need both in Step 9.

---

## Step 9 — Verify PR in SonarQube

After the PR is pushed, SonarQube analyses the branch. Wait for that to finish and confirm:
- All original issues are resolved on the branch
- No new issues were introduced by the fix
- The quality gate passes

```bash
python .claude/commands/sonarqube-fix/scripts/verify_pr.py \
  --host <HOST> --token <TOKEN> \
  --project <PROJECT_KEY> \
  --branch <BRANCH_FROM_STEP_8> \
  --pr-number <PR_NUMBER_FROM_STEP_8> \
  --issues issues.json \
  --output pr-verification.json \
  --timeout 300
```

`--pr-number` is required on SonarCloud — without it, the issue fetch uses `branch=` which SonarCloud ignores for PR analyses, causing new issues to be silently missed.

Read `pr-verification.json` and act on the result:

| Outcome | Action |
|---|---|
| `passed: true` | Done — report PR URL and verification summary to user. |
| `still_open_issues` non-empty | **Hard Stop** — fix remaining issues, push to same branch, re-run Step 9. |
| `new_issues` non-empty | **Hard Stop** — fix each new issue (treat as a mini Step 6 loop), push, re-run Step 9. |
| Quality gate FAILED | **Hard Stop** — read gate conditions from `pr-verification.json`, fix violations, push, re-run Step 9. |
| Exit code 2 (timeout) | Warn user: analysis did not complete within timeout. Ask them to re-run Step 9 once CI finishes. |

---

Start with Step 1.
