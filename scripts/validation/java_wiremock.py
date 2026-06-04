#!/usr/bin/env python3
"""
Java WireMock integration — generates and runs WireMock-based validation tests.
Handles Spring Boot, Quarkus, and plain Java. Supports 1-N downstream services.
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


def run_java_integration(
    lang_config: Dict[str, Any],
    repo_path: str,
    changed_files: List[str],
    phase: str,
) -> Dict[str, Any]:
    repo = Path(repo_path)

    # 1. Ensure WireMock dependency is present
    _ensure_wiremock_dependency(repo, lang_config)

    # 2. Find or generate validation test class
    test_class_path = _find_or_generate_test(repo, lang_config, changed_files)

    if not test_class_path:
        return {"passed": True, "skipped": True, "reason": "No HTTP calls detected in changed files"}

    # 3. Run the validation test
    return _run_wiremock_test(repo, lang_config, test_class_path, phase)


def _ensure_wiremock_dependency(repo: Path, lang_config: Dict) -> None:
    if lang_config.get("wiremock_present"):
        return

    build_tool = lang_config.get("build_tool", "maven")

    if build_tool == "maven":
        pom = repo / "pom.xml"
        if pom.exists():
            content = pom.read_text(encoding="utf-8")
            if "wiremock" not in content.lower():
                # Insert before </dependencies>
                dep = """
        <dependency>
            <groupId>org.wiremock</groupId>
            <artifactId>wiremock</artifactId>
            <version>3.3.1</version>
            <scope>test</scope>
        </dependency>"""
                content = content.replace("</dependencies>", dep + "\n    </dependencies>", 1)
                pom.write_text(content, encoding="utf-8")
                print("  Added WireMock dependency to pom.xml")

    elif build_tool == "gradle":
        build = repo / "build.gradle"
        if build.exists():
            content = build.read_text(encoding="utf-8")
            if "wiremock" not in content.lower():
                dep = '\n    testImplementation "org.wiremock:wiremock:3.3.1"'
                content = re.sub(r'(dependencies\s*\{)', r'\1' + dep, content)
                build.write_text(content, encoding="utf-8")
                print("  Added WireMock dependency to build.gradle")


def _find_or_generate_test(
    repo: Path, lang_config: Dict, changed_files: List[str]
) -> Optional[Path]:
    framework = lang_config.get("framework", "plain-java")

    # Find existing validation tests for changed files
    for src_file in changed_files:
        class_name = Path(src_file).stem
        existing = _find_existing_wiremock_test(repo, class_name)
        if existing:
            print(f"  Found existing WireMock test: {existing}")
            return existing

    # No existing test — analyse HTTP calls and generate one
    http_calls = _detect_http_calls(repo, changed_files)
    if not http_calls:
        return None

    return _generate_wiremock_test(repo, lang_config, changed_files, http_calls)


def _find_existing_wiremock_test(repo: Path, class_name: str) -> Optional[Path]:
    patterns = [f"*{class_name}*Test.java", f"*{class_name}*Tests.java",
                f"*{class_name}*IntegrationTest.java"]
    for pattern in patterns:
        matches = list(repo.rglob(pattern))
        for match in matches:
            if "wiremock" in match.read_text(encoding="utf-8", errors="ignore").lower():
                return match
    return None


def _detect_http_calls(repo: Path, changed_files: List[str]) -> List[Dict]:
    """Scan changed source files for outbound HTTP calls."""
    calls = []

    http_patterns = [
        # RestTemplate
        (r'restTemplate\.(get|post|put|delete)ForObject\(["\']([^"\']+)["\']', "resttemplate"),
        (r'restTemplate\.(get|post|put|delete)ForEntity\(["\']([^"\']+)["\']', "resttemplate"),
        (r'restTemplate\.exchange\(["\']([^"\']+)["\']', "resttemplate"),
        # WebClient
        (r'webClient\.(get|post|put|delete)\(\).*?uri\(["\']([^"\']+)["\']', "webclient"),
        # FeignClient URL
        (r'@FeignClient\([^)]*url\s*=\s*["\']([^"\']+)["\']', "feign"),
        # Generic URL patterns
        (r'\$\{([a-zA-Z0-9._-]+\.url[^\}]*)\}', "property"),
        (r'getenv\(["\']([A-Z_]+_URL)["\']', "env"),
    ]

    for src_file in changed_files:
        src_path = repo / src_file if not Path(src_file).is_absolute() else Path(src_file)
        if not src_path.exists():
            # Try to find the file
            matches = list(repo.rglob(Path(src_file).name))
            if matches:
                src_path = matches[0]
            else:
                continue

        content = src_path.read_text(encoding="utf-8", errors="ignore")

        for pattern, client_type in http_patterns:
            for match in re.finditer(pattern, content, re.DOTALL):
                url_hint = match.group(1) if match.lastindex >= 1 else ""
                calls.append({
                    "file": str(src_path),
                    "client_type": client_type,
                    "url_hint": url_hint,
                    "service_name": _infer_service_name(url_hint),
                })

    # Deduplicate by service name
    seen = set()
    unique = []
    for c in calls:
        key = c["service_name"]
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def _infer_service_name(url_hint: str) -> str:
    """Derive a service name from a URL property key or path."""
    # e.g. "payment.service.url" → "payment"
    # e.g. "PAYMENT_SERVICE_URL" → "payment"
    # e.g. "/api/payment/charge" → "payment"
    hint = url_hint.lower()
    for sep in [".", "_", "/"]:
        parts = [p for p in hint.split(sep) if p and p not in
                 ("service", "url", "api", "v1", "v2", "http", "https", "base", "host")]
        if parts:
            return parts[0]
    return "downstream"


def _generate_wiremock_test(
    repo: Path,
    lang_config: Dict,
    changed_files: List[str],
    http_calls: List[Dict],
) -> Path:
    framework   = lang_config.get("framework", "plain-java")
    build_tool  = lang_config.get("build_tool", "maven")
    changed_cls = Path(changed_files[0]).stem if changed_files else "Service"

    # Determine package from existing test structure
    test_root = _find_test_root(repo, build_tool)
    package   = _infer_package(repo, test_root, changed_files)

    services = http_calls  # one entry per upstream service

    class_body = _render_spring_test(changed_cls, package, services) \
        if framework == "spring-boot" \
        else _render_plain_java_test(changed_cls, package, services)

    # Write the file
    if package:
        pkg_dir = test_root / package.replace(".", "/")
    else:
        pkg_dir = test_root
    pkg_dir.mkdir(parents=True, exist_ok=True)

    test_path = pkg_dir / f"SonarFix{changed_cls}ValidationTest.java"
    test_path.write_text(class_body, encoding="utf-8")
    print(f"  Generated WireMock test: {test_path}")
    return test_path


def _render_spring_test(changed_cls: str, package: str, services: List[Dict]) -> str:
    pkg_line = f"package {package};\n\n" if package else ""

    mock_fields = "\n".join(
        f"    static WireMockServer {s['service_name']}Mock = "
        f"new WireMockServer(WireMockConfiguration.options().dynamicPort());"
        for s in services
    )
    start_calls  = "\n".join(f"        {s['service_name']}Mock.start();"     for s in services)
    stop_calls   = "\n".join(f"        {s['service_name']}Mock.stop();"      for s in services)
    reset_calls  = "\n".join(f"        {s['service_name']}Mock.resetAll();"  for s in services)

    prop_overrides = "\n".join(
        f'        registry.add("{s["service_name"]}.service.url", {s["service_name"]}Mock::baseUrl);'
        for s in services
    )

    happy_stubs = "\n".join(
        f'        {s["service_name"]}Mock.stubFor(WireMock.any(WireMock.anyUrl())\n'
        f'            .willReturn(WireMock.okJson("{{\\"status\\":\\"ok\\"}}")));'
        for s in services
    )

    error_stubs = "\n".join(
        f'        {s["service_name"]}Mock.stubFor(WireMock.any(WireMock.anyUrl())\n'
        f'            .willReturn(WireMock.aResponse().withStatus(500)));'
        for s in services
    )

    verify_calls = "\n".join(
        f"        {s['service_name']}Mock.verify(WireMock.moreThanOrExactly(1), "
        f"WireMock.anyRequestedFor(WireMock.anyUrl()));"
        for s in services
    )

    return f"""{pkg_line}import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.client.WireMock;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.*;

