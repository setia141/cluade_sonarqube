# SonarQube Fixer Agent

Autonomous agent that fixes SonarQube issues (Blocker, Critical, Major) across Java, Python, .NET, and Node.js projects. Runs on your local machine via Claude Code. Validates every fix with real tests before opening a pull request — no Docker required.

## Supported Languages

| Language | Build Tool | Test Framework | Coverage Tool |
|---|---|---|---|
| Java | Maven / Gradle | JUnit 5 | JaCoCo |
| .NET | dotnet CLI | xUnit / NUnit / MSTest | Coverlet |
| Python | pip / poetry | pytest | pytest-cov |
| Node.js | npm / yarn | Jest / Mocha | Jest --coverage |

## Prerequisites

| Tool | Purpose |
|---|---|
| Python 3.8+ | All scripts |
| `pip install requests` | SonarQube API calls |
| `gh` CLI (authenticated) | PR creation |
| Java 17+ / dotnet 8 / Node 20 | Only for the language you are fixing |

**Python command:**
- **Windows** — use `python`
- **Mac / Linux** — use `python3`

All examples below use `python` — substitute `python3` if you are on Mac/Linux.

## How to Run from Claude Code

### Setup

No copying required. The scripts live inside this repo at `.claude/commands/sonarqube-fix/scripts/` and are referenced with project-relative paths.

1. **Open this repo in Claude Code**
   ```cmd
   cd C:\path\to\cluade_sonarqube
   claude
   ```

2. **Type the slash command**
   ```
   /sonarqube-fix
   ```

Claude will:
- Detect the language automatically
- Ask for your SonarQube credentials if `issues.json` doesn't exist yet
- Run the full pipeline: coverage check → create missing tests → baseline → fix → validate → PR
- Stop and explain if anything goes wrong (failed enrichment, LOW confidence, etc.)

### If you already have issues.json

Copy it into your project root before running the command:
```cmd
copy C:\path\to\cluade_sonarqube\issues.json .
copy C:\path\to\cluade_sonarqube\enriched.json .
```
Claude will detect these files and skip the fetch and enrich steps.

---

## Pipeline (what Claude does internally)

### Step 1 — Detect language

```bash
python .claude/commands/sonarqube-fix/scripts/detect_language.py --repo . --output lang.json
```

Detects language, framework, build tool, HTTP client, test framework, and whether coverage tools (JaCoCo, pytest-cov, Coverlet, Jest) are already configured.

### Step 2 — Fetch issues

```bash
# Mac/Linux
python3 .claude/commands/sonarqube-fix/scripts/fetch_issues.py \
  --host $SONARQUBE_HOST_URL \
  --token $SONARQUBE_TOKEN \
  --project $SONARQUBE_PROJECT_KEY \
  --severities BLOCKER,CRITICAL,MAJOR \
  --output issues.json

# Windows
python .claude/commands/sonarqube-fix/scripts/fetch_issues.py ^
  --host %SONARQUBE_HOST_URL% ^
  --token %SONARQUBE_TOKEN% ^
  --project %SONARQUBE_PROJECT_KEY% ^
  --severities BLOCKER,CRITICAL,MAJOR ^
  --output issues.json
```

Token is optional for internal SonarQube instances with network authentication.

### Step 3 — Enrich issues with rule details

```bash
# Mac/Linux
python3 .claude/commands/sonarqube-fix/scripts/analyze_issue.py \
  --issues issues.json \
  --output enriched.json \
  --host $SONARQUBE_HOST_URL \
  --token $SONARQUBE_TOKEN \
  --project $SONARQUBE_PROJECT_KEY

# Windows
python .claude/commands/sonarqube-fix/scripts/analyze_issue.py ^
  --issues issues.json ^
  --output enriched.json ^
  --host %SONARQUBE_HOST_URL% ^
  --token %SONARQUBE_TOKEN% ^
  --project %SONARQUBE_PROJECT_KEY%
```

Calls `/api/rules/show` for every rule and attaches the rule name, full HTML description, severity, and type to each issue. Claude reads this to understand what to fix and how.

**SonarCloud:** `--project` is required — the script derives the organization from it automatically. Without it the rules API returns 400.

**Self-hosted SonarQube:** `--project` is optional.

### Step 4 — Pre-flight coverage check

```bash
python .claude/commands/sonarqube-fix/scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files "[list from enriched.json]" \
  --repo . \
  --phase check-tests \
  --output test-status.json
```

Runs existing tests with coverage enabled (JaCoCo / pytest-cov / Coverlet / Jest). Reports which lines of the files-to-be-changed are NOT covered. If `needs_tests: true` for any file, **Claude creates or enhances unit tests targeting those specific uncovered lines before continuing**.

### Step 5 — Baseline (before fix)

```bash
python .claude/commands/sonarqube-fix/scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files "[files to fix]" \
  --repo . \
  --phase baseline \
  --output baseline.json
```

Runs unit tests for the changed files **and** any classes that call them (impact analysis). Records pass/fail counts as the baseline — fix-scenario tests are expected to fail here.

### Step 6 — Apply fix

Claude reads `enriched.json`, reads each source file, and applies the minimal change using the Edit tool. No script — Claude is the fix engine.

### Step 7 — Validate (after fix)

```bash
python .claude/commands/sonarqube-fix/scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files "[fixed files]" \
  --repo . \
  --phase post-fix \
  --baseline baseline.json \
  --output validation.json
```

Expected: happy-path tests still pass, fix-scenario tests now pass (they failed at baseline), caller tests still pass.

Step 9 (`verify_pr.py`) is the authoritative end-to-end check — it asks SonarQube directly whether the issues are resolved on the PR branch.

### Step 8 — Create PR

```bash
python .claude/commands/sonarqube-fix/scripts/create_pr.py \
  --fixes fixes.json \
  --validation validation.json \
  --base main
```

HIGH confidence → ready PR. MEDIUM → draft PR. LOW → fix reverted.

## Confidence Scoring

| Score | Condition | Action |
|---|---|---|
| HIGH | Compile passes, all unit tests pass | Ready PR |
| LOW | Unit test regression after fix | Revert fix |
| SKIP | Compile failed | Do not touch file |

## Structure

```
.claude/commands/sonarqube-fix/
  sonarqube-fix.md          ← command definition — invoked as /sonarqube-fix
  scripts/
    detect_language.py      ← language/framework/coverage tool detection
    fetch_issues.py         ← fetch issues from SonarQube API
    analyze_issue.py        ← enrich issues with rule details
    create_pr.py            ← branch, commit, PR via gh CLI
    verify_pr.py            ← poll SonarQube to confirm PR is clean
    validation/
      run_validation.py     ← orchestrator: check-tests / baseline / post-fix
      coverage_check.py     ← JaCoCo / pytest-cov / Coverlet / Jest
```

Scripts are only ever run by Claude — never manually.

## Troubleshooting

**`python3` not found on Windows** — use `python` instead. If neither works, install Python from python.org (not the Microsoft Store version).

**No issues found** — check that the SonarQube analysis has completed and the project key is correct.

**`Bearer None` in logs** — token not set. Pass `--token $SONARQUBE_TOKEN` or set the env var. For internal SonarQube with network auth, omit the token entirely.

**`ModuleNotFoundError: No module named 'scripts'`** — run all scripts from the repo root, not from inside `scripts/`.

**Coverage report not generated** — the coverage tool (JaCoCo / pytest-cov / Coverlet) was added to your project automatically. Run `mvn test` / `pytest` / `dotnet test` once manually to confirm tests pass before running the agent.

**PR creation fails** — `gh` CLI must be installed and authenticated: `gh auth status`.
