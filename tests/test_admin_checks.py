import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from ssi_asset_limits.admin_checks import (
    SSA_AGE_SHARES,
    SSA_MARITAL,
    SSA_WITH_SOCIAL_SECURITY,
    eligible_apart_from_resources,
    new_recipient_decomposition,
    pool_definition_check,
    recipients_by_fine_age,
    recipients_by_marital_status,
    recipients_with_social_security,
    resources_of_the_eligible,
)


def toy_persons():
    """Six people chosen so every table can be checked by hand."""

    frame = pd.DataFrame(
        {
            "person_id": range(6),
            "person_weight": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "age": [16, 30, 62, 67, 72, 85],
            "ssi_countable_resources": [0, 0, 2500, 5000, 30000, 0],
            "ssi_baseline": [8000, 9000, 0, 0, 0, 7000],
            "ssi_ten_twenty": [8000, 9000, 6000, 0, 0, 7000],
            "ssi_no_limit": [8000, 9000, 6000, 0, 5000, 7000],
            "has_social_security": [False, True, False, True, True, True],
            # People 2 and 3 are a married couple; the rest live alone.
            "marital_unit_id": [0, 1, 2, 2, 4, 5],
            "marital_unit_size": [1, 1, 2, 2, 1, 1],
            "is_ssi_eligible_no_limit": [1, 1, 1, 1, 1, 1],
            "ssi_amount_if_eligible_no_limit": [9000] * 6,
            "ssi_countable_income_no_limit": [1000, 0, 3000, 2000, 4000, 2000],
            "meets_ssi_resource_test_baseline": [1, 1, 0, 0, 0, 1],
            "meets_ssi_resource_test_ten_twenty": [1, 1, 1, 1, 0, 1],
            "meets_ssi_resource_test_no_limit": [1, 1, 1, 1, 1, 1],
            # Person 3 becomes eligible at $10k/$20k but would not claim.
            "takes_up_ssi_if_eligible_baseline": [1, 1, 1, 0, 1, 1],
        }
    )
    return frame


def test_ssa_constants_are_internally_consistent():
    assert sum(share for *_, share in SSA_AGE_SHARES) == pytest.approx(
        100, abs=0.2
    )
    assert sum(SSA_MARITAL.values()) == 7_423_856
    assert sum(both for both, _ in SSA_WITH_SOCIAL_SECURITY.values()) == (
        2_548_159
    )
    assert sum(total for _, total in SSA_WITH_SOCIAL_SECURITY.values()) == (
        7_423_856
    )


def test_fine_age_bands_partition_current_recipients():
    table = recipients_by_fine_age(toy_persons())
    by_band = table.set_index("age_band")["policyengine_recipients"]
    assert by_band["15-17"] == 10
    assert by_band["30-39"] == 20
    assert by_band["80 or older"] == 60
    assert by_band.sum() == 90
    assert table["policyengine_share_pct"].sum() == pytest.approx(100)


def test_social_security_overlap_by_age():
    table = recipients_with_social_security(toy_persons()).set_index(
        "age_band"
    )
    assert table.loc["Under 18", "policyengine_with_social_security"] == 0
    assert table.loc["18-64", "policyengine_with_social_security"] == 20
    assert table.loc["65 or older", "policyengine_share_pct"] == 100
    assert table.loc["65 or older", "ssa_share_pct"] == pytest.approx(
        100 * 1_410_664 / 2_469_103
    )


def couples():
    """Complete couples and singles, with receipt that the claim flag misses.

    Units 10 and 11 are couples in which both spouses are aged, blind or
    disabled (a joint claim), but in unit 11 only one spouse receives SSI.
    """

    return pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4, 5, 6, 7, 8, 9],
            "marital_unit_id": [10, 10, 11, 11, 12, 12, 13, 14, 14],
            "marital_unit_size": [2, 2, 2, 2, 2, 2, 1, 2, 2],
            "person_weight": [5.0, 5.0, 7.0, 7.0, 4.0, 4.0, 3.0, 9.0, 9.0],
            "ssi_baseline": [6000, 6000, 6000, 0, 5000, 0, 9000, 0, 0],
            "ssi_claim_is_joint_baseline_january": [1, 1, 1, 1, 0, 0, 0, 1, 1],
        }
    )


