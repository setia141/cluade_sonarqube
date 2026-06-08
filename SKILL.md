---
name: sonarqube-fixer-agent
description: Autonomous agent that fixes SonarQube issues (Blocker, Critical, Major) across Java, Python, .NET, and Node.js projects. Validates every fix with compile and unit tests before opening a pull request.
---

# SonarQube Fixer Agent

## Skill vs Agent

This is an **agent**, not a passive skill. The distinction matters:

| Skill | Agent |
|---|---|
| Human invokes Claude, Claude reads skill and responds | Triggered by CI event, runs autonomously end-to-end |
| Interactive, conversational | Autonomous, unattended |
| Claude uses its tools ad hoc | Defined pipeline: fetch → analyze → fix → validate → PR |

**Dual-mode operation:**
- **CI mode**: GitHub Actions triggers this agent after a SonarQube scan. No human involved. Agent opens a PR with fixes and a validation report.
- **Interactive mode**: Developer invokes via Claude Code (`/sonarqube-fix`). Claude walks through the pipeline collaboratively.

---

## Supported Languages

| Language | Build Tool | Test Framework | Coverage Tool | SonarQube Prefix |
|---|---|---|---|---|
| Java | Maven / Gradle | JUnit 5 | JaCoCo | `java:` |
| .NET | dotnet CLI | xUnit / NUnit / MSTest | Coverlet | `csharpsquid:` |
| Python | pip / poetry | pytest | pytest-cov | `python:` |
| Node.js | npm / yarn | Jest / Mocha | Jest --coverage | `javascript:` / `typescript:` |

---

## Hard Stop Conditions

| Condition | Required action |
|---|---|
| `ruleDetails` is `{}` in enriched.json | STOP. Rule fetch failed. Tell the user which rule failed before proceeding. |
| Baseline confidence is `LOW` or `SKIP` | STOP. Diagnose root cause (wrong test path, compile error, missing dependency), fix it, re-run baseline. |
| Post-fix confidence is `LOW` | Open a **draft PR** with a clear note explaining what failed. |
| Post-fix confidence is `SKIP` | Revert all changes. Do not open a PR. |
| A test you write triggers a new SonarQube rule | Simplify the test — flat assertions only, no nested loops. |

---

## Pipeline

```
Note: use "python" on Windows, "python3" on Mac/Linux.
      use %VAR% on Windows cmd, $VAR on Mac/Linux.

PHASE 1 — DETECT
  python scripts/detect_language.py --repo . --output lang.json

PHASE 2 — FETCH ISSUES
  python scripts/fetch_issues.py \
    --host <SONARQUBE_HOST_URL> \
    --token <SONARQUBE_TOKEN> \
    --project <SONARQUBE_PROJECT_KEY> \
    --severities BLOCKER,CRITICAL,MAJOR --output issues.json

  python scripts/analyze_issue.py \
    --issues issues.json \
    --host <SONARQUBE_HOST_URL> \
    --token <SONARQUBE_TOKEN> \
    --project <SONARQUBE_PROJECT_KEY> \
    --output enriched.json
  # Calls /api/rules/show for every rule and attaches name, htmlDesc, severity, type.
  # SonarCloud: --project is required (organization is derived from it automatically).
  # Script exits with code 1 if any rule fetch fails — do not proceed if it fails.

PHASE 3 — ENSURE UNIT TESTS EXIST

  Step 3a — Pre-flight coverage check
    python scripts/validation/run_validation.py \
      --lang-config lang.json \
      --changed-files "[list of files that will be fixed]" \
      --repo . --phase check-tests --output test-status.json

    Runs the project's existing tests with coverage enabled:
      Java   → JaCoCo   (jacoco-maven-plugin added to pom.xml if missing)
      Python → pytest-cov (installed if missing, generates coverage.xml)
      .NET   → Coverlet  (dotnet test --collect:"XPlat Code Coverage")
      Node   → Jest --coverage (generates coverage/coverage-final.json)

    Read test-status.json. For every file where needs_tests=true:

  Step 3b — Create / enhance unit tests (Claude writes these directly)
    For each file where needs_tests=true:
      - If has_tests=false: create a new test file at expected_test_path
      - If has_tests=true but uncovered_lines non-empty: add test cases targeting those lines

      Write TWO test cases minimum:
        a. Happy path: call the method with valid input, assert expected output
        b. Fix scenario: call with input that triggers the SonarQube issue
           (e.g. null return, missing key) — this test FAILS before the fix. Expected.

      Run the tests immediately to confirm they compile:
        Java:   mvn test -Dtest=FooServiceTest --no-transfer-progress
        .NET:   dotnet test --filter "ClassName~FooServiceTests"
        Python: pytest tests/test_foo_service.py -v
        Node:   npx jest fooService --no-coverage

  Step 3c — Note callers (from test-status.json callers field)
    These will be included in baseline and post-fix runs automatically.

PHASE 4 — BASELINE CAPTURE

  python scripts/validation/run_validation.py \
    --lang-config lang.json \
    --changed-files "[files to be fixed]" \
    --repo . --phase baseline --output baseline.json

  Runs:
    Layer 1: Build / compile
    Layer 2: Unit tests for changed files AND their callers

  Fix-scenario tests will fail at baseline — that is expected and recorded.

  If baseline returns LOW or SKIP confidence — STOP and diagnose:
    1. Read baseline.json layers.unit_tests.stdout and stderr in full
    2. Common causes:
       - "no tests ran" / "collected 0 items" → wrong test path
       - "ModuleNotFoundError" → missing dependency, run pip/npm/mvn install
       - "cannot find symbol" / compile error → fix the build first
       - test file missing → go back to Step 3 and create it
    3. Fix root cause, re-run. Do NOT proceed until baseline passes
       (except for intentional fix-scenario failures).

PHASE 5 — APPLY FIX
  For each issue in enriched.json:
    1. Read the source file
    2. Apply the minimal change at the indicated line to resolve the rule
    3. Use Edit — change only what the SonarQube rule requires
    4. Compile immediately: if it fails, revert this file and skip the issue

PHASE 6 — VALIDATE

  python scripts/validation/run_validation.py \
    --lang-config lang.json \
    --changed-files "[fixed files]" \
    --repo . --phase post-fix --baseline baseline.json --output validation.json

  Expected:
    PASS: Happy-path tests   — must still pass (were passing at baseline)
    PASS: Fix-scenario tests — must NOW pass (were failing at baseline — proves fix works)
    PASS: Caller tests       — must still pass (no regression in calling code)

PHASE 7 — DECIDE
  HIGH  (compile passes, all unit tests pass)  → commit to fix branch, open ready PR
  LOW   (unit test regression detected)        → revert the fix, skip this issue
  SKIP  (compile failed)                       → revert, do not touch the file

PHASE 8 — PR
  python scripts/create_pr.py \
    --fixes fixes.json --validation validation.json --base main
  PR body includes: issues fixed, validation report per layer, reviewer checklist

PHASE 9 — VERIFY PR IN SONARQUBE
  python scripts/verify_pr.py \
    --host <HOST> --token <TOKEN> \
    --project <PROJECT_KEY> \
    --branch <BRANCH_FROM_STEP_8> \
    --pr-number <PR_NUMBER_FROM_STEP_8> \
    --issues issues.json \
    --output pr-verification.json \
    --timeout 300

  This is the authoritative end-to-end check. SonarQube analyses the PR branch
  and confirms all original issues are resolved with no new issues introduced.
```

