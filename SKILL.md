---
name: sonarqube-java-fixer
description: Fix Java code quality issues detected by SonarQube in GitHub repositories. Use this skill when you need to address critical or blocker SonarQube issues from a GitHub Actions workflow, analyze code violations, propose fixes, or automatically create pull requests with remediation code. Perfect for developers integrating SonarQube into CI/CD pipelines and needing intelligent code remediation suggestions for Java projects.
compatibility: Requires Git, GitHub CLI, and SonarQube API access
---

# SonarQube Java Fixer Skill

This skill helps fix Java code quality issues detected by SonarQube in GitHub repositories. It integrates with GitHub Actions workflows to retrieve issues, analyze them, and either suggest fixes or automatically create pull requests with remediation code.

## Overview

When triggered from a GitHub Actions workflow that runs SonarQube analysis, this skill can:

1. **Fetch critical/blocker issues** from the SonarQube API
2. **Analyze root causes** of each issue
3. **Suggest code fixes** with explanations
4. **Generate automated refactoring code** for applicable issues
5. **Create pull requests** with fixes on a dedicated branch

## Quick Start

### Prerequisites

- GitHub repository with SonarQube analysis in CI/CD
- SonarQube instance (Cloud or self-hosted) with API access
- GitHub token with repo write access
- Environment variables configured in GitHub Actions

### Required Environment Variables

```bash
SONARQUBE_HOST_URL      # e.g., https://sonarcloud.io
SONARQUBE_TOKEN         # SonarQube authentication token
GITHUB_TOKEN            # GitHub API token
GITHUB_REPOSITORY       # owner/repo format
GIT_COMMIT_SHA          # Current commit SHA
```

### Basic Usage Flow

1. GitHub Actions runs SonarQube analysis
2. Trigger this skill with the repository details
3. Skill fetches critical/blocker issues via SonarQube API
4. For each issue, provide:
   - Issue explanation
   - Code snippets showing the problem
   - Automated fix suggestions
   - Refactoring code (when applicable)
5. User chooses to either review suggestions or auto-create PR

## Workflow Details

### Step 1: Fetch SonarQube Issues

The skill retrieves critical and blocker issues from SonarQube for your project:

```
Issues are filtered by:
- Severity: CRITICAL or BLOCKER only
- Type: BUG, CODE_SMELL, VULNERABILITY
- Status: OPEN (not resolved/false positives)
```

See `references/sonarqube-api.md` for API endpoint details.

### Step 2: Analyze Issues

For each issue, the skill:
- Reads the problematic source code
- Understands the violation rule
- Identifies the root cause
- Categorizes the fix complexity

### Step 3: Generate Fixes

The skill provides multiple outputs:

#### A. Explanation + Fix Suggestions
Each issue includes:
- **Why it's an issue**: The rule violation explanation
- **Impact**: Severity and risk
- **Fix Strategy**: Recommended approach
- **Code Snippet**: Before/after example

#### B. Automated Refactoring Code
When applicable, the skill provides:
- Python or Shell scripts to auto-fix patterns
- Java code refactoring tools (e.g., using AST manipulation)
- Line-by-line transformations

#### C. Pull Request Creation
The skill can:
- Create a feature branch (`sonarqube/fixes-${timestamp}`)
- Commit fixes with descriptive messages
- Push to GitHub
- Open a Pull Request with detailed description

### Step 4: Review and Merge

Users can:
- Review suggested fixes before applying them
- Run tests on the PR to validate changes
- Merge the PR into main branch

## Common Issue Types & Fixes

See `references/java-issue-patterns.md` for patterns and fixes for:
- NullPointerException risks
- Resource leaks
- Unused code
- Code duplication
- Security vulnerabilities
- Naming conventions

## Integration Examples

### GitHub Actions Workflow

```yaml
name: SonarQube Analysis & Fix
on: [pull_request, push]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: SonarQube Scan
        uses: SonarSource/sonarcloud-github-action@v1
        env:
          SONARQUBE_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Fix Issues with Claude
        run: |
          # Call Claude API with skill access
          # Provide repository and scan results
```

