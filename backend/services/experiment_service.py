"""Deterministic variant assignment for LeadForge A/B experiments.

Design constraints:
- No randomness: same (assignment_key, variants) always returns the same variant.
- No external libraries: uses only hashlib from the stdlib.
- Transparent: the bucket value is derivable independently for any key.

Algorithm:
  1. SHA-256 hash of assignment_key (UTF-8 encoded).
  2. Interpret first 8 bytes of digest as a big-endian unsigned integer.
  3. Bucket = integer % 100  ->  value in [0, 99].
  4. Walk variants in list order, accumulating traffic_percentage.
     Return the first variant whose cumulative total exceeds the bucket.

Public API:
    assign_variant(assignment_key, variants) -> ExperimentVariantResponse
    evaluate_winner(metrics)               -> ExperimentWinnerResponse
"""
from __future__ import annotations

import hashlib

from models import ExperimentVariantMetrics, ExperimentVariantResponse, ExperimentWinnerResponse


def assign_variant(
    assignment_key: str,
    variants: list[ExperimentVariantResponse],
) -> ExperimentVariantResponse:
    """Return the variant assigned to assignment_key, deterministically.

    Args:
        assignment_key: Any stable string identifier — user_id, lead_id,
                        email address, etc.  Must be non-empty.
        variants:       Ordered list of ExperimentVariantResponse objects.
                        The list order determines bucket boundaries, so it
                        must be consistent across calls (e.g. sorted by id).

    Returns:
        The ExperimentVariantResponse whose traffic bucket contains
        the hashed assignment_key.

    Raises:
        ValueError: if variants is empty.
        ValueError: if sum(traffic_percentage) != 100.
    """
    if not variants:
        raise ValueError("variants list must not be empty")

    total = sum(v.traffic_percentage for v in variants)
    if total != 100:
        raise ValueError(
            f"traffic_percentage values must sum to 100, got {total}"
        )

    digest = hashlib.sha256(assignment_key.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], byteorder="big") % 100

    cumulative = 0
    for variant in variants:
        cumulative += variant.traffic_percentage
        if bucket < cumulative:
            return variant

    # Unreachable when total == 100, but satisfies the type checker.
    return variants[-1]


def evaluate_winner(
    metrics: list[ExperimentVariantMetrics],
) -> ExperimentWinnerResponse:
    """Return the winning variant based on highest exposures.

    Rules:
      - No variants supplied → no winner; basis explains empty input.
      - All exposures == 0   → no winner; basis = "no exposures recorded".
      - Multiple variants share the highest exposure count → tiebreak on
        distinct_campaigns; if still tied → no winner with clear reason.
      - Otherwise → winner is the single variant with the most exposures;
        basis = "highest exposures (X) with Y distinct campaigns".
    """
    if not metrics:
        return ExperimentWinnerResponse(
            winning_variant_id=None,
            winning_variant_name=None,
            basis="no variants defined for this experiment",
        )

    max_exposures = max(m.exposures for m in metrics)

    if max_exposures == 0:
        return ExperimentWinnerResponse(
            winning_variant_id=None,
            winning_variant_name=None,
            basis="no exposures recorded",
        )

    leaders = [m for m in metrics if m.exposures == max_exposures]

    if len(leaders) > 1:
        # Tiebreak: use distinct_campaigns as secondary metric
        max_campaigns = max(m.distinct_campaigns for m in leaders)
        leaders = [m for m in leaders if m.distinct_campaigns == max_campaigns]

        if len(leaders) > 1:
            return ExperimentWinnerResponse(
                winning_variant_id=None,
                winning_variant_name=None,
                basis=(
                    f"tie: {len(leaders)} variants at {max_exposures} exposures "
                    f"and {max_campaigns} distinct campaigns"
                ),
            )

    winner = leaders[0]
    return ExperimentWinnerResponse(
        winning_variant_id=winner.variant_id,
        winning_variant_name=winner.variant_name,
        basis=f"highest exposures ({winner.exposures}) with {winner.distinct_campaigns} distinct campaigns",
    )
