# GitHub Actions — SonarQube Fixer Agent

Complete workflow templates for all 4 supported languages.
The agent runs autonomously after every SonarQube scan.

## Prerequisites

| Secret | Description |
|---|---|
| `SONARQUBE_TOKEN` | SonarQube API token |
| `SONARQUBE_HOST_URL` | e.g. `https://sonarcloud.io` or internal URL |
| `SONARQUBE_PROJECT_KEY` | Project key from SonarQube dashboard |
| `ANTHROPIC_API_KEY` | Claude API key for the agent |
| `GITHUB_TOKEN` | Auto-provided — needs `contents:write` and `pull-requests:write` |

---

## Java (Maven + Spring Boot)

```yaml
name: SonarQube Fixer — Java
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

jobs:
  sonarqube-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Build
        run: mvn clean package -DskipTests --no-transfer-progress

      - name: SonarQube Scan
        uses: SonarSource/sonarcloud-github-action@v2
        env:
          SONAR_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONARQUBE_HOST_URL }}
        with:
          args: >
            -Dsonar.projectKey=${{ secrets.SONARQUBE_PROJECT_KEY }}
            -Dsonar.organization=your-org

  sonarqube-fix:
    runs-on: ubuntu-latest
    needs: sonarqube-scan
    if: github.ref == 'refs/heads/main'   # only auto-fix on main
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install agent dependencies
        run: pip install requests anthropic

      - name: Detect language
        run: |
          python3 scripts/detect_language.py --repo . --output lang.json
          cat lang.json

      - name: Fetch SonarQube issues
        env:
          SONARQUBE_HOST_URL: ${{ secrets.SONARQUBE_HOST_URL }}
          SONARQUBE_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONARQUBE_PROJECT_KEY: ${{ secrets.SONARQUBE_PROJECT_KEY }}
        run: |
          python3 scripts/fetch_issues.py \
            --host $SONARQUBE_HOST_URL \
            --token $SONARQUBE_TOKEN \
            --project $SONARQUBE_PROJECT_KEY \
            --severities BLOCKER,CRITICAL,MAJOR \
            --output issues.json
          echo "Issues found: $(jq length issues.json)"

      - name: Analyse issues
        run: python3 scripts/analyze_issue.py --issues issues.json --output analysis.json

      - name: Capture validation baseline
        run: |
          python3 scripts/validation/run_validation.py \
            --lang-config lang.json \
            --changed-files "[]" \
            --repo . \
            --phase baseline \
            --output baseline.json

      - name: Install Claude Code CLI
        run: npm install -g @anthropic-ai/claude-code

      - name: Apply fixes (Claude Code — headless)
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          # Claude Code runs non-interactively.
          # It reads analysis.json, reads each source file, applies fixes
          # using its Edit tool, then writes fixes.json via its Write tool.
          claude --print \
            --allowedTools "Read,Edit,Write,Bash" \
            "$(cat <<'EOF'
Read analysis.json and lang.json.
For every issue with category AUTO or GUIDED:
  1. The file path is the part after the colon in issue.component, e.g. myproject:src/Foo.java → src/Foo.java
  2. Read that file.
  3. Apply the minimal fix for the SonarQube rule at the given line — change only what the rule requires.
  4. Use Edit to write the change back.
After all fixes, write fixes.json at the repo root:
[{"rule":"...","file":"...","line":N,"severity":"...","fixStrategy":"...","confidence":"HIGH|MEDIUM","issue_key":"...","applied":true}]
Only include issues you successfully fixed. Write [] if nothing was fixable.
EOF
)"

      - name: Validate after fix
        run: |
          python3 scripts/validation/run_validation.py \
            --lang-config lang.json \
            --changed-files "$(jq -c '[.[].file]' fixes.json)" \
            --repo . \
            --phase post-fix \
            --baseline baseline.json \
            --output validation.json

      - name: Create PR
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          python3 scripts/create_pr.py \
            --fixes fixes.json \
            --validation validation.json \
            --base main
```

---

## Python (pip + pytest)

```yaml
name: SonarQube Fixer — Python
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

jobs:
  sonarqube-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests with coverage
        run: pytest --cov=. --cov-report=xml

      - name: SonarQube Scan
        uses: SonarSource/sonarcloud-github-action@v2
        env:
          SONAR_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONARQUBE_HOST_URL }}

  sonarqube-fix:
    runs-on: ubuntu-latest
    needs: sonarqube-scan
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install requests anthropic pytest-httpserver

      - name: Detect language
        run: python3 scripts/detect_language.py --repo . --output lang.json

      - name: Fetch issues
        env:
          SONARQUBE_HOST_URL: ${{ secrets.SONARQUBE_HOST_URL }}
          SONARQUBE_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONARQUBE_PROJECT_KEY: ${{ secrets.SONARQUBE_PROJECT_KEY }}
        run: |
          python3 scripts/fetch_issues.py \
            --host $SONARQUBE_HOST_URL \
            --token $SONARQUBE_TOKEN \
            --project $SONARQUBE_PROJECT_KEY \
            --output issues.json

      - name: Analyse, fix, validate, PR
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          python3 scripts/analyze_issue.py --issues issues.json --output analysis.json
          python3 scripts/validation/run_validation.py \
            --lang-config lang.json --changed-files "[]" --phase baseline --output baseline.json
          claude --print --allowedTools "Read,Edit,Write,Bash" "Read analysis.json and lang.json. For each AUTO/GUIDED issue: read the file (path is after the colon in issue.component), apply the minimal fix with Edit, then write fixes.json listing every applied fix with rule/file/line/severity/fixStrategy/confidence/issue_key/applied fields. Write [] if nothing fixable."
          python3 scripts/validation/run_validation.py \
            --lang-config lang.json \
            --changed-files "$(jq -r '[.[].file]' fixes.json | jq -c .)" \
            --phase post-fix --baseline baseline.json --output validation.json
          python3 scripts/create_pr.py --fixes fixes.json --validation validation.json
```

