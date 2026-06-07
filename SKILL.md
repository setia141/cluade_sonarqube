---
name: sonarqube-fixer-agent
description: Autonomous agent that fixes SonarQube issues (Blocker, Critical, Major) across Java, Python, .NET, and Node.js projects. Validates every fix using embedded mock servers (WireMock for Java/.NET, pytest-httpserver for Python, nock for Node) before opening a pull request. Runs autonomously in GitHub Actions CI or interactively via Claude Code.
---

# SonarQube Fixer Agent

## Skill vs Agent

This is an **agent**, not a passive skill. The distinction matters:

| Skill | Agent |
|---|---|
| Human invokes Claude, Claude reads skill and responds | Triggered by CI event, runs autonomously end-to-end |
| Interactive, conversational | Autonomous, unattended |
| Claude uses its tools ad hoc | Defined pipeline: fetch → analyze → fix → validate → PR |

**Dual-mode operation:**
- **CI mode**: GitHub Actions triggers this agent after a SonarQube scan. No human involved. Agent opens a PR with fixes and a validation report.
- **Interactive mode**: Developer invokes via Claude Code (`/sonarqube-fixer-agent`). Claude walks through the pipeline collaboratively.

---

## Supported Languages

| Language | Build Tool | Test Framework | Mock Library | SonarQube Prefix |
|---|---|---|---|---|
| Java | Maven / Gradle | JUnit 5 | WireMock | `java:` |
| .NET | dotnet CLI | xUnit / NUnit / MSTest | WireMock.Net | `csharpsquid:` |
| Python | pip / poetry | pytest | pytest-httpserver | `python:` |
| Node.js | npm / yarn | Jest / Mocha | nock | `javascript:` / `typescript:` |

---

## Hard Stop Conditions

These are non-negotiable gates. If any condition is met, **stop and surface the problem** — do not proceed silently.

| Condition | Required action |
|---|---|
| `ruleDetails` is `{}` in enriched.json | STOP. The rule description fetch failed (likely 400 from SonarQube API). Read the issue `message` field and search the SonarQube rule docs to understand the fix. Do not guess. Tell the user which rule could not be enriched and why before proceeding. |
| Baseline confidence is `LOW` or `SKIP` | STOP. Do not apply any fix. Read the validation stdout/stderr, diagnose the root cause (wrong test path, missing dependency, compile error), fix it, and re-run baseline until it passes. Only then continue. |
| Post-fix confidence is `LOW` | Do NOT open a ready PR. Open a **draft PR** with a clear note explaining what failed and why. |
| Post-fix confidence is `SKIP` | Revert all changes to the file. Do not open a PR. |
| A test you write triggers a new SonarQube rule | Simplify the test. Never use nested loops, deeply nested conditionals, or long methods in generated test code. Use parameterized tests or simple flat assertions instead. |

---

## Pipeline

Unit tests are **primary**. Integration tests (mock servers) are **optional** — only run them if the changed code makes outbound HTTP calls and you want that extra layer.

