#!/usr/bin/env python3
"""
Line-level coverage check using industry-standard tools.

  Java   → JaCoCo   (jacoco-maven-plugin / jacoco-gradle-plugin)
  Python → pytest-cov / coverage.py    → Cobertura XML
  .NET   → Coverlet  (built into dotnet test)  → Cobertura XML
  Node   → Jest --coverage / c8        → coverage-final.json

For each changed file returns which lines are NOT covered by existing tests.
Claude uses this to create targeted tests before the fix is applied.
"""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Set


def check_coverage(
    lang_config: Dict[str, Any],
    changed_files: List[str],
    repo_path: str,
) -> Dict[str, Any]:
    """
    Run existing tests with coverage enabled and return line coverage
    for the specific files that are about to be changed.

    Returns:
      {
        "tool": "jacoco",
        "files": {
          "src/main/java/com/example/PaymentService.java": {
            "covered_pct": 72.3,
            "covered_lines": [10, 11, 15, 42],
            "uncovered_lines": [43, 44, 50],
            "changed_lines_covered": [42],
            "changed_lines_uncovered": [43, 44],
            "needs_tests": true      # true if any changed lines are uncovered
          }
        },
        "overall_needs_tests": true,
        "summary": "2 of 3 changed lines in PaymentService.java are not covered"
      }
    """
    language = lang_config.get("language", "unknown")
    repo = Path(repo_path)

    if language == "java":
        return _java_coverage(lang_config, repo, changed_files)
    elif language == "python":
        return _python_coverage(lang_config, repo, changed_files)
    elif language == "dotnet":
        return _dotnet_coverage(lang_config, repo, changed_files)
    elif language == "node":
        return _node_coverage(lang_config, repo, changed_files)
    else:
        return {"tool": "none", "files": {}, "overall_needs_tests": False,
                "summary": f"No coverage tool available for {language}"}


# ── Java — JaCoCo ─────────────────────────────────────────────────────────────

