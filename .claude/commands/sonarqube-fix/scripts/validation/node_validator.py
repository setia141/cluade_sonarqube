#!/usr/bin/env python3
"""
Node.js nock integration — generates and runs nock-based validation tests.
Supports Jest, Vitest, and Mocha. Works with axios, fetch, node-fetch, got.
"""

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional


def run_node_integration(
    lang_config: Dict[str, Any],
    repo_path: str,
    changed_files: List[str],
    phase: str,
) -> Dict[str, Any]:
    repo = Path(repo_path)

    _ensure_nock_dependency(repo, lang_config)

    test_path = _find_or_generate_test(repo, lang_config, changed_files)
    if not test_path:
        return {"passed": True, "skipped": True, "reason": "No HTTP calls detected"}

    return _run_test(repo, lang_config, test_path, phase)


def _ensure_nock_dependency(repo: Path, lang_config: Dict) -> None:
    if lang_config.get("http_mock_present") and lang_config.get("http_mock_library") == "nock":
        return

    pkg_path = repo / "package.json"
    if not pkg_path.exists():
        return

    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    dev_deps = pkg.get("devDependencies", {})

    if "nock" not in dev_deps:
        dev_deps["nock"] = "^13.5.0"
        pkg["devDependencies"] = dev_deps
        pkg_path.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
        print("  Added nock to devDependencies")
        subprocess.run("npm install", shell=True, cwd=str(repo), capture_output=True)


def _find_or_generate_test(
    repo: Path, lang_config: Dict, changed_files: List[str]
) -> Optional[Path]:
    for src_file in changed_files:
        mod_name = Path(src_file).stem
        existing = _find_existing_test(repo, mod_name)
        if existing:
            print(f"  Found existing nock test: {existing}")
            return existing

    http_calls = _detect_http_calls(repo, changed_files, lang_config)
    if not http_calls:
        return None

    return _generate_test(repo, lang_config, changed_files, http_calls)


def _find_existing_test(repo: Path, mod_name: str) -> Optional[Path]:
    for pattern in [f"{mod_name}.test.js", f"{mod_name}.test.ts",
                    f"{mod_name}.spec.js", f"{mod_name}.spec.ts",
                    f"{mod_name}.integration.test.js"]:
        for match in repo.rglob(pattern):
            content = match.read_text(encoding="utf-8", errors="ignore")
            if "nock" in content or "msw" in content:
                return match
    return None


def _detect_http_calls(repo: Path, changed_files: List[str], lang_config: Dict) -> List[Dict]:
    http_client = lang_config.get("http_client", "fetch")

    patterns_by_client = {
        "axios": [
            r'axios\.(get|post|put|delete|patch)\([`\'"]([^`\'"]+)[`\'"]',
            r'axios\(\{[^}]*url:\s*[`\'"]([^`\'"]+)[`\'"]',
        ],
        "node-fetch": [
            r'fetch\([`\'"]([^`\'"]+)[`\'"]',
        ],
        "fetch": [
            r'fetch\([`\'"]([^`\'"]+)[`\'"]',
            r'fetch\(`\$\{([^}]+)\}',
        ],
        "got": [
            r'got\.(get|post|put|delete)\([`\'"]([^`\'"]+)[`\'"]',
        ],
    }

    env_patterns = [
        r'process\.env\.([A-Z_]+_URL)',
        r'process\.env\[["\']([A-Z_]+_URL)["\']\]',
        r'config\.get\(["\']([^"\']+)["\']',
    ]

    seen: set = set()
    calls: List[Dict] = []

    for src_file in changed_files:
        path = _resolve_file(repo, src_file)
        if not path:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")

        all_patterns = patterns_by_client.get(http_client, []) + env_patterns
        for pattern in all_patterns:
            for m in re.finditer(pattern, content):
                hint = m.group(m.lastindex or 1)
                svc  = _infer_service_name(hint)
                if svc not in seen:
                    seen.add(svc)
                    env_var = _to_env_var(svc)
                    calls.append({
                        "url_hint": hint,
                        "service_name": svc,
                        "env_var": env_var,
                    })

    return calls


def _infer_service_name(hint: str) -> str:
    hint = hint.lower()
    for sep in ["_", ".", "/"]:
        parts = [p for p in hint.split(sep) if p and p not in
                 ("url", "service", "api", "v1", "v2", "http", "https",
                  "base", "host", "env", "process", "config")]
        if parts:
            return parts[0]
    return "downstream"


def _to_env_var(service_name: str) -> str:
    return f"{service_name.upper()}_SERVICE_URL"


def _generate_test(
    repo: Path, lang_config: Dict, changed_files: List[str], services: List[Dict]
) -> Path:
    mod_name   = Path(changed_files[0]).stem if changed_files else "service"
    test_fw    = lang_config.get("test_framework", "jest")
    http_client= lang_config.get("http_client", "fetch")
    is_ts      = lang_config.get("typescript", False)

    ext = ".test.ts" if is_ts else ".test.js"

    test_dir = _find_test_dir(repo)
    test_dir.mkdir(parents=True, exist_ok=True)

    test_path = test_dir / f"sonarfix.{mod_name}.validation{ext}"
    body = _render_jest_test(mod_name, services, http_client, is_ts) \
        if test_fw in ("jest", "vitest") \
        else _render_mocha_test(mod_name, services, http_client)

    test_path.write_text(body, encoding="utf-8")
    print(f"  Generated nock test: {test_path}")
    return test_path


