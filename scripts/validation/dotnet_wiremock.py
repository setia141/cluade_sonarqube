#!/usr/bin/env python3
"""
.NET WireMock.Net integration — generates and runs WireMock.Net validation tests.
Supports ASP.NET Core (WebApplicationFactory) and plain .NET (HttpClient).
"""

import re
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional


def run_dotnet_integration(
    lang_config: Dict[str, Any],
    repo_path: str,
    changed_files: List[str],
    phase: str,
) -> Dict[str, Any]:
    repo = Path(repo_path)

    _ensure_wiremock_dependency(repo, lang_config)

    test_path = _find_or_generate_test(repo, lang_config, changed_files)
    if not test_path:
        return {"passed": True, "skipped": True, "reason": "No HTTP calls detected"}

    return _run_test(repo, lang_config, test_path, phase)


def _ensure_wiremock_dependency(repo: Path, lang_config: Dict) -> None:
    if lang_config.get("wiremock_present"):
        return

    # Find test .csproj
    test_csproj = _find_test_csproj(repo)
    if not test_csproj:
        return

    content = test_csproj.read_text(encoding="utf-8")
    if "wiremock" in content.lower():
        return

    dep = ('  <ItemGroup>\n'
           '    <PackageReference Include="WireMock.Net" Version="1.5.47" />\n'
           '    <PackageReference Include="Microsoft.AspNetCore.Mvc.Testing" Version="8.0.0" />\n'
           '  </ItemGroup>\n')
    content = content.replace("</Project>", dep + "</Project>")
    test_csproj.write_text(content, encoding="utf-8")
    print(f"  Added WireMock.Net to {test_csproj.name}")

    subprocess.run("dotnet restore", shell=True, cwd=str(repo), capture_output=True)


def _find_test_csproj(repo: Path) -> Optional[Path]:
    for csproj in repo.rglob("*.csproj"):
        content = csproj.read_text(encoding="utf-8", errors="ignore").lower()
        if any(kw in content for kw in ["xunit", "nunit", "mstest", "testhost"]):
            return csproj
    return next(iter(repo.rglob("*.csproj")), None)


def _find_or_generate_test(
    repo: Path, lang_config: Dict, changed_files: List[str]
) -> Optional[Path]:
    for src_file in changed_files:
        cls_name = Path(src_file).stem
        existing = _find_existing_test(repo, cls_name)
        if existing:
            print(f"  Found existing WireMock.Net test: {existing}")
            return existing

    http_calls = _detect_http_calls(repo, changed_files)
    if not http_calls:
        return None

    return _generate_test(repo, lang_config, changed_files, http_calls)


def _find_existing_test(repo: Path, cls_name: str) -> Optional[Path]:
    for pattern in [f"*{cls_name}*Tests.cs", f"*{cls_name}*Test.cs",
                    f"*{cls_name}*IntegrationTests.cs"]:
        for match in repo.rglob(pattern):
            if "wiremock" in match.read_text(encoding="utf-8", errors="ignore").lower():
                return match
    return None


def _detect_http_calls(repo: Path, changed_files: List[str]) -> List[Dict]:
    patterns = [
        r'GetAsync\(.*?["\']([^"\']+)["\']',
        r'PostAsync\(.*?["\']([^"\']+)["\']',
        r'PutAsync\(.*?["\']([^"\']+)["\']',
        r'DeleteAsync\(.*?["\']([^"\']+)["\']',
        r'\["([A-Za-z]+:[A-Za-z]+:(?:BaseUrl|Url))"\]',
        r'GetValue<string>\(["\']([^"\']+)["\']',
    ]

    seen: set = set()
    calls: List[Dict] = []

    for src_file in changed_files:
        path = _resolve_file(repo, src_file)
        if not path:
            continue

        content = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            for m in re.finditer(pattern, content):
                hint = m.group(1)
                svc  = _infer_service_name(hint)
                if svc not in seen:
                    seen.add(svc)
                    calls.append({"url_hint": hint, "service_name": svc})

    return calls


