"""Feature flag definitions for LeadForge subscription plans.

FEATURE_FLAGS maps plan name -> feature configuration dict.
Use get_plan_features(plan) to retrieve the config for a given plan.

Plans:
  free       - limited lead search, no campaigns, no experiments
  pro        - unlimited lead search, campaigns enabled
  enterprise - all features including experiments

Unknown plan names fall back to the 'free' configuration.
"""

FEATURE_FLAGS: dict[str, dict] = {
    "free": {
        "lead_search_limit": 50,
        "campaigns": False,
        "experiments": False,
    },
    "pro": {
        "lead_search_limit": None,
        "campaigns": True,
        "experiments": False,
    },
    "enterprise": {
        "lead_search_limit": None,
        "campaigns": True,
        "experiments": True,
    },
}


def get_plan_features(plan: str) -> dict:
    """Return the feature configuration for the given plan name.

    Falls back to 'free' if the plan is unrecognised, so new or
    unexpected plan values never raise and always default to the
    most restrictive tier.
    """
    return FEATURE_FLAGS.get(plan, FEATURE_FLAGS["free"])
