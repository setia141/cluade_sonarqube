# ⚡ Internal Network Quick Start

## 🎯 Your Situation
✅ Internal SonarQube instance  
✅ Direct API access (no token needed)  
✅ Network-level authentication

## 🚀 Setup (3 Steps)

### Step 1: Find Your SonarQube Host
```bash
# Your internal SonarQube URL
# Example: http://sonarqube.company.com:9000
# Example: http://sonarqube.internal:9000
# Example: http://192.168.x.x:9000
```

### Step 2: Find Your Project Key
```bash
# Open browser: http://your-sonarqube:9000
# Click on your project
# Check URL or project settings for key
# Example: my-java-app
```

### Step 3: Run (No Token!)
```bash
python3 scripts/fetch_issues.py \
  --host http://your-sonarqube:9000 \
  --project your-project-key
```

**That's it!** ✅

---

## 📋 Real Examples

### Example 1: Fetch Issues
```bash
python3 scripts/fetch_issues.py \
  --host http://sonarqube.company.com:9000 \
  --project team-app
```

### Example 2: With Enrichment
```bash
python3 scripts/fetch_issues.py \
  --host http://sonarqube.company.com:9000 \
  --project team-app \
  --enrich
```

### Example 3: Analyze
```bash
python3 scripts/analyze_issue.py \
  --issues issues.json
```

---

## 🔍 Test Connection

```bash
# Test if you can access without token
curl http://your-sonarqube:9000/api/system/status

# Should return JSON like:
# {"id":"...", "version":"..."}
```

---

## ✅ What Changed

The skill now supports **token-less access**:
- ✅ `--token` parameter is **optional**
- ✅ Works with internal network auth
- ✅ Same functionality, simpler setup
- ✅ Backward compatible with tokens

---

## 📚 Full Documentation

See **INTERNAL_NETWORK_SETUP.md** in the zip for:
- Detailed configuration
- Troubleshooting
- GitHub Actions setup
- Multiple network scenarios
- Docker examples

---

## 💡 Pro Tips

1. **Test first**: `curl http://sonarqube:9000/api/system/status`
2. **Know your key**: Check project settings
3. **Environment vars**: Create `.env` file
4. **Automate**: Add to cron for daily scans
5. **Monitor**: Review results regularly

---

## 🎊 Summary

**For internal SonarQube:**
```bash
# Just 2 parameters needed!
--host http://sonarqube:9000
--project project-key

# No token required! 🎉
```

**Get started now!**
