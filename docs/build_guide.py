"""Build docs/guide.html: a self-contained interactive guide to the project.

The hand-written explanations live in docs/guide_src/ (HTML shell, CSS, JS app, data files). This script adds the
parts that must never drift from the code: the module/function map, the import graph, line counts and test
coverage, all extracted with `ast`. Run from the repository root:

    python docs/build_guide.py
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "scholar_agent"
SRC = ROOT / "docs" / "guide_src"
OUT = ROOT / "docs" / "guide.html"


def first_line(doc: str | None) -> str:
    return (doc or "").strip().split("\n")[0].strip()


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = ast.unparse(node.args)
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"({args}){ret}"


def resolve_import(module: str, name: str | None, files: set[str]) -> str | None:
    """Map `scholar_agent.a.b` (+ optional imported name) to a module path inside the package."""
    parts = module.split(".")[1:]
    candidates = []
    if name:
        candidates.append("/".join([*parts, name]))
    candidates.append("/".join(parts))
    for cand in candidates:
        if not cand:
            continue
        for option in (f"{cand}.py", f"{cand}/__init__.py"):
            if option in files:
                return option
    return None


def extract() -> dict:
    files = {p.relative_to(PKG).as_posix() for p in PKG.rglob("*.py")}
    modules: dict[str, dict] = {}
    for path in sorted(PKG.rglob("*.py")):
        rel = path.relative_to(PKG).as_posix()
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        classes, functions, imports = [], [], set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("scholar_agent"):
                for alias in node.names:
                    target = resolve_import(node.module, alias.name, files)
                    if target and target != rel:
                        imports.add(target)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("scholar_agent"):
                        target = resolve_import(alias.name, None, files)
                        if target and target != rel:
                            imports.add(target)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({"name": node.name, "sig": signature(node), "doc": first_line(ast.get_docstring(node)),
                                  "line": node.lineno, "private": node.name.startswith("_")})
            elif isinstance(node, ast.ClassDef):
                methods = [
                    {"name": n.name, "sig": signature(n), "doc": first_line(ast.get_docstring(n)), "line": n.lineno}
                    for n in node.body
                    if isinstance(n, ast.FunctionDef) and not (n.name.startswith("__") and n.name.endswith("__"))
                ]
                fields = [n.target.id for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
                classes.append({"name": node.name, "doc": first_line(ast.get_docstring(node)), "line": node.lineno,
                                "bases": [ast.unparse(b) for b in node.bases], "methods": methods, "fields": fields,
                                "private": node.name.startswith("_")})
        modules[rel] = {
            "lines": len(text.splitlines()),
            "doc": first_line(ast.get_docstring(tree)),
            "classes": classes,
            "functions": functions,
            "imports": sorted(imports),
        }
    # reverse edges
    for rel, mod in modules.items():
        mod["usedBy"] = sorted(o for o, m in modules.items() if rel in m["imports"])
    return modules


def tests_info(modules: dict) -> dict:
    files = set(modules)
    info = {}
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        covered = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("scholar_agent"):
                for alias in node.names:
                    target = resolve_import(node.module, alias.name, files)
                    if target:
                        covered.add(target)
        names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        info[path.relative_to(ROOT).as_posix()] = {"tests": names, "covers": sorted(covered)}
    return info


def collect_pytest() -> int | None:
    try:
        out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                             cwd=ROOT, capture_output=True, text=True, timeout=120).stdout
        match = re.search(r"(\d+) tests? collected", out) or re.search(r"^(\d+) tests?", out, re.M)
        return int(match.group(1)) if match else None
    except Exception:
        return None


def tree_listing() -> list[str]:
    skip = {".venv", ".git", ".cache", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".index", "scholar_notes_agent.egg-info"}
    out = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if any(part in skip or part.startswith(".index") or part.endswith(".egg-info") for part in rel.parts):
            continue
        if path.is_file():
            out.append(rel.as_posix())
    return out


def js_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def main() -> None:
    modules = extract()
    tests = tests_info(modules)
    stats = {
        "modules": sum(1 for m in modules.values() if m["lines"] > 1),
        "lines": sum(m["lines"] for m in modules.values()),
        "testFunctions": sum(len(t["tests"]) for t in tests.values()),
        "testsCollected": collect_pytest(),
        "classes": sum(len(m["classes"]) for m in modules.values()),
        "functions": sum(len(m["functions"]) + sum(len(c["methods"]) for c in m["classes"]) for m in modules.values()),
    }
    files = tree_listing()
    stats["files"] = len(files)

    data_js = "\n".join(
        (SRC / name).read_text(encoding="utf-8")
        for name in ("data_overview.js", "data_adrs.js", "data_history.js", "data_modules.js")
    )
    generated = (
        f"const CODEMAP = {js_json(modules)};\nconst TESTMAP = {js_json(tests)};\n"
        f"const STATS = {js_json(stats)};\nconst FILES = {js_json(files)};\n"
    )
    html = (SRC / "index.html").read_text(encoding="utf-8")
    html = html.replace("/*__STYLE__*/", (SRC / "style.css").read_text(encoding="utf-8"))
    html = html.replace("/*__DATA__*/", generated + data_js)
    html = html.replace("/*__APP__*/", (SRC / "app.js").read_text(encoding="utf-8"))
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(html) // 1024} KiB) - {stats}")


if __name__ == "__main__":
    main()
