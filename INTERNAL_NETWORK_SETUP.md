# Internal SonarQube Access (Token-less Setup)

This guide explains how to use the skill with **internal SonarQube instances** where token-less API access is available.

## 🎯 When to Use This Guide

Use this setup if:
- ✅ Your SonarQube is on your internal network
- ✅ You can access SonarQube APIs without authentication
- ✅ Network-level authentication is configured (Kerberos, LDAP, etc.)
- ✅ You don't need API tokens

This is **much simpler** than token-based authentication!

---

## 🚀 Quick Start (Token-less)

### Step 1: No Token Needed! 🎉
```bash
# You don't need to export SONARQUBE_TOKEN
# Just set the host and project key
```

### Step 2: Set Environment Variables
```bash
export SONARQUBE_HOST_URL="http://your-internal-sonarqube:9000"
export SONARQUBE_PROJECT_KEY="myproject"
```

### Step 3: Run the Script (No Token Required)
```bash
python3 scripts/fetch_issues.py \
  --host http://your-internal-sonarqube:9000 \
  --project myproject
  # Notice: NO --token parameter needed!
```

That's it! 🎊

---

## 📋 Command Examples

### Example 1: Fetch All Critical Issues (No Token)
```bash
python3 scripts/fetch_issues.py \
  --host http://sonarqube.internal.com:9000 \
  --project my-java-app
```

### Example 2: Fetch with Enrichment (No Token)
```bash
python3 scripts/fetch_issues.py \
  --host http://sonarqube.internal.com:9000 \
  --project my-java-app \
  --enrich
```

### Example 3: Custom Filters (No Token)
```bash
python3 scripts/fetch_issues.py \
  --host http://sonarqube.internal.com:9000 \
  --project my-java-app \
  --severities CRITICAL \
  --types BUG,VULNERABILITY
```

---

## 🔍 Verify Your Setup

### Test Connection
```bash
# Test if you can access SonarQube without token
curl http://your-sonarqube:9000/api/components/show?component=myproject

# If you get valid JSON response, you're good to go!
# If you get 401 error, you need a token
```

### Test with Script
```bash
python3 scripts/fetch_issues.py \
  --host http://your-sonarqube:9000 \
  --project myproject

# If it works without token, you're set!
```

---

## 🔧 Configuration for Internal Networks

### Scenario 1: Basic Internal Access
```bash
# Just host + project (easiest!)
python3 scripts/fetch_issues.py \
  --host http://sonarqube.local:9000 \
  --project team-project
```

### Scenario 2: HTTPS Internal
```bash
# Use HTTPS if your internal SonarQube has it
python3 scripts/fetch_issues.py \
  --host https://sonarqube.internal.com \
  --project team-project
```

### Scenario 3: Non-Standard Port
```bash
# If SonarQube is on custom port
python3 scripts/fetch_issues.py \
  --host http://sonarqube.company.com:8080 \
  --project team-project
```

### Scenario 4: With Token (Fallback)
```bash
# If internal access requires token, just add it
python3 scripts/fetch_issues.py \
  --host http://sonarqube.internal.com:9000 \
  --project team-project \
  --token your-token
  # Token is optional, use only if needed
```

---

## 🐳 Docker / Network-Based Auth

If your internal network uses:
- **Kerberos** authentication
- **LDAP** integration
- **NTLM** (Windows)
- **SAML** with AD

The script will work automatically without tokens because:
1. Your network credentials are already authenticated
2. SonarQube recognizes your network identity
3. No additional tokens needed

---

## 📊 Performance Benefits

Token-less access is actually **better** for internal networks:

| Aspect | Token-less | Token-based |
|--------|-----------|------------|
| Setup Time | 2 minutes | 10 minutes |
| Configuration | Minimal | Token mgmt |
| Security | Network-based | Token-based |
| Network Overhead | Slightly lower | Slightly higher |
| Maintenance | None | Token rotation |

---

## ✅ Setup Checklist

- [ ] SonarQube is accessible from your network
- [ ] You can open `http://sonarqube-host:9000` in browser
- [ ] You know your project key
- [ ] Python 3.7+ is installed
- [ ] `requests` library is installed: `pip install requests`
- [ ] Run script without `--token` parameter

---

## 🚀 GitHub Actions (Token-less)

If you're using GitHub Actions with internal SonarQube:

```yaml
name: SonarQube Analyze
on: [push]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run SonarQube Analysis
        run: |
          python3 scripts/fetch_issues.py \
            --host http://sonarqube.internal.com:9000 \
            --project myproject
        env:
          # No token needed!
          # Just make sure GitHub Actions can reach internal SonarQube
```

**Note**: GitHub Actions must be able to reach your internal SonarQube. This may require:
- VPN connection
- Self-hosted runner
- Network proxy configuration

