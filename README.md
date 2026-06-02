# SonarQube Java Fixer Skill

A comprehensive Claude skill for fixing Java code quality issues detected by SonarQube in GitHub repositories.

## Features

✅ **Fetch SonarQube Issues** - Query SonarQube API for critical/blocker issues
✅ **Analyze Issues** - Understand root causes and categorize by fix complexity  
✅ **Suggest Fixes** - Provide explanations, code examples, and automated refactoring strategies
✅ **Multiple Outputs** - Code snippets, refactoring code, and diff-based fixes
✅ **Auto PR Creation** - Create pull requests with fixes on dedicated branches
✅ **GitHub Actions Integration** - Seamless CI/CD workflow integration

## Supported Issue Types

The skill provides automated fixes or guided recommendations for these critical Java issues:

| Issue | Rule | Type | Auto-Fix | Effort |
|-------|------|------|----------|--------|
| Unused private field | S1104 | Code Quality | ✅ | 5 min |
| Null pointer dereference | S2259 | Security | 🔶 | 30 min |
| Resource leak | S2095 | Reliability | ✅ | 20 min |
| SQL injection | S3649 | Security | ✅ | 30 min |
| Hardcoded credentials | S2115 | Security | 🔶 | 45 min |
| Code duplication | S1143 | Quality | 🔶 | 60 min |
| Exception handling | S1166 | Reliability | ✅ | 15 min |
| Weak crypto | S4790 | Security | 🔶 | 45 min |
| Naming conventions | S100/S101 | Quality | ✅ | 10 min |

**Legend**: ✅ Auto-fixable | 🔶 Guided fix available

## Quick Start

### 1. Prerequisites

```bash
# Required tools
- Python 3.7+
- Git
- GitHub CLI (for PR creation)

# Required credentials
- SonarQube API token
- GitHub token with repo:write permissions
```

### 2. Setup Environment

**For SonarCloud/External (requires token):**
```bash
export SONARQUBE_HOST_URL="https://sonarcloud.io"
export SONARQUBE_TOKEN="your-token"
export SONARQUBE_PROJECT_KEY="owner_repo"
export GITHUB_REPOSITORY="owner/repo"
export GITHUB_TOKEN="your-token"
```

**For Internal Network (NO TOKEN NEEDED!):**
```bash
# If your SonarQube is accessible without authentication:
export SONARQUBE_HOST_URL="http://sonarqube.internal.com:9000"
export SONARQUBE_PROJECT_KEY="myproject"
# See INTERNAL_NETWORK_SETUP.md for more details
```

### 3. Fetch Issues

```bash
# Fetch critical/blocker issues
python3 scripts/fetch_issues.py \
  --host https://sonarcloud.io \
  --token $SONARQUBE_TOKEN \
  --project owner_repo \
  --output issues.json
```

### 4. Analyze Issues

```bash
# Analyze and categorize
python3 scripts/analyze_issue.py \
  --issues issues.json \
  --output analysis.json
```

### 5. Review & Choose Fix Strategy

Review `analysis.json` to see:
- Which issues have automated fixes available
- Which require guided/manual fixes
- Estimated effort for each fix

### 6. Apply Fixes

Depending on your needs:

**Option A**: Review suggestions only
```bash
# Manually review and apply fixes from analysis.json
```

**Option B**: Auto-create PR with fixes
```bash
# GitHub Actions workflow handles this automatically
# See references/github-actions-setup.md
```

## Directory Structure

```
sonarqube-fixer-skill/
├── SKILL.md                          # Main skill definition
├── README.md                         # This file
├── references/
│   ├── sonarqube-api.md             # API documentation
│   ├── java-issue-patterns.md       # Issue patterns & fixes
│   └── github-actions-setup.md      # CI/CD integration
└── scripts/
    ├── fetch_issues.py              # Fetch from SonarQube API
    ├── analyze_issue.py             # Analyze and suggest fixes
    └── generate_fixes.py            # (Coming) Generate refactoring code
```

## Usage Examples

### Example 1: Review Only

```bash
# Fetch issues
python3 scripts/fetch_issues.py \
  --host https://sonarcloud.io \
  --token $TOKEN \
  --project myorg_myproject \
  --output issues.json \
  --enrich  # Include rule details and source code

# Analyze
python3 scripts/analyze_issue.py \
  --issues issues.json \
  --output analysis.json

# Review analysis.json and manually implement fixes
```

### Example 2: GitHub Actions Auto-Fix

```bash
# Add to .github/workflows/sonarqube-fix.yml
# See references/github-actions-setup.md for complete workflow
```

### Example 3: Using with Claude