```
PHASE 1 — DETECT
  python3 scripts/detect_language.py --repo . --output lang.json

PHASE 2 — FETCH ISSUES
  python3 scripts/fetch_issues.py --host $SONARQUBE_HOST_URL \
    --token $SONARQUBE_TOKEN --project $SONARQUBE_PROJECT_KEY \
    --severities BLOCKER,CRITICAL,MAJOR --output issues.json

  python3 scripts/analyze_issue.py --issues issues.json --output enriched.json
  # Calls /api/rules/show for every rule and attaches name, htmlDesc, severity, type
  # to each issue. Claude reads enriched.json and decides what to fix and how.

PHASE 3 — ENSURE UNIT TESTS EXIST  ← NEW: always do this before baseline

  Step 3a — Pre-flight coverage check
    python3 scripts/validation/run_validation.py \
      --lang-config lang.json \
      --changed-files "[list of files that will be fixed]" \
      --repo . --phase check-tests --output test-status.json

    This runs the project's existing tests with coverage enabled:
      Java   → JaCoCo   (jacoco-maven-plugin added to pom.xml if missing)
      Python → pytest-cov (installed if missing, generates coverage.xml)
      .NET   → Coverlet  (dotnet test --collect:"XPlat Code Coverage")
      Node   → Jest --coverage (generates coverage/coverage-final.json)

    Read test-status.json. For every file where needs_tests=true
    (coverage_pct < 80% OR uncovered_lines is non-empty OR has_tests=false):

  Step 3b — Create / enhance unit tests (Claude writes these directly)
    For each file where needs_tests=true:
      - If has_tests=false: create a new test file
      - If has_tests=true but uncovered_lines is non-empty: ADD test cases
        to the existing test file specifically for those uncovered line numbers
      1. Read the source file
      2. Identify the class/struct/module name and the methods that enriched.json
         says will be changed
      3. Write a unit test file at expected_test_path from test-status.json:

         Java   → src/test/java/.../FooServiceTest.java
                  Use @ExtendWith(MockitoExtension.class), @Mock for each dependency,
                  @InjectMocks for the class under test
         .NET   → FooServiceTests.cs
                  Use xUnit [Fact], Moq Mock<IDep>, new FooService(mock.Object)
         Python → tests/test_foo_service.py
                  Use pytest, unittest.mock.patch or MagicMock for dependencies
         Node   → __tests__/fooService.test.js
                  Use jest.mock() for module dependencies

      4. Write TWO test cases minimum:
         a. Happy path: call the method with valid input, assert expected output
         b. Fix scenario: call with input that triggers the SonarQube issue
            (e.g. null return, missing key, bare except) — this test will FAIL
            before the fix is applied. That is correct and expected.

      5. Run the tests immediately to confirm they compile:
         Java:   mvn test -Dtest=FooServiceTest --no-transfer-progress
         .NET:   dotnet test --filter "ClassName~FooServiceTests"
         Python: pytest tests/test_foo_service.py -v
         Node:   npx jest fooService --no-coverage
         Fix any compilation errors before continuing.

  Step 3c — Also check callers (from test-status.json callers field)
    test-status.json lists which other classes call into the changed class.
    Note those caller test files — they will be included in the baseline run.

PHASE 4 — BASELINE CAPTURE

  Step 4a — Unit test baseline (always)
    python3 scripts/validation/run_validation.py \
      --lang-config lang.json \
      --changed-files "[files to be fixed]" \
      --repo . --phase baseline --output baseline.json

    This runs unit tests for both the changed files AND their callers.
    Records pass/fail counts. Some tests (the fix-scenario ones) will fail here
    — that is expected and is recorded as the baseline.

    ** If baseline returns LOW or SKIP confidence — STOP and diagnose: **
      1. Read baseline.json layers.unit_tests.stdout and stderr in full
      2. Common causes and fixes:
         - "no tests ran" / "collected 0 items" → wrong test path. Check where
           test files actually live (tests/, test/, src/test/) and correct
           the --changed-files paths or the test runner command.
         - "ModuleNotFoundError" → missing dependency. Run pip/npm/mvn install.
         - "cannot find symbol" / compile error → fix the build first.
         - "FileNotFoundError" for test file → the expected test file doesn't
           exist yet. Go back to Step 3 and create it.
      3. Fix the root cause, re-run baseline. Do NOT proceed until baseline
         passes or until the only failing tests are the intentional fix-scenario
         tests (which are expected to fail before the fix).

  Step 4b — Integration baseline (optional — only if code makes HTTP calls)
    python3 scripts/validation/run_validation.py \
      --lang-config lang.json \
      --changed-files "[files to be fixed]" \
      --repo . --phase baseline --integration --output baseline-integration.json

    The script generates a WireMock/nock/pytest-httpserver test scaffold.
    After the script runs, it will print the generated test file path.
    Claude MUST complete the scaffold:
      1. Read the generated test file
      2. Read the source file being tested
      3. Fill in the service/function call inside the test body:
         Java:   @Autowired private FooService fooService;
                 FooService result = fooService.methodName(validInput());
         .NET:   var result = await _client.PostAsJsonAsync("/endpoint", req);
         Python: from foo_service import foo_function
                 result = foo_function(valid_input())
         Node:   const { fooFunction } = require('../src/fooService');
                 const result = await fooFunction(validInput());
      4. Re-run the integration test to confirm it compiles and the stubs are hit
    Record stub interaction counts as integration baseline.

PHASE 5 — APPLY FIX
  For each AUTO/GUIDED issue in enriched.json:
    1. Read the source file
    2. Apply the minimal change at the indicated line to resolve the rule
    3. Use Edit — change only what the SonarQube rule requires
    4. Compile immediately after: if it fails, revert this file and skip the issue

PHASE 6 — VALIDATE

  Step 6a — Unit tests (primary gate)
    python3 scripts/validation/run_validation.py \
      --lang-config lang.json \
      --changed-files "[fixed files]" \
      --repo . --phase post-fix --baseline baseline.json --output validation.json

    Expected:
    ✓ Happy path tests:     must still pass (were passing at baseline)
    ✓ Fix-scenario tests:   must NOW pass (were failing at baseline — proves fix works)
    ✓ Caller tests:         must still pass (no regression in calling code)

  Step 6b — Integration tests (optional, if Step 4b was run)
    python3 scripts/validation/run_validation.py \
      --lang-config lang.json \
      --changed-files "[fixed files]" \
      --repo . --phase post-fix --baseline baseline-integration.json \
      --integration --output validation-integration.json

    Checks: stub call counts match baseline (fix didn't add/remove downstream calls)

PHASE 7 — DECIDE
  HIGH confidence   (unit tests pass, fix-scenario now passes, callers pass)
    → commit to fix branch, open PR ready for review
  MEDIUM confidence (most pass, minor issue flagged)
    → open draft PR with validation report attached
  LOW confidence    (unit test regression detected)
    → revert the fix, skip this issue, note it in the PR description
  SKIP              (compile failed)
    → revert, do not touch the file

PHASE 8 — PR
  python3 scripts/create_pr.py \
    --fixes fixes.json --validation validation.json --base main
  PR body includes: issues fixed, validation report per layer, reviewer checklist
```

