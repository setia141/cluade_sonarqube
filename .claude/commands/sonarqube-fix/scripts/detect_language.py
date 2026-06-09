#!/usr/bin/env python3
"""
Detect programming language, framework, HTTP client, and test framework from repo structure.
Usage: python3 detect_language.py --repo /path/to/repo --output lang.json
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Set
import xml.etree.ElementTree as ET


def detect_language(repo_path: str = ".") -> Dict[str, Any]:
    repo = Path(repo_path).resolve()

    # Java — pom.xml or build.gradle
    if (repo / "pom.xml").exists():
        return _java_details(repo, "maven")
    if (repo / "build.gradle").exists() or (repo / "build.gradle.kts").exists():
        return _java_details(repo, "gradle")

    # .NET — *.csproj or *.sln
    csproj_files = list(repo.rglob("*.csproj"))
    if csproj_files or list(repo.rglob("*.sln")):
        return _dotnet_details(repo, csproj_files)

    # Python — before Node because some Python projects have package.json
    if any((repo / f).exists() for f in ["setup.py", "pyproject.toml", "requirements.txt", "setup.cfg"]):
        return _python_details(repo)

    # Node.js
    if (repo / "package.json").exists():
        try:
            pkg = json.loads((repo / "package.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pkg = {}
        return _node_details(repo, pkg)

    return {"language": "unknown", "confidence": "low"}


# ── Java ──────────────────────────────────────────────────────────────────────

def _java_details(repo: Path, build_tool: str) -> Dict[str, Any]:
    deps = _maven_deps(repo) if build_tool == "maven" else _gradle_deps(repo)

    framework = "plain-java"
    if any("spring-boot" in d for d in deps):
        framework = "spring-boot"
    elif any("quarkus" in d for d in deps):
        framework = "quarkus"
    elif any("micronaut" in d for d in deps):
        framework = "micronaut"

    if "junit-jupiter-api" in deps or "junit-jupiter" in deps:
        test_framework = "junit5"
    elif "junit" in deps:
        test_framework = "junit4"
    else:
        test_framework = "junit5"

    if any("spring-web" in d or "spring-webflux" in d for d in deps):
        http_client = "resttemplate-webclient"
    elif any("feign" in d for d in deps):
        http_client = "feign"
    elif any("okhttp" in d for d in deps):
        http_client = "okhttp"
    elif any("httpclient" in d for d in deps):
        http_client = "apache-httpclient"
    else:
        http_client = "java-net"

    wiremock_present = any("wiremock" in d for d in deps)
    jacoco_present   = any("jacoco" in d for d in deps)

    if framework == "spring-boot":
        url_config = "application-properties"
        test_override = "dynamic-property-source"
    elif framework == "quarkus":
        url_config = "quarkus-config"
        test_override = "quarkus-test-profile"
    else:
        url_config = "system-properties"
        test_override = "system-properties"

    return {
        "language": "java",
        "framework": framework,
        "build_tool": build_tool,
        "test_framework": test_framework,
        "http_client": http_client,
        "wiremock_present": wiremock_present,
        "wiremock_dependency": "org.wiremock:wiremock:3.3.1",
        "jacoco_present": jacoco_present,
        "url_config_pattern": url_config,
        "test_override_method": test_override,
        "sonarqube_rule_prefix": "java:",
        "build_command": "mvn compile" if build_tool == "maven" else "gradle compileJava",
        "test_command": "mvn test" if build_tool == "maven" else "gradle test",
        "confidence": "high",
        **_detect_integration_tests(repo, "java", build_tool),
    }


def _maven_deps(repo: Path) -> Set[str]:
    deps: Set[str] = set()
    pom = repo / "pom.xml"
    if not pom.exists():
        return deps
    try:
        ns = {"m": "http://maven.apache.org/POM/4.0.0"}
        root = ET.parse(pom).getroot()
        for el in root.findall(".//m:artifactId", ns):
            if el.text:
                deps.add(el.text.lower())
    except ET.ParseError:
        pass
    return deps


def _gradle_deps(repo: Path) -> Set[str]:
    deps: Set[str] = set()
    for fname in ["build.gradle", "build.gradle.kts"]:
        f = repo / fname
        if f.exists():
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                # rough: extract artifact names from dependency strings
                for part in line.split('"'):
                    if ":" in part:
                        segments = part.split(":")
                        if len(segments) >= 2:
                            deps.add(segments[1].lower())
    return deps


# ── .NET ─────────────────────────────────────────────────────────────────────

def _dotnet_details(repo: Path, csproj_files: List[Path]) -> Dict[str, Any]:
    packages: Set[str] = set()
    for csproj in csproj_files[:5]:
        try:
            root = ET.parse(csproj).getroot()
            for ref in root.findall(".//PackageReference"):
                name = ref.get("Include", "").lower()
                if name:
                    packages.add(name)
        except ET.ParseError:
            pass

    framework = "aspnet-core" if any("aspnetcore" in p for p in packages) else "dotnet-generic"

    if "xunit" in packages:
        test_framework = "xunit"
    elif "nunit" in packages:
        test_framework = "nunit"
    elif "mstest.testframework" in packages:
        test_framework = "mstest"
    else:
        test_framework = "xunit"

    http_client      = "refit" if any("refit" in p for p in packages) else "httpclient"
    wiremock_present = any("wiremock" in p for p in packages)
    coverlet_present = any("coverlet" in p for p in packages)

    return {
        "language": "dotnet",
        "framework": framework,
        "build_tool": "dotnet",
        "test_framework": test_framework,
        "http_client": http_client,
        "wiremock_present": wiremock_present,
        "wiremock_dependency": "WireMock.Net",
        "coverlet_present": coverlet_present,
        "url_config_pattern": "appsettings-json",
        "test_override_method": "webapplicationfactory-config",
        "sonarqube_rule_prefix": "csharpsquid:",
        "build_command": "dotnet build",
        "test_command": "dotnet test",
        "confidence": "high",
        **_detect_integration_tests(repo, "dotnet"),
    }


# ── Python ────────────────────────────────────────────────────────────────────

def _python_details(repo: Path) -> Dict[str, Any]:
    deps: Set[str] = set()
    for req_file in ["requirements.txt", "requirements-dev.txt",
                     "requirements/base.txt", "requirements/dev.txt"]:
        p = repo / req_file
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                pkg = line.split("==")[0].split(">=")[0].split("[")[0].strip().lower()
                if pkg and not pkg.startswith("#"):
                    deps.add(pkg)

    # pyproject.toml
    pyproject = repo / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
        for pkg in ["fastapi", "django", "flask", "requests", "httpx",
                    "aiohttp", "pytest", "pytest-httpserver", "responses"]:
            if pkg in content:
                deps.add(pkg)

    if "fastapi" in deps:
        framework = "fastapi"
    elif "django" in deps:
        framework = "django"
    elif "flask" in deps:
        framework = "flask"
    else:
        framework = "plain-python"

    if "httpx" in deps:
        http_client = "httpx"
    elif "aiohttp" in deps:
        http_client = "aiohttp"
    else:
        http_client = "requests"

    if "pytest-httpserver" in deps:
        http_mock_library = "pytest-httpserver"
        http_mock_present = True
    elif "responses" in deps:
        http_mock_library = "responses"
        http_mock_present = True
    else:
        http_mock_library = "pytest-httpserver"
        http_mock_present = False

    coverage_tool_present = "pytest-cov" in deps or "coverage" in deps
    coverage_tool = "pytest-cov" if "pytest-cov" in deps else ("coverage" if "coverage" in deps else None)

    return {
        "language": "python",
        "framework": framework,
        "build_tool": "pip",
        "test_framework": "pytest",
        "http_client": http_client,
        "http_mock_library": http_mock_library,
        "http_mock_present": http_mock_present,
        "http_mock_dependency": "pytest-httpserver==1.0.8",
        "coverage_tool_present": coverage_tool_present,
        "coverage_tool": coverage_tool,
        "url_config_pattern": "env-vars",
        "test_override_method": "monkeypatch-env",
        "sonarqube_rule_prefix": "python:",
        "build_command": "pip install -r requirements.txt",
        "test_command": "pytest",
        "confidence": "high",
        **_detect_integration_tests(repo, "python"),
    }


# ── Node.js ───────────────────────────────────────────────────────────────────

def _node_details(repo: Path, pkg: Dict) -> Dict[str, Any]:
    all_deps: Set[str] = set()
    all_deps.update(k.lower() for k in pkg.get("dependencies", {}).keys())
    all_deps.update(k.lower() for k in pkg.get("devDependencies", {}).keys())

    if "express" in all_deps:
        framework = "express"
    elif "@nestjs/core" in all_deps or "nestjs" in all_deps:
        framework = "nestjs"
    elif "fastify" in all_deps:
        framework = "fastify"
    elif "koa" in all_deps:
        framework = "koa"
    else:
        framework = "plain-node"

    if "jest" in all_deps:
        test_framework = "jest"
    elif "vitest" in all_deps:
        test_framework = "vitest"
    elif "mocha" in all_deps:
        test_framework = "mocha"
    else:
        test_framework = "jest"

    if "axios" in all_deps:
        http_client = "axios"
    elif "node-fetch" in all_deps:
        http_client = "node-fetch"
    elif "got" in all_deps:
        http_client = "got"
    else:
        http_client = "fetch"

    if "nock" in all_deps:
        http_mock_library = "nock"
        http_mock_present = True
    elif "msw" in all_deps:
        http_mock_library = "msw"
        http_mock_present = True
    else:
        http_mock_library = "nock"
        http_mock_present = False

    # Detect TypeScript
    is_typescript = "typescript" in all_deps or (repo / "tsconfig.json").exists()
    sonarqube_prefix = "typescript:" if is_typescript else "javascript:"

    # Detect coverage tooling
    # Vitest needs @vitest/coverage-v8 or @vitest/coverage-istanbul explicitly
    # Jest has --coverage built-in but needs the flag; check jest.config for coverageProvider
    vitest_coverage = "@vitest/coverage-v8" in all_deps or "@vitest/coverage-istanbul" in all_deps
    jest_coverage_configured = _jest_coverage_configured(repo, pkg)
    coverage_configured = vitest_coverage or jest_coverage_configured
    # Which provider to use
    if vitest_coverage:
        coverage_tool = "@vitest/coverage-v8"
    elif "jest" in all_deps or "jest" in pkg.get("scripts", {}).get("test", ""):
        coverage_tool = "jest-coverage"
    else:
        coverage_tool = None

    return {
        "language": "node",
        "framework": framework,
        "build_tool": "npm",
        "test_framework": test_framework,
        "http_client": http_client,
        "http_mock_library": http_mock_library,
        "http_mock_present": http_mock_present,
        "http_mock_dependency": "nock",
        "typescript": is_typescript,
        "coverage_configured": coverage_configured,
        "coverage_tool": coverage_tool,
        "url_config_pattern": "env-vars",
        "test_override_method": "process-env",
        "sonarqube_rule_prefix": sonarqube_prefix,
        "build_command": "npm install",
        "test_command": "npm test",
        "confidence": "high",
        **_detect_integration_tests(repo, "node"),
    }


def _jest_coverage_configured(repo: Path, pkg: Dict) -> bool:
    """Check if Jest is configured to collect coverage in package.json or jest.config.*"""
    # Check package.json jest key
    jest_config = pkg.get("jest", {})
    if jest_config.get("collectCoverage") or jest_config.get("coverageDirectory"):
        return True
    # Check for jest.config.js / jest.config.ts / jest.config.json
    for cfg_name in ["jest.config.js", "jest.config.ts", "jest.config.cjs", "jest.config.json"]:
        cfg = repo / cfg_name
        if cfg.exists():
            content = cfg.read_text(encoding="utf-8", errors="ignore")
            if "collectCoverage" in content or "coverageDirectory" in content:
                return True
    return False


def _detect_integration_tests(repo: Path, language: str, build_tool: str = "") -> Dict[str, Any]:
    """Detect existing integration tests and produce a ready-to-run command."""
    none = {"has_integration_tests": False, "integration_test_command": None, "integration_test_dir": None}

    if language == "java":
        it_files = list(repo.rglob("*IT.java")) + list(repo.rglob("*IntegrationTest.java"))
        if not it_files:
            return none
        if build_tool == "maven":
            cmd = "mvn test -Dtest='*IT,*IntegrationTest' --no-transfer-progress -DfailIfNoTests=false"
        else:
            cmd = "gradle test --tests '*IT' --tests '*IntegrationTest'"
        return {"has_integration_tests": True, "integration_test_command": cmd, "integration_test_dir": "src/test/java"}

    if language == "dotnet":
        it_projects = [p for p in repo.rglob("*.csproj") if "integration" in p.name.lower()]
        it_files    = list(repo.rglob("*IntegrationTest.cs")) + list(repo.rglob("*IntegrationTests.cs"))
        if not it_projects and not it_files:
            return none
        if it_projects:
            cmd = f'dotnet test "{it_projects[0].relative_to(repo)}"'
        else:
            cmd = 'dotnet test --filter "Category=Integration|FullyQualifiedName~IntegrationTest"'
        return {"has_integration_tests": True, "integration_test_command": cmd, "integration_test_dir": None}

    if language == "python":
        integration_dir = repo / "tests" / "integration"
        it_files = list(repo.rglob("test_*integration*.py")) + list(repo.rglob("*_integration_test.py"))
        if not integration_dir.exists() and not it_files:
            return none
        if integration_dir.exists():
            cmd = f"pytest tests/integration/ -v"
            d   = "tests/integration"
        else:
            cmd = "pytest -m integration -v"
            d   = None
        return {"has_integration_tests": True, "integration_test_command": cmd, "integration_test_dir": d}

    if language == "node":
        integration_dirs = [repo / "tests" / "integration", repo / "__tests__" / "integration", repo / "test" / "integration"]
        it_files = (list(repo.rglob("*.integration.test.js")) + list(repo.rglob("*.integration.test.ts")) +
                    list(repo.rglob("*.integration.spec.js")) + list(repo.rglob("*.integration.spec.ts")))
        found_dir = next((d for d in integration_dirs if d.exists()), None)
        if not found_dir and not it_files:
            return none
        cmd = "npx jest --testPathPattern='integration' --no-coverage"
        return {"has_integration_tests": True, "integration_test_command": cmd,
                "integration_test_dir": str(found_dir.relative_to(repo)) if found_dir else None}

    return none


def main():
    parser = argparse.ArgumentParser(description="Detect project language and framework")
    parser.add_argument("--repo", default=".", help="Repository root path")
    parser.add_argument("--output", default=None, help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    result = detect_language(args.repo)
    output = json.dumps(result, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(output)

    lang = result.get("language", "unknown")
    fw   = result.get("framework", "N/A")
    print(f"\nDetected: {lang} / {fw}", file=sys.stderr)


if __name__ == "__main__":
    main()
