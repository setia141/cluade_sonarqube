# .NET / C# SonarQube Issue Patterns

Common SonarQube rules for .NET projects, with fix strategies and templates.

## Rule Index

| Rule | Title | Severity | Category | Auto-Fix |
|---|---|---|---|---|
| `csharpsquid:S2583` | Condition always true/false | MAJOR | Reliability | ✅ |
| `csharpsquid:S3966` | Object disposed multiple times | MAJOR | Reliability | ✅ |
| `csharpsquid:S2068` | Hardcoded password | BLOCKER | Security | 🔶 |
| `csharpsquid:S1075` | Hardcoded URI | MAJOR | Maintainability | 🔶 |
| `csharpsquid:S2259` | Null dereference | BLOCKER | Reliability | 🔶 |
| `csharpsquid:S1481` | Unused local variable | MINOR | Code Quality | ✅ |
| `csharpsquid:S1172` | Unused method parameter | MAJOR | Code Quality | ✅ |
| `csharpsquid:S3776` | Cognitive complexity | MAJOR | Maintainability | Manual |
| `csharpsquid:S4524` | `switch` missing `default` | MAJOR | Reliability | ✅ |
| `csharpsquid:S2737` | Catch rethrows same exception | MAJOR | Code Quality | ✅ |

---

## `csharpsquid:S2583` — Condition always true/false

**Message**: Change this condition so that it does not always evaluate to "true"/"false".

**Fix**: Remove the dead condition or fix the logic so the branch is reachable.

```csharp
// Before
string? name = GetName();
if (name != null)
{
    if (name != null)  // S2583: always true inside null-checked block
        Process(name);
}

// After
string? name = GetName();
if (name != null)
{
    Process(name);
}
```

---

## `csharpsquid:S3966` — Object disposed more than once

**Message**: Refactor this code to not dispose "x" more than once.

**Fix**: Use `using` statement — it handles disposal exactly once even on exception. Remove explicit `.Dispose()` calls.

```csharp
// Before
var stream = new FileStream(path, FileMode.Open);
try
{
    Process(stream);
    stream.Dispose();
}
finally
{
    stream.Dispose();  // S3966: disposed twice
}

// After
using var stream = new FileStream(path, FileMode.Open);
Process(stream);
```

---

## `csharpsquid:S2068` — Hardcoded password

**Message**: Remove this hard-coded password.

**Fix**: Use `IConfiguration`, environment variables, or Azure Key Vault.

```csharp
// Before — BLOCKER
private const string DbPassword = "P@ssw0rd!";

// After — IConfiguration
public class MyService(IConfiguration config)
{
    private readonly string _dbPassword = config["Database:Password"]
        ?? throw new InvalidOperationException("Database:Password not configured");
}

// After — environment variable direct
var password = Environment.GetEnvironmentVariable("DB_PASSWORD")
    ?? throw new InvalidOperationException("DB_PASSWORD not set");
```

---

## `csharpsquid:S1075` — Hardcoded URI / URL

**Message**: Refactor this code and extract this hardcoded path/URI.

**Fix**: Move URIs to `appsettings.json` and inject via `IConfiguration` or strongly-typed options.

```csharp
// Before
private static readonly string ApiUrl = "https://api.internal.company.com/v1";

// After — appsettings.json: { "Services": { "InternalApi": { "BaseUrl": "..." } } }
public class ApiClient(IOptions<InternalApiOptions> opts)
{
    private readonly string _baseUrl = opts.Value.BaseUrl;
}

public class InternalApiOptions
{
    public string BaseUrl { get; set; } = string.Empty;
}
```

---

## `csharpsquid:S2259` — Null dereference

**Message**: Dereference of a possibly null reference.

**Fix**: Add null check or use null-conditional operator. In C# 8+ with nullable reference types enabled, the compiler guides you.

```csharp
// Before
public string GetDisplayName(User? user)
{
    return user.Name.Trim();  // S2259: user may be null
}

// After
public string GetDisplayName(User? user)
{
    return user?.Name?.Trim() ?? "Unknown";
}
```

---

## `csharpsquid:S4524` — Switch missing default

**Message**: Add a `default` clause to this `switch` statement.

**Fix**: Add a `default` case. For exhaustive enums, throw `ArgumentOutOfRangeException`.

```csharp
// Before
switch (status)
{
    case Status.Active:   return "Active";
    case Status.Inactive: return "Inactive";
}

// After
switch (status)
{
    case Status.Active:   return "Active";
    case Status.Inactive: return "Inactive";
    default:
        throw new ArgumentOutOfRangeException(nameof(status), status, null);
}
```

---

## `csharpsquid:S2737` — Catch rethrows same exception

**Message**: Add logic to this catch clause or eliminate it and rethrow the exception automatically.

**Fix**: Use bare `throw` (preserves stack trace) or remove the try/catch if no handling is done.

```csharp
// Before
try { DoWork(); }
catch (Exception ex)
{
    throw ex;  // S2737: throws ex loses stack trace
}

// After
try { DoWork(); }
catch (Exception)
{
    throw;  // preserves full stack trace
}

// Or if no handling needed, remove the try/catch entirely
DoWork();
```

---

## Effort Estimates

| Rule | Typical effort | Notes |
|---|---|---|
| S2583 (dead condition) | 10 min | Understand the intent first |
| S3966 (double dispose) | 10 min | Convert to `using` statement |
| S2068 (hardcoded password) | 20 min | Update all environments |
| S1075 (hardcoded URI) | 20 min | Add options class + DI registration |
| S2259 (null dereference) | 15–30 min | Check all call sites |
| S4524 (missing default) | 5 min | Usually one line |
| S2737 (catch rethrows) | 5 min | One character change |