---

## Phase 1: Language Detection

Run `scripts/detect_language.py` first. It reads repo structure and returns:

```json
{
  "language": "java",
  "framework": "spring-boot",
  "build_tool": "maven",
  "test_framework": "junit5",
  "http_client": "spring-resttemplate-webclient",
  "wiremock_present": true,
  "url_config_pattern": "application-properties",
  "test_override_method": "dynamic-property-source",
  "sonarqube_rule_prefix": "java:"
}
```

Detection signals by language:

```
Java   → pom.xml | build.gradle
.NET   → *.csproj | *.sln
Python → setup.py | pyproject.toml | requirements.txt
Node   → package.json (without *.csproj)
```

---

## Phase 3 & 5: Validation — WireMock (Java and .NET)

WireMock runs **inside the test process** as an embedded HTTP server. No Docker. No external process. Real TCP sockets, real HTTP — your application code is unchanged.

### Java — WireMock Setup Pattern

**Detect if WireMock is present** (`pom.xml` / `build.gradle`):
```xml
<!-- If not present, agent adds this to pom.xml test scope -->
<dependency>
  <groupId>org.wiremock</groupId>
  <artifactId>wiremock</artifactId>
  <version>3.3.1</version>
  <scope>test</scope>
</dependency>
```

**Generated validation test class** (agent writes this to `src/test/java/.../`):
```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@WireMockTest
class SonarFixValidationTest {

    // One WireMockServer per downstream service
    static WireMockServer paymentMock = new WireMockServer(WireMockConfiguration.options().dynamicPort());
    static WireMockServer userMock    = new WireMockServer(WireMockConfiguration.options().dynamicPort());

    @DynamicPropertySource
    static void overrideServiceUrls(DynamicPropertyRegistry registry) {
        // Inject mock URLs — app code unchanged, just points at localhost
        registry.add("payment.service.url", paymentMock::baseUrl);
        registry.add("user.service.url",    userMock::baseUrl);
    }

    @BeforeAll
    static void startMocks() {
        paymentMock.start();
        userMock.start();
    }

    @AfterAll
    static void stopMocks() {
        paymentMock.stop();
        userMock.stop();
    }

    @BeforeEach
    void resetMocks() {
        paymentMock.resetAll();
        userMock.resetAll();
    }

    @Test
    void happyPath_unchangedByFix() {
        // Stub all downstreams
        paymentMock.stubFor(post(urlEqualTo("/charge"))
            .willReturn(okJson("{\"paymentId\":\"pay-123\",\"approved\":true}")));
        userMock.stubFor(get(urlPathMatching("/users/.*"))
            .willReturn(okJson("{\"name\":\"Alice\",\"active\":true}")));

        // Call service under test — real HTTP, real deserialization
        OrderResult result = orderService.create(testRequest());

        // Behavioral assertions — must pass BEFORE and AFTER fix
        assertThat(result.getPaymentId()).isEqualTo("pay-123");

        // Interaction verification — confirm downstream call pattern unchanged
        paymentMock.verify(1, postRequestedFor(urlEqualTo("/charge")));
        userMock.verify(1, getRequestedFor(urlPathMatching("/users/.*")));
    }

    @Test
    void nullResponse_handledGracefully() {
        // Specifically targets the fix scenario (e.g. S2259 null pointer)
        paymentMock.stubFor(post(urlEqualTo("/charge"))
            .willReturn(okJson("{}")));  // missing paymentId field

        // BEFORE fix: would throw NPE
        // AFTER fix:  should handle gracefully (return null, throw checked exception, etc.)
        assertThatCode(() -> orderService.create(testRequest()))
            .doesNotThrowAnyException();
    }

    @Test
    void downstreamError_handledCorrectly() {
        paymentMock.stubFor(post(urlEqualTo("/charge"))
            .willReturn(serverError()));

        assertThatThrownBy(() -> orderService.create(testRequest()))
            .isInstanceOf(PaymentException.class);

        // Confirm inventory was NOT called after payment failure
        inventoryMock.verify(0, anyRequestedFor(anyUrl()));
    }
}
```