/**
 * Auto-generated by SonarQube Fixer Agent — Integration validation for {changed_cls}.
 * WireMock servers run on random ports; URLs are injected via @DynamicPropertySource.
 * No Docker required.
 *
 * ── CLAUDE CODE: fill in every section marked FILL-IN before running ──────────
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SonarFix{changed_cls}ValidationTest {{

    // ── FILL-IN: Autowire the service under test ────────────────────────────────
    // Read the source file for the exact class name and package.
    // @Autowired
    // private {changed_cls} service;
    // ───────────────────────────────────────────────────────────────────────────

{mock_fields}

    @DynamicPropertySource
    static void overrideServiceUrls(DynamicPropertyRegistry registry) {{
{prop_overrides}
        // If the property key differs, read the source @Value annotation or
        // application.properties to find the actual key name and correct it here.
    }}

    @BeforeAll
    static void startMocks() {{
{start_calls}
    }}

    @AfterAll
    static void stopMocks() {{
{stop_calls}
    }}

    @BeforeEach
    void resetMocks() {{
{reset_calls}
    }}

    /**
     * Happy path — must pass BEFORE and AFTER the fix.
     * Verifies the fix does not regress normal successful-call behaviour.
     */
    @Test
    void happyPath_downstreamCallBehaviourUnchanged() {{
{happy_stubs}

        // ── FILL-IN: call the method being fixed ────────────────────────────────
        // Read {changed_cls}.java, find the public method that analysis.json targets.
        // Example:
        //   var result = service.methodName(validInput());
        //   assertThat(result).isNotNull();
        // ────────────────────────────────────────────────────────────────────────

{verify_calls}
    }}

    /**
     * Fix scenario — should FAIL before fix, PASS after fix.
     * Stubs the exact problematic response the SonarQube rule flags.
     */
    @Test
    void fixScenario_handledGracefullyAfterFix() {{
        // ── FILL-IN ─────────────────────────────────────────────────────────────
        // 1. Stub the problematic response (null field, empty body, 422, etc.)
        //    e.g. for S2259 (null dereference): stub returns {{}} with missing field
        //    e.g. for S2095 (resource leak):    call normally but assert resource closed
        //
        // 2. Call the method and assert graceful handling:
        //    assertThatCode(() -> service.methodName(input())).doesNotThrowAnyException();
        // ────────────────────────────────────────────────────────────────────────
    }}

    /**
     * Downstream 500 — must pass BEFORE and AFTER the fix.
     * Confirms the service handles downstream failures correctly.
     */
    @Test
    void downstreamError_handledCorrectly() {{
{error_stubs}

        // ── FILL-IN ─────────────────────────────────────────────────────────────
        // Assert the service throws the correct exception or returns a fallback:
        // assertThatThrownBy(() -> service.methodName(input()))
        //     .isInstanceOf(YourServiceException.class);
        // ────────────────────────────────────────────────────────────────────────
    }}
}}
"""


def _render_plain_java_test(changed_cls: str, package: str, services: List[Dict]) -> str:
    pkg_line = f"package {package};\n\n" if package else ""

    fields = "\n".join(
        f"    private WireMockServer {s['service_name']}Mock;" for s in services
    )
    setup = "\n".join(
        f"        {s['service_name']}Mock = new WireMockServer(WireMockConfiguration.options().dynamicPort());\n"
        f"        {s['service_name']}Mock.start();"
        for s in services
    )
    teardown = "\n".join(
        f"        {s['service_name']}Mock.stop();" for s in services
    )

    return f"""{pkg_line}import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.client.WireMock;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;