See `references/github-actions-setup.md` for complete workflow examples.

### Command-Line Usage

```bash
# Fetch and analyze issues
claude --skill sonarqube-java-fixer \
  --repo owner/repo \
  --sonarqube-host https://sonarcloud.io \
  --sonarqube-token $SONARQUBE_TOKEN \
  --action analyze

# Auto-fix and create PR
claude --skill sonarqube-java-fixer \
  --repo owner/repo \
  --sonarqube-host https://sonarcloud.io \
  --sonarqube-token $SONARQUBE_TOKEN \
  --action fix-and-pr
```

## Configuration

### Filter Settings

Control which issues to process:

```json
{
  "minSeverity": "BLOCKER",  // BLOCKER, CRITICAL, MAJOR
  "issueTypes": ["BUG", "VULNERABILITY"],  // Exclude CODE_SMELL if desired
  "maxIssuesPerRun": 20,  // Limit number of fixes per execution
  "excludePatterns": ["test/**", "generated/**"]  // Exclude files
}
```

### Fix Automation Levels

- **Level 1 - Review Only**: Suggest fixes, user manually implements
- **Level 2 - Code Generation**: Provide refactoring scripts, user reviews
- **Level 3 - Auto PR**: Automatically create PR with all fixes applied

## Advanced Topics

### Handling Complex Issues

Some SonarQube issues require architectural changes:
- Multi-file refactoring
- Design pattern implementation
- Dependency updates

The skill identifies these and flags them for manual review.

### Custom Rules

If your SonarQube instance uses custom rules, ensure the skill has access to rule descriptions via the SonarQube API.

### Testing Generated Fixes

The skill can optionally:
- Run Maven/Gradle builds to validate
- Execute unit tests
- Report results back to PR

See `references/testing-integration.md` for test automation details.

## Troubleshooting

### Common Issues

**"Cannot connect to SonarQube"**
- Verify `SONARQUBE_HOST_URL` is correct
- Check `SONARQUBE_TOKEN` has API access
- Ensure network connectivity to SonarQube instance

**"No issues found"**
- SonarQube analysis may not have completed
- Check that project key matches repository
- Verify issues are CRITICAL or BLOCKER severity

**"PR creation failed"**
- Verify `GITHUB_TOKEN` has repo:write permissions
- Check branch name doesn't already exist
- Ensure user has push permissions

See `references/troubleshooting.md` for more detailed diagnostics.

## Scripts

Helper scripts are available in `scripts/`:

- `fetch_issues.py` - Query SonarQube API
- `analyze_issue.py` - Analyze single issue and suggest fixes
- `generate_fixes.py` - Generate refactoring code
- `create_pr.py` - Create GitHub PR with fixes

Run individually or use the main orchestration script.

## Output Formats

### Issue Report (JSON)

```json
{
  "issueKey": "sonarqube:S1104",
  "severity": "CRITICAL",
  "type": "BUG",
  "message": "Remove this unused private field",
  "file": "src/main/java/App.java",
  "line": 42,
  "explanation": "...",
  "fixSuggestion": "...",
  "autoFixCode": "...",
  "testValidation": true/false
}
```

### Fix Summary Report

```
Total Issues Found: 15
Critical: 8
Blocker: 7

Fixed: 12
Requires Manual Review: 3

Branch: sonarqube/fixes-20240115-093045
PR Link: https://github.com/owner/repo/pull/XXX
```

## Limitations & Future Enhancements

- Currently supports **Java only** (other languages can be added)
- Some architectural issues require **manual review**
- **Test coverage** validation is optional
- **Custom SonarQube rules** need explicit configuration

Future enhancements planned:
- Support for multiple languages (Python, JavaScript, etc.)
- Automatic test generation for fixed issues
- Integration with code review tools
- Metrics tracking for issue resolution trends

---

## Support & References

- [SonarQube API Documentation](https://docs.sonarqube.org/latest/user-guide/web-api/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Java Code Quality Best Practices](references/java-best-practices.md)