**Key WireMock verification patterns:**
```java
// Call count
mock.verify(1, postRequestedFor(urlEqualTo("/charge")));

// Request body contains field
mock.verify(postRequestedFor(urlEqualTo("/charge"))
    .withRequestBody(matchingJsonPath("$.amount", equalTo("100"))));

// Service was NOT called (critical for error path testing)
mock.verify(0, anyRequestedFor(anyUrl()));

// Call order verification
InOrder inOrder = inOrder(paymentMock, inventoryMock);
// (use WireMock ServeEvents for sequence verification)
```

**Service URL override methods by framework:**

| Framework | Override method |
|---|---|
| Spring Boot 2.2.6+ | `@DynamicPropertySource` |
| Spring Boot (any) | `application-test.properties` |
| Quarkus | `%test.payment.url=http://localhost:${wiremock.port}` |
| Plain Java | `System.setProperty("payment.url", mock.baseUrl())` |

---

### .NET — WireMock.Net Setup Pattern

**Add WireMock.Net** (if not present):
```xml
<!-- .csproj -->
<PackageReference Include="WireMock.Net" Version="1.5.47" />
<PackageReference Include="Microsoft.AspNetCore.Mvc.Testing" Version="8.0.0" />
```

**Generated validation test class:**
```csharp
public class SonarFixValidationTests : IAsyncLifetime
{
    private WireMockServer _paymentMock;
    private WireMockServer _userMock;
    private WebApplicationFactory<Program> _factory;
    private HttpClient _client;

    public async Task InitializeAsync()
    {
        _paymentMock = WireMockServer.Start();
        _userMock    = WireMockServer.Start();

        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {
                builder.ConfigureAppConfiguration((_, cfg) =>
                {
                    // Override service URLs — app code unchanged
                    cfg.AddInMemoryCollection(new Dictionary<string, string>
                    {
                        ["Services:Payment:BaseUrl"] = _paymentMock.Urls[0],
                        ["Services:User:BaseUrl"]    = _userMock.Urls[0],
                    });
                });
            });

        _client = _factory.CreateClient();
    }

    [Fact]
    public async Task HappyPath_UnchangedByFix()
    {
        _paymentMock
            .Given(Request.Create().WithPath("/charge").UsingPost())
            .RespondWith(Response.Create().WithStatusCode(200)
                .WithBodyAsJson(new { paymentId = "pay-123", approved = true }));

        _userMock
            .Given(Request.Create().WithPath("/users/*").UsingGet())
            .RespondWith(Response.Create().WithStatusCode(200)
                .WithBodyAsJson(new { name = "Alice", active = true }));

        var response = await _client.PostAsJsonAsync("/api/orders", TestRequest());

        response.EnsureSuccessStatusCode();
        var result = await response.Content.ReadFromJsonAsync<OrderResult>();
        Assert.Equal("pay-123", result!.PaymentId);

        // Verify downstream interactions unchanged
        Assert.Equal(1, _paymentMock.LogEntries.Count());
        Assert.Equal(1, _userMock.LogEntries.Count());
    }

    [Fact]
    public async Task NullResponse_HandledGracefully()
    {
        _paymentMock
            .Given(Request.Create().WithPath("/charge").UsingPost())
            .RespondWith(Response.Create().WithStatusCode(200)
                .WithBodyAsJson(new { }));  // missing paymentId

        var response = await _client.PostAsJsonAsync("/api/orders", TestRequest());

        // After fix: no unhandled exception, meaningful error response
        Assert.NotEqual(HttpStatusCode.InternalServerError, response.StatusCode);
    }

    public async Task DisposeAsync()
    {
        _paymentMock?.Stop();
        _userMock?.Stop();
        _factory?.Dispose();
        _client?.Dispose();
    }
}
```