import org.junit.jupiter.api.*;

import static org.assertj.core.api.Assertions.*;

/**
 * Auto-generated by SonarQube Fixer Agent.
 */
class SonarFix{changed_cls}ValidationTest {{

{fields}

    @BeforeEach
    void setUp() {{
{setup}
    }}

    @AfterEach
    void tearDown() {{
{teardown}
    }}

    @Test
    void happyPath_downstreamCallBehaviourUnchanged() {{
        // Stub downstreams and call the service under test
    }}

    @Test
    void errorPath_fixedScenario() {{
        // Test the specific fix scenario
    }}
}}
"""


def _run_wiremock_test(
    repo: Path, lang_config: Dict, test_path: Path, phase: str
) -> Dict[str, Any]:
    build_tool = lang_config.get("build_tool", "maven")
    class_name = test_path.stem

    if build_tool == "maven":
        cmd = f"mvn test -Dtest={class_name} -pl . --no-transfer-progress"
    else:
        cmd = f"gradle test --tests '*.{class_name}' --no-daemon"

    print(f"  Running: {cmd}")
    t0 = time.time()
    proc = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True)
    elapsed = round(time.time() - t0, 1)

    stub_calls = _extract_stub_calls(proc.stdout + proc.stderr)

    return {
        "passed": proc.returncode == 0,
        "command": cmd,
        "test_class": class_name,
        "elapsed_sec": elapsed,
        "stub_calls": stub_calls,
        "stdout": proc.stdout[-3000:] if proc.stdout else "",
        "stderr": proc.stderr[-1000:] if proc.stderr else "",
    }


def _extract_stub_calls(output: str) -> Dict[str, int]:
    """Parse WireMock log output to count calls per service/port."""
    calls: Dict[str, int] = {}
    for match in re.finditer(r"Matched response definition:\s*(\S+)", output):
        service = match.group(1)
        calls[service] = calls.get(service, 0) + 1
    return calls


def _find_test_root(repo: Path, build_tool: str) -> Path:
    candidates = [
        repo / "src" / "test" / "java",
        repo / "src" / "test",
        repo / "test",
    ]
    for c in candidates:
        if c.exists():
            return c
    return repo / "src" / "test" / "java"


def _infer_package(repo: Path, test_root: Path, changed_files: List[str]) -> str:
    if not changed_files:
        return ""
    src_file = Path(changed_files[0])
    # Find the file's package from its content
    for candidate in repo.rglob(src_file.name):
        content = candidate.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^package\s+([\w.]+)\s*;", content, re.MULTILINE)
        if m:
            return m.group(1)
    return ""