def _java_coverage(lang_config: Dict, repo: Path, changed_files: List[str]) -> Dict:
    build_tool = lang_config.get("build_tool", "maven")
    # lang_config.jacoco_present comes from detect_language.py —
    # skip the pom.xml check if detect_language already confirmed it's there
    if not lang_config.get("jacoco_present"):
        _ensure_jacoco(repo, build_tool)

    if build_tool == "maven":
        cmd = "mvn test jacoco:report --no-transfer-progress -q"
        report_path = repo / "target" / "site" / "jacoco" / "jacoco.xml"
    else:
        cmd = "gradle test jacocoTestReport"
        # Gradle default: build/reports/jacoco/test/jacocoTestReport.xml
        report_path = repo / "build" / "reports" / "jacoco" / "test" / "jacocoTestReport.xml"

    print(f"  [Coverage] Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True)

    if not report_path.exists():
        return _no_report("jacoco", "JaCoCo report not generated — tests may have failed")

    return _parse_jacoco_xml(report_path, changed_files, repo)


def _ensure_jacoco(repo: Path, build_tool: str) -> None:
    """Add JaCoCo plugin to build file if not present."""
    if build_tool == "maven":
        pom = repo / "pom.xml"
        if not pom.exists():
            return
        content = pom.read_text(encoding="utf-8")
        if "jacoco-maven-plugin" in content:
            return

        plugin = """
        <plugin>
            <groupId>org.jacoco</groupId>
            <artifactId>jacoco-maven-plugin</artifactId>
            <version>0.8.11</version>
            <executions>
                <execution>
                    <goals><goal>prepare-agent</goal></goals>
                </execution>
                <execution>
                    <id>report</id>
                    <phase>test</phase>
                    <goals><goal>report</goal></goals>
                </execution>
            </executions>
        </plugin>"""

        if "<plugins>" in content:
            content = content.replace("<plugins>", "<plugins>" + plugin, 1)
        else:
            content = content.replace(
                "</build>",
                "  <plugins>" + plugin + "\n  </plugins>\n</build>"
            )
        pom.write_text(content, encoding="utf-8")
        print("  [Coverage] Added jacoco-maven-plugin to pom.xml")

    elif build_tool == "gradle":
        build = repo / "build.gradle"
        if not build.exists():
            build = repo / "build.gradle.kts"
        if not build.exists():
            return
        content = build.read_text(encoding="utf-8")
        if "jacoco" in content.lower():
            return
        # Append JaCoCo plugin
        content += "\napply plugin: 'jacoco'\njacocoTestReport { reports { xml.required = true } }\n"
        build.write_text(content, encoding="utf-8")
        print("  [Coverage] Added JaCoCo plugin to build.gradle")


def _parse_jacoco_xml(report_path: Path, changed_files: List[str], repo: Path) -> Dict:
    """
    JaCoCo XML format:
      <sourcefile name="PaymentService.java">
        <line nr="42" mi="0" ci="1" .../>   ci=covered instructions, mi=missed
      </sourcefile>
    """
    try:
        tree = ET.parse(report_path)
    except ET.ParseError as e:
        return _no_report("jacoco", f"Failed to parse jacoco.xml: {e}")

    root = tree.getroot()
    files_result = {}

    for src_file in changed_files:
        filename = Path(src_file).name
        covered: Set[int] = set()
        uncovered: Set[int] = set()

        for sf in root.iter("sourcefile"):
            if sf.get("name") == filename:
                for line in sf.iter("line"):
                    nr = int(line.get("nr", 0))
                    ci = int(line.get("ci", 0))  # covered instructions
                    mi = int(line.get("mi", 0))  # missed instructions
                    if ci > 0:
                        covered.add(nr)
                    elif mi > 0:
                        uncovered.add(nr)
                break

        if not covered and not uncovered:
            files_result[src_file] = {
                "covered_pct": 0.0,
                "covered_lines": [],
                "uncovered_lines": [],
                "changed_lines_covered": [],
                "changed_lines_uncovered": [],
                "needs_tests": True,
                "note": "File not found in JaCoCo report — not reached by any test",
            }
            continue

        total = len(covered) + len(uncovered)
        pct = round(len(covered) / total * 100, 1) if total else 0.0

        files_result[src_file] = _build_file_result(
            covered, uncovered, pct, changed_files
        )

    return _build_summary("jacoco", files_result)


# ── Python — pytest-cov ───────────────────────────────────────────────────────

def _python_coverage(lang_config: Dict, repo: Path, changed_files: List[str]) -> Dict:
    # lang_config.coverage_tool_present comes from detect_language.py
    if not lang_config.get("coverage_tool_present"):
        _ensure_pytest_cov(repo)

    src_dirs = _find_python_src_dirs(repo)
    cov_args = " ".join(f"--cov={d}" for d in src_dirs) if src_dirs else "--cov=."
    report_path = repo / "coverage.xml"

    cmd = f"pytest {cov_args} --cov-report=xml:coverage.xml -q"
    print(f"  [Coverage] Running: {cmd}")
    subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True)

    if not report_path.exists():
        return _no_report("pytest-cov", "coverage.xml not generated")

    result = _parse_cobertura_xml(report_path, changed_files, repo)
    result["tool"] = lang_config.get("coverage_tool", "pytest-cov")
    return result


def _ensure_pytest_cov(repo: Path) -> None:
    """Install pytest-cov if not present in the environment or requirements files."""
    # Check requirements files first (don't install silently into a venv you don't own)
    for req_file in ["requirements.txt", "requirements-dev.txt", "requirements/dev.txt"]:
        p = repo / req_file
        if p.exists():
            content = p.read_text(encoding="utf-8")
            if "pytest-cov" in content or "coverage" in content:
                return   # already declared, pip install would have handled it

    # Check if importable in current environment
    probe = subprocess.run(
        [sys.executable, "-c", "import pytest_cov"],
        capture_output=True
    )
    if probe.returncode == 0:
        return   # already installed

    print("  [Coverage] pytest-cov not found - installing (add pytest-cov to requirements-dev.txt to avoid this)")
    subprocess.run("pip install pytest-cov -q", shell=True)


