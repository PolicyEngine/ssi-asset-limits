from ssi_asset_limits.reform import (
    COUPLE_LIMIT_PATH,
    INDIVIDUAL_LIMIT_PATH,
    asset_limit_reform_dict,
)


def test_asset_limit_reform_dict_sets_both_resource_limits():
    reform = asset_limit_reform_dict(
        individual_limit=9_999,
        couple_limit=19_999,
        start_year=2026,
        end_year=2030,
    )

    assert reform == {
        INDIVIDUAL_LIMIT_PATH: {"2026-01-01.2030-12-31": 9_999},
        COUPLE_LIMIT_PATH: {"2026-01-01.2030-12-31": 19_999},
    }
