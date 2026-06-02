# Installation & Setup Guide

## 📦 Installation Methods

Choose the method that works best for your environment:

### Method 1: Claude Skill (Recommended for Claude Users)

1. **Download the skill**
   ```bash
   # Copy the entire sonarqube-fixer-skill directory
   cp -r sonarqube-fixer-skill ~/.claude/skills/
   ```

2. **Verify installation**
   ```bash
   ls ~/.claude/skills/sonarqube-fixer-skill/SKILL.md
   ```

3. **Use in Claude**
   ```
   "Analyze my SonarQube issues and suggest fixes"
   ```

### Method 2: Standalone Scripts (Universal)

1. **Prerequisites**
   ```bash
   python3 --version  # Python 3.7+
   pip install requests  # HTTP library
   ```

2. **Install dependencies**
   ```bash
   cd sonarqube-fixer-skill
   pip install requests  # Only external dependency
   ```

3. **Make scripts executable**
   ```bash
   chmod +x scripts/*.py
   ```

4. **Test installation**
   ```bash
   python3 scripts/fetch_issues.py --help
   ```

### Method 3: GitHub Actions (CI/CD)

1. **Copy workflow file**
   ```bash
   mkdir -p .github/workflows
   cp references/github-actions-setup.md .github/workflows/sonarqube.yml
   ```

2. **Add repository secrets** (GitHub Settings → Secrets)
   - `SONARQUBE_TOKEN` - Your SonarQube API token
   - `SONARQUBE_HOST_URL` - Your SonarQube instance URL (optional)

3. **Update workflow variables**
   ```yaml
   env:
     SONARQUBE_PROJECT_KEY: owner_repo
     SONARQUBE_HOST_URL: https://sonarcloud.io
   ```

4. **Commit and trigger**
   ```bash
   git push origin main  # Triggers workflow
   ```

---

## 🔐 Credentials Setup

### SonarQube Token Generation

