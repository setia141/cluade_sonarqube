#!/usr/bin/env python3
"""
Validation orchestrator — compile, then unit tests.

Phases:
  check-tests  Pre-flight: report which changed files have unit tests + who calls them
  baseline     Run tests before fix
  post-fix     Run tests after fix, compare against baseline

Usage:
  # Pre-flight (always run first)
  python3 run_validation.py --lang-config lang.json --changed-files files.json \
      --repo . --phase check-tests --output test-status.json

  # Baseline
  python3 run_validation.py --lang-config lang.json --changed-files files.json \
      --repo . --phase baseline --output baseline.json

  # Post-fix
  python3 run_validation.py --lang-config lang.json --changed-files files.json \
      --repo . --phase post-fix --baseline baseline.json --output validation.json
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure repo root is on sys.path when this script is run directly
_repo_root = Path(__file__).parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


CONFIDENCE_HIGH   = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW    = "LOW"
CONFIDENCE_SKIP   = "SKIP"


# ── Pre-flight: check which files have tests and who calls them ────────────────

def check_tests(
    lang_config: Dict[str, Any],
    changed_files: List[str],
    repo_path: str,
) -> Dict[str, Any]:
    """
    Pre-flight check — run BEFORE baseline. Reports:
    - Line-level coverage for changed files (JaCoCo / pytest-cov / Coverlet / Jest)
    - Which specific lines are NOT covered by any existing test
    - Which other source files call into the changed class/module (impact scope)
    - Expected test file path for each file that needs tests

    Claude Code uses this to create or enhance tests before capturing the baseline.
    """
    from scripts.validation.coverage_check import check_coverage

    language = lang_config.get("language", "unknown")
    repo = Path(repo_path)

    print("\n[Pre-flight] Running coverage analysis...")
    coverage = check_coverage(lang_config, changed_files, repo_path)

    files_status = {}

    for src_file in changed_files:
        stem = Path(src_file).stem
        existing = _find_existing_test(repo, stem, language)
        callers  = _find_callers(repo, src_file, language)

        caller_info = []
        for caller in callers:
            caller_test = _find_existing_test(repo, Path(caller).stem, language)
            caller_info.append({
                "file": caller,
                "has_tests": caller_test is not None,
                "test_file": str(caller_test.relative_to(repo)) if caller_test else None,
            })

        cov_data = coverage.get("files", {}).get(src_file, {})

        files_status[src_file] = {
            "has_tests": existing is not None,
            "test_file": str(existing.relative_to(repo)) if existing else None,
            "expected_test_path": str(
                _expected_test_path(repo, src_file, language).relative_to(repo)
            ),
            "coverage_pct": cov_data.get("covered_pct", 0.0),
            "uncovered_lines": cov_data.get("uncovered_lines", []),
            "covered_lines": cov_data.get("covered_lines", []),
            "needs_tests": cov_data.get("needs_tests", existing is None),
            "callers": caller_info,
        }

    overall_needs = any(v["needs_tests"] for v in files_status.values())

    return {
        "language": language,
        "coverage_tool": coverage.get("tool", "none"),
        "coverage_summary": coverage.get("summary", ""),
        "overall_needs_tests": overall_needs,
        "files": files_status,
    }


# ── Main validation orchestrator ───────────────────────────────────────────────

def run_validation(
    lang_config: Dict[str, Any],
    changed_files: List[str],
    repo_path: str,
    phase: str,
    baseline_result: Optional[Dict] = None,
    run_integration: bool = False,
) -> Dict[str, Any]:
    """
    Runs validation layers and returns a result dict.

    Layer 1: Build / compile
    Layer 2: Unit tests (changed files + callers)
    Layer 3: Integration tests (opt-in via run_integration=True)

    phase="baseline"  → record state before fix
    phase="post-fix"  → compare against baseline, produce confidence score
    """
    language = lang_config.get("language", "unknown")

    result: Dict[str, Any] = {
        "phase":      phase,
        "language":   language,
        "layers":     {},
        "confidence": CONFIDENCE_SKIP,
        "passed":     False,
        "summary":    [],
    }

    print(f"\n{'='*60}")
    print(f"Validation — phase: {phase.upper()} | language: {language}")
    print(f"{'='*60}")

    # ── Layer 1: Build / compile ───────────────────────────────────────────────
    layer1 = _run_build(lang_config, repo_path)
    result["layers"]["compile"] = layer1
    if not layer1["passed"]:
        result["summary"].append("FAIL: Compile error — aborting")
        result["confidence"] = CONFIDENCE_SKIP
        return result
    result["summary"].append("PASS: Compile")

    # ── Layer 2: Unit tests — changed files + callers ──────────────────────────
    caller_patterns: List[str] = []
    for src_file in changed_files:
        for caller in _find_callers(Path(repo_path), src_file, language):
            t = _find_existing_test(Path(repo_path), Path(caller).stem, language)
            if t:
                caller_patterns.append(Path(caller).stem)

    layer2 = _run_unit_tests(lang_config, repo_path, changed_files, caller_patterns)
    result["layers"]["unit_tests"] = layer2

    if not layer2["passed"]:
        if phase == "post-fix" and baseline_result:
            baseline_unit = baseline_result.get("layers", {}).get("unit_tests", {})
            if not baseline_unit.get("passed"):
                result["summary"].append(
                    "WARN: Unit tests also failed at baseline — pre-existing failure, not caused by fix"
                )
            else:
                result["summary"].append("FAIL: Unit tests regressed after fix")
                result["confidence"] = CONFIDENCE_LOW
                return result
        else:
            result["summary"].append("WARN: Unit tests failed at baseline")
    else:
        extra = f" + {len(caller_patterns)} caller class(es)" if caller_patterns else ""
        result["summary"].append(f"PASS: Unit tests{extra}")

    # ── Layer 3: Integration tests (opt-in) ────────────────────────────────────
    if run_integration:
        layer3 = _run_integration_tests(lang_config, repo_path)
        result["layers"]["integration_tests"] = layer3
        if layer3.get("skipped"):
            result["summary"].append("SKIP: No integration tests detected")
        elif not layer3["passed"]:
            if phase == "post-fix" and baseline_result:
                baseline_int = baseline_result.get("layers", {}).get("integration_tests", {})
                if not baseline_int.get("passed") and not baseline_int.get("skipped"):
                    result["summary"].append(
                        "WARN: Integration tests also failed at baseline — pre-existing failure, not caused by fix"
                    )
                else:
                    result["summary"].append("FAIL: Integration tests regressed after fix")
                    result["confidence"] = CONFIDENCE_LOW
                    return result
            else:
                result["summary"].append("WARN: Integration tests failed at baseline")
        else:
            result["summary"].append(f"PASS: Integration tests ({layer3.get('tests_passed', '?')} passed)")

    result["passed"] = True
    result["confidence"] = _score_confidence(result["layers"], phase, baseline_result)

    print("\n".join(f"  {s}" for s in result["summary"]))
    print(f"\nConfidence: {result['confidence']}")
    return result


# ── Layer runners ──────────────────────────────────────────────────────────────

def _run_build(lang_config: Dict, repo_path: str) -> Dict[str, Any]:
    cmd = lang_config.get("build_command", "")
    if not cmd:
        return {"passed": True, "skipped": True, "reason": "No build command configured"}

    print(f"\n[Layer 1] Build: {cmd}")
    t0 = time.time()
    proc = subprocess.run(cmd, shell=True, cwd=repo_path, capture_output=True, text=True)
    return {
        "passed": proc.returncode == 0,
        "command": cmd,
        "elapsed_sec": round(time.time() - t0, 1),
        "stdout": proc.stdout[-2000:] if proc.stdout else "",
        "stderr": proc.stderr[-2000:] if proc.stderr else "",
    }


def _run_unit_tests(
    lang_config: Dict,
    repo_path: str,
    changed_files: List[str],
    caller_patterns: List[str],
) -> Dict[str, Any]:
    language = lang_config.get("language")
    cmd = _unit_test_command(lang_config, changed_files, caller_patterns)

    print(f"\n[Layer 2] Unit tests: {cmd}")
    t0 = time.time()
    proc = subprocess.run(cmd, shell=True, cwd=repo_path, capture_output=True, text=True)
    elapsed = round(time.time() - t0, 1)

    passed_count, failed_count = _parse_test_counts(proc.stdout + proc.stderr, language)
    return {
        "passed": proc.returncode == 0,
        "command": cmd,
        "elapsed_sec": elapsed,
        "tests_passed": passed_count,
        "tests_failed": failed_count,
        "stdout": proc.stdout[-3000:] if proc.stdout else "",
        "stderr": proc.stderr[-1000:] if proc.stderr else "",
    }


def _run_integration_tests(lang_config: Dict, repo_path: str) -> Dict[str, Any]:
    if not lang_config.get("has_integration_tests"):
        return {"passed": True, "skipped": True, "reason": "No integration tests detected"}

    cmd = lang_config.get("integration_test_command", "")
    if not cmd:
        return {"passed": True, "skipped": True, "reason": "No integration test command configured"}

    print(f"\n[Layer 3] Integration tests: {cmd}")
    t0 = time.time()
    proc = subprocess.run(cmd, shell=True, cwd=repo_path, capture_output=True, text=True)
    elapsed = round(time.time() - t0, 1)

    language = lang_config.get("language")
    passed_count, failed_count = _parse_test_counts(proc.stdout + proc.stderr, language)
    return {
        "passed": proc.returncode == 0,
        "skipped": False,
        "command": cmd,
        "elapsed_sec": elapsed,
        "tests_passed": passed_count,
        "tests_failed": failed_count,
        "stdout": proc.stdout[-3000:] if proc.stdout else "",
        "stderr": proc.stderr[-1000:] if proc.stderr else "",
    }


# ── Caller / impact detection ──────────────────────────────────────────────────

def _find_callers(repo: Path, src_file: str, language: str) -> List[str]:
    stem = Path(src_file).stem

    if language == "java":
        search_patterns = [rf'\b{re.escape(stem)}\b']
        globs = ["**/*.java"]
    elif language == "dotnet":
        search_patterns = [rf'\b{re.escape(stem)}\b']
        globs = ["**/*.cs"]
    elif language == "python":
        search_patterns = [
            rf'^\s*import\s+[\w.]*{re.escape(stem)}',
            rf'^\s*from\s+[\w.]*{re.escape(stem)}\s+import',
        ]
        globs = ["**/*.py"]
    elif language == "node":
        search_patterns = [
            rf'require\(["\'][./]+{re.escape(stem)}',
            rf'from\s+["\'][./]+{re.escape(stem)}',
        ]
        globs = ["**/*.js", "**/*.ts", "**/*.mjs"]
    else:
        return []

    callers: List[str] = []
    src_name = Path(src_file).name

    for glob in globs:
        for candidate in repo.rglob(glob.replace("**/", "")):
            rel = str(candidate.relative_to(repo))
            if _is_test_file(rel, language):
                continue
            if candidate.name == src_name:
                continue
            try:
                content = candidate.read_text(encoding="utf-8", errors="ignore")
                if any(re.search(p, content, re.MULTILINE) for p in search_patterns):
                    callers.append(rel)
            except OSError:
                continue

    return callers


def _is_test_file(rel_path: str, language: str) -> bool:
    p = rel_path.lower().replace("\\", "/")
    if language == "java":
        return p.endswith("test.java") or p.endswith("tests.java") or "/test/" in p
    if language == "dotnet":
        return "test" in p and p.endswith(".cs")
    if language == "python":
        name = Path(rel_path).name
        return name.startswith("test_") or name.endswith("_test.py") or "/test/" in p or "/tests/" in p
    if language == "node":
        return ".test." in p or ".spec." in p or "/__tests__/" in p
    return False


def _find_existing_test(repo: Path, stem: str, language: str) -> Optional[Path]:
    if language == "java":
        candidates = [f"{stem}Test.java", f"{stem}Tests.java", f"{stem}IntegrationTest.java"]
    elif language == "dotnet":
        candidates = [f"{stem}Tests.cs", f"{stem}Test.cs"]
    elif language == "python":
        candidates = [f"test_{stem}.py", f"{stem}_test.py"]
    elif language == "node":
        candidates = [f"{stem}.test.js", f"{stem}.test.ts", f"{stem}.spec.js", f"{stem}.spec.ts"]
    else:
        return None

    for name in candidates:
        matches = list(repo.rglob(name))
        if matches:
            return matches[0]
    return None


def _expected_test_path(repo: Path, src_file: str, language: str) -> Path:
    stem = Path(src_file).stem
    if language == "java":
        mirrored = src_file.replace("src/main/java", "src/test/java") \
                           .replace("src\\main\\java", "src\\test\\java")
        if mirrored != src_file:
            return repo / mirrored.replace(f"{stem}.java", f"{stem}Test.java")
        return repo / "src" / "test" / "java" / f"{stem}Test.java"
    if language == "dotnet":
        return repo / f"{stem}Tests.cs"
    if language == "python":
        return repo / "tests" / f"test_{stem}.py"
    if language == "node":
        return repo / "__tests__" / f"{stem}.test.js"
    return repo / f"{stem}.test"


# ── Test command builders ──────────────────────────────────────────────────────

def _unit_test_command(
    lang_config: Dict,
    changed_files: List[str],
    extra_patterns: List[str],
) -> str:
    language = lang_config.get("language")
    build    = lang_config.get("build_tool")

    patterns = _derive_test_patterns(changed_files, language)
    for p in extra_patterns:
        if p not in patterns:
            patterns.append(p)

    if language == "java":
        pat = ",".join(patterns)
        if build == "maven":
            return f"mvn test -Dtest={pat} --no-transfer-progress" if pat else "mvn test --no-transfer-progress"
        return f"gradle test --tests '{pat}'" if pat else "gradle test"

    if language == "dotnet":
        if patterns:
            f_expr = "|".join(f"ClassName~{p}" for p in patterns)
            return f'dotnet test --filter "{f_expr}"'
        return "dotnet test"

    if language == "python":
        return f"pytest {' '.join(patterns)} -v" if patterns else "pytest -v"

    if language == "node":
        if patterns:
            return f"npx jest --testPathPattern='{'|'.join(patterns)}' --no-coverage"
        return "npm test"

    return lang_config.get("test_command", "echo 'no test command'")


def _derive_test_patterns(changed_files: List[str], language: str) -> List[str]:
    patterns = []
    for f in changed_files:
        stem = Path(f).stem
        if language == "java":
            patterns.append(f"{stem}Test")
        elif language == "dotnet":
            patterns.append(f"{stem}Tests")
        elif language == "python":
            patterns.append(f"test_{stem}.py")
        elif language == "node":
            patterns.append(stem)
    return patterns


def _parse_test_counts(output: str, language: str):
    passed = failed = 0
    if language == "java":
        m = re.search(r"Tests run: (\d+).*?Failures: (\d+).*?Errors: (\d+)", output)
        if m:
            total = int(m.group(1))
            failed = int(m.group(2)) + int(m.group(3))
            passed = total - failed
    elif language == "dotnet":
        m = re.search(r"Passed:\s*(\d+).*?Failed:\s*(\d+)", output, re.DOTALL)
        if m:
            passed, failed = int(m.group(1)), int(m.group(2))
    elif language == "python":
        m = re.search(r"(\d+) passed", output)
        if m: passed = int(m.group(1))
        m = re.search(r"(\d+) failed", output)
        if m: failed = int(m.group(1))
    elif language == "node":
        m = re.search(r"Tests:\s+(\d+) passed", output)
        if m: passed = int(m.group(1))
        m = re.search(r"(\d+) failed", output)
        if m: failed = int(m.group(1))
    return passed, failed


def _score_confidence(layers: Dict, phase: str, baseline: Optional[Dict]) -> str:
    if not layers.get("compile", {}).get("passed", False):
        return CONFIDENCE_SKIP
    if not layers.get("unit_tests", {}).get("passed", False):
        return CONFIDENCE_LOW
    return CONFIDENCE_HIGH


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run validation pipeline")
    parser.add_argument("--lang-config",   required=True, help="lang.json from detect_language.py")
    parser.add_argument("--changed-files", required=True, help="JSON array of changed file paths")
    parser.add_argument("--repo",          default=".",   help="Repo root path")
    parser.add_argument("--phase",         required=True,
                        choices=["check-tests", "baseline", "post-fix"])
    parser.add_argument("--baseline",      default=None,
                        help="baseline.json — required for post-fix phase")
    parser.add_argument("--integration",   action="store_true",
                        help="Also run integration tests (Layer 3) if detected")
    parser.add_argument("--output",        default=None, help="Write result JSON to this file")
    args = parser.parse_args()

    lang_config   = json.loads(Path(args.lang_config).read_text())
    changed_files = (json.loads(args.changed_files)
                     if args.changed_files.startswith("[")
                     else json.loads(Path(args.changed_files).read_text()))

    if args.phase == "check-tests":
        result    = check_tests(lang_config, changed_files, args.repo)
        exit_code = 0
    else:
        baseline_result = None
        if args.baseline:
            baseline_result = json.loads(Path(args.baseline).read_text())

        result = run_validation(
            lang_config=lang_config,
            changed_files=changed_files,
            repo_path=args.repo,
            phase=args.phase,
            baseline_result=baseline_result,
            run_integration=args.integration,
        )
        exit_code = 0 if result["passed"] else 1

    output = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"\nResult saved to {args.output}")
    else:
        print(output)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