**Service URL override methods by framework:**

| Framework | Override method |
|---|---|
| ASP.NET Core | `WebApplicationFactory` + `ConfigureAppConfiguration` |
| Worker Service | `IHostBuilder.ConfigureAppConfiguration` |
| Plain .NET | `Environment.SetEnvironmentVariable` in test setup |

---

## Phase 3 & 5: Validation — Python (pytest-httpserver)

**Add dependency** (if not present):
```
pytest-httpserver==1.0.8   # add to requirements-dev.txt
```

**Generated conftest.py fixture:**
```python
# conftest.py — agent adds these fixtures
import pytest
from pytest_httpserver import HTTPServer

@pytest.fixture(scope="session")
def payment_server():
    with HTTPServer(host="127.0.0.1", port=0) as server:  # port=0 → random free port
        yield server

@pytest.fixture(scope="session")
def user_server():
    with HTTPServer(host="127.0.0.1", port=0) as server:
        yield server

@pytest.fixture(autouse=True)
def clear_servers(payment_server, user_server):
    yield
    payment_server.clear()
    user_server.clear()
```

**Generated validation test:**
```python
import pytest
import os

class TestSonarFixValidation:

    def test_happy_path_unchanged_by_fix(self, payment_server, user_server, monkeypatch):
        monkeypatch.setenv("PAYMENT_SERVICE_URL", payment_server.url_for(""))
        monkeypatch.setenv("USER_SERVICE_URL",    user_server.url_for(""))

        payment_server.expect_request("/charge", method="POST") \
            .respond_with_json({"paymentId": "pay-123", "approved": True})
        user_server.expect_request("/users/1") \
            .respond_with_json({"name": "Alice", "active": True})

        result = order_service.create(test_request())

        assert result["paymentId"] == "pay-123"
        payment_server.check_assertions()  # verifies all expected requests were made
        user_server.check_assertions()

    def test_null_response_handled_gracefully(self, payment_server, monkeypatch):
        monkeypatch.setenv("PAYMENT_SERVICE_URL", payment_server.url_for(""))

        payment_server.expect_request("/charge", method="POST") \
            .respond_with_json({})  # missing paymentId

        # After fix: should not raise AttributeError/KeyError
        result = order_service.create(test_request())
        assert result is not None  # or whatever graceful behavior is expected

    def test_downstream_error_handled(self, payment_server, user_server, monkeypatch):
        monkeypatch.setenv("PAYMENT_SERVICE_URL", payment_server.url_for(""))

        payment_server.expect_request("/charge", method="POST") \
            .respond_with_data("Internal Server Error", status=500)

        with pytest.raises(PaymentException):
            order_service.create(test_request())

        # Confirm user service not called after payment failure
        assert len(user_server.log) == 0
```

