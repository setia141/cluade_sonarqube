# Java SonarQube Issue Patterns & Fixes

This document provides common SonarQube issues found in Java code and their remediation strategies.

## Common Critical/Blocker Issues

### 1. NullPointerException Risk (S2259, S2637)

**Issue**: Potential null pointer dereference without null check

**Before**:
```java
public String getName(User user) {
    return user.getProfile().getName();  // NPE if user or profile is null
}
```

**Fix Strategy**: Add null checks or use Optional
```java
public String getName(User user) {
    if (user == null || user.getProfile() == null) {
        return null;
    }
    return user.getProfile().getName();
}

// OR using Optional (Java 8+)
public String getName(User user) {
    return Optional.ofNullable(user)
        .map(User::getProfile)
        .map(Profile::getName)
        .orElse(null);
}
```

**Automated Fix**: 
- Check method contract: does it accept null?
- Add null checks at method entry
- Or use Objects.requireNonNull() for non-nullable parameters

---

### 2. Resource Leak (S2095, S2093)

**Issue**: Stream/Connection not closed in try-with-resources

**Before**:
```java
public void readFile(String path) throws IOException {
    FileInputStream fis = new FileInputStream(path);
    byte[] data = new byte[1024];
    fis.read(data);  // Resource not closed on exception
}
```

**Fix Strategy**: Use try-with-resources
```java
public void readFile(String path) throws IOException {
    try (FileInputStream fis = new FileInputStream(path)) {
        byte[] data = new byte[1024];
        fis.read(data);
    }
    // fis automatically closed
}

// OR explicit try-finally
public void readFile(String path) throws IOException {
    FileInputStream fis = new FileInputStream(path);
    try {
        byte[] data = new byte[1024];
        fis.read(data);
    } finally {
        fis.close();
    }
}
```

**Automated Fix**:
- Identify Closeable/AutoCloseable resources
- Wrap in try-with-resources statement
- Remove manual close() calls (if present)

---

### 3. SQL Injection (S3649)

**Issue**: String concatenation in SQL queries (not parameterized)

**Before**:
```java
String query = "SELECT * FROM users WHERE id = " + userId;
ResultSet rs = statement.executeQuery(query);  // SQL Injection risk
```

**Fix Strategy**: Use PreparedStatement
```java
String query = "SELECT * FROM users WHERE id = ?";
PreparedStatement stmt = connection.prepareStatement(query);
stmt.setInt(1, userId);
ResultSet rs = stmt.executeQuery();
```

**Automated Fix**:
- Identify direct concatenation in SQL strings
- Convert to parameterized queries
- Replace execute/executeQuery calls with prepared statements

---

### 4. Hardcoded Credentials (S2115, S1313)

**Issue**: Passwords/tokens/secrets hardcoded in source code

**Before**:
```java
String apiKey = "sk_live_1234567890abcdef";
String dbPassword = "admin123";
HttpClient client = new HttpClient(apiKey);
```

**Fix Strategy**: Use environment variables/config files
```java
// Option 1: Environment variables
String apiKey = System.getenv("API_KEY");

// Option 2: Properties file
Properties props = new Properties();
props.load(new FileInputStream("config.properties"));
String apiKey = props.getProperty("api.key");

// Option 3: Spring Configuration (if using Spring)
@Value("${api.key}")
private String apiKey;
```

**Automated Fix**:
- Extract hardcoded strings that look like credentials
- Replace with configuration property access
- Add .gitignore entries for config files

---

### 5. Unused Code (S1104, S1481)

**Issue**: Unused private fields, methods, or variables

**Before**:
```java
public class User {
    private String unused;  // Never used
    
    private void helperMethod() {  // Never called
        // ...
    }
}
```

**Fix Strategy**: Remove unused code
```java
public class User {
    // unused field removed
    // helperMethod() removed
}
```

**Automated Fix**:
- Scan for methods/fields with only private/protected access
- Verify no external callers (check comments, serialization)
- Remove if truly unused

---

### 6. Code Duplication (S1143, S4634)

**Issue**: Similar code blocks repeated multiple times

**Before**:
```java
public void processOrderA(Order order) {
    log.info("Processing order: " + order.getId());
    validate(order);
    save(order);
    notifyUser(order.getUser());
}

public void processOrderB(Order order) {
    log.info("Processing order: " + order.getId());
    validate(order);
    save(order);
    notifyUser(order.getUser());
}
```

