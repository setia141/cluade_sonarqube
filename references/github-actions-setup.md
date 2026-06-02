# GitHub Actions Integration Guide

This guide explains how to integrate the SonarQube Java Fixer skill into your GitHub Actions workflows.

## Prerequisites

1. **GitHub Repository**: With source code
2. **SonarQube Setup**: 
   - SonarCloud account (free) OR self-hosted SonarQube instance
   - Project key configured
   - API token generated
3. **GitHub Tokens**:
   - `SONARQUBE_TOKEN` - SonarQube API token
   - `GITHUB_TOKEN` - GitHub token (usually auto-provided)

## Setup Instructions

### Step 1: Generate Tokens

#### SonarQube Token
1. Go to SonarCloud.io → My Account → Security
2. Generate new token with name like "GitHub Actions"
3. Copy and save the token

#### GitHub Repository Secret
1. Go to Settings → Secrets and variables → Actions
2. Create new repository secret
3. Name: `SONARQUBE_TOKEN`
4. Value: Paste your SonarQube token

### Step 2: Find Your Project Key

#### For SonarCloud
1. Log in to SonarCloud.io
2. Go to your project
3. Project information shows the key (e.g., `owner_repo`)

#### For Self-Hosted SonarQube
1. Log in to your SonarQube instance
2. Administration → Projects → Management
3. Find your project key

## Workflow Examples

### Basic: Run SonarQube Analysis

```yaml
name: SonarQube Analysis
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  sonarqube:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Full history for SonarQube
      
      - name: Set up Java
        uses: actions/setup-java@v3
        with:
          distribution: 'temurin'
          java-version: '11'
      
      - name: SonarQube Analysis
        uses: SonarSource/sonarcloud-github-action@v1
        env:
          SONAR_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONAR_HOST_URL: https://sonarcloud.io
        with:
          args: >
            -Dsonar.projectKey=owner_repo
            -Dsonar.organization=your-org
```

### Intermediate: Analyze + Comment on PR

```yaml
name: SonarQube Analysis with PR Comment
on:
  pull_request:
    branches: [main]

jobs:
  sonarqube:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0
      
      - name: Set up Java
        uses: actions/setup-java@v3
        with:
          distribution: 'temurin'
          java-version: '11'
      
      - name: Build with Maven
        run: mvn clean package -DskipTests
      
      - name: SonarQube Analysis
        uses: SonarSource/sonarcloud-github-action@v1
        env:
          SONAR_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONAR_HOST_URL: https://sonarcloud.io
        with:
          args: >
            -Dsonar.projectKey=owner_repo
            -Dsonar.organization=your-org
            -Dsonar.branch.name=${{ github.head_ref }}
            -Dsonar.pullRequest.key=${{ github.event.pull_request.number }}
      
      - name: Comment Quality Gate Status
        if: always()
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const qualityGateResult = require('./.sonar/qualityGate.json');
            
            const comment = `### 📊 SonarQube Quality Gate Results
            Status: **${qualityGateResult.projectStatus.status}**
            [View Full Report](https://sonarcloud.io/dashboard?id=owner_repo)`;
            
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: comment
            });
```

### Advanced: Analyze + Auto-Fix + Create PR

```yaml
name: SonarQube Analyze & Auto-Fix
on:
  push:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC

