# SonarQube API Reference

This document covers the SonarQube API endpoints used by the skill.

## Authentication

All requests require a token passed as a Bearer token or basic auth:

```bash
curl -H "Authorization: Bearer $SONARQUBE_TOKEN" \
  https://sonarcloud.io/api/issues/search
```

## Endpoints Used

### 1. Search Issues

**Endpoint**: `GET /api/issues/search`

**Parameters**:
- `componentKeys` (string): Project key (required)
- `severities` (string): Comma-separated values: BLOCKER, CRITICAL, MAJOR, MINOR, INFO
- `types` (string): BUG, VULNERABILITY, CODE_SMELL
- `statuses` (string): OPEN, CONFIRMED, REOPENED, RESOLVED, CLOSED
- `p` (integer): Page number (1-based)
- `ps` (integer): Page size (default 100, max 500)

**Example**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://sonarcloud.io/api/issues/search?componentKeys=org.example:app&severities=BLOCKER,CRITICAL&types=BUG,VULNERABILITY&statuses=OPEN&ps=500"
```

**Response** (JSON):
```json
{
  "total": 15,
  "p": 1,
  "ps": 100,
  "paging": {
    "pageIndex": 1,
    "pageSize": 100,
    "total": 15
  },
  "effortTotal": 45,
  "debtTotal": 90000,
  "issues": [
    {
      "key": "sonarqube:AXp7KqQcGg7B2nLZUU6z",
      "rule": "java:S1104",
      "severity": "CRITICAL",
      "type": "CODE_SMELL",
      "mainLocation": {
        "component": "org.example:app:src/main/java/App.java",
        "file": "src/main/java/App.java",
        "startLine": 42,
        "startLineOffset": 10,
        "endLine": 42,
        "endLineOffset": 25,
        "message": "Remove this unused private field 'unused'"
      },
      "flows": [],
      "ruleDescriptionContextKey": null,
      "quickFixAvailable": false,
      "creationDate": "2024-01-10T12:34:56+0000",
      "updateDate": "2024-01-15T08:22:11+0000",
      "closeDate": null,
      "effort": "3min",
      "status": "OPEN",
      "fromHotspot": false,
      "assignee": null,
      "author": "sonar-java-plugin",
      "tags": ["clumsy"],
      "transitions": [],
      "actions": [],
      "comments": [],
      "externalRuleEngine": null,
      "externalRuleEngineDescription": null,
      "codeVariants": [],
      "cleanCodeAttribute": "LOGICAL",
      "cleanCodeAttributeCategory": "INTENTIONAL",
      "impacts": [
        {
          "softwareQuality": "MAINTAINABILITY",
          "severity": "LOW"
        }
      ],
      "prioritizedRule": false
    }
  ],
  "components": [
    {
      "key": "org.example:app",
      "uuid": "AXp7KqQGg7B2nLZUU6yY",
      "enabled": true,
      "qualifier": "TRK",
      "name": "Example App",
      "longName": "Example App",
      "path": null
    }
  ],
  "rules": [
    {
      "key": "java:S1104",
      "name": "Remove this unused private field 'unused'",
      "type": "CODE_SMELL",
      "status": "READY"
    }
  ],
  "facets": []
}
```

### 2. Get Issue Details

**Endpoint**: `GET /api/issues/show`

**Parameters**:
- `key` (string): Issue key (required)

**Response**: Same structure as individual issue in search results.

### 3. Get Rule Details

**Endpoint**: `GET /api/rules/show`

**Parameters**:
- `key` (string): Rule key like `java:S1104` (required)

**Example**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://sonarcloud.io/api/rules/show?key=java:S1104"
```