def _ensure_coverlet(repo: Path) -> None:
    """Add coverlet.collector to the test .csproj if not already present."""
    # Find test project(s)
    test_csprojs = [
        p for p in repo.rglob("*.csproj")
        if any(kw in p.read_text(encoding="utf-8", errors="ignore").lower()
               for kw in ["xunit", "nunit", "mstest", "testhost"])
    ]
    if not test_csprojs:
        test_csprojs = list(repo.rglob("*.csproj"))

    for csproj in test_csprojs:
        content = csproj.read_text(encoding="utf-8")
        if "coverlet" in content.lower():
            return  # already present in this project

        dep = (
            '  <ItemGroup>\n'
            '    <PackageReference Include="coverlet.collector" Version="6.0.0">\n'
            '      <PrivateAssets>all</PrivateAssets>\n'
            '      <IncludeAssets>runtime; build; native; contentfiles; analyzers</IncludeAssets>\n'
            '    </PackageReference>\n'
            '  </ItemGroup>\n'
        )
        content = content.replace("</Project>", dep + "</Project>")
        csproj.write_text(content, encoding="utf-8")
        print(f"  [Coverage] Added coverlet.collector to {csproj.name}")
        subprocess.run("dotnet restore", shell=True, cwd=str(repo), capture_output=True)
        break  # only need it in one test project


def _find_python_src_dirs(repo: Path) -> List[str]:
    candidates = []
    for name in ["src", "app", "lib"]:
        if (repo / name).is_dir():
            candidates.append(name)
    return candidates or ["."]


# ── .NET — Coverlet ───────────────────────────────────────────────────────────

def _dotnet_coverage(lang_config: Dict, repo: Path, changed_files: List[str]) -> Dict:
    coverage_dir = repo / "coverage"
    coverage_dir.mkdir(exist_ok=True)

    # Ensure Coverlet is referenced — lang_config.coverlet_present from detect_language.py
    if not lang_config.get("coverlet_present"):
        _ensure_coverlet(repo)

    cmd = (
        f'dotnet test --collect:"XPlat Code Coverage" --results-directory "{coverage_dir}"'
    )
    print(f"  [Coverage] Running: {cmd}")
    subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True)

    # Coverlet writes to a timestamped subdirectory
    xml_files = list(coverage_dir.rglob("coverage.cobertura.xml"))
    if not xml_files:
        return _no_report("coverlet", "coverage.cobertura.xml not generated")

    result = _parse_cobertura_xml(xml_files[0], changed_files, repo)
    result["tool"] = "coverlet"
    return result


# ── Node.js — Jest --coverage ─────────────────────────────────────────────────

def _node_coverage(lang_config: Dict, repo: Path, changed_files: List[str]) -> Dict:
    coverage_dir = repo / "coverage"
    test_fw      = lang_config.get("test_framework", "jest")

    # For Vitest, @vitest/coverage-v8 must be installed — lang_config tells us if it is
    if test_fw == "vitest":
        if not lang_config.get("coverage_configured"):
            _ensure_vitest_coverage(repo)
        cmd = "npx vitest run --coverage --coverage.reporter=json"
    else:
        # Jest --coverage is built-in, no extra install needed
        cmd = "npx jest --coverage --coverageReporters=json --coverageDirectory=coverage"

    print(f"  [Coverage] Running: {cmd}")
    subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True, text=True)

    report_path = coverage_dir / "coverage-final.json"
    if not report_path.exists():
        return _no_report("jest-coverage", "coverage-final.json not generated")

    return _parse_jest_json(report_path, changed_files, repo)


def _ensure_vitest_coverage(repo: Path) -> None:
    """Add @vitest/coverage-v8 devDependency if not already present."""
    pkg_path = repo / "package.json"
    if not pkg_path.exists():
        return
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    dev_deps = pkg.get("devDependencies", {})
    if "@vitest/coverage-v8" in dev_deps or "@vitest/coverage-istanbul" in dev_deps:
        return
    dev_deps["@vitest/coverage-v8"] = "^1.0.0"
    pkg["devDependencies"] = dev_deps
    pkg_path.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
    print("  [Coverage] Added @vitest/coverage-v8 to devDependencies")
    subprocess.run("npm install", shell=True, cwd=str(repo), capture_output=True)