---

## 🔐 Security Notes for Internal Access

### ✅ Best Practices
- Use HTTPS if available (even internally)
- Keep SonarQube URL in environment variables
- Don't commit SonarQube URL to public repos
- Use network segmentation
- Monitor API access logs

### Network-Level Security
Since you're not using tokens, rely on:
- Network firewall rules
- VPN/internal access only
- Kerberos/LDAP authentication
- Network monitoring
- Active Directory integration (if applicable)

---

## 🆘 Troubleshooting

### Issue: "Connection refused"
```bash
# Check if SonarQube is accessible
curl http://sonarqube-host:9000/api/system/status

# If fails, verify:
# 1. SonarQube is running
# 2. Correct host/port
# 3. Network connectivity
# 4. Firewall rules
```

### Issue: "401 Unauthorized"
```bash
# Token-less access failed, need token
python3 scripts/fetch_issues.py \
  --host http://sonarqube.internal.com:9000 \
  --project myproject \
  --token your-token
```

### Issue: "Project not found"
```bash
# Verify project key is correct
curl http://sonarqube-host:9000/api/components/search?q=myproject

# Get correct key and use it
```

### Issue: "No issues found"
```bash
# Check if:
# 1. SonarQube analysis has completed
# 2. Project has critical/blocker issues
# 3. Correct project key is used
```

---

## 🔍 Finding Your Project Key

If you don't know your project key:

### Method 1: Via Browser
1. Go to `http://sonarqube-host:9000`
2. Click on your project
3. Look at the URL: `key=project-key`
4. Or check project settings

### Method 2: Via API
```bash
# List all projects
curl http://sonarqube-host:9000/api/components/search

# Find your project and note its key
```

### Method 3: Via Script
```bash
# This will show you available projects
python3 << 'EOF'
import requests
response = requests.get('http://sonarqube-host:9000/api/components/search')
projects = response.json()['components']
for p in projects:
    print(f"{p['name']} => key: {p['key']}")
EOF
```

---

## 📝 Environment Setup

### Bash (macOS/Linux)
```bash
# Add to ~/.bashrc or ~/.zshrc
export SONARQUBE_HOST_URL="http://sonarqube.internal.com:9000"
export SONARQUBE_PROJECT_KEY="myproject"

# No token needed!
source ~/.bashrc
```

### PowerShell (Windows)
```powershell
# Add to profile
[Environment]::SetEnvironmentVariable("SONARQUBE_HOST_URL", "http://sonarqube.internal.com:9000", "User")
[Environment]::SetEnvironmentVariable("SONARQUBE_PROJECT_KEY", "myproject", "User")

# Reload PowerShell
```

### .env File
```bash
# Create .env in project directory
cat > .env << 'EOF'
SONARQUBE_HOST_URL=http://sonarqube.internal.com:9000
SONARQUBE_PROJECT_KEY=myproject
# No token needed!
EOF

# Load it
source .env
```

---

## 🎯 Common Internal Network Setups

### Setup 1: Same Corporate Network
```bash
# Simplest setup
python3 scripts/fetch_issues.py \
  --host http://sonarqube.company.com:9000 \
  --project my-app
```

### Setup 2: VPN Required
```bash
# Make sure VPN is connected, then:
python3 scripts/fetch_issues.py \
  --host http://internal-sonarqube:9000 \
  --project my-app
```

### Setup 3: Self-Hosted with AD
```bash
# Active Directory authenticated SonarQube
# Your AD login = automatic access
python3 scripts/fetch_issues.py \
  --host https://sonarqube.domain.local \
  --project my-app
```

### Setup 4: Docker Network
```bash
# If SonarQube is in Docker on same network
python3 scripts/fetch_issues.py \
  --host http://sonarqube-container:9000 \
  --project my-app
```

---

## 🚀 Next Steps

1. ✅ Verify network access to SonarQube
2. ✅ Find your project key
3. ✅ Run script without token
4. ✅ Check `issues.json` for results
5. ✅ Run analysis: `python3 scripts/analyze_issue.py`

---

## 💡 Pro Tips

1. **Network Access**: Make sure your machine can reach SonarQube
2. **Project Key**: Use correct key from SonarQube dashboard
3. **Enrichment**: Use `--enrich` to get more details
4. **Caching**: Results are saved to `issues.json`
5. **Automation**: Add to cron/Task Scheduler for regular runs

---

## Summary

**For internal network access:**
- ✅ No token needed!
- ✅ Simpler setup
- ✅ Network-based auth
- ✅ Just host + project key
- ✅ Same performance, less configuration

**You're all set to use the skill!** 🎉

---

**Enjoy token-less SonarQube integration!**
