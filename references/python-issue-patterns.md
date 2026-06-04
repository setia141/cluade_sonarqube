# Python SonarQube Issue Patterns

Common SonarQube rules for Python projects, with fix strategies and templates.

## Rule Index

| Rule | Title | Severity | Category | Auto-Fix |
|---|---|---|---|---|
| `python:S1172` | Unused function parameters | MAJOR | Code Quality | ✅ |
| `python:S1481` | Unused local variables | MAJOR | Code Quality | ✅ |
| `python:S5754` | Bare `except:` clause | MAJOR | Reliability | ✅ |
| `python:S2077` | SQL injection via format string | CRITICAL | Security | 🔶 |
| `python:S106` | Hardcoded password | BLOCKER | Security | 🔶 |
| `python:S1134` | FIXME comment | MINOR | Code Quality | Manual |
| `python:S1135` | TODO comment | INFO | Code Quality | Manual |
| `python:S3776` | Cognitive complexity too high | MAJOR | Maintainability | Manual |
| `python:S4144` | Duplicate function implementations | MAJOR | Code Quality | Manual |
| `python:S2301` | Function with boolean parameter flag | MAJOR | Design | Manual |

---

## `python:S1172` — Unused function parameters

**Message**: Remove this unused function parameter "x" or correct the code.

**Fix**: Remove the parameter if truly unused. If it's part of a required interface (e.g. a Django view or Flask route), prefix with `_` to signal intent.

```python
# Before
def process(data, unused_flag):
    return data.strip()

# After — remove if not needed by interface
def process(data):
    return data.strip()

# After — keep with underscore if interface requires it
def process(data, _unused_flag=None):
    return data.strip()
```

---

## `python:S1481` — Unused local variable

**Message**: Remove the unused local variable "x".

**Fix**: Remove the assignment. If the value is needed for side effects only (e.g., unpacking), use `_`.

```python
# Before
def calculate(values):
    total = sum(values)
    average = total / len(values)  # average never used
    return total

# After
def calculate(values):
    return sum(values)

# Before — tuple unpack with unused element
x, y = get_coords()

# After
_, y = get_coords()
```

---

## `python:S5754` — Bare `except:` clause

**Message**: Specify an exception class to catch.

**Fix**: Replace bare `except:` with `except Exception:` at minimum. Prefer specific exception types.

```python
# Before
try:
    result = risky_operation()
except:
    result = default_value

# After — specific exception
try:
    result = risky_operation()
except ValueError as exc:
    logger.warning("Invalid value: %s", exc)
    result = default_value

# After — minimum acceptable (when specific type is unknown)
try:
    result = risky_operation()
except Exception as exc:
    logger.error("Unexpected error: %s", exc)
    result = default_value
```

---

## `python:S2077` — SQL injection via string formatting

**Message**: Make sure that formatting this SQL query is safe here.

**Fix**: Use parameterised queries. Never build SQL by string interpolation.

```python
# Before — CRITICAL vulnerability
def get_user(conn, user_id):
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    return cursor.fetchone()

# After — parameterised
def get_user(conn, user_id):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    return cursor.fetchone()

# SQLAlchemy / ORM pattern
def get_user(session, user_id):
    return session.query(User).filter(User.id == user_id).first()
```

---

## `python:S106` — Hardcoded password / credential

**Message**: Remove this hard-coded password.

**Fix**: Move credentials to environment variables or a secrets manager.

```python
# Before — BLOCKER
DB_PASSWORD = "supersecret123"

# After
import os
DB_PASSWORD = os.environ["DB_PASSWORD"]

# With python-decouple
from decouple import config
DB_PASSWORD = config("DB_PASSWORD")
```

---

## Common Fix Patterns by Framework

### Django

```python
# S2077 — Use ORM or .raw() with params
User.objects.filter(username=username)                    # ORM (safe)
User.objects.raw("SELECT * FROM auth_user WHERE id = %s", [user_id])  # raw + params
```

### FastAPI

```python
# S5754 — HTTPException instead of bare except
from fastapi import HTTPException
try:
    result = await service.call()
except ServiceError as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from exc
```

### requests / httpx

```python
# S1481 — unused response variable
response = requests.post(url, json=payload)  # response unused
# After
requests.post(url, json=payload)
```

---

## Effort Estimates

| Rule | Typical effort | Notes |
|---|---|---|
| S1172 (unused param) | 5 min | Check interface requirements first |
| S1481 (unused var) | 5 min | Use `_` for intentional discards |
| S5754 (bare except) | 10 min | Must identify the right exception type |
| S2077 (SQL injection) | 30 min | Test with existing queries |
| S106 (hardcoded cred) | 20 min | Update all environments |
