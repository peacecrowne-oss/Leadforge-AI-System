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
        db_create_campaign,
        db_list_campaigns,
        db_get_campaign,
        db_update_campaign,
        db_delete_campaign,
        db_add_lead_to_campaign,
        db_list_campaign_leads,
        db_remove_lead_from_campaign,
        db_run_campaign,
        db_get_campaign_stats,
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
        db_create_campaign,
        db_list_campaigns,
        db_get_campaign,
        db_update_campaign,
        db_delete_campaign,
        db_add_lead_to_campaign,
        db_list_campaign_leads,
        db_remove_lead_from_campaign,
        db_run_campaign,
        db_get_campaign_stats,
        db_get_experiment_metrics,
    )
    _BACKEND = "sqlite"
