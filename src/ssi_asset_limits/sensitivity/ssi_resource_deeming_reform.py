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
e7171e8639). 2.2.1 has no parent links, so parents are found by the branch's
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
        # Marriage uses the same spouse test as resource deeming, so the
        # default marital unit of a situation that omits marital units does
        # not marry a child to the parent who claims them.
        # age is annual in the model: supply the relevant attained age.
        return (
            person("is_ssi_aged_blind_disabled", period)
            & meets_immigration_status
            & (person("age", period.this_year) < 18)
            & (_ssi_spouse_index(person, period) < 0)
            & ~person("is_household_head", period)
            & ~person("ssi_lives_in_medical_treatment_facility", period)
            & ~person("ssi_resource_deeming_waiver", period)
            & ~person("ssi_resource_deeming_child_is_ineligible", period)
        )


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/is_ssi_spousal_resource_deeming_applies.py
class is_ssi_spousal_resource_deeming_applies(Variable):
    value_type = bool
    entity = Person
    label = "Spouse's resources count toward the SSI resource test"
    definition_period = MONTH
    reference = (
        "https://www.ecfr.gov/current/title-20/section-416.1202#p-416.1202(a)",
        "https://www.ecfr.gov/current/title-20/section-416.1160",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330100",
        "https://www.ecfr.gov/current/title-20/section-416.1167",
    )

    def formula(person, period, parameters):
        # 416.1160: an ineligible spouse 'lives with you as your husband or
        # wife and is not eligible for SSI benefits'; 416.1205(a) counts 'the
        # resources of the spouse' against the couple limit. Eligibility is
        # not known before the resource test, and 416.1205(b) tests an
        # eligible couple's combined resources against the same limit, so a
        # spouse's resources count either way when the claim is not already
        # joint. The spouse is identified as a parent's spouse is in parental
        # deeming. 416.1167 retains an absent person's household membership:
        # enter a temporarily absent spouse in the household they remain in.
        spouse = _ssi_spouse_index(person, period)
        return (
            person("is_ssi_aged_blind_disabled", period)
            & ~person("ssi_claim_is_joint", period)
            & (spouse >= 0)
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
    """Rows of each person's co-resident spouse, or -1.

    SSI resource deeming uses this one test for a claimant's spouse
    (416.1202(a)), a parent's spouse (416.1202(b)) and whether a child is
    married (416.1856). A marital unit holds an unmarried person or a married,
    cohabiting couple, so the members of a two-person marital unit who live in
    the same household are spouses. So are the head and spouse of one tax
    unit who share a marital unit, which covers situations that omit marital
    units (those put everyone in one unit). Parent links that name one as the
    other's parent always rule a pair out. When the simulation has a single
    marital unit, which may be that default group, a pair is also ruled out
    when exactly one of them is a dependent of the tax unit they share (no
    one can claim a spouse), so a default unit never pairs a parent with the
    child they claim. Explicit marital units otherwise stand, whatever tax
    roles the model infers. Ambiguous candidates resolve to no spouse.
    Known limitation: a simulation holding only a married couple in which
    one spouse is the other's tax dependent (as the model infers for a
    married minor when tax roles are omitted) cannot be told apart from a
    default group, so that couple is not treated as married; supply tax roles
    that do not make a spouse a dependent.
    """
    head_or_spouse = person("is_tax_unit_head_or_spouse", period)
    dependent = person("is_tax_unit_dependent", period)
    joint = head_or_spouse & person.tax_unit("tax_unit_married", period)
    tax_unit = person.tax_unit.reference_entity.members_entity_id
    couple = person.marital_unit.nb_persons() == 2
    marital_unit = person.marital_unit.reference_entity.members_entity_id
    possible_default = person.marital_unit.count == 1
    own_index = np.arange(person.count)
    spouse = np.full(person.count, -1, dtype=int)
    candidates = np.zeros(person.count, dtype=int)
    household = person.household
    for position in range(
        int(np.max(household.reference_entity.members_position, initial=-1)) + 1
    ):
        member = household.value_nth_person(position, own_index, default=-1)
        safe = np.maximum(member, 0)
        names_applicant = (first[safe] == own_index) | (second[safe] == own_index)
        named_by_applicant = (first == member) | (second == member)
        same_tax_unit = tax_unit[safe] == tax_unit
        # One claims the other when exactly one of them is a dependent of
        # the tax unit they share; two dependents can be a married couple.
        claims = possible_default & same_tax_unit & (dependent != dependent[safe])
        same_marital_unit = marital_unit[safe] == marital_unit
        shown = (
            (member >= 0)
            & (member != own_index)
            & same_marital_unit
            & (couple | (joint & head_or_spouse[safe] & same_tax_unit))
            & ~claims
            & ~names_applicant
            & ~named_by_applicant
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
    """The row of each person's co-resident spouse, or -1."""
    first, second = co_resident_parent_indices(person, period)
    return _ssi_established_spouse_indices(person, period, first, second)


def _ssi_unlinked_parental_resource_pool(person, resources, parent, spouse):
    """Return tax-unit/household proxy resources, count and exact pool keys.

    The deemors are the child's co-resident tax-unit members who are unlinked
    parents or a parent's spouse, and the spouse of each of those, wherever
    that spouse files (416.1202(b)(1): a parent and the parent's spouse).
    With no parent ids, is_parent cannot distinguish a grandparent or an
    unrelated parent from the child's parent: this is a data limitation.
    Keys hold every deemor's row, sorted, so children share a pool exactly
    when they share a deemor set.
    """
    parent = parent | ((spouse >= 0) & parent[np.maximum(spouse, 0)])
    group = person.tax_unit
    indices = np.arange(person.count)
    households = person.household.reference_entity.members_entity_id
    tax_units = group.reference_entity.members_entity_id
    positions = range(
        int(np.max(group.reference_entity.members_position, initial=-1)) + 1
    )

    def deemors():
        for position in positions:
            member = group.value_nth_person(position, indices, default=-1)
            safe = np.maximum(member, 0)
            selected = (member >= 0) & (households[safe] == households) & parent[safe]
            yield member, selected
            # Members of this tax unit are scanned above; add spouses who
            # file elsewhere. Each person has at most one spouse.
            partner = np.where(selected, spouse[safe], -1)
            outside = (partner >= 0) & (tax_units[np.maximum(partner, 0)] != tax_units)
            yield partner, outside

    count = np.zeros(person.count, dtype=int)
    for _, selected in deemors():
        count += selected
    keys = np.full((person.count, max(4, int(np.max(count, initial=0)))), -1)
    total = np.zeros(person.count)
    filled = np.zeros(person.count, dtype=int)
    for rows, selected in deemors():
        keys[indices[selected], filled[selected]] = rows[selected]
        total += np.where(selected, resources[np.maximum(rows, 0)], 0)
        filled += selected
    return total, count, keys


def _ssi_parental_resource_pool(person, period, resources):
    """No-link adapter: US 2.2.1 has no parent ids, so every child uses the
    tax-unit proxy; the branch's linked-child overlay is omitted."""
    first = second = np.full(person.count, -1, dtype=int)
    spouse = _ssi_established_spouse_indices(person, period, first, second)
    total, count, keys = _ssi_unlinked_parental_resource_pool(
        person, resources, person("is_parent", period), spouse
    )
    keys.sort(axis=1)
    _, pool = np.unique(keys, axis=0, return_inverse=True)
    return (total, count, pool)


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
        # SI 01330.200 B divides among SSI-eligible children. A child whose
        # countable income (with income deemed from parents) already reaches
        # the payment is ineligible 'for any reason': they are still deemed a
        # share, but do not count in the division. Neither variable reads the
        # resource test.
        income_eligible = person(
            "ssi_countable_income", period.this_year
        ) / MONTHS_IN_YEAR < person("ssi_amount_if_eligible", period)
        deemed = np.zeros(person.count)
        # SI 01330.200 B: 'equally divide' among eligible children; when a
        # child is ineligible 'divide ... among the remaining eligible children'.
        # A child outside the division is deemed the eligible children's share,
        # or the whole excess when none is left. Retain the last tested share
        # for a child who fails on resources, then redistribute.
        # Each round removes at least one child or leaves the result stable;
        # at most the largest household size rounds are needed (Goode, .280).
        rounds = int(np.max(person.household.nb_persons(), initial=0))
        pool_count = int(np.max(pool, initial=-1)) + 1
        for _ in range(rounds):
            count = np.bincount(pool[active & income_eligible], minlength=pool_count)
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
    label = "SSI resources counted from a spouse"
    unit = USD
    definition_period = MONTH
    quantity_type = STOCK
    reference = (
        "https://www.ecfr.gov/current/title-20/section-416.1202#p-416.1202(a)",
        "https://secure.ssa.gov/poms.nsf/lnx/0501330100",
    )

    def formula(person, period, parameters):
        spouse = np.maximum(_ssi_spouse_index(person, period), 0)
        # 416.1202(a): an ineligible spouse's resources count 'whether or not
        # such resources are available', less the exclusions 416.1202(a)(2)
        # grants an ineligible spouse. An aged, blind or disabled spouse who
        # meets the immigration condition is tested as part of a couple under
        # 416.1205(b), with only the exclusions an eligible individual gets.
        # A spouse who fails SSI's citizenship or qualified-noncitizen
        # condition is 'not eligible for SSI benefits' (416.1160) whatever
        # their age or disability, so keeps the ineligible-spouse exclusions.
        immigration_status = person("immigration_status", period)
        could_be_eligible = person("is_ssi_aged_blind_disabled", period) & (
            (immigration_status == immigration_status.possible_values.CITIZEN)
            | person("is_ssi_qualified_noncitizen", period)
        )
        resources = where(
            could_be_eligible[spouse],
            person("ssi_countable_resources", period)[spouse],
            person("ssi_resources_for_deeming", period)[spouse],
        )
        return where(
            person("is_ssi_spousal_resource_deeming_applies", period),
            resources,
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
