#!/usr/bin/env python3
import importlib
import sys
from pathlib import Path

MODULES = [
    "main",
    "routes.auth",
    "routes.leads",
    "routes.system",
    "services.search_service",
    "db.sqlite",
    "auth.jwt",
    "auth.dependencies",
    "core.errors",
    "core.logging",
]


def main():
    root = Path(".").resolve()
    backend_dir = root / "backend"

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    for mod in MODULES:
        importlib.import_module(mod)

    print("PASS test_import_graph")


if __name__ == "__main__":
    main()
