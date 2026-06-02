---
name: sonarqube-java-fixer-test-cases
description: Test cases for the SonarQube Java Fixer skill
---

# Test Cases for SonarQube Java Fixer Skill

This file contains test cases to verify the skill works correctly.

## Test Case 1: Fetch Critical Issues

**Prompt**: "I have a Java project in SonarCloud called 'myorg_myapp'. Can you fetch all the critical and blocker SonarQube issues using the API and provide a summary?"

**Expected Output**:
- ✅ Connected to SonarCloud API
- ✅ Retrieved issues filtered by CRITICAL/BLOCKER severity
- ✅ Listed issues with rule names and descriptions
- ✅ Categorized by issue type (BUG, VULNERABILITY, CODE_SMELL)
- ✅ Provided actionable summary

**Success Criteria**:
- Calls `fetch_issues.py` with correct parameters
- Returns JSON structure with issues array
- Includes severity, type, line number, and file path
- Shows count breakdown by category

---

## Test Case 2: Analyze Issues for Fixes

**Prompt**: "Here's my SonarQube issues JSON. Analyze these issues and tell me which ones can be automatically fixed, which need guided fixes, and which require manual review."

**Expected Output**:
- ✅ Parsed issues correctly
- ✅ Identified which issues have automated fixes available
- ✅ Provided fix templates for each issue
- ✅ Estimated effort for each fix
- ✅ Categorized by fix complexity

**Success Criteria**:
- Calls `analyze_issue.py` appropriately
- Returns categorization with counts
- Provides specific fix strategies
- Includes code examples (before/after)
- Estimates time to implement

---

## Test Case 3: Provide Fix for SQL Injection (S3649)

**Prompt**: "My SonarQube found a SQL injection vulnerability in my code. Can you explain the issue and provide a detailed fix with code examples?"

**Expected Output**:
- ✅ Explained SQL injection risk
- ✅ Showed vulnerable code pattern
- ✅ Provided fixed code using PreparedStatement
- ✅ Explained parameterized queries
- ✅ Included testing recommendations

**Success Criteria**:
- Identifies issue as java:S3649
- Shows before/after code
- Explains why fix resolves the issue
- Provides multiple approaches (if applicable)
- Includes security best practices

---

## Test Case 4: Suggest Fix for Null Pointer Exception (S2259)

**Prompt**: "My Java code has a potential null pointer dereference. How can I fix this SonarQube issue?"

**Expected Output**:
- ✅ Explained null pointer risk
- ✅ Showed vulnerable code
- ✅ Provided multiple fix options (null checks vs Optional)
- ✅ Explained pros/cons of each approach
- ✅ Recommended best practice

**Success Criteria**:
- Identifies pattern in provided code
- Shows before/after examples
- Explains Optional approach (Java 8+)
- Shows defensive null checking
- Provides testing strategy for null cases

---

## Test Case 5: Provide Guidance for Resource Leak (S2095)

**Prompt**: "I have resource leak warnings from SonarQube. What's the proper way to fix FileInputStream and Connection resources?"

**Expected Output**:
- ✅ Explained resource leak risk
- ✅ Showed try-finally vs try-with-resources
- ✅ Recommended try-with-resources (modern Java)
- ✅ Provided working code examples
- ✅ Included best practices

**Success Criteria**:
- Identifies issue as java:S2095
- Shows try-with-resources syntax
- Explains AutoCloseable interface
- Provides multiple patterns
- Includes testing guidance

---

## Test Case 6: GitHub Actions Integration

**Prompt**: "How do I integrate this skill into my GitHub Actions workflow to automatically fix SonarQube issues and create PRs?"

**Expected Output**:
- ✅ Provided complete workflow YAML
- ✅ Showed environment variable setup
- ✅ Explained how to configure SonarQube token
- ✅ Provided PR creation logic
- ✅ Included trigger conditions

**Success Criteria**:
- References appropriate documentation file
- Provides working workflow example
- Explains each step clearly
- Shows how to handle PR creation
- Includes error handling

---

## Test Case 7: Categorize Mixed Issues

**Prompt**: "Analyze these SonarQube issues: java:S2095, java:S3649, java:S1104, java:S2115, and java:S1143. Which can be auto-fixed?"

**Expected Output**:
- ✅ S2095 (Resource Leak): Auto-fixable
- ✅ S3649 (SQL Injection): Auto-fixable
- ✅ S1104 (Unused Field): Auto-fixable
- ✅ S2115 (Hardcoded Credentials): Requires manual review
- ✅ S1143 (Code Duplication): Requires guided fix

**Success Criteria**:
- Correctly categorizes each issue
- Explains reasoning for categorization
- Provides effort estimates
- Shows applicable fix templates
- Recommends approach for each

---

## Test Case 8: Compare Multiple Solutions

**Prompt**: "For the S2259 null pointer exception, I see two approaches: adding null checks and using Optional. Which should I use?"

