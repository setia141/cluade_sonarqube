# Node.js / JavaScript / TypeScript SonarQube Issue Patterns

Common SonarQube rules for Node.js projects, with fix strategies and templates.

## Rule Index

| Rule | Title | Severity | Category | Auto-Fix |
|---|---|---|---|---|
| `javascript:S3827` | Undefined variable | BLOCKER | Reliability | ✅ |
| `javascript:S1068` | Unused private field | MAJOR | Code Quality | ✅ |
| `javascript:S2814` | Variable re-declared | MAJOR | Code Quality | ✅ |
| `typescript:S4325` | Unnecessary type cast | MINOR | Code Quality | ✅ |
| `javascript:S1481` | Unused local variable | MINOR | Code Quality | ✅ |
| `javascript:S2201` | Return value ignored | MAJOR | Reliability | 🔶 |
| `javascript:S4144` | Duplicate function | MAJOR | Code Quality | Manual |
| `javascript:S1135` | TODO comment | INFO | Code Quality | Manual |
| `javascript:S5759` | Forwarded client IP | CRITICAL | Security | 🔶 |
| `javascript:S2255` | `document.cookie` write | CRITICAL | Security | 🔶 |

---

## `javascript:S3827` — Undefined variable

**Message**: "x" is not defined.

**Fix**: Declare the variable, import it, or remove the usage.

```javascript
// Before
function process() {
    return results.map(r => r.id);  // S3827: results not declared
}

// After
function process(results) {        // pass as parameter
    return results.map(r => r.id);
}

// Or — import from correct module
import { results } from './store';
```

---

## `javascript:S2814` — Variable re-declared with `var`

**Message**: "x" is already declared in the upper scope.

**Fix**: Replace `var` with `const` or `let` throughout. `var` has function scope and allows re-declaration; `const`/`let` have block scope and do not.

```javascript
// Before
var count = 0;
function increment() {
    var count = count + 1;  // S2814: re-declares outer count
    return count;
}

// After
let count = 0;
function increment() {
    count = count + 1;
    return count;
}
```

---

## `javascript:S1481` — Unused local variable

**Message**: Remove the declaration of the unused "x" variable.

**Fix**: Remove the variable or use it. For destructuring where some elements are intentionally unused, use `_`.

```javascript
// Before
const { id, name, createdAt } = user;  // createdAt unused
return { id, name };

// After
const { id, name } = user;
return { id, name };

// Before — positional destructure
const [first, second, third] = array;  // third unused

// After
const [first, second] = array;
// or if position matters:
const [first, second, _] = array;
```

---

## `typescript:S4325` — Unnecessary type cast

**Message**: This assertion is unnecessary since it does not change the type of the expression.

**Fix**: Remove the cast. TypeScript already knows the type.

```typescript
// Before
const name = (user.name as string).trim();  // user.name is already string

// After
const name = user.name.trim();
```

---

## `javascript:S2201` — Return value of pure function ignored

**Message**: The return value of "x" must be used.

**Fix**: Assign the return value or use a mutating variant.

```javascript
// Before — Array methods return new arrays, don't mutate
const items = ['b', 'a', 'c'];
items.sort();      // S2201: return value ignored
items.filter(Boolean);  // S2201

// After
const sorted = [...items].sort();
const filtered = items.filter(Boolean);
```

---

## `javascript:S5759` — Client IP forwarded insecurely

**Message**: Make sure forwarding client IP address is safe here.

**Fix**: Only trust `X-Forwarded-For` from known reverse proxies. Use a library like `proxy-addr`.

```javascript
// Before — Express
app.set('trust proxy', true);  // trusts ALL proxies — dangerous

// After — trust only your own proxy
app.set('trust proxy', '10.0.0.0/8');  // internal network only

// Or use proxy-addr
import proxyAddr from 'proxy-addr';
const clientIp = proxyAddr(req, ['127.0.0.1', '10.0.0.0/8']);
```

---

## `javascript:S2255` — `document.cookie` written without security attributes

**Message**: Make sure this cookie is used safely.

**Fix**: Always set `Secure`, `HttpOnly`, and `SameSite` when writing cookies. In Node.js backends, use the `res.cookie()` Express method with options.

```javascript
// Before — client-side
document.cookie = "session=" + token;

// After — with security attributes
document.cookie = `session=${token}; Secure; HttpOnly; SameSite=Strict; Path=/`;

// Express server-side
res.cookie('session', token, {
    httpOnly: true,
    secure: true,
    sameSite: 'strict',
    maxAge: 3600000,
});
```

---

## Common Fix Patterns by Framework

### Express

```javascript
// S3827 — req/res typos
app.get('/users', async (req, res) => {
    const { id } = req.params;   // not request.params
    res.json(await userService.find(id));
});
```

### TypeScript strict mode

Enable in `tsconfig.json` to catch S2259/S4325 at compile time:
```json
{
  "compilerOptions": {
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  }
}
```

---

## Effort Estimates

| Rule | Typical effort | Notes |
|---|---|---|
| S3827 (undefined var) | 10 min | Find correct import or declaration |
| S2814 (var re-declared) | 5 min | `var` → `const`/`let` |
| S1481 (unused var) | 5 min | Remove or use `_` prefix |
| S4325 (TS cast) | 5 min | Remove cast |
| S2201 (ignored return) | 10 min | Assign result or use mutating API |
| S5759 (forwarded IP) | 20 min | Audit proxy trust config |
| S2255 (cookie security) | 15 min | Add security attributes |
