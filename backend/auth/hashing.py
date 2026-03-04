"""Password hashing helpers.

Uses bcrypt directly (bypassing passlib) because passlib 1.7.4 is
incompatible with bcrypt >= 4.0: passlib's detect_wrap_bug() calls
hashpw() with a >72-byte test password, which bcrypt 4+ rejects with
ValueError.  Calling bcrypt.hashpw / bcrypt.checkpw directly avoids
that adapter layer entirely.  bcrypt is already a declared dependency.
"""
from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*.

    The hash includes the salt, cost factor, and algorithm identifier, so
    the returned string is self-contained and suitable for direct storage.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return True if *password* matches *hashed*, False otherwise.

    bcrypt.checkpw uses a constant-time comparison to prevent timing attacks.
    """
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
