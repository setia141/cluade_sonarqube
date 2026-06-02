#!/usr/bin/env python3
"""
Analyze SonarQube issues and suggest fixes
Usage: python3 analyze_issue.py --issues issues.json --output analysis.json
"""

import argparse
import json
import re
import sys
from typing import Dict, List, Any, Optional


class JavaIssueAnalyzer:
    """Analyze Java SonarQube issues and suggest fixes"""
    
    # Common issue patterns and their fixes
    ISSUE_FIXES = {
        "java:S1104": {
            "title": "Remove unused private field",
            "category": "Code Quality",
            "severity": "MAJOR",
            "fixStrategy": "Remove the unused field declaration",
            "autoFixPossible": True,
            "fixTemplate": """
// BEFORE:
private String fieldName;

// AFTER:
// Field removed - it was unused

// Steps:
// 1. Verify the field is not used anywhere in the class
// 2. Remove the field declaration
// 3. Run tests to ensure nothing breaks
            """,
            "pattern": r"private\s+(\w+)\s+(\w+)\s*;",
        },
        "java:S1481": {
            "title": "Remove unused local variable",
            "category": "Code Quality",
            "severity": "MINOR",
            "fixStrategy": "Remove the unused variable declaration",
            "autoFixPossible": True,
            "fixTemplate": """
// BEFORE:
String unused = "value";
doSomething();

// AFTER:
doSomething();

// Steps:
// 1. Verify the variable is not used
// 2. Delete the variable declaration
// 3. Test the affected method
            """,
        },
        "java:S2095": {
            "title": "Resources should be closed",
            "category": "Security/Reliability",
            "severity": "CRITICAL",
            "fixStrategy": "Use try-with-resources statement",
            "autoFixPossible": True,
            "fixTemplate": """
// BEFORE:
FileInputStream fis = new FileInputStream(path);
byte[] data = new byte[1024];
fis.read(data);

// AFTER:
try (FileInputStream fis = new FileInputStream(path)) {
    byte[] data = new byte[1024];
    fis.read(data);
}
// fis automatically closed

// Steps:
// 1. Identify the Closeable/AutoCloseable resource
// 2. Wrap instantiation in try-with-resources (try (...) { ... })
// 3. Move resource creation to try statement
// 4. Run tests to verify behavior unchanged
            """,
        },
        "java:S2259": {
            "title": "Null pointer dereference",
            "category": "Security/Reliability",
            "severity": "CRITICAL",
            "fixStrategy": "Add null checks before dereferencing",
            "autoFixPossible": True,
            "fixTemplate": """
// BEFORE:
public String getName(User user) {
    return user.getProfile().getName();
}

// AFTER - Option 1: Null checks
public String getName(User user) {
    if (user == null || user.getProfile() == null) {
        return null;
    }
    return user.getProfile().getName();
}

// AFTER - Option 2: Optional (Java 8+)
public String getName(User user) {
    return Optional.ofNullable(user)
        .map(User::getProfile)
        .map(Profile::getName)
        .orElse(null);
}

// Steps:
// 1. Identify the potential null variable
// 2. Check method contract - should it accept null?
// 3. Add defensive null checks or use Optional
// 4. Test with null inputs
            """,
        },
        "java:S3649": {
            "title": "SQL injection vulnerability",
            "category": "Security",
            "severity": "BLOCKER",
            "fixStrategy": "Use parameterized queries (PreparedStatement)",
            "autoFixPossible": True,
            "fixTemplate": """
// BEFORE - VULNERABLE:
String query = "SELECT * FROM users WHERE id = " + userId;
ResultSet rs = statement.executeQuery(query);

// AFTER - FIXED:
String query = "SELECT * FROM users WHERE id = ?";
PreparedStatement stmt = connection.prepareStatement(query);
stmt.setInt(1, userId);
ResultSet rs = stmt.executeQuery();

// Steps:
// 1. Replace string concatenation with ? placeholders
// 2. Use PreparedStatement instead of Statement
// 3. Use setXxx() methods to set parameter values
// 4. Test with various inputs including special characters
            """,
        },
        "java:S2115": {
            "title": "Hardcoded credentials",
            "category": "Security",
            "severity": "BLOCKER",
            "fixStrategy": "Use environment variables or config files",
            "autoFixPossible": False,  # Requires manual judgment
            "fixTemplate": """
// BEFORE - VULNERABLE:
String apiKey = "sk_live_1234567890";
String dbPassword = "admin123";

// AFTER - Option 1: Environment variables
String apiKey = System.getenv("API_KEY");
String dbPassword = System.getenv("DB_PASSWORD");

// AFTER - Option 2: Properties file
Properties props = new Properties();
props.load(new FileInputStream("config.properties"));
String apiKey = props.getProperty("api.key");

// AFTER - Option 3: Spring Configuration
@Value("${api.key}")
private String apiKey;

// Steps:
// 1. Create .gitignore entry for config files
// 2. Move credentials to environment variables or config
// 3. Update code to read from configuration
// 4. Update deployment to set environment variables
// 5. Rotate all exposed credentials
            """,
        },
        "java:S100": {
            "title": "Method name should follow conventions",
            "category": "Code Quality",
            "severity": "MINOR",
            "fixStrategy": "Rename method to camelCase",
            "autoFixPossible": True,
            "fixTemplate": """
// BEFORE:
public void process_data() { ... }

// AFTER:
public void processData() { ... }

// Steps:
// 1. Use IDE refactoring: Right-click → Refactor → Rename
// 2. Confirm all references are updated
// 3. Run tests to ensure no breakage
// 4. Follow camelCase convention: methodName()
            """,
        },
        "java:S101": {
            "title": "Class name should follow conventions",
            "category": "Code Quality",
            "severity": "MINOR",
            "fixStrategy": "Rename class to PascalCase",
            "autoFixPossible": True,
            "fixTemplate": """
// BEFORE:
public class userManager { ... }

// AFTER:
public class UserManager { ... }

// Steps:
// 1. Use IDE refactoring: Right-click → Refactor → Rename
// 2. IDE automatically updates all references
// 3. Update filename to match class name
// 4. Run full test suite
// 5. Follow PascalCase convention: ClassName
            """,
        },
        "java:S1143": {
            "title": "Code duplication detected",
            "category": "Code Quality",
            "severity": "MAJOR",
            "fixStrategy": "Extract duplicated code to shared method",
            "autoFixPossible": False,  # Requires judgment on how to refactor
            "fixTemplate": """
// BEFORE - Duplicated code:
public void processOrderA(Order order) {
    validate(order);
    save(order);
    notify(order);
}

public void processOrderB(Order order) {
    validate(order);
    save(order);
    notify(order);
}

// AFTER - Extracted:
public void processOrder(Order order) {
    validate(order);
    save(order);
    notify(order);
}

public void processOrderA(Order order) {
    processOrder(order);
}

public void processOrderB(Order order) {
    processOrder(order);
}

// Steps:
// 1. Identify the duplicate code blocks
// 2. Verify they have identical logic
// 3. Extract to a new method with appropriate name
// 4. Update callers to use extracted method
// 5. Test all paths
            """,
        },
        "java:S1166": {
            "title": "Exception caught but not logged",
            "category": "Reliability",
            "severity": "MAJOR",
            "fixStrategy": "Log the exception or re-throw",
            "autoFixPossible": True,
            "fixTemplate": """
// BEFORE - Silent catch:
try {
    riskyOperation();
} catch (IOException e) {
    // Silent - problem hidden
}

// AFTER - Option 1: Log and re-throw
try {
    riskyOperation();
} catch (IOException e) {
    log.error("Operation failed", e);
    throw new RuntimeException("Failed to complete operation", e);
}

// AFTER - Option 2: Log and handle
try {
    riskyOperation();
} catch (IOException e) {
    log.warn("Operation failed, using fallback", e);
    return getFallbackResult();
}

// Steps:
// 1. Determine if exception should be logged
// 2. Add log.error/warn/info with context
// 3. Re-throw if caller should handle, or handle here
// 4. Include the exception in error message
// 5. Test error paths
            """,
        },
        "java:S4790": {
            "title": "Weak encryption algorithm",
            "category": "Security",
            "severity": "CRITICAL",
            "fixStrategy": "Use strong algorithm (AES, SHA-256)",
            "autoFixPossible": False,  # Context-dependent
            "fixTemplate": """
// BEFORE - Weak:
MessageDigest md = MessageDigest.getInstance("MD5");
Cipher cipher = Cipher.getInstance("DES");

// AFTER - Strong:
// For hashing passwords:
BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();
String hashedPassword = encoder.encode(password);

// For general hashing:
MessageDigest md = MessageDigest.getInstance("SHA-256");

// For encryption:
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
SecretKey key = new SecretKeySpec(keyBytes, 0, keyBytes.length, "AES");
GCMParameterSpec spec = new GCMParameterSpec(128, ivBytes);
cipher.init(Cipher.ENCRYPT_MODE, key, spec);

// Steps:
// 1. Identify the weak algorithm
// 2. Choose strong replacement (SHA-256, AES)
// 3. For passwords, use bcrypt or Argon2
// 4. Update key generation to proper length
// 5. Test encryption/decryption
// 6. Review security best practices
            """,
        },
    }
    
    def analyze_issue(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a single issue and return suggestions
        """
        rule_key = issue.get("rule", "")
        
        analysis = {
            "issueKey": issue.get("key"),
            "rule": rule_key,
            "severity": issue.get("severity"),
            "type": issue.get("type"),
            "message": issue.get("mainLocation", {}).get("message", ""),
            "file": issue.get("mainLocation", {}).get("file", ""),
            "line": issue.get("mainLocation", {}).get("startLine"),
            "explanation": issue.get("ruleDetails", {}).get("htmlDesc", ""),
        }
        
        # Look up fix information
        if rule_key in self.ISSUE_FIXES:
            fix_info = self.ISSUE_FIXES[rule_key]
            analysis["fixAvailable"] = True
            analysis["fixTitle"] = fix_info["title"]
            analysis["fixCategory"] = fix_info["category"]
            analysis["fixSeverity"] = fix_info["severity"]
            analysis["fixStrategy"] = fix_info["fixStrategy"]
            analysis["autoFixPossible"] = fix_info["autoFixPossible"]
            analysis["fixTemplate"] = fix_info["fixTemplate"]
            analysis["estimatedEffort"] = self._estimate_effort(rule_key)
        else:
            analysis["fixAvailable"] = False
            analysis["requiresManualReview"] = True
        
        return analysis
    
    def _estimate_effort(self, rule_key: str) -> str:
        """Estimate effort to fix based on rule"""
        effort_map = {
            "java:S1104": "5 min",
            "java:S1481": "5 min",
            "java:S100": "10 min",  # Requires testing
            "java:S101": "15 min",  # Class rename affects multiple files
            "java:S2095": "20 min",  # Requires testing
            "java:S2259": "30 min",  # May require design changes
            "java:S3649": "30 min",  # Security fix, needs thorough testing
            "java:S2115": "45 min",  # Infrastructure setup needed
            "java:S1143": "60 min",  # Complex refactoring
            "java:S4790": "45 min",  # Crypto is complex
        }
        return effort_map.get(rule_key, "1 hour")
    
    def categorize_issues(self, issues: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
        """Categorize issues by complexity"""
        categorized = {
            "autoFixable": [],
            "guidedFix": [],
            "manualReview": [],
        }
        
        for issue in issues:
            analysis = self.analyze_issue(issue)
            
            if not analysis.get("fixAvailable"):
                categorized["manualReview"].append(analysis)
            elif analysis.get("autoFixPossible"):
                categorized["autoFixable"].append(analysis)
            else:
                categorized["guidedFix"].append(analysis)
        
        return categorized


def main():
    parser = argparse.ArgumentParser(description="Analyze SonarQube issues")
    parser.add_argument(
        "--issues",
        default="issues.json",
        help="Input issues JSON file"
    )
    parser.add_argument(
        "--output",
        default="analysis.json",
        help="Output analysis JSON file"
    )
    
    args = parser.parse_args()
    
    # Load issues
    try:
        with open(args.issues) as f:
            issues = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find {args.issues}", file=sys.stderr)
        sys.exit(1)
    
    # Analyze
    analyzer = JavaIssueAnalyzer()
    print(f"Analyzing {len(issues)} issues...")
    
    analyses = []
    for issue in issues:
        analysis = analyzer.analyze_issue(issue)
        analyses.append(analysis)
    
    # Categorize
    categorized = analyzer.categorize_issues(analyses)
    
    # Write output
    output = {
        "totalIssues": len(issues),
        "analyses": analyses,
        "categorized": {
            "autoFixable": len(categorized["autoFixable"]),
            "guidedFix": len(categorized["guidedFix"]),
            "manualReview": len(categorized["manualReview"]),
        },
        "details": categorized,
    }
    
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"✓ Analysis saved to {args.output}")
    
    # Print summary
    print("\n=== Analysis Summary ===")
    print(f"Total Issues: {len(issues)}")
    print(f"Auto-fixable: {len(categorized['autoFixable'])}")
    print(f"Guided Fix: {len(categorized['guidedFix'])}")
    print(f"Manual Review: {len(categorized['manualReview'])}")
    
    print("\n=== Top Auto-Fixable Issues ===")
    for analysis in categorized["autoFixable"][:5]:
        print(f"- {analysis['rule']}: {analysis['message'][:60]}...")


if __name__ == "__main__":
    main()