def _parse_jest_json(report_path: Path, changed_files: List[str], repo: Path) -> Dict:
    """
    Jest coverage-final.json format:
      {
        "/abs/path/to/fooService.js": {
          "s": {"0": 3, "1": 0},     # statement hit counts (0 = not covered)
          "statementMap": {
            "0": {"start": {"line": 10, ...}, "end": {"line": 10, ...}}
          }
        }
      }
    """
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return _no_report("jest-coverage", f"Failed to parse coverage-final.json: {e}")

    files_result = {}

    for src_file in changed_files:
        stem = Path(src_file).name
        file_data = None

        # Match by filename (Jest uses absolute paths)
        for abs_path, cov in data.items():
            if Path(abs_path).name == stem:
                file_data = cov
                break

        if not file_data:
            files_result[src_file] = _uncovered_file("File not found in Jest coverage report")
            continue

        covered: Set[int] = set()
        uncovered: Set[int] = set()

        stmt_map = file_data.get("statementMap", {})
        stmt_hits = file_data.get("s", {})

        for stmt_id, loc in stmt_map.items():
            line = loc.get("start", {}).get("line", 0)
            hits = stmt_hits.get(stmt_id, 0)
            if hits > 0:
                covered.add(line)
            else:
                uncovered.add(line)

        total = len(covered) + len(uncovered)
        pct = round(len(covered) / total * 100, 1) if total else 0.0
        files_result[src_file] = _build_file_result(covered, uncovered, pct, changed_files)

    return _build_summary("jest-coverage", files_result)


# ── Cobertura XML parser (shared by pytest-cov and Coverlet) ──────────────────

def _parse_cobertura_xml(
    report_path: Path, changed_files: List[str], repo: Path
) -> Dict:
    """
    Cobertura XML format:
      <class filename="payment_service.py">
        <lines>
          <line number="42" hits="1"/>   hits > 0 → covered
        </lines>
      </class>
    """
    try:
        tree = ET.parse(report_path)
    except ET.ParseError as e:
        return _no_report("cobertura", f"Failed to parse coverage XML: {e}")

    root = tree.getroot()
    files_result = {}

    for src_file in changed_files:
        filename = Path(src_file).name
        covered: Set[int] = set()
        uncovered: Set[int] = set()

        for cls in root.iter("class"):
            cls_filename = Path(cls.get("filename", "")).name
            if cls_filename == filename:
                for line in cls.iter("line"):
                    nr = int(line.get("number", 0))
                    hits = int(line.get("hits", 0))
                    if hits > 0:
                        covered.add(nr)
                    else:
                        uncovered.add(nr)
                break

        if not covered and not uncovered:
            files_result[src_file] = _uncovered_file(
                "File not found in coverage report — not reached by any test"
            )
            continue

        total = len(covered) + len(uncovered)
        pct = round(len(covered) / total * 100, 1) if total else 0.0
        files_result[src_file] = _build_file_result(covered, uncovered, pct, changed_files)

    return files_result  # caller sets "tool" key


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_file_result(
    covered: Set[int],
    uncovered: Set[int],
    pct: float,
    changed_files: List[str],
) -> Dict:
    return {
        "covered_pct": pct,
        "covered_lines": sorted(covered),
        "uncovered_lines": sorted(uncovered),
        "needs_tests": pct < 80.0 or len(uncovered) > 0,
    }


def _build_summary(tool: str, files_result: Dict) -> Dict:
    overall_needs = any(v.get("needs_tests") for v in files_result.values())
    parts = []
    for f, info in files_result.items():
        unc = info.get("uncovered_lines", [])
        pct = info.get("covered_pct", 0)
        if unc:
            parts.append(f"{Path(f).name}: {pct}% covered, lines {unc} NOT covered")
        else:
            parts.append(f"{Path(f).name}: {pct}% covered")

    return {
        "tool": tool,
        "files": files_result,
        "overall_needs_tests": overall_needs,
        "summary": " | ".join(parts) if parts else "No coverage data",
    }


def _no_report(tool: str, reason: str) -> Dict:
    return {
        "tool": tool,
        "files": {},
        "overall_needs_tests": True,
        "summary": f"Coverage not available: {reason}",
    }


def _uncovered_file(note: str) -> Dict:
    return {
        "covered_pct": 0.0,
        "covered_lines": [],
        "uncovered_lines": [],
        "needs_tests": True,
        "note": note,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Check line coverage for changed files")
    parser.add_argument("--lang-config",   required=True)
    parser.add_argument("--changed-files", required=True, help="JSON array")
    parser.add_argument("--repo",          default=".")
    parser.add_argument("--output",        default=None)
    args = parser.parse_args()

    lang_config   = json.loads(Path(args.lang_config).read_text())
    changed_files = json.loads(args.changed_files)

    result = check_coverage(lang_config, changed_files, args.repo)

    output = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Coverage report saved to {args.output}")
    else:
        print(output)

    sys.exit(0 if not result.get("overall_needs_tests") else 1)