**Expected Output**:
- ✅ Compared both approaches
- ✅ Null checks: Traditional, compatible with old Java
- ✅ Optional: Modern, functional style (Java 8+)
- ✅ Recommended for each context
- ✅ Provided decision framework

**Success Criteria**:
- Provides balanced comparison
- Shows code for both approaches
- Explains trade-offs
- Recommends based on context (Java version, team preference)
- Includes testing strategy for both

---

## Test Case 9: Handle Unknown Rule

**Prompt**: "SonarQube reported issue 'java:S9999' which I've never seen. Can you help?"

**Expected Output**:
- ✅ Acknowledged unknown rule
- ✅ Checked SonarQube API for rule details
- ✅ Provided available information
- ✅ Suggested next steps
- ✅ Offered general debugging guidance

**Success Criteria**:
- Handles unknown rules gracefully
- Attempts to fetch details from API
- Provides fallback information
- Suggests where to find documentation
- Doesn't make up rule details

---

## Test Case 10: Create PR with Multiple Fixes

**Prompt**: "Create a PR that fixes all the auto-fixable SonarQube issues in my Java project (myorg/myapp). Include a detailed commit message explaining each fix."

**Expected Output**:
- ✅ Created feature branch
- ✅ Applied automated fixes
- ✅ Created meaningful commit message
- ✅ Pushed to GitHub
- ✅ Opened PR with description

**Success Criteria**:
- Branch name includes "sonarqube/fixes"
- Commit message references each fix
- PR description lists issues fixed
- PR includes testing instructions
- PR is draft/ready for review

---

## Test Case 11: Estimate Effort and Impact

**Prompt**: "I found 15 SonarQube critical issues. How long will it take to fix them all?"

**Expected Output**:
- ✅ Broke down by issue type
- ✅ Estimated time for each fix
- ✅ Total estimated effort
- ✅ Suggested prioritization
- ✅ Recommended approach (batch vs iterative)

**Success Criteria**:
- Provides effort estimate per issue
- Calculates total effort
- Considers dependencies between fixes
- Recommends prioritization strategy
- Suggests batch size for PR(s)

---

## Test Case 12: Security-Focused Analysis

**Prompt**: "Which of my SonarQube issues are security vulnerabilities? Prioritize by risk level."

**Expected Output**:
- ✅ Filtered for VULNERABILITY type
- ✅ Prioritized by severity (BLOCKER > CRITICAL > MAJOR)
- ✅ Provided risk explanations
- ✅ Included compliance implications
- ✅ Recommended immediate vs backlog

**Success Criteria**:
- Identifies all security issues
- Ranks by risk/impact
- Explains security implications
- Suggests CWE/OWASP references
- Recommends fix order

---

## Test Case 13: Naming Convention Fixes

**Prompt**: "SonarQube reported naming convention violations in my code. Can you show me what needs to be changed?"

**Expected Output**:
- ✅ Listed all naming violations (S100, S101, etc.)
- ✅ Showed current vs. correct naming
- ✅ Explained Java naming conventions
- ✅ Provided refactoring strategy
- ✅ Warned about impact on references

**Success Criteria**:
- Identifies specific naming issues
- Shows proper convention
- Explains why convention matters
- Provides IDE refactoring tips
- Lists all affected files/references

---

## Test Case 14: Code Duplication Analysis

**Prompt**: "How do I fix S1143 code duplication issues in my Java code?"

**Expected Output**:
- ✅ Explained code duplication impact
- ✅ Showed duplicated code blocks
- ✅ Suggested extraction strategy
- ✅ Provided refactored example
- ✅ Explained trade-offs

**Success Criteria**:
- Identifies duplication patterns
- Shows before/after code
- Explains extraction technique
- Considers method signatures
- Includes testing strategy

---

## Test Case 15: End-to-End Workflow

**Prompt**: "Walk me through the complete process of fixing SonarQube issues in my Java GitHub project using this skill."

**Expected Output**:
- ✅ Step 1: Setup credentials and tokens
- ✅ Step 2: Fetch issues from SonarQube
- ✅ Step 3: Analyze and categorize
- ✅ Step 4: Review auto-fixable issues
- ✅ Step 5: Apply fixes locally or via PR
- ✅ Step 6: Run tests and validate
- ✅ Step 7: Merge and monitor

**Success Criteria**:
- Provides complete workflow
- Includes all necessary setup steps
- Shows commands/examples
- Explains decision points
- References documentation
- Includes validation/testing steps

---

## Evaluation Criteria

Each test case should be evaluated on:

1. **Accuracy**: Is the information correct?
2. **Completeness**: Are all aspects covered?
3. **Actionability**: Can the user implement the suggestion?
4. **Clarity**: Is it easy to understand?
5. **Timeliness**: Is the response appropriately detailed?

## Notes

- Tests assume Java 8+ environment
- SonarCloud API is used (can adapt for self-hosted)
- GitHub Actions integration is modern (v3+ actions)
- All code examples use Java best practices
