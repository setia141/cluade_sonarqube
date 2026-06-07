#!/usr/bin/env python3
"""
Python pytest-httpserver integration — generates and runs validation tests.
Supports Django, FastAPI, Flask, and plain Python.
"""

import re
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional


def run_python_integration(
    lang_config: Dict[str, Any],
    repo_path: str,
    changed_files: List[str],
    phase: str,
) -> Dict[str, Any]:
    repo = Path(repo_path)

    _ensure_dependency(repo, lang_config)

    test_path = _find_or_generate_test(repo, lang_config, changed_files)
    if not test_path:
        return {"passed": True, "skipped": True, "reason": "No HTTP calls detected"}

    return _run_test(repo, lang_config, test_path, phase)


def _ensure_dependency(repo: Path, lang_config: Dict) -> None:
    if lang_config.get("http_mock_present"):
        return

    for req_file in ["requirements-dev.txt", "requirements/dev.txt", "requirements.txt"]:
        req_path = repo / req_file
        if req_path.exists():
            content = req_path.read_text(encoding="utf-8")
            if "pytest-httpserver" not in content:
                req_path.write_text(content.rstrip() + "\npytest-httpserver==1.0.8\n",
                                    encoding="utf-8")
                print(f"  Added pytest-httpserver to {req_file}")
                subprocess.run("pip install pytest-httpserver",
                               shell=True, capture_output=True)
            return

    # Fallback: write requirements-dev.txt
    (repo / "requirements-dev.txt").write_text("pytest-httpserver==1.0.8\n", encoding="utf-8")
    subprocess.run("pip install pytest-httpserver", shell=True, capture_output=True)
    print("  Created requirements-dev.txt with pytest-httpserver")


def _find_or_generate_test(
    repo: Path, lang_config: Dict, changed_files: List[str]
) -> Optional[Path]:
    for src_file in changed_files:
        mod_name = Path(src_file).stem
        existing = _find_existing_test(repo, mod_name)
        if existing:
            print(f"  Found existing pytest-httpserver test: {existing}")
            return existing

    http_calls = _detect_http_calls(repo, changed_files)
    if not http_calls:
        return None

    return _generate_test(repo, lang_config, changed_files, http_calls)


def _find_existing_test(repo: Path, mod_name: str) -> Optional[Path]:
    for pattern in [f"test_{mod_name}.py", f"tests/test_{mod_name}.py",
                    f"test_{mod_name}_integration.py"]:
        for match in repo.rglob(Path(pattern).name):
            content = match.read_text(encoding="utf-8", errors="ignore")
            if "httpserver" in content or "responses" in content:
                return match
    return None


def _detect_http_calls(repo: Path, changed_files: List[str]) -> List[Dict]:
    patterns = [
        r'requests\.(get|post|put|delete|patch)\([f]?["\']([^"\']+)["\']',
        r'httpx\.(get|post|put|delete)\([f]?["\']([^"\']+)["\']',
        r'aiohttp\.ClientSession.*?(get|post|put)\([f]?["\']([^"\']+)["\']',
        r'os\.environ(?:\.get)?\(["\']([A-Z_]+_URL)["\']',
        r'settings\.([A-Z_]+_URL)',
        r'config\.["\']([a-z_]+_url)["\']',
    ]

    seen: set = set()
    calls: List[Dict] = []

    for src_file in changed_files:
        path = _resolve_file(repo, src_file)
        if not path:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                hint = m.group(m.lastindex or 1)
                svc  = _infer_service_name(hint)
                if svc not in seen:
                    seen.add(svc)
                    calls.append({"url_hint": hint, "service_name": svc})

    return calls


def _infer_service_name(hint: str) -> str:
    hint = hint.lower()
    for sep in ["_", ".", "/"]:
        parts = [p for p in hint.split(sep) if p and p not in
                 ("url", "service", "api", "v1", "v2", "http", "https", "base", "host")]
        if parts:
            return parts[0]
    return "downstream"


def _generate_test(
    repo: Path, lang_config: Dict, changed_files: List[str], services: List[Dict]
) -> Path:
    mod_name  = Path(changed_files[0]).stem if changed_files else "service"
    framework = lang_config.get("framework", "plain-python")

    test_dir = _find_test_dir(repo)
    test_dir.mkdir(parents=True, exist_ok=True)

    # Ensure conftest.py has the httpserver fixtures
    _ensure_conftest(test_dir, services)

    test_path = test_dir / f"test_sonarfix_{mod_name}_validation.py"
    test_path.write_text(
        _render_test(mod_name, services, framework),
        encoding="utf-8"
    )
    print(f"  Generated pytest-httpserver test: {test_path}")
    return test_path