---

## .NET (dotnet CLI + xUnit)

```yaml
name: SonarQube Fixer — .NET
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

jobs:
  sonarqube-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.x'

      - name: Build and test
        run: |
          dotnet build
          dotnet test --collect:"XPlat Code Coverage"

      - name: SonarQube Scan
        uses: SonarSource/sonarcloud-github-action@v2
        env:
          SONAR_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONARQUBE_HOST_URL }}

  sonarqube-fix:
    runs-on: ubuntu-latest
    needs: sonarqube-scan
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.x'

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install agent dependencies
        run: pip install requests anthropic

      - name: Detect language
        run: python3 scripts/detect_language.py --repo . --output lang.json

      - name: Fetch issues & fix
        env:
          SONARQUBE_HOST_URL: ${{ secrets.SONARQUBE_HOST_URL }}
          SONARQUBE_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONARQUBE_PROJECT_KEY: ${{ secrets.SONARQUBE_PROJECT_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          python3 scripts/fetch_issues.py \
            --host $SONARQUBE_HOST_URL --token $SONARQUBE_TOKEN \
            --project $SONARQUBE_PROJECT_KEY --output issues.json
          python3 scripts/analyze_issue.py --issues issues.json --output analysis.json
          python3 scripts/validation/run_validation.py \
            --lang-config lang.json --changed-files "[]" --phase baseline --output baseline.json
          claude --print --allowedTools "Read,Edit,Write,Bash" "Read analysis.json and lang.json. For each AUTO/GUIDED issue: read the file (path is after the colon in issue.component), apply the minimal fix with Edit, then write fixes.json listing every applied fix with rule/file/line/severity/fixStrategy/confidence/issue_key/applied fields. Write [] if nothing fixable."
          python3 scripts/validation/run_validation.py \
            --lang-config lang.json \
            --changed-files "$(jq -r '[.[].file]' fixes.json | jq -c .)" \
            --phase post-fix --baseline baseline.json --output validation.json
          python3 scripts/create_pr.py --fixes fixes.json --validation validation.json
```

---

## Node.js (npm + Jest)

```yaml
name: SonarQube Fixer — Node.js
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

jobs:
  sonarqube-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - run: npm ci

      - name: Test with coverage
        run: npm test -- --coverage --coverageReporters=lcov

      - name: SonarQube Scan
        uses: SonarSource/sonarcloud-github-action@v2
        env:
          SONAR_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONARQUBE_HOST_URL }}

  sonarqube-fix:
    runs-on: ubuntu-latest
    needs: sonarqube-scan
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: npm ci
      - run: pip install requests anthropic

      - name: Detect language
        run: python3 scripts/detect_language.py --repo . --output lang.json

      - name: Fetch issues & fix
        env:
          SONARQUBE_HOST_URL: ${{ secrets.SONARQUBE_HOST_URL }}
          SONARQUBE_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONARQUBE_PROJECT_KEY: ${{ secrets.SONARQUBE_PROJECT_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          python3 scripts/fetch_issues.py \
            --host $SONARQUBE_HOST_URL --token $SONARQUBE_TOKEN \
            --project $SONARQUBE_PROJECT_KEY --output issues.json
          python3 scripts/analyze_issue.py --issues issues.json --output analysis.json
          python3 scripts/validation/run_validation.py \
            --lang-config lang.json --changed-files "[]" --phase baseline --output baseline.json
          claude --print --allowedTools "Read,Edit,Write,Bash" "Read analysis.json and lang.json. For each AUTO/GUIDED issue: read the file (path is after the colon in issue.component), apply the minimal fix with Edit, then write fixes.json listing every applied fix with rule/file/line/severity/fixStrategy/confidence/issue_key/applied fields. Write [] if nothing fixable."
          python3 scripts/validation/run_validation.py \
            --lang-config lang.json \
            --changed-files "$(jq -r '[.[].file]' fixes.json | jq -c .)" \
            --phase post-fix --baseline baseline.json --output validation.json
          python3 scripts/create_pr.py --fixes fixes.json --validation validation.json
```

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `SONARQUBE_HOST_URL` | Yes | SonarQube instance URL |
| `SONARQUBE_TOKEN` | Yes | API authentication token |
| `SONARQUBE_PROJECT_KEY` | Yes | Project key in SonarQube |
| `ANTHROPIC_API_KEY` | Yes | Claude API key for fix generation |
| `GITHUB_TOKEN` | Auto | Repo write access for PR creation |
| `GITHUB_REPOSITORY` | Auto | `owner/repo` format |

## WireMock Availability on GitHub Runners

GitHub-hosted runners (`ubuntu-latest`, `windows-latest`, `macos-latest`) have:
- Docker pre-installed — Testcontainers available if needed
- Java pre-installed — WireMock standalone JAR can be downloaded
- Node.js pre-installed — nock available via npm
- Python pre-installed — pytest-httpserver available via pip

No special runner configuration needed for the validation layer.

## Scheduled Scanning

Add to any workflow to run daily:
```yaml
on:
  schedule:
    - cron: '0 3 * * *'   # daily at 3 AM UTC
  push:
    branches: [main]
```
