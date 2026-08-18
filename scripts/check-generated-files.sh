#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 - <<'PY'
import subprocess
import sys

tracked = subprocess.run(
    ["git", "ls-files", "-z"],
    check=True,
    capture_output=True,
).stdout.split(b"\0")

bad_paths = []
for raw_path in tracked:
    if not raw_path:
        continue

    path = raw_path.decode()
    normalized = f"/{path}"

    if (
        "/node_modules/" in normalized
        or "/__pycache__/" in normalized
        or normalized.endswith((".pyc", ".pyo"))
        or "/dist/" in normalized
        or path == "docs/index.html"
        or path.startswith("docs/assets/")
    ):
        bad_paths.append(path)

if bad_paths:
    print("Tracked generated files found:", file=sys.stderr)
    for path in bad_paths:
        print(path, file=sys.stderr)
    sys.exit(1)
PY