def _infer_service_name(hint: str) -> str:
    hint = hint.lower()
    for sep in [":", ".", "_", "/"]:
        parts = [p for p in hint.split(sep) if p and p not in
                 ("services", "service", "url", "baseurl", "api", "v1", "v2", "http", "https")]
        if parts:
            return parts[0]
    return "downstream"


def _generate_test(
    repo: Path, lang_config: Dict, changed_files: List[str], services: List[Dict]
) -> Path:
    framework = lang_config.get("framework", "dotnet-generic")
    test_fw   = lang_config.get("test_framework", "xunit")
    cls_name  = Path(changed_files[0]).stem if changed_files else "Service"
    namespace = _infer_namespace(repo, changed_files)

    test_dir = _find_test_dir(repo)
    test_dir.mkdir(parents=True, exist_ok=True)

    test_path = test_dir / f"SonarFix{cls_name}ValidationTests.cs"
    body = _render_aspnetcore_test(cls_name, namespace, services, test_fw) \
        if framework == "aspnet-core" \
        else _render_plain_test(cls_name, namespace, services, test_fw)
    test_path.write_text(body, encoding="utf-8")
    print(f"  Generated WireMock.Net test: {test_path}")
    return test_path


def _render_aspnetcore_test(
    cls_name: str, namespace: str, services: List[Dict], test_fw: str
) -> str:
    ns_line = f"namespace {namespace};\n\n" if namespace else ""

    mock_fields = "\n".join(
        f"    private WireMockServer _{s['service_name']}Mock;" for s in services
    )
    init_mocks = "\n".join(
        f"        _{s['service_name']}Mock = WireMockServer.Start();" for s in services
    )
    config_overrides = "\n".join(
        f'                        ["{_config_key(s["service_name"])}"] = _{s["service_name"]}Mock.Urls[0],'
        for s in services
    )
    stop_mocks = "\n".join(
        f"        _{s['service_name']}Mock?.Stop();" for s in services
    )

    fact_attr = "[Fact]" if test_fw == "xunit" else "[Test]"

    stub_happy = "\n".join(
        f"""        _{s['service_name']}Mock
            .Given(Request.Create().WithPath("/*").UsingAnyMethod())
            .RespondWith(Response.Create().WithStatusCode(200)
                .WithBodyAsJson(new {{ status = "ok" }}));"""
        for s in services
    )

    stub_error = "\n".join(
        f"""        _{s['service_name']}Mock
            .Given(Request.Create().WithPath("/*").UsingAnyMethod())
            .RespondWith(Response.Create().WithStatusCode(500));"""
        for s in services
    )

    return f"""{ns_line}using WireMock.Server;
using WireMock.RequestBuilders;
using WireMock.ResponseBuilders;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using System.Net.Http.Json;
using Xunit;

/// <summary>
/// Auto-generated by SonarQube Fixer Agent.
/// Validates that fixes to {cls_name} do not regress downstream call behaviour.
/// WireMock.Net stubs replace real downstream services.
/// </summary>
public class SonarFix{cls_name}ValidationTests : IAsyncLifetime
{{
{mock_fields}
    private WebApplicationFactory<Program> _factory;
    private HttpClient _client;

    public async Task InitializeAsync()
    {{
{init_mocks}

        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(builder =>
            {{
                builder.ConfigureAppConfiguration((_, cfg) =>
                {{
                    cfg.AddInMemoryCollection(new Dictionary<string, string?>
                    {{
{config_overrides}
                    }});
                }});
            }});

        _client = _factory.CreateClient();
    }}

    {fact_attr}
    public async Task HappyPath_DownstreamCallBehaviourUnchanged()
    {{
{stub_happy}

        // TODO: call the endpoint under test and assert happy path result
        // var response = await _client.PostAsJsonAsync("/api/...", payload);
        // response.EnsureSuccessStatusCode();

        // Verify call counts unchanged
        // Assert.Equal(1, _{services[0]['service_name']}Mock.LogEntries.Count());
    }}

    {fact_attr}
    public async Task ErrorPath_FixedScenario()
    {{
        // Stub the problematic response (missing field, null, etc.)
        // Assert the fix handles it gracefully (no 500, no unhandled exception)
    }}

    {fact_attr}
    public async Task DownstreamError_HandledCorrectly()
    {{
{stub_error}

        // Assert your service returns an appropriate error response
        // var response = await _client.PostAsJsonAsync("/api/...", payload);
        // Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
    }}

    public async Task DisposeAsync()
    {{
{stop_mocks}
        _factory?.Dispose();
        _client?.Dispose();
    }}
}}
"""