```bash
# When using Claude with this skill:
claude --skill sonarqube-java-fixer \
  "Analyze my SonarQube issues from sonarcloud.io for myorg_myproject and create a PR with fixes"

# Claude will:
# 1. Fetch issues from SonarQube API
# 2. Analyze each one
# 3. Generate fixes
# 4. Create a PR with the fixes
```

## Configuration

### Minimal Setup

```bash
export SONARQUBE_HOST_URL="https://sonarcloud.io"
export SONARQUBE_TOKEN="token"
export SONARQUBE_PROJECT_KEY="owner_repo"
```

### For Self-Hosted SonarQube

```bash
export SONARQUBE_HOST_URL="https://your-sonarqube.com"
export SONARQUBE_TOKEN="token"
export SONARQUBE_PROJECT_KEY="my-project"
```

### Advanced Filtering

```python
# In scripts or workflows, customize:
severities = ["BLOCKER", "CRITICAL", "MAJOR"]  # Change filtering
issue_types = ["BUG", "VULNERABILITY", "CODE_SMELL"]  # Include code smells
max_issues = 20  # Limit issues per run
exclude_files = ["test/**", "generated/**"]  # Skip files
```

## Integration with GitHub Actions

The skill integrates seamlessly with GitHub Actions workflows:

1. **SonarQube scans your code**
2. **Workflow triggers this skill**
3. **Skill fetches critical/blocker issues**
4. **Skill analyzes and generates fixes**
5. **Skill creates PR with fixes**
6. **Team reviews and merges**

See `references/github-actions-setup.md` for complete workflow examples including:
- Basic analysis workflow
- Analysis with PR comments
- Analysis + auto-fix with PR creation

## Output Formats

### Issues JSON
```json
{
  "key": "sonarqube:AXp7KqQcGg7B2nLZUU6z",
  "rule": "java:S2095",
  "severity": "CRITICAL",
  "type": "BUG",
  "message": "Close this resource",
  "file": "src/main/java/App.java",
  "line": 42
}
```

### Analysis JSON
```json
{
  "issueKey": "sonarqube:...",
  "rule": "java:S2095",
  "fixTitle": "Resources should be closed",
  "fixStrategy": "Use try-with-resources statement",
  "autoFixPossible": true,
  "estimatedEffort": "20 min",
  "fixTemplate": "..."
}
```

## Troubleshooting

### "Cannot connect to SonarQube"
- Verify SONARQUBE_HOST_URL is correct
- Check SONARQUBE_TOKEN has API access
- Ensure network connectivity

### "No issues found"
- Verify project key matches SonarQube configuration
- Check that SonarQube analysis has completed
- Ensure issues are CRITICAL or BLOCKER severity

### "Fix not available for rule X"
- Some rules require manual judgment
- See fix template in analysis output for guidance
- Can still manually implement from suggestions

### "PR creation failed"
- Verify GITHUB_TOKEN has repo:write permissions
- Check branch name doesn't already exist
- Ensure user has push permissions to repository

## Capabilities & Limitations

### ✅ What This Skill Does Well

- Fetches and analyzes critical Java issues
- Provides detailed fix explanations
- Generates code examples for common patterns
- Creates PRs with fixes for testable issues
- Integrates with GitHub Actions CI/CD

### ⚠️ Limitations

- **Java only** (other languages can be added)
- **Critical/blocker issues only** (by design)
- **Architectural issues** may need manual refactoring
- **Test coverage** validation is optional

### 🚀 Future Enhancements

- Support for Python, JavaScript/TypeScript
- Automatic test generation for fixed issues
- Integration with code review tools
- Metrics tracking for issue resolution trends
- Machine learning for pattern-based auto-fixes

## Support

### Documentation
- `SKILL.md` - Comprehensive skill guide
- `references/sonarqube-api.md` - API endpoints and authentication
- `references/java-issue-patterns.md` - Issue patterns with code examples
- `references/github-actions-setup.md` - CI/CD integration

### Scripts
- `scripts/fetch_issues.py` - Query SonarQube issues
- `scripts/analyze_issue.py` - Analyze and suggest fixes

## Contributing

To add support for new issue types:

1. Add pattern to `JavaIssueAnalyzer.ISSUE_FIXES` in `scripts/analyze_issue.py`
2. Include fix template with before/after examples
3. Update `java-issue-patterns.md` with documentation
4. Test with real SonarQube issues

## License

This skill is provided as-is for use with Claude by Anthropic.

## Support & Questions

For issues or questions:
1. Check the troubleshooting section
2. Review reference documentation
3. Check SonarQube API documentation
4. Consult Java best practices guides

---

**Last Updated**: 2024
**Skill Version**: 1.0
**Tested With**: Java 8-17, SonarCloud, Self-hosted SonarQube
