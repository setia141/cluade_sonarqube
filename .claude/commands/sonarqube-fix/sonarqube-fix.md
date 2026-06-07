You are running the SonarQube Fixer Agent.

Scripts are at: ~/.claude/commands/sonarqube-fix/scripts/
Windows users:  %USERPROFILE%\.claude\commands\sonarqube-fix\scripts\

Detect the OS at the start and set SCRIPTS accordingly:
- Mac/Linux: SCRIPTS=~/.claude/commands/sonarqube-fix/scripts
- Windows:   SCRIPTS=%USERPROFILE%\.claude\commands\sonarqube-fix\scripts

The current working directory is the project you are fixing.
All output files (lang.json, issues.json, enriched.json, baseline.json, validation.json, fixes.json) are written to the project root.

---

## HARD STOP CONDITIONS

These are non-negotiable. Do not proceed silently past any of these.

1. **enriched.json has any issue with `ruleDetails: {}`** — STOP.
   The rules API call failed (likely missing --project for SonarCloud, or auth issue).
   Tell the user which rule failed and why. Do not guess the fix from the message alone.

2. **Baseline confidence is LOW or SKIP** — STOP. Do not apply any fix.
   Read baseline.json → layers.unit_tests.stdout and stderr in full.
   Diagnose the root cause:
   - "collected 0 items" → wrong test path, check where test files actually are
   - "ModuleNotFoundError" / compile error → missing dependency, fix it first
   - Test file missing → go back and create it
   Fix the root cause, re-run baseline. Only continue when it passes.

3. **Post-fix confidence is LOW** — open a DRAFT PR with explanation. Never a ready PR.

4. **Post-fix confidence is SKIP** — revert all changes. Do not open any PR.

5. **Test code you write must be simple** — no nested loops, no deeply nested conditionals.
   Use flat assertions and parametrize. If it would trigger S3776, rewrite it.

---

## PIPELINE

### Step 1 — Detect language
```
python $SCRIPTS/detect_language.py --repo . --output lang.json
```
Tell the user what language and framework was detected.

### Step 2 — Fetch issues
If `issues.json` already exists in the project root, skip this step.

Otherwise ask the user for: HOST, TOKEN, PROJECT_KEY. Then:
```
python $SCRIPTS/fetch_issues.py --host <HOST> --token <TOKEN> --project <PROJECT_KEY> --severities BLOCKER,CRITICAL,MAJOR --output issues.json
```

### Step 3 — Enrich issues with rule details
If `enriched.json` already exists in the project root, skip this step.

Otherwise:
```
python $SCRIPTS/analyze_issue.py --issues issues.json --output enriched.json --host <HOST> --token <TOKEN> --project <PROJECT_KEY>
```
If the script exits with a non-zero code → apply STOP CONDITION 1.
Check every issue in enriched.json — if any has `ruleDetails: {}` → apply STOP CONDITION 1.

### Step 4 — Pre-flight coverage check
Get affected files from enriched.json (component field, split on first `:`, take the right side).
```
python $SCRIPTS/validation/run_validation.py --lang-config lang.json --changed-files "<JSON array of files>" --repo . --phase check-tests --output test-status.json
```
Read test-status.json. For every file where `needs_tests: true`:
- Read the source file
- Look at `uncovered_lines` — create or add tests targeting those exact lines
- Keep tests simple: flat assertions, no nested loops
- Test patterns:
  - Python → pytest with unittest.mock.patch
  - Java  → JUnit 5 + Mockito @Mock/@InjectMocks
  - .NET  → xUnit + Moq
  - Node  → Jest + jest.mock()
- Write TWO tests minimum: happy path + fix scenario (fix scenario WILL fail before the fix — expected)
- Run the tests to confirm they compile

### Step 5 — Baseline (before fix)
```
python $SCRIPTS/validation/run_validation.py --lang-config lang.json --changed-files "<files>" --repo . --phase baseline --output baseline.json
```
Read baseline.json confidence. If LOW or SKIP → apply STOP CONDITION 2.

### Step 6 — Apply fix
For each issue in enriched.json:
- File path = component field, split on first `:`, take right side
- Read the file
- Understand the issue from `message` and `ruleDetails.htmlDesc`
- Apply the minimal fix at line `line` using the Edit tool
- Change only what the rule requires — nothing else
- Write fixes.json with every applied change:
  ```json
  [{"rule":"...","file":"...","line":N,"severity":"...","fixStrategy":"...","applied":true}]
  ```

### Step 7 — Validate (after fix)
```
python $SCRIPTS/validation/run_validation.py --lang-config lang.json --changed-files "<fixed files>" --repo . --phase post-fix --baseline baseline.json --output validation.json
```
Read validation.json confidence:
- HIGH   → proceed to Step 8
- MEDIUM → open DRAFT PR
- LOW    → apply STOP CONDITION 3
- SKIP   → apply STOP CONDITION 4

### Step 8 — Create PR
```
python $SCRIPTS/create_pr.py --fixes fixes.json --validation validation.json --base main
```

---

Start now: run Step 1 and tell the user what was detected.
