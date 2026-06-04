# SonarQube API Reference

Endpoints used by this agent. Base URL is your `SONARQUBE_HOST_URL`.

## Authentication

Pass the token as a Bearer header. Omit the header entirely for internal SonarQube instances with network authentication.

```bash
curl -H "Authorization: Bearer $SONARQUBE_TOKEN" \
  "$SONARQUBE_HOST_URL/api/issues/search?..."
```

---

## Endpoints

### `GET /api/issues/search`

Fetch open issues for a project, filtered by severity and type.

**Parameters**

| Parameter | Description |
|---|---|
| `componentKeys` | Project key (required) |
| `severities` | `BLOCKER,CRITICAL,MAJOR,MINOR,INFO` |
| `types` | `BUG,VULNERABILITY,CODE_SMELL` |
| `statuses` | `OPEN` (default) |
| `ps` | Page size — max 500 |
| `p` | Page number (1-based) |

**Example**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$HOST/api/issues/search?componentKeys=my-project&severities=BLOCKER,CRITICAL&types=BUG,VULNERABILITY&statuses=OPEN&ps=500"
```

**Response**
```json
{
  "total": 3,
  "issues": [
    {
      "key": "AXp7KqQcGg7B2nLZUU6z",
      "rule": "java:S2259",
      "severity": "CRITICAL",
      "type": "BUG",
      "status": "OPEN",
      "component": "my-project:src/main/java/com/example/OrderService.java",
      "line": 42,
      "message": "A 'NullPointerException' could be thrown; 'result' is nullable here.",
      "textRange": {
        "startLine": 42,
        "endLine": 42,
        "startOffset": 8,
        "endOffset": 22
      },
      "effort": "10min",
      "creationDate": "2024-01-10T12:34:56+0000"
    }
  ]
}
```

---

### `GET /api/rules/show`

Fetch full description and metadata for a single rule.

**Parameters**

| Parameter | Description |
|---|---|
| `key` | Rule key e.g. `java:S2259` (required) |

**Example**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$HOST/api/rules/show?key=java:S2259"
```

**Response**
```json
{
  "rule": {
    "key": "java:S2259",
    "name": "Null pointers should not be dereferenced",
    "htmlDesc": "<h2>Why is this an issue?</h2><p>...</p>",
    "severity": "CRITICAL",
    "type": "BUG",
    "status": "READY",
    "lang": "java",
    "langName": "Java",
    "tags": ["bug", "cwe"],
    "params": []
  }
}
```

---

### `GET /api/sources/show`

Fetch raw source lines for a file component.

**Parameters**

| Parameter | Description |
|---|---|
| `key` | Component key (required) — same as `component` field in issue |
| `from` | Start line (optional) |
| `to` | End line (optional) |

**Example**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$HOST/api/sources/show?key=my-project:src/main/java/com/example/OrderService.java&from=38&to=48"
```

**Response**
```json
{
  "sources": [
    [38, "    public OrderResult process(String id) {"],
    [39, "        OrderResult result = repository.find(id);"],
    [40, "        return result.getName();"]
  ]
}
```

---

## Notes

- `component` in an issue is `projectKey:path/to/File.java` — split on the first `:` to get the file path
- `line` is the 1-based line number of the issue
- There is no `/api/issues/show` endpoint — use `/api/issues/search?issues=KEY` to fetch a single issue by key
- Pagination: check `total` vs `ps * p` to determine if more pages exist
