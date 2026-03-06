"""LeadForge DB package — selects backend based on DATABASE_URL.

If DATABASE_URL starts with 'postgres://' or 'postgresql://', the Postgres
backend (db.postgres) is used.  Otherwise SQLite is used (the default for
local development).

Both existing direct imports and the unified path work:
    from db.sqlite import db_save_job   # existing code — unchanged
    from db import db_save_job          # new unified path
"""
import os

_url = os.environ.get("DATABASE_URL", "")

if _url.startswith(("postgres://", "postgresql://")):
    from .postgres import (  # noqa: F401
        db_connect,
        db_init,
        db_save_job,
        db_get_job,
        db_load_job,
        db_save_results,
        db_load_results,
        db_create_user,
        db_get_user_by_email,
        db_get_user_by_id,
    )
    _BACKEND = "postgres"
else:
    from .sqlite import (  # noqa: F401
        db_connect,
        db_init,
        db_save_job,
        db_get_job,
        db_load_job,
        db_save_results,
        db_load_results,
        db_create_user,
        db_get_user_by_email,
        db_get_user_by_id,
    )
    _BACKEND = "sqlite"