---

## Phase 1: Language Detection

Run `scripts/detect_language.py` first. It reads repo structure and returns:

```json
{
  "language": "java",
  "framework": "spring-boot",
  "build_tool": "maven",
  "test_framework": "junit5",
  "sonarqube_rule_prefix": "java:"
}
```

Detection signals by language:

```
Java   → pom.xml | build.gradle
.NET   → *.csproj | *.sln
Python → setup.py | pyproject.toml | requirements.txt
Node   → package.json (without *.csproj)
```

---

## Validation Architecture

The validator (`run_validation.py`) runs two layers:

**Layer 1 — Build / compile**
Catches syntax errors introduced by the fix before running any tests.

**Layer 2 — Unit tests**
Runs tests for the directly changed files plus any files that import/call them (caller impact analysis). Uses language-native test runners:

| Language | Unit test command (targeted) |
|---|---|
| Java/Maven | `mvn test -Dtest=FooTest,BarTest` |
| Java/Gradle | `gradle test --tests '*.FooTest'` |
| .NET | `dotnet test --filter "ClassName~FooTests\|ClassName~BarTests"` |
| Python | `pytest test_foo.py test_bar.py -v` |
| Node | `npx jest --testPathPattern='foo\|bar' --no-coverage` |

**Confidence scoring:**

| Score | Condition | Action |
|---|---|---|
| HIGH | Compile passes + unit tests pass | Ready PR |
| LOW | Unit tests regressed after fix | Revert fix |
| SKIP | Compile failed | Revert, do not open PR |

The SonarQube PR analysis (Phase 9) is the authoritative end-to-end check — it confirms the fix is actually recognised by SonarQube as resolving the issues.

---

## Confidence Scoring

| Score | Condition | Action |
|---|---|---|
| HIGH | All layers pass, fix-scenario tests now pass, callers pass | Auto-commit to PR |
| LOW | Unit test regression detected | Revert, annotate SonarQube issue |
| SKIP | Cannot compile | Log and skip, do not touch code |

---

## Environment Variables

```bash
SONARQUBE_HOST_URL         # e.g. https://sonarcloud.io or internal URL
SONARQUBE_TOKEN            # API token (Bearer auth)
SONARQUBE_PROJECT_KEY      # project key on SonarQube
GITHUB_TOKEN               # repo write access for PR creation
GITHUB_REPOSITORY          # owner/repo format
GIT_BRANCH                 # current branch name
```

---

## Scripts

| Script | Purpose |
|---|---|
| `scripts/detect_language.py` | Language, framework, coverage tool detection |
| `scripts/fetch_issues.py` | Fetch issues from SonarQube API |
| `scripts/analyze_issue.py` | Enrich issues with rule details from SonarQube Rules API |
| `scripts/validation/run_validation.py` | Orchestrator — phases: check-tests, baseline, post-fix |
| `scripts/validation/coverage_check.py` | Line-level coverage via JaCoCo / pytest-cov / Coverlet / Jest |
| `scripts/create_pr.py` | Branch, commit, PR via gh CLI |
| `scripts/verify_pr.py` | Poll SonarQube to confirm PR branch is clean |

Claude applies fixes directly using Read/Edit/Write tools. Claude writes unit tests — no scaffolding scripts.

---

## References

- `references/sonarqube-api.md` — SonarQube API endpoints
- `references/github-actions-setup.md` — CI workflow examples