**Response**:
```json
{
  "rule": {
    "key": "java:S1104",
    "repo": "java",
    "name": "Class variable fields should be declared "final"",
    "htmlDesc": "<h2>Why is this an issue?</h2>\n<p>...",
    "mdDesc": "## Why is this an issue?\n\n...",
    "severity": "MAJOR",
    "status": "READY",
    "internalKey": "org.sonar.java.checks.UnusedPrivateFieldCheck",
    "isTemplate": false,
    "tags": ["clumsy"],
    "sysTags": ["java-syntax"],
    "langName": "Java",
    "lang": "java",
    "params": [],
    "defaultDebtRemFnType": "CONSTANT_ISSUE",
    "defaultDebtRemFnOffset": "3min",
    "debtOverloaded": false,
    "debtRemFnType": "CONSTANT_ISSUE",
    "debtRemFnOffset": "3min",
    "gapDescription": null,
    "scope": "MAIN",
    "standards": ["CWE"],
    "securityStandards": ["OWASP Top 10 2021 A05"],
    "isExternal": false,
    "numericId": 1000,
    "isAdHoc": false,
    "createdAt": "2013-01-10T18:22:50+0000",
    "updatedAt": "2023-11-15T12:34:56+0000"
  }
}
```

### 4. Get Source Code

**Endpoint**: `GET /api/sources/show`

**Parameters**:
- `key` (string): File component key (required)
- `from` (integer): Start line number (optional)
- `to` (integer): End line number (optional)

**Example**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://sonarcloud.io/api/sources/show?key=org.example:app:src/main/java/App.java&from=35&to=50"
```

**Response**:
```json
{
  "sources": [
    {
      "lineNumber": 35,
      "line": "    public void processData() {"
    },
    {
      "lineNumber": 36,
      "line": "        Data data = getData();"
    },
    ...
  ]
}
```

### 5. Get Project Details

**Endpoint**: `GET /api/components/show`

**Parameters**:
- `component` (string): Component/project key (required)

**Response**:
```json
{
  "component": {
    "key": "org.example:app",
    "uuid": "AXp7KqQGg7B2nLZUU6yY",
    "id": 123456,
    "enabled": true,
    "qualifier": "TRK",
    "name": "Example App",
    "longName": "Example App",
    "path": null,
    "tags": [],
    "isFavorite": false,
    "visibility": "public",
    "leakPeriodDate": "2024-01-01T00:00:00+0000"
  }
}
```

## Project Keys

### For SonarCloud
- Use the format: `owner/repo` or `org.example:project`
- Find it in SonarCloud project dashboard

### For Self-Hosted SonarQube
- Configure in your SonarQube instance
- Typically in Administration > Projects > Management

## Rate Limiting

- **SonarCloud**: 100 requests per second
- **Self-hosted**: Configured by instance admin

Implement exponential backoff for retries.

## Error Handling

Errors return standard HTTP status codes:

- `400`: Invalid parameters
- `401`: Authentication failed
- `403`: Permission denied
- `404`: Resource not found
- `429`: Rate limit exceeded

Example error response:
```json
{
  "errors": [
    {
      "msg": "Unknown component key: invalid-key"
    }
  ]
}
```

## Pagination

Use `p` (page) and `ps` (page size) parameters:

```bash
# Get issues page 2, 50 per page
curl "https://sonarcloud.io/api/issues/search?componentKeys=org.example:app&p=2&ps=50"
```

Response includes paging metadata to determine if more results exist.

## Useful Query Examples

### Get all critical bugs in Java files

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://sonarcloud.io/api/issues/search?componentKeys=org.example:app&severities=CRITICAL&types=BUG&languages=java"
```

### Get all open vulnerabilities

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://sonarcloud.io/api/issues/search?componentKeys=org.example:app&types=VULNERABILITY&statuses=OPEN"
```

### Get issues updated in last 7 days

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://sonarcloud.io/api/issues/search?componentKeys=org.example:app&updatedInLast=7d"
```

## Region-Specific Endpoints

- **Default (US)**: `https://sonarcloud.io`
- **EU**: `https://sonarcloud.io` (same, but data stored in EU)
- **Self-hosted**: Use your SonarQube instance URL

## Authentication Methods

### Token Authentication (Recommended)
```bash
Authorization: Bearer YOUR_TOKEN
```

### Basic Authentication
```bash
Authorization: Basic base64(token:)
```

### User Token in URL (Deprecated)
```bash
?login=token_value
```

Always use HTTPS for API requests to protect authentication tokens.
