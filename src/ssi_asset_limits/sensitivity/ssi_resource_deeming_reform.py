"""SSI resource deeming (20 CFR 416.1202) as a reform on policyengine-us 2.2.1.

The certified bundle pins policyengine-us 2.2.1, whose SSI resource test
counts only the person's own resources (or a couple's when both spouses are
eligible). PolicyEngine/policyengine-us#10040 (branch
``ssi-resource-deeming``, fixing PolicyEngine/policyengine-us#3557) adds the
federal deeming rules. Until a certified bundle carries that change, this
module installs the same variable classes on 2.2.1 so the effect on the
certified population can be measured. It is a sensitivity variant, never the
published estimate.

This is the branch's own 2.2.1 companion (``backport/`` at commit
190f45824e). 2.2.1 has no parent links, so parents are found by the branch's
no-link proxy (tax unit and household, over ``is_parent``); every other
policy class and helper is the branch source, which the branch's checker
compares class by class. The branch's regulation-sourced cases that 2.2.1 can
express run against this reform in
``tests/engine/test_resource_deeming_reform.py``.
"""

from policyengine_us.model_api import *
from policyengine_core.reforms import Reform


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/is_ssi_resource_deeming_child.py
class is_ssi_resource_deeming_child(Variable):
    value_type = bool
    entity = Person
    label = "Child subject to parental SSI resource deeming"
    definition_period = MONTH
    reference = (
        "https://www.ecfr.gov/current/title-20/section-416.1202#p-416.1202(b)",
        "https://www.ecfr.gov/current/title-20/section-416.1856",
        "https://www.ecfr.gov/current/title-20/section-416.1167",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330200",
    )

    def formula(person, period, parameters):
        # SI 01330.200 B divides only among SSI-eligible children. Match
        # is_ssi_eligible's immigration gate without reading eligibility or
        # the resource test, which depend on this allocation.
        immigration_status = person("immigration_status", period)
        is_citizen = immigration_status == immigration_status.possible_values.CITIZEN
        meets_immigration_status = is_citizen | person(
            "is_ssi_qualified_noncitizen", period
        )
        # 416.1856: 'You are not married' and 'not the head of a household'.
        # A two-person marital unit represents married, cohabiting spouses.
        # age is annual in the model: supply the relevant attained age.
        return (
            person("is_ssi_aged_blind_disabled", period)
            & meets_immigration_status
            & (person("age", period.this_year) < 18)
            & (person.marital_unit.nb_persons() == 1)
            & ~person("is_household_head", period)
            & ~person("ssi_lives_in_medical_treatment_facility", period)
            & ~person("ssi_resource_deeming_waiver", period)
            & ~person("ssi_resource_deeming_child_is_ineligible", period)
        )


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/is_ssi_spousal_resource_deeming_applies.py
class is_ssi_spousal_resource_deeming_applies(Variable):
    value_type = bool
    entity = Person
    label = "Ineligible spouse's resources are deemed for SSI"
    definition_period = MONTH
    reference = (
        "https://www.ecfr.gov/current/title-20/section-416.1202#p-416.1202(a)",
        "https://www.ecfr.gov/current/title-20/section-416.1160",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330100",
        "https://www.ecfr.gov/current/title-20/section-416.1167",
    )

    def formula(person, period, parameters):
        # 416.1160: an ineligible spouse 'lives with you as your husband or
        # wife and is not eligible for SSI benefits'. Identify the spouse with
        # the same evidence as a parent's spouse in parental deeming, so one
        # couple is never married for one rule and not the other. 416.1167
        # retains an absent person's household membership: enter a temporarily
        # absent spouse in the household they remain a member of.
        spouse = _ssi_spouse_index(person, period)
        aged_blind_disabled = person("is_ssi_aged_blind_disabled", period)
        # As is_ssi_ineligible_spouse, a spouse who is not aged, blind or
        # disabled cannot be eligible; two such spouses claim jointly.
        spouse_ineligible = (spouse >= 0) & ~aged_blind_disabled[np.maximum(spouse, 0)]
        return (
            aged_blind_disabled
            & ~person("ssi_claim_is_joint", period)
            & spouse_ineligible
        )


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/ssi_resource_deeming_child_is_ineligible.py
class ssi_resource_deeming_child_is_ineligible(Variable):
    value_type = bool
    entity = Person
    label = "Child is otherwise ineligible for SSI resource deeming allocation"
    definition_period = MONTH
    reference = "https://secure.ssa.gov/poms.nsf/lnx/0501330200"
    documentation = """
    Adjudicated SSI ineligibility for a reason other than the resource test,
    used to remove a child from the equal parental resource allocation.
    POMS SI 01330.200 B: 'If an eligible child is later determined ineligible
    for any reason' redivide among the remaining eligible children effective
    the first month of ineligibility. Resource ineligibility is calculated
    within the resource deeming formula, avoiding an eligibility cycle.
    """


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/ssi_resource_deeming_excluded_military_resources.py
class ssi_resource_deeming_excluded_military_resources(Variable):
    value_type = float
    entity = Person
    label = "Unspent retroactive military payments excluded from SSI deeming"
    unit = USD
    definition_period = MONTH
    quantity_type = STOCK
    reference = "https://www.ecfr.gov/current/title-20/section-416.1202"
    documentation = """
    The part of otherwise countable resources consisting of qualifying
    retroactive special pay under 37 USC 310 or combat-zone family separation
    allowance under 37 USC 427. Sections 416.1202(a)(2)-(3) and (b)(1)(ii)-(iii)
    exclude the unspent amount for nine months beginning with the month
    following receipt. Supply only the amount within that exclusion window;
    the model has no payment receipt history from which to derive it.
    """


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/ssi_resource_deeming_waiver.py
class ssi_resource_deeming_waiver(Variable):
    value_type = bool
    entity = Person
    label = "Child meets the SSI resource deeming home care exception"
    definition_period = MONTH
    reference = (
        "https://www.ecfr.gov/current/title-20/section-416.1202#p-416.1202(b)(2)"
    )
    documentation = """
    Adjudicated exception under 20 CFR 416.1202(b)(2). All three conditions
    must hold: the disabled child previously received reduced SSI in a
    medical treatment facility under 416.414; qualifies for Medicaid home
    care under 1915(c) or 1902(e)(3); and would otherwise be ineligible due
    to parental income or resource deeming. Medicaid enrollment alone does
    not establish this exception. Supply the determination for each month.
    """


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/_ssi_spouses.py
def _ssi_established_spouse_indices(person, period, first, second):
    """Rows of established co-resident spouses, with the Medicaid bound.

    SSI resource deeming uses this one test for a claimant's spouse
    (416.1202(a)) and for a parent's spouse (416.1202(b)). As in
    _medicaid_parents, marriage is shown by the other head/spouse of a
    married tax unit (here also in the same marital unit, so a tax-unit
    spouse role alone never makes a spouse of someone with their own marital
    unit), or by a two-person marital unit with cohabitating_spouses on
    either tax unit. A marital unit alone is insufficient: situations
    omitting marital units put everyone in one.
    Two dependents of one tax unit who share a two-person marital unit are
    spouses too, since a default marital unit also holds the tax unit's head
    and so never has two people. tax_unit_married is exactly when
    filing_status is JOINT; reading filing_status would pull the tax-filing
    chain (dependents, gross income, retirement-contribution limits) into SSI
    eligibility. Parent-child links exclude candidates even when tax roles
    suggest marriage; ambiguous candidates resolve to no spouse.
    """
    head_or_spouse = person("is_tax_unit_head_or_spouse", period)
    tax_unit = person.tax_unit.reference_entity.members_entity_id
    joint = head_or_spouse & person.tax_unit("tax_unit_married", period)
    married = person.marital_unit.nb_persons() == 2
    marital_unit = person.marital_unit.reference_entity.members_entity_id
    cohabiting = person.tax_unit("cohabitating_spouses", period)
    own_index = np.arange(person.count)
    spouse = np.full(person.count, -1, dtype=int)
    candidates = np.zeros(person.count, dtype=int)
    household = person.household
    for position in range(
        int(np.max(household.reference_entity.members_position, initial=-1)) + 1
    ):
        member = household.value_nth_person(position, own_index, default=-1)
        names_applicant = (first[member] == own_index) | (second[member] == own_index)
        named_by_applicant = (first == member) | (second == member)
        shown = (
            (member >= 0)
            & (member != own_index)
            & ~names_applicant
            & ~named_by_applicant
            & (
                (
                    joint
                    & head_or_spouse[member]
                    & (tax_unit[member] == tax_unit)
                    & (marital_unit[member] == marital_unit)
                )
                | (
                    married
                    & (marital_unit[member] == marital_unit)
                    & (
                        cohabiting
                        | cohabiting[member]
                        | (
                            ~head_or_spouse
                            & ~head_or_spouse[member]
                            & (tax_unit[member] == tax_unit)
                        )
                    )
                )
            )
        )
        spouse = np.where(shown, member, spouse)
        candidates += shown
    return np.where(candidates == 1, spouse, -1)