def _render_jest_test(
    mod_name: str, services: List[Dict], http_client: str, is_ts: bool
) -> str:
    import_line = "import nock from 'nock';" if is_ts else "const nock = require('nock');"

    env_setup = "\n".join(
        "  process.env.{env_var} = 'http://{svc}-mock.local';".format(
            env_var=s['env_var'], svc=s['service_name']
        )
        for s in services
    )

    happy_stubs = "\n".join(
        "  nock(process.env.{env_var})\n    .post('/')\n    .reply(200, {{ status: 'ok', service: '{svc}' }});".format(
            env_var=s['env_var'], svc=s['service_name']
        )
        for s in services
    )

    error_stubs = "\n".join(
        f"  nock(process.env.{s['env_var']})\n"
        f"    .post('/')\n"
        f"    .reply(500);"
        for s in services
    )

    return f"""/**
 * Auto-generated by SonarQube Fixer Agent — integration validation for {mod_name}.
 * nock intercepts outbound HTTP calls at the network layer (no Docker required).
 *
 * ── CLAUDE CODE: fill in every section marked FILL-IN before running ──────────
 */
{import_line}

// ── FILL-IN: import the module under test ─────────────────────────────────────
// Read the source file and import the function/class being fixed.
// Example:
//   const {{ {mod_name}Function }} = require('../src/{mod_name}');
// ─────────────────────────────────────────────────────────────────────────────

describe('SonarFix {mod_name} Validation', () => {{

  beforeEach(() => {{
    nock.cleanAll();
{env_setup}
  }});

  afterEach(() => {{
    if (!nock.isDone()) {{
      console.warn('Unused nock interceptors:', nock.pendingMocks());
    }}
    nock.cleanAll();
  }});

  test('happy path — downstream call behaviour unchanged by fix', async () => {{
    // Must pass BEFORE and AFTER the fix.
{happy_stubs}

    // ── FILL-IN ────────────────────────────────────────────────────────────────
    // Call the function under test with valid input and assert expected output:
    //   const result = await {mod_name}Function(validInput());
    //   expect(result).toBeDefined();
    //   expect(nock.isDone()).toBe(true);  // confirms all stubs were hit
    // ──────────────────────────────────────────────────────────────────────────
  }});

  test('fix scenario — handled gracefully after fix', async () => {{
    // Should FAIL before fix, PASS after fix.
    // Stubs the exact problematic response the SonarQube rule flags.
{"".join(f"    nock(process.env.{s['env_var']}).post('/').reply(200, {{}});  // missing/null field{chr(10)}" for s in services)}
    // ── FILL-IN ────────────────────────────────────────────────────────────────
    // Call the function with the input that triggers the SonarQube issue:
    //   await expect({mod_name}Function(input())).resolves.not.toThrow();
    // ──────────────────────────────────────────────────────────────────────────
  }});

  test('downstream 500 — handled correctly', async () => {{
    // Must pass BEFORE and AFTER the fix.
{error_stubs}

    // ── FILL-IN ────────────────────────────────────────────────────────────────
    // Assert the error is handled correctly (typed error, fallback value, etc.):
    //   await expect({mod_name}Function(input())).rejects.toThrow('SomeError');
    // ──────────────────────────────────────────────────────────────────────────
  }});
}});
"""


def _render_mocha_test(mod_name: str, services: List[Dict], http_client: str) -> str:
    env_setup = "\n".join(
        "    process.env.{env_var} = 'http://{svc}-mock.local';".format(
            env_var=s['env_var'], svc=s['service_name']
        )
        for s in services
    )

    return f"""const nock = require('nock');
// const {{ someFunction }} = require('../src/{mod_name}');
const {{ expect }} = require('chai');

describe('SonarFix {mod_name} Validation', function () {{

  beforeEach(function () {{
    nock.cleanAll();
{env_setup}
  }});

  afterEach(function () {{
    nock.cleanAll();
  }});

  it('happy path — downstream call behaviour unchanged', async function () {{
    // stub + call + assert
  }});

  it('error path — fixed scenario', async function () {{
    // stub problematic response + assert graceful handling
  }});

  it('downstream 500 — handled correctly', async function () {{
    // stub 500 + assert typed error
  }});
}});
"""


def _run_test(repo: Path, lang_config: Dict, test_path: Path, phase: str) -> Dict[str, Any]:
    test_fw  = lang_config.get("test_framework", "jest")
    try:
        rel_path = test_path.relative_to(repo)
    except ValueError:
        rel_path = test_path

    if test_fw in ("jest", "vitest"):
        cmd = f"npx {test_fw} {rel_path} --no-coverage --forceExit"
    else:
        cmd = f"npx mocha {rel_path}"

    print(f"  Running: {cmd}")
    t0 = time.time()
    proc = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True)
    elapsed = round(time.time() - t0, 1)

    stub_calls = _extract_stub_calls(proc.stdout + proc.stderr)

    return {
        "passed": proc.returncode == 0,
        "command": cmd,
        "test_file": str(rel_path),
        "elapsed_sec": elapsed,
        "stub_calls": stub_calls,
        "stdout": proc.stdout[-3000:] if proc.stdout else "",
        "stderr": proc.stderr[-1000:] if proc.stderr else "",
    }


def _extract_stub_calls(output: str) -> Dict[str, int]:
    calls: Dict[str, int] = {}
    for m in re.finditer(r"nock.*?intercepted.*?(\S+-mock\.local)", output, re.IGNORECASE):
        key = m.group(1)
        calls[key] = calls.get(key, 0) + 1
    return calls


def _find_test_dir(repo: Path) -> Path:
    for candidate in ["__tests__", "test", "tests", "src/__tests__"]:
        p = repo / candidate
        if p.is_dir():
            return p
    return repo / "__tests__"


def _resolve_file(repo: Path, src_file: str) -> Optional[Path]:
    p = Path(src_file)
    if p.is_absolute() and p.exists():
        return p
    c = repo / src_file
    if c.exists():
        return c
    matches = list(repo.rglob(p.name))
    return matches[0] if matches else None