**Service URL override methods:**

| Framework | Override method |
|---|---|
| Any | `monkeypatch.setenv` |
| Django | `override_settings(PAYMENT_URL=server.url_for(""))` |
| FastAPI | `app.dependency_overrides` |
| Pydantic Settings | `monkeypatch.setenv` (Settings reads env vars) |

---

## Phase 3 & 5: Validation — Node.js (nock)

**Add dependency** (if not present):
```bash
npm install --save-dev nock
```

**Generated validation test (Jest):**
```javascript
const nock = require('nock');
const { orderService } = require('../src/orderService');

describe('SonarFix Validation', () => {

    afterEach(() => {
        nock.cleanAll();
    });

    test('happy path — unchanged by fix', async () => {
        nock(process.env.PAYMENT_SERVICE_URL)
            .post('/charge')
            .reply(200, { paymentId: 'pay-123', approved: true });

        nock(process.env.USER_SERVICE_URL)
            .get(/\/users\/\d+/)
            .reply(200, { name: 'Alice', active: true });

        const result = await orderService.create(testRequest());

        expect(result.paymentId).toBe('pay-123');
        expect(nock.isDone()).toBe(true);  // all registered mocks were called
    });

    test('null response — handled gracefully', async () => {
        nock(process.env.PAYMENT_SERVICE_URL)
            .post('/charge')
            .reply(200, {});  // missing paymentId

        // After fix: should not throw TypeError
        const result = await orderService.create(testRequest());
        expect(result).toBeDefined();
    });

    test('downstream error — correct behavior', async () => {
        nock(process.env.PAYMENT_SERVICE_URL)
            .post('/charge')
            .reply(500);

        await expect(orderService.create(testRequest()))
            .rejects.toThrow('PaymentException');

        // Confirm user service not hit after payment failure
        expect(nock.pendingMocks()).toHaveLength(0);
    });
});
```

---

## Stub Generation Strategy (when no stubs exist)

When the agent finds no existing WireMock/nock/httpserver stubs, it generates them:

**Step 1 — Scan HTTP call sites in the changed file:**

```
Java:   Look for RestTemplate.*, WebClient.*, FeignClient @GetMapping/@PostMapping
.NET:   Look for HttpClient.GetAsync/PostAsync, typed HttpClient injections
Python: Look for requests.get/post/put, httpx.get/post, aiohttp.ClientSession
Node:   Look for axios.get/post, fetch(, node-fetch, got(
```