def test_marital_status_uses_the_spouses_receipt():
    table = recipients_by_marital_status(couples()).set_index("marital_status")
    recipients = table["policyengine_recipients"]
    assert recipients["No spouse"] == 3
    # Only unit 10: unit 11 files jointly but one spouse is not paid.
    assert recipients["Spouse also receives SSI"] == 10
    assert recipients["Spouse does not receive SSI"] == 7 + 4
    assert recipients.sum() == 3 + 10 + 7 + 4
    assert table["policyengine_share_pct"].sum() == pytest.approx(100)
    assert table.loc["Spouse also receives SSI", "ssa_category"] == (
        "Eligible spouse"
    )
    assert table["ssa_recipients"].sum() == sum(SSA_MARITAL.values())


def test_marital_status_rejects_units_larger_than_a_couple():
    frame = couples()
    frame.loc[6, "marital_unit_id"] = 10
    frame["marital_unit_size"] = frame.groupby("marital_unit_id")[
        "person_id"
    ].transform("size")
    with pytest.raises(ValueError, match="more than two"):
        recipients_by_marital_status(frame)


@given(
    st.lists(
        st.tuples(
            st.booleans(),
            st.booleans(),
            st.booleans(),
            st.floats(0.5, 100),
        ),
        min_size=1,
        max_size=30,
    )
)
def test_marital_categories_partition_recipients(units):
    """Each recipient lands in exactly one category; paid couples pair up."""

    rows = []
    for unit, (couple, first_paid, second_paid, weight) in enumerate(units):
        members = [first_paid, second_paid] if couple else [first_paid]
        for paid in members:
            rows.append(
                {
                    "person_id": len(rows),
                    "marital_unit_id": unit,
                    "marital_unit_size": len(members),
                    "person_weight": weight,
                    "ssi_baseline": 100 if paid else 0,
                }
            )
    persons = pd.DataFrame(rows)
    recipients = persons.loc[persons.ssi_baseline > 0, "person_weight"].sum()
    if recipients == 0:
        return
    table = recipients_by_marital_status(persons).set_index("marital_status")
    assert table["policyengine_recipients"].sum() == pytest.approx(recipients)
    both = sum(
        2 * weight for couple, a, b, weight in units if couple and a and b
    )
    assert table.loc[
        "Spouse also receives SSI", "policyengine_recipients"
    ] == pytest.approx(both)


def test_pool_and_decomposition_by_hand():
    persons = toy_persons()
    assert eligible_apart_from_resources(persons).all()
    table = new_recipient_decomposition(persons).set_index(
        ["scenario", "age_band"]
    )
    adults = table.loc[("ten_twenty", "18-64")]
    assert adults["excluded_by_resource_test"] == 30
    assert adults["admitted_by_reform"] == 30
    assert adults["model_new_recipients"] == 30
    elderly = table.loc[("ten_twenty", "65 or older")]
    assert elderly["excluded_by_resource_test"] == 90
    # Person 3 (weight 40) is admitted but has no take-up flag.
    assert elderly["admitted_by_reform"] == 40
    assert elderly["admitted_with_take_up_flag"] == 0
    assert elderly["model_new_recipients"] == 0
    removal = table.loc[("no_limit", "65 or older")]
    assert removal["admitted_by_reform"] == 90
    assert removal["admitted_with_take_up_flag"] == 50
    assert removal["model_new_recipients"] == 50
    # Admitted people who claim are exactly the model's new recipients.
    assert (
        table["admitted_with_take_up_flag"] == table["model_new_recipients"]
    ).all()


def test_pool_definition_check_flags_disagreement():
    persons = toy_persons()
    clean = pool_definition_check(persons).iloc[0]
    assert clean["paid_but_not_in_pool"] == 0
    assert clean["in_pool_but_not_paid"] == 0
    persons.loc[1, "ssi_countable_income_no_limit"] = 99_999
    broken = pool_definition_check(persons).iloc[0]
    assert broken["paid_but_not_in_pool"] == 20


def test_resource_bins_partition_each_age_band():
    table = resources_of_the_eligible(toy_persons())
    bins = table[table.own_countable_resources != "of which exactly $0"]
    for _, group in bins.groupby("age_band"):
        assert group["share_pct"].sum() == pytest.approx(100)
    zero = table[table.own_countable_resources == "of which exactly $0"]
    assert zero.set_index("age_band").loc["65 or older", "people"] == 60
