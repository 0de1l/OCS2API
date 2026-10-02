"""Validate files selected by Git for publication without printing secrets."""

import ast
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
PRIVATE_NAMES = {"config.json", "question_bank.json", ".env"}
GENERATED_DIRS = {".venv", "venv", "__pycache__", "build", "dist", "data", "logs", "exports", "backups"}


def main():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True,
    )
    names = sorted(set(result.stdout.decode("utf-8").strip("\0").split("\0")) - {""})
    problems = []
    for name in names:
        path = ROOT / name
        if not path.is_file():
            problems.append(f"Missing selected file: {name}")
            continue
        private_env = path.name.startswith(".env.") and path.name != ".env.example"
        if path.name in PRIVATE_NAMES or private_env or GENERATED_DIRS.intersection(Path(name).parts):
            problems.append(f"Private or generated file selected: {name}")
        if path.suffix.lower() in {".exe", ".zip", ".pyc", ".log"}:
            problems.append(f"Runtime or release artifact selected: {name}")
        if path.stat().st_size > 5 * 1024 * 1024:
            problems.append(f"File exceeds source repository limit (5 MiB): {name}")
        if path.suffix.lower() in {".png", ".ico"}:
            continue
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            problems.append(f"Non-UTF-8 text file: {name}")
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            problems.append(f"Potential credential detected (value withheld): {name}")
        if re.search(r"[A-Za-z]:[\\/]Users[\\/](?!<)[^\s/\\]+", content):
            problems.append(f"Personal Windows path in source: {name}")
        try:
            if path.suffix == ".json":
                json.loads(content)
            if path.suffix in {".py", ".spec"}:
                compile(content, name, "exec")
        except (ValueError, SyntaxError):
            problems.append(f"Invalid syntax: {name}")

    defaults = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    if defaults["openai_api_key"] or defaults["access_token"]:
        problems.append("Example configuration must contain empty credentials")
    tree = ast.parse((ROOT / "OCS2API.spec").read_text(encoding="utf-8"))
    analysis = next(node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Analysis")
    resources = ast.literal_eval(next(keyword.value for keyword in analysis.keywords if keyword.arg == "datas"))
    if set(resources) != {("templates", "templates"), ("static", "static"), ("api_docs.md", "."), ("logo.png", ".")}:
        problems.append("Unexpected PyInstaller resource list; review for private data")
    for folder in ("templates", "static"):
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.relative_to(ROOT).as_posix() not in names:
                problems.append(f"Unreviewed bundled resource: {path.relative_to(ROOT).as_posix()}")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"Release source checks passed: {len(names)} files; examples have no credentials; bundle uses an explicit resource list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
