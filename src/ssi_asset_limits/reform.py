"""PolicyEngine reform for relaxing or removing SSI resource limits."""

from __future__ import annotations

from .constants import DEFAULT_COUPLE_LIMIT, DEFAULT_INDIVIDUAL_LIMIT

INDIVIDUAL_LIMIT_PATH = "gov.ssa.ssi.eligibility.resources.limit.individual"
COUPLE_LIMIT_PATH = "gov.ssa.ssi.eligibility.resources.limit.couple"


def _date_range(start_year: int, end_year: int) -> str:
    return f"{start_year}-01-01.{end_year}-12-31"


def asset_limit_reform_dict(
    individual_limit: float = DEFAULT_INDIVIDUAL_LIMIT,
    couple_limit: float = DEFAULT_COUPLE_LIMIT,
    start_year: int = 2026,
    end_year: int = 2100,
) -> dict[str, dict[str, float]]:
    """Return a parameter reform that raises SSI resource limits."""

    active_range = _date_range(start_year, end_year)
    return {
        INDIVIDUAL_LIMIT_PATH: {active_range: individual_limit},
        COUPLE_LIMIT_PATH: {active_range: couple_limit},
    }


def create_asset_limit_reform(
    individual_limit: float = DEFAULT_INDIVIDUAL_LIMIT,
    couple_limit: float = DEFAULT_COUPLE_LIMIT,
    start_year: int = 2026,
    end_year: int = 2100,
):
    """Create a PolicyEngine US reform object for SSI asset limit removal."""

    from policyengine_core.reforms import Reform

    return Reform.from_dict(
        asset_limit_reform_dict(
            individual_limit=individual_limit,
            couple_limit=couple_limit,
            start_year=start_year,
            end_year=end_year,
        ),
        "policyengine_us",
    )
