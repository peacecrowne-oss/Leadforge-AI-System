#!/usr/bin/env python3
from pathlib import Path
import ast

REQUIRED_PATHS = [
    "backend/routes/leads.py",
    "backend/routes/auth.py",
    "backend/routes/system.py",
    "backend/services/search_service.py",
    "backend/db/sqlite.py",
    "backend/auth/jwt.py",
    "backend/core/errors.py",
    "backend/core/logging.py",
    "backend/main.py",
]


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    root = Path(".")

    missing = []
    for p in REQUIRED_PATHS:
        if not (root / p).exists():
            missing.append(p)

    assert_true(not missing, f"Missing files: {missing}")

    main_file = Path("backend/main.py")
    source = main_file.read_text()

    # main.py should stay small
    assert_true(len(source.splitlines()) < 250, "main.py too large")

    tree = ast.parse(source)

    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    assert_true(len(classes) == 0, "main.py should not define classes")

    print("PASS test_architecture_structure")


if __name__ == "__main__":
    main()