**Fix Strategy**: Extract to shared method
```java
public void processOrder(Order order) {
    log.info("Processing order: " + order.getId());
    validate(order);
    save(order);
    notifyUser(order.getUser());
}

public void processOrderA(Order order) {
    processOrder(order);
}

public void processOrderB(Order order) {
    processOrder(order);
}
```

**Automated Fix**:
- Identify similar code blocks
- Extract to common method
- Replace duplicates with method calls
- Use generics/polymorphism where applicable

---

### 7. Exception Handling (S1166, S1147)

**Issue**: Swallowing exceptions silently

**Before**:
```java
try {
    riskyOperation();
} catch (IOException e) {
    // Silent catch - problem hidden
}
```

**Fix Strategy**: Log or re-throw exceptions
```java
try {
    riskyOperation();
} catch (IOException e) {
    log.error("Failed to perform operation", e);
    throw new RuntimeException("Operation failed", e);
}

// OR handle appropriately
try {
    riskyOperation();
} catch (IOException e) {
    log.warn("Operation failed, using fallback", e);
    return getFallbackResult();
}
```

**Automated Fix**:
- Add logging for all caught exceptions
- Re-throw if not handled
- Add comments explaining why exception is caught

---

### 8. Naming Conventions (S100, S101)

**Issue**: Non-standard naming for classes/methods/variables

**Before**:
```java
public class userManager {  // Should be UserManager
    public void process_data() {  // Should be processData
        int userId_value = 123;  // Should be userIdValue
    }
}
```

**Fix Strategy**: Rename to follow conventions
```java
public class UserManager {
    public void processData() {
        int userIdValue = 123;
    }
}
```

**Automated Fix**:
- Use IDE refactoring (Rename) for automated updates
- Update all references automatically
- Test compilation after rename

---

### 9. Security: Weak Cryptography (S5547, S4790)

**Issue**: Using weak encryption algorithms

**Before**:
```java
MessageDigest md = MessageDigest.getInstance("MD5");  // Weak hash
Cipher cipher = Cipher.getInstance("DES");  // Weak encryption
```

**Fix Strategy**: Use strong algorithms
```java
// For hashing: Use SHA-256 or better
MessageDigest md = MessageDigest.getInstance("SHA-256");

// For encryption: Use AES with proper mode
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");

// Even better: Use bcrypt for passwords
BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();
String hashedPassword = encoder.encode(password);
```

**Automated Fix**:
- Replace weak algorithms with modern equivalents
- Add proper key derivation (PBKDF2 for passwords)
- Use strong random number generation

---

### 10. Missing Override Annotation (S4144)

**Issue**: Overridden method without @Override annotation

**Before**:
```java
public class Child extends Parent {
    public void process() {  // Missing @Override
        // ...
    }
}
```

**Fix Strategy**: Add @Override
```java
public class Child extends Parent {
    @Override
    public void process() {
        // ...
    }
}
```

**Automated Fix**:
- Scan for methods matching parent signatures
- Add @Override annotation automatically
- IDE has built-in inspect & fix for this

---

## Fix Generation Script Template

```python
def fix_issue(issue: dict, source_code: str) -> dict:
    """
    Generate fix for a SonarQube issue
    
    Args:
        issue: SonarQube issue dict with key, rule, line, message
        source_code: Full source file content
        
    Returns:
        dict with original, fixed, and explanation
    """
    rule_key = issue['rule']
    line_num = issue['mainLocation']['startLine']
    
    if rule_key == 'java:S1104':  # Unused field
        return fix_unused_field(source_code, line_num)
    elif rule_key == 'java:S2095':  # Resource leak
        return fix_resource_leak(source_code, line_num)
    elif rule_key == 'java:S3649':  # SQL injection
        return fix_sql_injection(source_code, line_num)
    # ... more rules
    
    return {
        'error': f'No automated fix available for {rule_key}',
        'requires_manual_review': True
    }
```

## Testing Recommendations

After applying fixes:

1. **Compile**: `mvn compile` or `gradle build`
2. **Run Tests**: `mvn test` or `gradle test`
3. **Re-scan**: Run SonarQube to verify issues resolved
4. **Code Review**: Have team member review changes

## Tools for Automated Fixes

- **Eclipse IDE**: Built-in inspections and quick fixes
- **IntelliJ IDEA**: Code inspections and intention actions
- **Spotbugs Maven Plugin**: Automated bug detection
- **Checkstyle**: Code style violations
- **SonarQube Analysis**: Run locally before pushing

## References

- [SonarQube Java Rules](https://rules.sonarsource.com/java/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [OWASP Top 10](https://owasp.org/Top10/)
