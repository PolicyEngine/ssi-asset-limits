"""Run the regulation-sourced SSI deeming cases on the certified engine.

The cases in ``tests/fixtures/ssi_resource_deeming`` are the YAML tests of the
policyengine-us pull request that adds 20 CFR 416.1202 resource deeming
(expected values come from the regulation and the POMS examples, not from
either model). Here they run against policyengine-us 2.2.1 with
``SSIResourceDeemingReform`` installed, so the reform used for the sensitivity
run is held to the same cases as the branch it copies.
"""

from pathlib import Path

import pytest

FIXTURES = (
    Path(__file__).resolve().parents[1] / "fixtures/ssi_resource_deeming"
)


@pytest.fixture(scope="module")
def reformed_system():
    from policyengine_us import CountryTaxBenefitSystem

    from ssi_asset_limits.sensitivity.ssi_resource_deeming_reform import (
        SSIResourceDeemingReform,
    )

    return SSIResourceDeemingReform(CountryTaxBenefitSystem())


def test_fixture_files_are_present():
    assert sorted(path.name for path in FIXTURES.glob("*.yaml")) == [
        "is_ssi_spousal_resource_deeming_applies.yaml",
        "meets_ssi_resource_test.yaml",
        "ssi_resources_deemed_from_ineligible_parent.yaml",
        "ssi_resources_deemed_from_ineligible_spouse.yaml",
    ]


def test_regulation_cases_pass_with_the_reform(reformed_system):
    from policyengine_core.tools.test_runner import run_tests

    assert run_tests(reformed_system, [str(FIXTURES)]) == 0


def test_cases_fail_without_the_reform():
    """The cases must bite: the unmodified 2.2.1 engine cannot pass them."""
    from policyengine_core.tools.test_runner import run_tests
    from policyengine_us import CountryTaxBenefitSystem

    path = FIXTURES / "meets_ssi_resource_test.yaml"
    assert run_tests(CountryTaxBenefitSystem(), [str(path)]) != 0
