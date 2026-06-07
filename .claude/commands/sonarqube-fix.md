You are running the SonarQube Fixer Agent.

IMPORTANT: Update the two paths below to match where you cloned this repo before using this command.

Full pipeline details: `C:\Users\deepa\Desktop\cluade_sonarqube\SKILL.md`
Agent scripts: `C:\Users\deepa\Desktop\cluade_sonarqube\scripts\`

The current working directory is the project you are fixing.

---

## HARD STOP CONDITIONS — read these before starting

These are non-negotiable. Violating them has caused bad PRs in the past.

1. **Enrich returned empty ruleDetails `{}`** — STOP. Do not guess the fix from the message alone.
   - Check if the 400 error is an auth issue (wrong token) or the rule simply not being in the public API.
   - Try fetching the rule manually: `python C:\Users\deepa\Desktop\cluade_sonarqube\scripts\analyze_issue.py --issues issues.json --output enriched.json --host <HOST> --token <TOKEN>`
   - If it still fails, read the SonarQube documentation for that rule key before proceeding.
   - Tell the user what rule could not be enriched and why.

2. **Baseline confidence is LOW or SKIP** — STOP. Do not apply any fix yet.
   - Read `baseline.json` → `layers.unit_tests.stdout` and `stderr` in full.
   - Diagnose the root cause:
     - "collected 0 items" or "no tests ran" → wrong test path. Check actual test file locations.
     - "ModuleNotFoundError" / "cannot find symbol" → missing dependency or compile error.
     - Test file doesn't exist → go back and create it first.
   - Fix the root cause, re-run baseline. Only continue when baseline passes.

3. **Post-fix confidence is LOW** — open a DRAFT PR with a note explaining the failure. Never open a ready PR.

4. **Post-fix confidence is SKIP** — revert all changes. Do not open any PR.

5. **Test code you write must be simple** — no nested loops, no deeply nested conditionals.
   Use flat assertions and parametrize. If your test would trigger S3776 (cognitive complexity), rewrite it.

---

## Pipeline

### 1 — Detect language
```
python C:\Users\deepa\Desktop\cluade_sonarqube\scripts\detect_language.py --repo . --output lang.json
```
Read lang.json and tell the user what was detected.

### 2 — Fetch issues
If `issues.json` already exists in the project root, skip this step.

Otherwise ask the user for: HOST, TOKEN, PROJECT_KEY. Then:
```
python C:\Users\deepa\Desktop\cluade_sonarqube\scripts\fetch_issues.py --host <HOST> --token <TOKEN> --project <PROJECT_KEY> --severities BLOCKER,CRITICAL,MAJOR --output issues.json
```

### 3 — Enrich issues with rule details
```
python C:\Users\deepa\Desktop\cluade_sonarqube\scripts\analyze_issue.py --issues issues.json --output enriched.json --host <HOST> --token <TOKEN> --project <PROJECT_KEY>
```
The script derives the SonarCloud organization from the project key automatically.
If it exits with a non-zero code, enrichment failed — apply STOP CONDITION 1 above before proceeding.

### 4 — Pre-flight coverage check
Get the list of affected files from enriched.json (the `component` field, part after the first `:`).
```
python C:\Users\deepa\Desktop\cluade_sonarqube\scripts\validation\run_validation.py --lang-config lang.json --changed-files "<JSON array>" --repo . --phase check-tests --output test-status.json
```
Read test-status.json. For every file where `needs_tests: true`:
- Read the source file
- Create or enhance the unit test at `expected_test_path`, targeting `uncovered_lines`
- Keep tests simple: flat assertions, no nested loops
- Run the tests immediately to confirm they compile and execute

### 5 — Baseline (before fix)
```
python C:\Users\deepa\Desktop\cluade_sonarqube\scripts\validation\run_validation.py --lang-config lang.json --changed-files "<files>" --repo . --phase baseline --output baseline.json
```
**Read baseline.json confidence. If LOW or SKIP, apply STOP CONDITION 2 above.**

### 6 — Apply fix
For each issue in enriched.json:
- File path = `component` field value, split on first `:`, take the right side
- Read the file
- Understand the issue from `message` and `ruleDetails.htmlDesc`
- Apply the **minimal** fix at line `line` using Edit
- Do not refactor unrelated code
- Write `fixes.json` listing every applied change

### 7 — Validate (after fix)
```
python C:\Users\deepa\Desktop\cluade_sonarqube\scripts\validation\run_validation.py --lang-config lang.json --changed-files "<fixed files>" --repo . --phase post-fix --baseline baseline.json --output validation.json
```
Read validation.json confidence:
- HIGH → proceed to Step 8
- MEDIUM → open DRAFT PR
- LOW → apply STOP CONDITION 3
- SKIP → apply STOP CONDITION 4

### 8 — Create PR
```
python C:\Users\deepa\Desktop\cluade_sonarqube\scripts\create_pr.py --fixes fixes.json --validation validation.json --base main
```

---

Start now: run Step 1 and report what language was detected.