**Step 2 — Extract URL patterns:**
```
Java:   @Value("${payment.url}") + restTemplate.postForEntity(paymentUrl + "/charge", ...)
        → service: payment, path: /charge, method: POST

.NET:   _httpClient.GetAsync($"{_config["Services:User:BaseUrl"]}/users/{id}")
        → service: user, path: /users/{id}, method: GET
```

**Step 3 — Find response DTOs:**
```
Java:   ResponseEntity<PaymentResponse> → read PaymentResponse fields → generate JSON stub
.NET:   ReadFromJsonAsync<PaymentResult> → read PaymentResult properties → generate JSON stub
Python: response.json() → infer from usage (result["paymentId"]) → generate JSON stub
Node:   response.data.paymentId → infer from usage → generate JSON stub
```

**Step 4 — Generate stubs for both happy path and null/error scenarios.**

---

## Validation Comparison: Before vs After Fix

The agent runs validation in two passes and compares:

```
BASELINE (before fix):
  Record: test pass/fail, stub call counts, stub paths hit, response fields accessed

AFTER FIX:
  Record: same metrics

COMPARE:
  ✓ Happy path tests:  must pass both before and after
  ✓ Stub call counts:  must be identical (fix should not add or drop downstream calls)
  ✓ Stub paths:        must be identical (fix should not change which endpoints are called)
  ✗ Error path tests:  expected to FAIL before fix, PASS after fix (proves fix works)
```

---

## Confidence Scoring

| Score | Condition | Action |
|---|---|---|
| HIGH | All layers pass, happy path unchanged, error paths now fixed | Auto-commit to PR |
| MEDIUM | Happy path passes, error paths pass, but semantic review flagged subtle change | Draft PR + manual review note |
| LOW | Stub call count changed, or unexpected test failure | Revert, annotate SonarQube issue |
| SKIP | Cannot compile, cannot detect language, no tests and no HTTP calls found | Log and skip, do not touch code |

---

## Environment Variables

```bash
SONARQUBE_HOST_URL         # e.g. https://sonarcloud.io or internal URL
SONARQUBE_TOKEN            # API token (Bearer auth)
SONARQUBE_PROJECT_KEY      # project key on SonarQube
GITHUB_TOKEN               # repo write access for PR creation
GITHUB_REPOSITORY          # owner/repo format
GIT_BRANCH                 # current branch name
```

---

## Scripts

| Script | Purpose |
|---|---|
| `scripts/detect_language.py` | Language, framework, HTTP client detection |
| `scripts/fetch_issues.py` | Query SonarQube API for open issues |
| `scripts/analyze_issue.py` | Enrich issues with rule details from SonarQube Rules API |
| `scripts/validation/run_validation.py` | Validation orchestrator — phases: check-tests, baseline, post-fix |
| `scripts/validation/coverage_check.py` | Line-level coverage via JaCoCo / pytest-cov / Coverlet / Jest |
| `scripts/validation/java_wiremock.py` | Java WireMock integration test scaffold generator |
| `scripts/validation/dotnet_wiremock.py` | .NET WireMock.Net integration test scaffold generator |
| `scripts/validation/python_validator.py` | Python pytest-httpserver integration test scaffold generator |
| `scripts/validation/node_validator.py` | Node nock integration test scaffold generator |
| `scripts/create_pr.py` | Branch creation, commit, PR creation via gh CLI |

**Claude Code applies fixes directly** using Read/Edit/Write tools — there is no `generate_fix.py` script.
**Claude Code fills in test scaffolds** — after generators produce the skeleton, Claude reads the source file and completes the FILL-IN sections.

---

## References

- `references/sonarqube-api.md` — SonarQube API endpoints
- `references/validation-approach.md` — WireMock/mock server patterns deep dive
- `references/github-actions-setup.md` — CI workflow examples