#### For SonarCloud
1. Log in to https://sonarcloud.io
2. Click avatar → My Account
3. Navigate to Security → Tokens
4. Generate token named "GitHub Actions"
5. Copy token (you won't see it again)

#### For Self-Hosted SonarQube
1. Log in to your SonarQube instance
2. Go to User → Security (icon in top-right)
3. Generate token named "GitHub Actions"
4. Copy token immediately

### GitHub Token Generation

1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Click "Generate new token"
3. Name: "SonarQube Fixer"
4. Scopes needed:
   - `repo` (full control)
   - `workflow` (GitHub Actions)
5. Copy token immediately

### Environment Variables

**Local Development**
```bash
# Add to ~/.bashrc or ~/.zshrc
export SONARQUBE_HOST_URL="https://sonarcloud.io"
export SONARQUBE_TOKEN="your-token-here"
export SONARQUBE_PROJECT_KEY="owner_repo"
export GITHUB_TOKEN="your-github-token"

# Or create .env file
cat > .env << 'ENVFILE'
SONARQUBE_HOST_URL=https://sonarcloud.io
SONARQUBE_TOKEN=your-token
SONARQUBE_PROJECT_KEY=owner_repo
GITHUB_TOKEN=your-github-token
ENVFILE

# Load environment
source .env
```

**GitHub Actions**
```yaml
env:
  SONARQUBE_HOST_URL: https://sonarcloud.io
  SONARQUBE_PROJECT_KEY: owner_repo

jobs:
  fix:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: python3 scripts/fetch_issues.py
        env:
          SONARQUBE_TOKEN: ${{ secrets.SONARQUBE_TOKEN }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Docker Setup (Optional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY sonarqube-fixer-skill .

RUN pip install requests

ENTRYPOINT ["python3", "scripts/fetch_issues.py"]
```

```bash
# Build
docker build -t sonarqube-fixer .

# Run
docker run --rm \
  -e SONARQUBE_TOKEN=$SONARQUBE_TOKEN \
  -e SONARQUBE_PROJECT_KEY=$SONARQUBE_PROJECT_KEY \
  -v $(pwd):/output \
  sonarqube-fixer --output /output/issues.json
```

---

## ✅ Verification Checklist

After installation, verify everything works:

- [ ] Python 3.7+ installed: `python3 --version`
- [ ] Scripts are executable: `ls -la scripts/*.py`
- [ ] Dependencies installed: `pip list | grep requests`
- [ ] SONARQUBE_TOKEN set: `echo $SONARQUBE_TOKEN`
- [ ] SONARQUBE_PROJECT_KEY set: `echo $SONARQUBE_PROJECT_KEY`
- [ ] GITHUB_TOKEN set: `echo $GITHUB_TOKEN`
- [ ] Can read documentation: `ls -la *.md`
- [ ] Test API connection: `python3 scripts/fetch_issues.py --help`

### Quick Test

```bash
# Test with public SonarCloud project
python3 scripts/fetch_issues.py \
  --host https://sonarcloud.io \
  --token $SONARQUBE_TOKEN \
  --project myorg_myproject \
  --output test-issues.json

# Should create test-issues.json with issues
ls -la test-issues.json
wc -l test-issues.json
```

---

## 🚀 First Run

### Run 1: Fetch Issues
```bash
python3 scripts/fetch_issues.py \
  --host https://sonarcloud.io \
  --token $SONARQUBE_TOKEN \
  --project owner_repo
```

**Expected output**:
```
Fetching issues from https://sonarcloud.io for project owner_repo...
✓ Found 12 critical/blocker issues
✓ Saved 12 issues to issues.json

=== Summary ===
Total issues: 12

By Severity:
  CRITICAL: 8
  BLOCKER: 4

By Type:
  BUG: 6
  VULNERABILITY: 4
  CODE_SMELL: 2

Top 5 Rules:
  java:S2095: 3
  java:S3649: 2
  java:S1104: 2
  java:S2259: 2
  java:S1166: 1
```

### Run 2: Analyze Issues
```bash
python3 scripts/analyze_issue.py --issues issues.json
```

**Expected output**:
```
Analyzing 12 issues...
✓ Analysis saved to analysis.json

=== Analysis Summary ===
Total Issues: 12
Auto-fixable: 8
Guided Fix: 3
Manual Review: 1

=== Top Auto-Fixable Issues ===
- java:S2095: Close this resource (src/main/java/App.java:42)...
- java:S3649: SQL injection (src/main/java/Query.java:15)...
- java:S1104: Remove unused field (src/main/java/Model.java:8)...
- java:S1166: Exception not logged (src/main/java/Handler.java:22)...
- java:S100: Method naming (src/main/java/Service.java:45)...
```

### Run 3: Review Analysis
```bash
# View analysis results
cat analysis.json | python3 -m json.tool

# Or use jq if available
jq '.details.autoFixable[0]' analysis.json
```

---

## 📋 Configuration Files

### config.json (Optional)
```json
{
  "sonarqube": {
    "host": "https://sonarcloud.io",
    "projectKey": "owner_repo"
  },
  "filtering": {
    "severities": ["BLOCKER", "CRITICAL"],
    "types": ["BUG", "VULNERABILITY"],
    "maxIssues": 50
  },
  "output": {
    "format": "json",
    "includeSourceCode": true,
    "includeRuleDetails": true
  }
}
```

### .gitignore Entries
```
# Secrets
.env
.env.local
*.key
*.pem

# Output files (optional - add if needed)
issues.json
analysis.json
fixes.json

# IDE
.vscode/
.idea/
*.swp
```

---

## 🐛 Troubleshooting Installation

### Issue: "python3: command not found"
**Solution**: Install Python 3.7+
```bash
# macOS
brew install python3

# Ubuntu/Debian
sudo apt-get install python3 python3-pip

# Windows
# Download from python.org or use Windows Store
```

### Issue: "ModuleNotFoundError: No module named 'requests'"
**Solution**: Install requests
```bash
pip install requests
# or
pip3 install requests
```

### Issue: "Permission denied" running scripts
**Solution**: Make executable
```bash
chmod +x scripts/*.py
```

### Issue: "SONARQUBE_TOKEN: not found"
**Solution**: Export environment variables
```bash
export SONARQUBE_TOKEN="your-token"
export SONARQUBE_PROJECT_KEY="owner_repo"

# Verify
echo $SONARQUBE_TOKEN
```

### Issue: "Cannot connect to SonarQube"
**Solution**: Check credentials and network
```bash
# Test connection
curl -H "Authorization: Bearer $SONARQUBE_TOKEN" \
  https://sonarcloud.io/api/components/show?component=$SONARQUBE_PROJECT_KEY

# Should return valid JSON
```

---

## 🔄 Updating the Skill

### Update from Source
```bash
# Get latest version
git clone https://github.com/your-repo/sonarqube-fixer-skill.git

# Backup old version
mv ~/.claude/skills/sonarqube-fixer-skill ~/.claude/skills/sonarqube-fixer-skill.bak

# Install new version
cp -r sonarqube-fixer-skill ~/.claude/skills/
```

### Update Scripts Only
```bash
# Get latest scripts
wget https://raw.githubusercontent.com/.../scripts/fetch_issues.py
wget https://raw.githubusercontent.com/.../scripts/analyze_issue.py

# Update
mv fetch_issues.py scripts/
mv analyze_issue.py scripts/
```

---

## 📚 Next Steps

1. **Read README.md** - User guide (5 min)
2. **Read SKILL.md** - Complete documentation (20 min)
3. **Run first example** - Test on sample project (10 min)
4. **Review test cases** - See TEST_CASES.md (10 min)
5. **Set up workflow** - Follow github-actions-setup.md (15 min)

---

## 🆘 Support & Help

### Documentation
- README.md - Quick start
- SKILL.md - Complete guide
- QUICK_REFERENCE.md - Command reference
- TEST_CASES.md - Examples

### Verification
```bash
# Check installation
python3 scripts/fetch_issues.py --help
python3 scripts/analyze_issue.py --help

# Test API access
python3 scripts/fetch_issues.py \
  --host https://sonarcloud.io \
  --token $SONARQUBE_TOKEN \
  --project test_project
```

### Common Issues
See **Troubleshooting Installation** section above

---

**Version**: 1.0 | **Last Updated**: 2024
