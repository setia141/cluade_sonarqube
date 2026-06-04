# SonarQube Fixer Agent

Autonomous agent that fixes SonarQube issues (Blocker, Critical, Major) across Java, Python, .NET, and Node.js projects. Validates every fix using embedded mock servers before opening a pull request. Runs in GitHub Actions CI or interactively via Claude Code.

## Supported Languages

| Language | Build Tool | Test Framework | Mock Library |
|---|---|---|---|
| Java | Maven / Gradle | JUnit 5 | WireMock |
| .NET | dotnet CLI | xUnit / NUnit / MSTest | WireMock.Net |
| Python | pip / poetry | pytest | pytest-httpserver |
| Node.js | npm / yarn | Jest / Mocha | nock |

## Prerequisites

| Tool | Required for |
|---|---|
| Python 3.8+ | All scripts |
| `pip install anthropic requests` | Fix generation and issue fetching |
| `gh` CLI | PR creation (`create_pr.py`) |
| Java 17+ / dotnet 8 / Node 20 | Language-specific validation layers |

### Secrets (GitHub Actions)

| Secret | Description |
|---|---|
| `SONARQUBE_TOKEN` | SonarQube API token |
| `SONARQUBE_HOST_URL` | e.g. `https://sonarcloud.io` |
| `SONARQUBE_PROJECT_KEY` | Project key from SonarQube dashboard |
| `ANTHROPIC_API_KEY` | Claude API key for fix generation |
| `GITHUB_TOKEN` | Auto-provided — needs `contents:write` and `pull-requests:write` |

## Quick Start (Interactive)

```bash
# 1. Detect language
python3 scripts/detect_language.py --repo . --output lang.json

# 2. Fetch issues
python3 scripts/fetch_issues.py \
  --host $SONARQUBE_HOST_URL \
  --token $SONARQUBE_TOKEN \
  --project $SONARQUBE_PROJECT_KEY \
  --output issues.json

# 3. Analyse
python3 scripts/analyze_issue.py --issues issues.json --output analysis.json

# 4. Capture baseline (before fix)
python3 scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files "[]" \
  --repo . \
  --phase baseline \
  --output baseline.json

# 5. Apply fixes
# Claude reads analysis.json, uses Read/Edit/Write to fix each file,
# and writes fixes.json — no separate script needed.
# In Claude Code: just ask Claude to "apply the fixes from analysis.json"

# 6. Validate after fix
python3 scripts/validation/run_validation.py \
  --lang-config lang.json \
  --changed-files "$(jq -c '[.[].file]' fixes.json)" \
  --repo . \
  --phase post-fix \
  --baseline baseline.json \
  --output validation.json

# 7. Create PR
python3 scripts/create_pr.py \
  --fixes fixes.json \
  --validation validation.json \
  --base main
```

## GitHub Actions

See `references/github-actions-setup.md` for complete workflow YAML for all 4 languages.

## Validation Pipeline

Four layers run for every fix:

| Layer | What it checks |
|---|---|
| 1. Compile | Project still builds after fix |
| 2. Scoped unit tests | Tests for changed files still pass |
| 3. Integration (mock server) | Downstream HTTP calls unchanged |
| 4. Stub interaction comparison | Call counts match baseline |

**Confidence scores**: HIGH → auto PR, MEDIUM → draft PR, LOW → revert, SKIP → compile failed.

Mock servers run in-process (no Docker):
- Java/.NET: WireMock / WireMock.Net — real TCP socket on dynamic port
- Python: pytest-httpserver — real HTTP server via `with` block
- Node.js: nock — intercepts at `http.request` level, no network needed

See `references/validation-approach.md` for full design.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/detect_language.py` | Detect language, framework, build tool, HTTP client |
| `scripts/fetch_issues.py` | Fetch issues from SonarQube API |
| `scripts/analyze_issue.py` | Categorise issues, estimate effort, suggest strategies |
| `scripts/validation/run_validation.py` | Orchestrate all 4 validation layers |
| `scripts/validation/java_wiremock.py` | WireMock integration test generator |
| `scripts/validation/dotnet_wiremock.py` | WireMock.Net integration test generator |
| `scripts/validation/python_validator.py` | pytest-httpserver test generator |
| `scripts/validation/node_validator.py` | nock test generator |
| `scripts/create_pr.py` | Create GitHub PR with validation report |

## References

| File | Content |
|---|---|
| `references/github-actions-setup.md` | Complete CI workflow YAML for all 4 languages |
| `references/sonarqube-api.md` | SonarQube REST API reference |
| `references/java-issue-patterns.md` | Java SonarQube rule patterns and fix templates |
| `references/python-issue-patterns.md` | Python SonarQube rule patterns |
| `references/dotnet-issue-patterns.md` | .NET/C# SonarQube rule patterns |
| `references/node-issue-patterns.md` | JavaScript/TypeScript SonarQube rule patterns |
| `references/validation-approach.md` | Validation architecture and mock server design |

## Troubleshooting

**`Bearer None` in logs** — token was not set. Pass `--token` or set `SONARQUBE_TOKEN`. Token-less mode works for internal SonarQube with network auth.

**`ModuleNotFoundError: No module named 'scripts'`** — run scripts from the repo root, not from inside `scripts/`. The validation orchestrator adds the repo root to `sys.path` automatically.

**Fix not applied** — `old_code` from Claude did not match the file exactly. Check for CRLF vs LF line endings or tabs vs spaces differences.

**PR creation fails** — `gh` CLI must be installed and authenticated (`gh auth status`).