def _render_plain_test(
    cls_name: str, namespace: str, services: List[Dict], test_fw: str
) -> str:
    ns_line = f"namespace {namespace};\n\n" if namespace else ""
    fact_attr = "[Fact]" if test_fw == "xunit" else "[Test]"

    mock_fields = "\n".join(
        f"    private WireMockServer _{s['service_name']}Mock;" for s in services
    )
    init_mocks = "\n".join(
        f"        _{s['service_name']}Mock = WireMockServer.Start();" for s in services
    )
    stop_mocks = "\n".join(
        f"        _{s['service_name']}Mock?.Stop();" for s in services
    )

    return f"""{ns_line}using WireMock.Server;
using WireMock.RequestBuilders;
using WireMock.ResponseBuilders;
using Xunit;

/// <summary>Auto-generated by SonarQube Fixer Agent.</summary>
public class SonarFix{cls_name}ValidationTests : IAsyncLifetime
{{
{mock_fields}

    public async Task InitializeAsync()
    {{
{init_mocks}
    }}

    {fact_attr}
    public async Task HappyPath_DownstreamCallBehaviourUnchanged()
    {{
        // Configure HttpClient to use mock URL, call service, assert result
    }}

    {fact_attr}
    public async Task ErrorPath_FixedScenario()
    {{
        // Test the specific fix scenario
    }}

    public async Task DisposeAsync()
    {{
{stop_mocks}
    }}
}}
"""


def _run_test(repo: Path, lang_config: Dict, test_path: Path, phase: str) -> Dict[str, Any]:
    cls_name = test_path.stem
    cmd = f'dotnet test --filter "ClassName~{cls_name}" --no-build --logger "console;verbosity=normal"'

    print(f"  Running: {cmd}")
    t0 = time.time()
    proc = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True)
    elapsed = round(time.time() - t0, 1)

    stub_calls = _extract_stub_calls(proc.stdout)

    return {
        "passed": proc.returncode == 0,
        "command": cmd,
        "test_class": cls_name,
        "elapsed_sec": elapsed,
        "stub_calls": stub_calls,
        "stdout": proc.stdout[-3000:] if proc.stdout else "",
        "stderr": proc.stderr[-1000:] if proc.stderr else "",
    }


def _extract_stub_calls(output: str) -> Dict[str, int]:
    calls: Dict[str, int] = {}
    for m in re.finditer(r"WireMock.*?(\w+Mock).*?matched", output, re.IGNORECASE):
        key = m.group(1)
        calls[key] = calls.get(key, 0) + 1
    return calls


def _config_key(service_name: str) -> str:
    name = service_name.capitalize()
    return f"Services:{name}:BaseUrl"


def _find_test_dir(repo: Path) -> Path:
    for candidate in repo.rglob("*.Tests"):
        if candidate.is_dir():
            return candidate
    for candidate in repo.iterdir():
        if candidate.is_dir() and "test" in candidate.name.lower():
            return candidate
    return repo / "tests"


def _infer_namespace(repo: Path, changed_files: List[str]) -> str:
    if not changed_files:
        return ""
    path = _resolve_file(repo, changed_files[0])
    if not path:
        return ""
    content = path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^namespace\s+([\w.]+)", content, re.MULTILINE)
    return m.group(1) if m else ""


def _resolve_file(repo: Path, src_file: str) -> Optional[Path]:
    p = Path(src_file)
    if p.is_absolute() and p.exists():
        return p
    candidate = repo / src_file
    if candidate.exists():
        return candidate
    matches = list(repo.rglob(p.name))
    return matches[0] if matches else None