# Stand-in for co_resident_parent_indices in
# policyengine_us/variables/household/demographic/person/_parent_links.py.
# US 2.2.1 has no parent_1_id/parent_2_id: every parent row is unresolved, as
# in the no-link specialization of _ssi_parental_resource_pool.
def co_resident_parent_indices(person, period):
    return (
        np.full(person.count, -1, dtype=int),
        np.full(person.count, -1, dtype=int),
    )


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/_ssi_spouses.py
def _ssi_spouse_index(person, period):
    """The row of each person's established co-resident spouse, or -1."""
    first, second = co_resident_parent_indices(person, period)
    return _ssi_established_spouse_indices(person, period, first, second)


def _ssi_unlinked_parental_resource_pool(person, resources, parent, spouse):
    """Return tax-unit/household proxy resources, count and exact pool keys.

    Only unlinked parents and their established spouses enter this proxy.
    With no parent ids, is_parent cannot distinguish a grandparent or an
    unrelated parent from the child's parent: this is a data limitation.
    The first four key columns hold deemor row indices. A proxy with more
    than four deemors cannot equal a linked pool (two parents and at most
    their two spouses), so its fifth column identifies its tax-unit and
    household intersection. Thus keys are exact, with linear memory.
    """
    named = parent
    parent = parent | ((spouse >= 0) & parent[spouse])
    group = person.tax_unit
    indices = np.arange(person.count)
    households = person.household.reference_entity.members_entity_id
    tax_units = group.reference_entity.members_entity_id
    total = np.zeros(person.count)
    count = np.zeros(person.count, dtype=int)
    keys = np.full((person.count, 5), -1, dtype=int)

    def add(rows, selected):
        nonlocal total, count
        store = selected & (count < 4)
        keys[indices[store], count[store]] = rows[store]
        total = total + np.where(selected, resources[np.maximum(rows, 0)], 0)
        count = count + selected

    for position in range(
        int(np.max(group.reference_entity.members_position, initial=-1)) + 1
    ):
        member = group.value_nth_person(position, indices, default=-1)
        safe = np.maximum(member, 0)
        selected = (member >= 0) & (households[safe] == households) & parent[safe]
        add(member, selected)
        # A parent's established spouse counts wherever they file
        # (416.1202(b)(1)); members of this tax unit were counted above.
        partner = np.where(selected & named[safe], spouse[safe], -1)
        add(partner, (partner >= 0) & (tax_units[np.maximum(partner, 0)] != tax_units))
    keys[:, :4].sort(axis=1)
    large = count > 4
    if np.any(large):
        _, intersections = np.unique(
            np.column_stack((group.reference_entity.members_entity_id, households)),
            axis=0,
            return_inverse=True,
        )
        keys[large, :4] = -1
        keys[large, 4] = intersections[large]
    return total, count, keys


