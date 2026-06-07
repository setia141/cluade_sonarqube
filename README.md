# SonarQube Fixer Agent

Autonomous agent that fixes SonarQube issues (Blocker, Critical, Major) across Java, Python, .NET, and Node.js projects. Runs on your local machine via Claude Code. Validates every fix with real tests before opening a pull request — no Docker required.

## Supported Languages

| Language | Build Tool | Test Framework | Coverage Tool | Mock Library (integration) |
|---|---|---|---|---|
| Java | Maven / Gradle | JUnit 5 | JaCoCo | WireMock |
| .NET | dotnet CLI | xUnit / NUnit / MSTest | Coverlet | WireMock.Net |
| Python | pip / poetry | pytest | pytest-cov | pytest-httpserver |
| Node.js | npm / yarn | Jest / Mocha | Jest --coverage | nock |

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

## How to Use

This is a Claude Code agent. Open your repo in Claude Code and invoke it — Claude drives the full pipeline below using its Read/Edit/Write/Bash tools.

## Pipeline

### Step 1 — Detect language

```bash
python scripts/detect_language.py --repo . --output lang.json
```

Detects language, framework, build tool, HTTP client, test framework, and whether coverage tools (JaCoCo, pytest-cov, Coverlet, Jest) are already configured.

### Step 2 — Fetch issues

```bash
# Mac/Linux
python3 scripts/fetch_issues.py \
  --host $SONARQUBE_HOST_URL \
  --token $SONARQUBE_TOKEN \
  --project $SONARQUBE_PROJECT_KEY \
  --severities BLOCKER,CRITICAL,MAJOR \
  --output issues.json

# Windows
python scripts/fetch_issues.py ^
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
python3 scripts/analyze_issue.py \
  --issues issues.json \
  --output enriched.json \
  --host $SONARQUBE_HOST_URL \
  --token $SONARQUBE_TOKEN \
  --project $SONARQUBE_PROJECT_KEY

# Windows
python scripts/analyze_issue.py ^
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
python scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files "[list from enriched.json]" \
  --repo . \
  --phase check-tests \
  --output test-status.json
```

Runs existing tests with coverage enabled (JaCoCo / pytest-cov / Coverlet / Jest). Reports which lines of the files-to-be-changed are NOT covered. If `needs_tests: true` for any file, **Claude creates or enhances unit tests targeting those specific uncovered lines before continuing**.

### Step 5 — Baseline (before fix)

```bash
# Unit tests only (always)
python scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files "[files to fix]" \
  --repo . \
  --phase baseline \
  --output baseline.json

# + Integration tests with mock servers (optional — only if code makes HTTP calls)
python scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files "[files to fix]" \
  --repo . \
  --phase baseline \
  --integration \
  --output baseline-integration.json
```

Unit tests run for changed files **and** any classes that call them (impact analysis). Integration tests generate WireMock/nock/pytest-httpserver scaffolds — **Claude fills in the actual function calls** in the generated test before running.

### Step 6 — Apply fix

Claude reads `enriched.json`, reads each source file, and applies the minimal change using the Edit tool. No script — Claude is the fix engine.

### Step 7 — Validate (after fix)

```bash
python scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files "[fixed files]" \
  --repo . \
  --phase post-fix \
  --baseline baseline.json \
  --output validation.json
```

Expected: happy-path tests still pass, fix-scenario tests now pass (they failed at baseline), caller tests still pass.

### Step 8 — Create PR

```bash
python scripts/create_pr.py \
  --fixes fixes.json \
  --validation validation.json \
  --base main
```

HIGH confidence → ready PR. MEDIUM → draft PR. LOW → fix reverted.

## Confidence Scoring

| Score | Condition | Action |
|---|---|---|
| HIGH | All unit tests pass, fix-scenario test now passes, callers pass | Ready PR |
| MEDIUM | Most pass, minor flag | Draft PR |
| LOW | Unit test regression detected | Revert fix |
| SKIP | Compile failed | Do not touch file |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/detect_language.py` | Language, framework, coverage tool detection |
| `scripts/fetch_issues.py` | Fetch issues from SonarQube API |
| `scripts/analyze_issue.py` | Enrich issues with rule details from SonarQube Rules API |
| `scripts/validation/run_validation.py` | Orchestrator — phases: check-tests, baseline, post-fix |
| `scripts/validation/coverage_check.py` | Line-level coverage via JaCoCo / pytest-cov / Coverlet / Jest |
| `scripts/validation/java_wiremock.py` | WireMock integration test scaffold (Java) |
| `scripts/validation/dotnet_wiremock.py` | WireMock.Net integration test scaffold (.NET) |
| `scripts/validation/python_validator.py` | pytest-httpserver integration test scaffold (Python) |
| `scripts/validation/node_validator.py` | nock integration test scaffold (Node.js) |
| `scripts/create_pr.py` | Branch, commit, PR via `gh` CLI |

## References

| File | Content |
|---|---|
| `references/sonarqube-api.md` | SonarQube REST API reference |
| `references/validation-approach.md` | Validation architecture, mock server design |
| `references/github-actions-setup.md` | Optional CI workflow YAML for all 4 languages |

## Troubleshooting

**`python3` not found on Windows** — use `python` instead. If neither works, install Python from python.org (not the Microsoft Store version).

**No issues found** — check that the SonarQube analysis has completed and the project key is correct.

**`Bearer None` in logs** — token not set. Pass `--token $SONARQUBE_TOKEN` or set the env var. For internal SonarQube with network auth, omit the token entirely.

**`ModuleNotFoundError: No module named 'scripts'`** — run all scripts from the repo root, not from inside `scripts/`.

**Coverage report not generated** — the coverage tool (JaCoCo / pytest-cov / Coverlet) was added to your project automatically. Run `mvn test` / `pytest` / `dotnet test` once manually to confirm tests pass before running the agent.

**PR creation fails** — `gh` CLI must be installed and authenticated: `gh auth status`.
