"""SSI resource deeming (20 CFR 416.1202) as a reform on policyengine-us 2.2.1.

The certified bundle pins policyengine-us 2.2.1, whose SSI resource test
counts only the person's own resources (or a couple's when both spouses are
eligible). PolicyEngine/policyengine-us pull request "Deem SSI resources from
ineligible spouses and parents" adds the federal deeming rules. Until a
certified bundle carries that change, this module installs the same variable
classes on 2.2.1 so the effect on the certified population can be measured.
It is a sensitivity variant, never the published estimate.

The classes below are copied from that branch (commit 482467511a). Their
source is compared with the branch class by class in the branch's own
differential check, and the same regulation-sourced cases are run against
this reform in ``tests/engine/test_resource_deeming_reform.py``.
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
        # 416.1856: 'You are not married' and 'not the head of a household'.
        # A two-person marital unit represents married, cohabiting spouses.
        # age is annual in the model: supply the relevant attained age.
        return (
            person("is_ssi_aged_blind_disabled", period)
            & (person("age", period.this_year) < 18)
            & (person.marital_unit.nb_persons() == 1)
            & ~person("is_household_head", period)
            & ~(
                person("ssi_lives_in_medical_treatment_facility", period)
                & ~person("ssi_resource_deeming_temporary_absence", period)
            )
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
        "https://secure.ssa.gov/poms.nsf/lnx/0501330100",
        "https://www.ecfr.gov/current/title-20/section-416.1167",
    )

    def formula(person, period, parameters):
        ineligible = person("is_ssi_ineligible_spouse", period)
        # Marital units represent spouses living together. Subtract self:
        # an unmarried ineligible adult is not their own ineligible spouse.
        has_ineligible_spouse = person.marital_unit.sum(ineligible) > ineligible
        households = person.household.reference_entity.members_entity_id
        first_home = person.marital_unit.value_nth_person(0, households, default=-1)
        second_home = person.marital_unit.value_nth_person(1, households, default=-2)
        return (
            person("is_ssi_aged_blind_disabled", period)
            & ~person("ssi_claim_is_joint", period)
            & has_ineligible_spouse
            & (
                (first_home == second_home)
                | person.marital_unit.any(
                    person("ssi_resource_deeming_temporary_absence", period)
                )
            )
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


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/ssi_resource_deeming_temporary_absence.py
class ssi_resource_deeming_temporary_absence(Variable):
    value_type = bool
    entity = Person
    label = "Temporary absence retaining SSI deeming household membership"
    definition_period = MONTH
    reference = "https://www.ecfr.gov/current/title-20/section-416.1167"
    documentation = """
    Adjudicated SSI household membership during a temporary absence under
    416.1167. The tax unit and marital unit must still represent that SSI
    household. Includes absence with intended and actual return in the same
    or next month; medical-facility absence while 416.212 benefits are payable
    (including the specified discharge extension); children away at school
    subject to parental control; and active-duty absence without contrary
    evidence. For active-duty contrary evidence, deeming ceases the following
    month under 416.1167(c). Set this monthly determination accordingly; actual
    return dates, 416.212 awards and contrary evidence are not model inputs.
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


# Source: policyengine_us/variables/gov/ssa/ssi/eligibility/resources/deemed/ssi_resources_deemed_from_ineligible_parent.py
def _sum_coresident_tax_unit(person, values, temporary):
    """Sum over the intersection of a tax unit and an actual household.

    Keep the same tax-unit family proxy as SSI income deeming. A tax unit
    must contain only the child's natural/adoptive parents and their spouses
    as parental participants; is_parent alone cannot identify which child's
    parent an unrelated adult is. Separate tax units need explicit inputs
    for their deemed amounts. No optional parent-link APIs are required.
    """
    group = person.tax_unit
    indices = np.arange(person.count)
    households = person.household.reference_entity.members_entity_id
    total = np.zeros(person.count)
    for position in range(int(np.max(group.reference_entity.members_position)) + 1):
        member = group.value_nth_person(position, indices, default=-1)
        # 416.1167: an adjudicated temporary absence retains membership in
        # the SSI household represented by this tax unit, including a medical
        # facility absence while benefits under 416.212 remain payable.
        coresident = (member >= 0) & (
            (households[member] == households) | temporary[member] | temporary
        )
        total += where(coresident, values[member], 0)
    return total


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
        parent = person("is_parent", period)
        # 416.1202(b)(1): the parent's spouse is a stepparent living with
        # the child and parent. A marital-unit spouse need not have own children.
        parent = parent | person.marital_unit.any(parent)
        temporary = person("ssi_resource_deeming_temporary_absence", period)
        parental_resources = _sum_coresident_tax_unit(
            person, parent * person("ssi_resources_for_deeming", period), temporary
        )
        parent_count = _sum_coresident_tax_unit(person, parent, temporary)
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
        # at most the largest tax-unit size rounds are needed (Goode, .280).
        rounds = int(np.max(person.tax_unit.nb_persons()))
        for _ in range(rounds):
            count = _sum_coresident_tax_unit(person, active, temporary)
            share = excess / max_(1, count)
            deemed = where(active, share, deemed)
            active = active & (own_resources + share <= p.individual)
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
        ineligible = person("is_ssi_ineligible_spouse", period)
        spouse_resources = (
            person.marital_unit.sum(resources * ineligible) - resources * ineligible
        )
        # 416.1202(a): 'whether or not such resources are available'.
        return person("is_ssi_spousal_resource_deeming_applies", period) * max_(
            0, spouse_resources
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
            ssi_resource_deeming_temporary_absence,
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