def _ssi_parental_resource_pool(person, period, resources):
    """Group the no-link tax-unit/household proxy by its exact deemor sets.

    US 2.2.1 has no parent ids, so is_parent is the available parent proxy.
    It cannot distinguish a grandparent or unrelated parent from this child's
    parent, nor identify a co-resident parent in another tax unit. Spouse
    identification, allowances and eligible-child redistribution match the
    branch's no-link path. Represent temporary absence through household
    membership under 20 CFR 416.1167, as on the current branch.
    """
    first = second = np.full(person.count, -1, dtype=int)
    spouse = _ssi_established_spouse_indices(person, period, first, second)
    total, count, keys = _ssi_unlinked_parental_resource_pool(
        person, resources, person("is_parent", period), spouse
    )
    _, pool = np.unique(keys, axis=0, return_inverse=True)
    return total, count, pool


class ssi_resources_deemed_from_ineligible_parent(Variable):
    value_type = float
    entity = Person
    label = "SSI resources deemed from ineligible parents"
    unit = USD
    definition_period = MONTH
    quantity_type = STOCK
    reference = (
        "https://www.ecfr.gov/current/title-20/section-416.1202#p-416.1202(b)",
        "https://www.ecfr.gov/current/title-20/section-416.1205",
        "https://www.ecfr.gov/current/title-20/section-416.1167",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330200",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330280",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330310",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330340",
    )

    def formula(person, period, parameters):
        p = parameters(period).gov.ssa.ssi.eligibility.resources.limit
        # Under 416.1167 a temporarily absent person should be entered in
        # the household they remain a member of; tax-unit membership alone
        # does not bring permanently nonresident relatives into that home.
        parental_resources, parent_count, pool = _ssi_parental_resource_pool(
            person, period, person("ssi_resources_for_deeming", period)
        )
        # 'only to the extent that those resources exceed the resource limits
        # described in § 416.1205': use the reformable individual/couple limits.
        allowance = where(parent_count > 1, p.couple, p.individual)
        excess = max_(0, parental_resources - allowance)
        # Do not discard ABD parents. SI 01330.310 B-C says zero if parent(s)
        # meets resource eligibility, usual deeming if not. The Ryder example
        # (.340) has an ABD mother failing the couple limit: 3100-3000=100.
        own_resources = person("ssi_countable_resources", period)
        active = person("is_ssi_resource_deeming_child", period) & (
            own_resources <= p.individual
        )
        deemed = np.zeros(person.count)
        # SI 01330.200 B: 'equally divide' among eligible children; when a
        # child is ineligible 'divide ... among the remaining eligible children'.
        # Retain the last tested share for a failed child, then redistribute.
        # Each round removes at least one child or leaves the result stable;
        # at most the largest household size rounds are needed (Goode, .280).
        rounds = int(np.max(person.household.nb_persons(), initial=0))
        pool_count = int(np.max(pool, initial=-1)) + 1
        for _ in range(rounds):
            count = np.bincount(pool[active], minlength=pool_count)
            share = excess / max_(1, count[pool])
            deemed = where(active, share, deemed)
            remaining = active & (own_resources + share <= p.individual)
            if np.array_equal(active, remaining):
                break
            active = remaining
        return deemed


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/ssi_resources_deemed_from_ineligible_spouse.py
class ssi_resources_deemed_from_ineligible_spouse(Variable):
    value_type = float
    entity = Person
    label = "SSI resources deemed from an ineligible spouse"
    unit = USD
    definition_period = MONTH
    quantity_type = STOCK
    reference = (
        "https://www.ecfr.gov/current/title-20/section-416.1202#p-416.1202(a)",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330100",
    )

    def formula(person, period, parameters):
        resources = person("ssi_resources_for_deeming", period)
        spouse = _ssi_spouse_index(person, period)
        # 416.1202(a): 'whether or not such resources are available'.
        return where(
            person("is_ssi_spousal_resource_deeming_applies", period),
            resources[np.maximum(spouse, 0)],
            0,
        )


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/ssi_resources_for_deeming.py
class ssi_resources_for_deeming(Variable):
    value_type = float
    entity = Person
    label = "Countable SSI resources of a spouse or parent for deeming"
    unit = USD
    definition_period = MONTH
    quantity_type = STOCK
    reference = (
        "https://www.ecfr.gov/current/title-20/section-416.1202",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330220",
    )

    def formula(person, period, parameters):
        # 416.1202(a)(1), (b)(1)(i): 'Pension funds' include IRAs and
        # work-related pension plans. ssi_countable_resources already excludes
        # retirement assets, the home, vehicle and other noncountable assets.
        resources = person("ssi_countable_resources", period)
        excluded = person("ssi_resource_deeming_excluded_military_resources", period)
        return max_(0, resources - max_(0, excluded))


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/meets_ssi_resource_test.py
class meets_ssi_resource_test(Variable):
    value_type = bool
    entity = Person
    label = "Meets SSI resource test"
    definition_period = MONTH
    reference = (
        "https://www.ecfr.gov/current/title-20/section-416.1202",
        "https://www.ecfr.gov/current/title-20/section-416.1205",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330110",
    )

    def formula(person, period, parameters):
        p = parameters(period).gov.ssa.ssi
        joint_claim = person("ssi_claim_is_joint", period)
        personal_resources = person("ssi_countable_resources", period)
        spousal_deeming = person("is_ssi_spousal_resource_deeming_applies", period)
        deemed_resources = add(
            person,
            period,
            [
                "ssi_resources_deemed_from_ineligible_spouse",
                "ssi_resources_deemed_from_ineligible_parent",
            ],
        )
        countable_resources = where(
            joint_claim,
            person.marital_unit.sum(personal_resources),
            personal_resources + deemed_resources,
        )
        # 416.1205(a): an individual living with an ineligible spouse counts
        # 'including the resources of the spouse' against the spouse limit.
        # This applies even when no income is deemed or the spouse owns zero.
        resource_limit = where(
            joint_claim | spousal_deeming,
            p.eligibility.resources.limit.couple,
            p.eligibility.resources.limit.individual,
        )
        return countable_resources <= resource_limit


class SSIResourceDeemingReform(Reform):
    """Install only the changed SSI resource-deeming definitions."""

    def apply(self):
        for variable in (
            is_ssi_resource_deeming_child,
            is_ssi_spousal_resource_deeming_applies,
            ssi_resource_deeming_child_is_ineligible,
            ssi_resource_deeming_excluded_military_resources,
            ssi_resource_deeming_waiver,
            ssi_resources_deemed_from_ineligible_parent,
            ssi_resources_deemed_from_ineligible_spouse,
            ssi_resources_for_deeming,
            meets_ssi_resource_test,
        ):
            if variable.__name__ in self.variables:
                self.update_variable(variable)
            else:
                self.add_variable(variable)