def _ensure_conftest(test_dir: Path, services: List[Dict]) -> None:
    conftest = test_dir / "conftest.py"
    existing = conftest.read_text(encoding="utf-8") if conftest.exists() else ""

    fixtures = []
    for s in services:
        svc = s["service_name"]
        if f"def {svc}_server" not in existing:
            fixtures.append(f"""
@pytest.fixture(scope="session")
def {svc}_server():
    with HTTPServer(host="127.0.0.1", port=0) as server:
        yield server
""")

    if fixtures:
        header = "import pytest\nfrom pytest_httpserver import HTTPServer\n"
        if "from pytest_httpserver" not in existing:
            existing = header + existing
        existing = existing.rstrip() + "\n" + "\n".join(fixtures)
        conftest.write_text(existing, encoding="utf-8")
        print(f"  Updated {conftest} with httpserver fixtures")


def _render_test(mod_name: str, services: List[Dict], framework: str) -> str:
    fixture_args = ", ".join(s["service_name"] + "_server" for s in services)
    if fixture_args:
        fixture_args = ", " + fixture_args

    env_patches = "\n".join(
        f'        monkeypatch.setenv("{s["service_name"].upper()}_SERVICE_URL", '
        f'{s["service_name"]}_server.url_for(""))'
        for s in services
    )

    happy_stubs = "\n".join(
        f'        {s["service_name"]}_server.expect_request("/", method="GET") \\\n'
        f'            .respond_with_json({{"status": "ok", "service": "{s["service_name"]}"}})'
        for s in services
    )

    check_assertions = "\n".join(
        f"        {s['service_name']}_server.check_assertions()"
        for s in services
    )

    error_stubs = "\n".join(
        f'        {s["service_name"]}_server.expect_request("/", method="POST") \\\n'
        f'            .respond_with_data("Internal Server Error", status=500)'
        for s in services
    )

    return f'''"""
Auto-generated by SonarQube Fixer Agent — integration validation for {mod_name}.
pytest-httpserver stubs replace real downstream services (no Docker required).

── CLAUDE CODE: fill in every section marked FILL-IN before running ────────────
"""
import pytest


class TestSonarFix{mod_name.capitalize()}Validation:

    def test_happy_path_unchanged_by_fix(self, monkeypatch{fixture_args}):
        """
        Must pass BEFORE and AFTER the fix.
        Confirms downstream call behaviour is not changed by the fix.
        """
{env_patches}

{happy_stubs}

        # ── FILL-IN ──────────────────────────────────────────────────────────────
        # Read {mod_name}.py and import the function/class being fixed.
        # Example:
        #   from {mod_name} import some_function
        #   result = some_function(valid_input())
        #   assert result is not None
        # ─────────────────────────────────────────────────────────────────────────

{check_assertions}

    def test_fix_scenario_handled_gracefully(self, monkeypatch{fixture_args}):
        """
        Should FAIL before fix, PASS after fix.
        Stubs the exact problematic response the SonarQube rule flags.
        """
{env_patches}

        # ── FILL-IN ──────────────────────────────────────────────────────────────
        # 1. Stub the problematic response (missing key, null, wrong type, etc.)
        # 2. Call the function and assert graceful handling after the fix:
        #   result = some_function(bad_input())
        #   assert result is not None  # or assert correct fallback behaviour
        # ─────────────────────────────────────────────────────────────────────────

    def test_downstream_error_handled_correctly(self, monkeypatch{fixture_args}):
        """
        Downstream returns 500 — must pass BEFORE and AFTER the fix.
        """
{env_patches}

{error_stubs}

        # ── FILL-IN ──────────────────────────────────────────────────────────────
        # Assert the service raises the correct exception or returns a fallback:
        #   with pytest.raises(YourServiceException):
        #       some_function(valid_input())
        # ─────────────────────────────────────────────────────────────────────────
'''


def _run_test(repo: Path, lang_config: Dict, test_path: Path, phase: str) -> Dict[str, Any]:
    cmd = f"pytest {test_path} -v --tb=short --no-header"

    print(f"  Running: {cmd}")
    t0 = time.time()
    proc = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True)
    elapsed = round(time.time() - t0, 1)

    stub_calls = _extract_stub_calls(proc.stdout + proc.stderr)

    return {
        "passed": proc.returncode == 0,
        "command": cmd,
        "test_file": str(test_path),
        "elapsed_sec": elapsed,
        "stub_calls": stub_calls,
        "stdout": proc.stdout[-3000:] if proc.stdout else "",
        "stderr": proc.stderr[-1000:] if proc.stderr else "",
    }


def _extract_stub_calls(output: str) -> Dict[str, int]:
    calls: Dict[str, int] = {}
    for m in re.finditer(r"(\w+_server).*?check_assertions", output):
        key = m.group(1)
        calls[key] = calls.get(key, 0) + 1
    return calls


def _find_test_dir(repo: Path) -> Path:
    for candidate in ["tests", "test"]:
        p = repo / candidate
        if p.is_dir():
            return p
    return repo / "tests"


def _resolve_file(repo: Path, src_file: str) -> Optional[Path]:
    p = Path(src_file)
    if p.is_absolute() and p.exists():
        return p
    c = repo / src_file
    if c.exists():
        return c
    matches = list(repo.rglob(p.name))
    return matches[0] if matches else None