jobs:
  sonarqube:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Set up Java
        uses: actions/setup-java@v3
        with:
          distribution: 'temurin'
          java-version: '11'
      
      - name: Build with Maven
        run: mvn clean package -DskipTests
      
      - name: SonarQube Analysis
        uses: SonarSource/sonarcloud-github-action@v1
        env:
          SONAR_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          SONAR_HOST_URL: https://sonarcloud.io
        with:
          args: >
            -Dsonar.projectKey=owner_repo
            -Dsonar.organization=your-org
      
      - name: Fetch SonarQube Issues
        id: fetch_issues
        run: |
          python3 << 'EOF'
          import requests
          import json
          import os
          
          sonarqube_host = "https://sonarcloud.io"
          token = "${{ secrets.SONARQUBE_TOKEN }}"
          project_key = "owner_repo"
          
          # Fetch critical/blocker issues
          url = f"{sonarqube_host}/api/issues/search"
          params = {
              "componentKeys": project_key,
              "severities": "BLOCKER,CRITICAL",
              "types": "BUG,VULNERABILITY",
              "statuses": "OPEN",
              "ps": 500
          }
          
          response = requests.get(
              url,
              params=params,
              headers={"Authorization": f"Bearer {token}"}
          )
          
          issues = response.json().get("issues", [])
          with open("issues.json", "w") as f:
              json.dump(issues, f, indent=2)
          
          print(f"Found {len(issues)} critical/blocker issues")
          EOF
      
      - name: Generate Fixes
        id: generate_fixes
        run: |
          python3 << 'EOF'
          import json
          
          # Read issues
          with open("issues.json") as f:
              issues = json.load(f)
          
          fixes = []
          for issue in issues:
              fix = {
                  "key": issue.get("key"),
                  "file": issue["mainLocation"]["file"],
                  "line": issue["mainLocation"]["startLine"],
                  "message": issue["mainLocation"]["message"],
                  "rule": issue["rule"]
              }
              fixes.append(fix)
          
          with open("fixes.json", "w") as f:
              json.dump(fixes, f, indent=2)
          
          print(f"Generated fixes for {len(fixes)} issues")
          EOF
      
      - name: Create Fix Branch
        if: env.FIXES_COUNT > '0'
        run: |
          git config user.name "sonarqube-bot"
          git config user.email "bot@sonarqube.local"
          
          BRANCH_NAME="sonarqube/fixes-$(date +%Y%m%d-%H%M%S)"
          git checkout -b "$BRANCH_NAME"
          
          echo "$BRANCH_NAME" > branch_name.txt
      
      - name: Apply Fixes
        run: |
          python3 << 'EOF'
          import json
          
          # This is a placeholder - actual fix implementation depends on issue types
          with open("fixes.json") as f:
              fixes = json.load(f)
          
          # Example: Remove unused fields, add null checks, etc.
          for fix in fixes:
              print(f"Processing {fix['rule']}: {fix['message']}")
              # Apply fix logic here
          EOF
      
      - name: Commit & Push
        if: hashFiles('branch_name.txt') != ''
        run: |
          git add -A
          git commit -m "fix: resolve SonarQube critical/blocker issues" || true
          git push origin $(cat branch_name.txt)
      
      - name: Create Pull Request
        if: hashFiles('branch_name.txt') != ''
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const branchName = fs.readFileSync('branch_name.txt', 'utf8').trim();
            const fixes = JSON.parse(fs.readFileSync('fixes.json', 'utf8'));
            
            const body = `## 🔧 SonarQube Auto-Fix PR
            
            This PR automatically fixes critical and blocker SonarQube issues.
            
            ### Issues Fixed (${fixes.length})
            ${fixes.map(f => `- **${f.rule}**: ${f.message} (${f.file}:${f.line})`).join('\n')}
            
            ### Before Merging
            - [ ] Review changes carefully
            - [ ] Run tests locally: \`mvn clean test\`
            - [ ] Verify SonarQube Quality Gate passes
            - [ ] Run full build: \`mvn clean package\`
            
            Created by SonarQube Auto-Fixer Bot`;
            
            const pr = await github.rest.pulls.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              head: branchName,
              base: 'main',
              title: '🔧 Fix SonarQube critical/blocker issues',
              body: body,
              draft: false
            });
            
            console.log(`Created PR: ${pr.data.html_url}`);
```

### For Self-Hosted SonarQube

```yaml
name: SonarQube Self-Hosted Analysis
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  sonarqube:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0
      
      - name: Set up Java
        uses: actions/setup-java@v3
        with:
          distribution: 'temurin'
          java-version: '11'
      
      - name: Build with Maven
        run: mvn clean package -DskipTests
      
      - name: SonarQube Analysis
        run: |
          mvn clean verify \
            -Dsonar.projectKey=my-project \
            -Dsonar.sources=src \
            -Dsonar.host.url=${{ secrets.SONARQUBE_HOST }} \
            -Dsonar.login=${{ secrets.SONARQUBE_TOKEN }}
        env:
          SONARQUBE_HOST: ${{ secrets.SONARQUBE_HOST }}
          SONARQUBE_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
```

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `SONARQUBE_HOST_URL` | SonarQube instance URL | `https://sonarcloud.io` |
| `SONARQUBE_TOKEN` | API token for authentication | (secret) |
| `GITHUB_TOKEN` | GitHub API token (auto-provided) | (auto) |
| `GITHUB_REPOSITORY` | Repo in owner/repo format | `my-org/my-repo` |
| `GIT_COMMIT_SHA` | Current commit hash | (auto via github.sha) |

## Troubleshooting

### Issue: "SonarQube analysis failed"

**Solution**: 
- Check Java version (11+ recommended)
- Verify SonarQube token is valid
- Ensure project key matches SonarQube configuration
- Check for compilation errors first

### Issue: "Quality Gate failed"

**Solution**:
- This is expected on PRs with new issues
- Review issues in SonarQube dashboard
- Fix issues locally first
- Re-push to trigger new analysis

### Issue: "Token authentication failed"

**Solution**:
- Verify token in GitHub Secrets is correct
- Regenerate token in SonarCloud/SonarQube
- Check token has appropriate permissions

### Issue: "PR creation failed"

**Solution**:
- Verify GitHub token has `repo` scope
- Check if branch already exists
- Ensure user has push permissions
- Check GitHub Actions write permissions

## Best Practices

1. **Always use HTTPS**: For SonarQube API calls
2. **Store secrets properly**: Use GitHub Secrets, never in code
3. **Run on schedule**: Daily scans catch issues early
4. **Review before merge**: Always review auto-generated PRs
5. **Test thoroughly**: Run full test suite after fixes
6. **Monitor trends**: Track SonarQube metrics over time

## Next Steps

1. Copy one of the workflow templates above
2. Update project key and organization name
3. Add to `.github/workflows/sonarqube.yml`
4. Commit and push to trigger first run
5. Check SonarQube dashboard for results
