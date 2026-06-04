# Validation Approach

How the SonarQube Fixer Agent validates fixes without Docker or external services.

## Design Goal

Give integration-level confidence that a fix does not regress downstream behaviour, using only tools that are already available on developer laptops and GitHub-hosted runners — no Docker, no TestContainers, no external processes.

## Four Layers

```
Layer 1 — Compile
  Build the project. If the fix introduces a syntax or type error, fail immediately.
  Cost: ~5–60 s depending on language.

Layer 2 — Scoped Unit Tests
  Run only the test class(es) for the changed source file(s).
  Derived by convention: FooService → FooServiceTest (Java), test_foo.py (Python), etc.
  Cost: seconds.

Layer 3 — Integration Tests with Mock Servers
  Spin up embedded HTTP mock servers for every downstream service the changed code calls.
  Run a generated test class that:
    a. happy path — must pass BEFORE and AFTER fix
    b. error path  — the specific failing scenario the fix addresses; expected to fail before, pass after
    c. downstream-error — downstream returns 500; confirm the service handles it correctly
  Cost: seconds (no network calls, no Docker).

Layer 4 — Stub Interaction Comparison
  Compare call counts per mock server between baseline and post-fix runs.
  If the fix causes the code to call a downstream service more or fewer times, flag it.
```

## Confidence Scoring

| Result | Confidence | Action |
|---|---|---|
| All 4 layers pass | HIGH | Auto-open PR (not draft) |
| Compile + unit pass, integration minor issue | MEDIUM | Draft PR |
| Unit tests regressed | LOW | Revert fix, open issue |
| Compile failed | SKIP | Revert fix, alert |

## Mock Server Libraries

### Java — WireMock (`org.wiremock:wiremock:3.3.1`)

- Runs as an embedded JUnit 5 extension (`@WireMockTest`)
- One `WireMockServer` field per downstream service, started with `WireMockServer(wireMockConfig().dynamicPort())`
- URL injected into Spring context via `@DynamicPropertySource`: `registry.add("services.payment.base-url", paymentMock::baseUrl)`
- No external process, no Docker. Works on any laptop.

```java
@SpringBootTest(webEnvironment = RANDOM_PORT)
@WireMockTest
class SonarFixPaymentServiceValidation {

    static WireMockServer paymentMock;

    @BeforeAll
    static void startMocks() {
        paymentMock = new WireMockServer(wireMockConfig().dynamicPort());
        paymentMock.start();
    }

    @DynamicPropertySource
    static void injectUrls(DynamicPropertyRegistry r) {
        r.add("services.payment.base-url", paymentMock::baseUrl);
    }

    @Test
    void happyPath_downstreamCallBehaviourUnchanged() {
        paymentMock.stubFor(post("/charge").willReturn(okJson("{\"status\":\"ok\"}")));
        // call service under test
        // verify paymentMock.verify(postRequestedFor(urlEqualTo("/charge")));
    }
}
```

### .NET — WireMock.Net (`WireMock.Net 1.5.47`)

- Uses `WebApplicationFactory<Program>` + `IAsyncLifetime`
- Config overridden via `AddInMemoryCollection`: `{"Services:Payment:BaseUrl", server.Urls[0]}`
- One `WireMockServer` per downstream

```csharp
public class SonarFixPaymentValidation : IClassFixture<WebApplicationFactory<Program>>, IAsyncLifetime
{
    private WireMockServer _paymentMock = null!;
    private HttpClient _client = null!;

    public Task InitializeAsync()
    {
        _paymentMock = WireMockServer.Start();
        _client = _factory
            .WithWebHostBuilder(b => b.ConfigureAppConfiguration((_, cfg) =>
                cfg.AddInMemoryCollection(new Dictionary<string, string?> {
                    ["Services:Payment:BaseUrl"] = _paymentMock.Urls[0]
                })))
            .CreateClient();
        return Task.CompletedTask;
    }
}
```

### Python — pytest-httpserver (`pytest-httpserver==1.0.8`)

- Session-scoped fixtures in `conftest.py`
- `HTTPServer(host="127.0.0.1", port=0)` — OS assigns a free port
- URL injected via `monkeypatch.setenv`

```python
@pytest.fixture(scope="session")
def payment_server():
    with HTTPServer(host="127.0.0.1", port=0) as server:
        yield server

def test_happy_path(monkeypatch, payment_server):
    monkeypatch.setenv("PAYMENT_SERVICE_URL", payment_server.url_for(""))
    payment_server.expect_request("/charge", method="POST") \
        .respond_with_json({"status": "ok"})
    # call function under test
    payment_server.check_assertions()
```

### Node.js — nock (`^13.5.0`)

- Intercepts at `http.request` level — no real network calls
- `process.env.SERVICE_URL` is set before each test
- `nock.cleanAll()` in `afterEach` prevents stub leakage

```javascript
const nock = require('nock');

beforeEach(() => {
    process.env.PAYMENT_SERVICE_URL = 'http://payment-mock.local';
});

afterEach(() => { nock.cleanAll(); });

test('happy path', async () => {
    nock(process.env.PAYMENT_SERVICE_URL).post('/charge').reply(200, { status: 'ok' });
    // call function under test
    expect(nock.isDone()).toBe(true);
});
```

## Baseline vs Post-Fix Comparison

```
Baseline run (before fix):
  Layer 3 result: { stub_calls: { "payment-mock.local": 2, "inventory-mock.local": 1 } }

Post-fix run (after fix):
  Layer 3 result: { stub_calls: { "payment-mock.local": 2, "inventory-mock.local": 1 } }

Layer 4: counts match → PASS
```

If counts differ, the fix changed the number of downstream calls — flag as MEDIUM confidence.

## Why Not VCR/Cassettes?

VCR records real HTTP responses and plays them back. The problem: you have to have already made the real calls to record. On a fresh CI runner with a new fix branch, there are no cassettes yet. Generating them from scratch requires real downstream services — the thing we're trying to avoid.

WireMock/nock/pytest-httpserver generate *stub-first* tests: the agent writes the stub before running the test. No real services needed.
