import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@policyengine/ui-kit";

const ITEMS = [
  {
    key: "precision",
    title: "The estimates rest on few sample records",
    body: "The population file has 57,240 households, but about 12,000 of them carry 99 percent of the weight, and a reform that reaches a narrow group ends up resting on a few dozen records. The sampling ranges on this page show how far the estimates could move if the sample were redrawn. They do not include any of the problems listed below, so the real uncertainty is wider.",
  },
  {
    key: "higher",
    title: "Why the 65-and-over figures may be too high, and what pushes the other way",
    body: "The model's new recipients differ from CBPP's by age, not across the board. For the $10,000 and $20,000 limits it has about as many new recipients aged 18 to 64 as CBPP (153,000 against 154,000), many more aged 65 and over (363,000 against roughly 47,000 implied by CBPP) and no children (against 23,000). For removing the limits it has fewer aged 18 to 64 (253,000 against 298,000), many more aged 65 and over (694,000 against 115,000) and no children (against 49,000). Its added SSI for the $10,000 and $20,000 limits, $3.6 billion in 2026, is about three and a half times the $1.0 billion that SSA's actuaries estimated for 2026 in their 2024 letter; they have not estimated removing the limits. We suspect the model overstates gains for people 65 and over: too few of its older recipients get Social Security (see the checks below), and part of that is a defect in the population file. Other gaps push the other way: the model has almost no disabled children, and it does not yet count a spouse's or a parent's savings, which the sensitivity table shows would raise the estimate. Read these figures as a rough estimate, not as a finding that the reform would cost this much.",
  },
  {
    key: "static",
    title: "This is a one-year, static estimate",
    body: "The new limits apply for all of 2026 to a population of US households built from 2024 survey data and projected to 2026. The estimate does not model how long it takes people to learn about a change and apply, or any change in how much people save. The added SSI on this page is federal SSI only. The changes in household income and poverty also include the other benefits the model ties to SSI, such as state supplements and lower SNAP benefits, but not Medicaid coverage, which the model leaves out of income.",
  },
  {
    key: "claiming",
    title: "Who would claim is an assumption",
    body: "Each person in the population carries a fixed yes-or-no flag for whether they would claim SSI if eligible. Everyone who reported receiving SSI in the Census survey keeps a yes. The other flags are drawn at one rate within each age group. For adults aged 18 to 64 and for people 65 and over, the rate is set so the model's December 2024 recipients match SSA's count. Too few children qualify to reach SSA's count, so for children the rate is the share of qualifying children who report receiving SSI. Within an age group the rate does not depend on savings, so people who become eligible under a higher limit are assumed to claim like people already under the limit. CBPP's model instead has claiming fall as savings rise. Survey data cannot settle which is right, because people with savings above the limit cannot be on SSI today. In the Census Bureau's 2023 SIPP, among unmarried older people who appear income-eligible and have savings under $2,000, SSI receipt rises with savings when people with no savings are included, and falls with savings when they are left out (PolicyEngine/microcosm#584). Neither pattern shows how newly eligible people would claim.",
  },
  {
    key: "children",
    title: "Children with disabilities are almost entirely missing",
    body: "The Census survey behind the population asks its disability questions only from age 15, so almost no child under 15 in the population meets SSI's disability standard (one sample record, with a negligible weight). The model has about 180,000 child recipients, against SSA's 1.0 million. A stage that adds disabled children from the Census Bureau's SIPP is not part of the population used here (PolicyEngine/microcosm#509). No child gains from a higher limit for two reasons: almost no disabled child in this population has savings of their own (one sample record has any, under $2,000), and PolicyEngine does not yet count a parent's savings when it tests a child's eligibility, although SSA counts a parent's savings above an allowance (20 CFR 416.1202(b); PolicyEngine/policyengine-us#3557). The resource-deeming sensitivity above adds that rule.",
  },
  {
    key: "couples",
    title: "Married people are over-represented, and a spouse's savings are not counted",
    body: "When both spouses are aged, blind or disabled, PolicyEngine tests their combined savings against the couple limit, as SSA does. When only one spouse is, SSA also counts the other spouse's savings (20 CFR 416.1202(a)); PolicyEngine does not yet. The population also records each household's savings on a single person, the household's reference person, so when that person is the spouse who does not qualify, the spouse who does is treated as having no savings. In the model about one in five current recipients lives with a spouse, against about one in twelve in SSA's records, and about one in six has a spouse who does not receive SSI, against about one in forty. About two-thirds of the people the model adds under the $10,000 and $20,000 limits are married.",
  },
  {
    key: "composition",
    title: "The model's SSI recipients are too young and too rarely on Social Security",
    body: "Within ages 18 to 64 the model has more than twice SSA's number of recipients in their twenties and about an eighth of SSA's number aged 60 to 64; only the age group's total is targeted. Among recipients 65 and over, about one in six in the model also receives Social Security, against more than half in SSA's records. Older people are more likely to have savings, and SSA's records show people with Social Security receiving much smaller SSI payments, so both gaps bear on who gains from a higher limit and by how much. Part of the Social Security gap is a defect in the population file, which sets Social Security to zero for some people who report it in the Census survey (PolicyEngine/microcosm#1178). Restoring it, in the table above, roughly halves the number of new recipients aged 65 and over.",
  },
  {
    key: "savings",
    title: "Savings are imputed, and only bank accounts, stocks and bonds count",
    body: "Each household's savings are drawn from a statistical model of either the Census Bureau's Survey of Income and Program Participation (2023) or the Federal Reserve's Survey of Consumer Finances (2022), half from each, rather than observed for that household, and the totals are not calibrated to a benchmark. PolicyEngine counts bank accounts, stocks and bonds as SSI resources. SSA also counts some other assets, such as retirement accounts from which the person can withdraw a lump sum (POMS SI 01120.210), so the model misses some savings that would put people over the limit today.",
  },
  {
    key: "comparators",
    title: "What the comparisons do and do not show",
    body: "CBPP (2023) estimated new beneficiaries, not cost, from 2014 SIPP data, scaled to SSA's 2014 caseload by age. For the $10,000 limit it did not publish a number for people 65 and over because the sample was too small; subtracting its published rows from its total leaves about 47,000, but CBPP notes its rows may not sum. SSA's actuaries estimate cost, not recipients, from the Current Population Survey, for limits indexed to inflation, over a ten-year window. Neither is a measurement of what would happen; both are models, and so is this one.",
  },
];

export default function Caveats() {
  return (
    <div className="grid gap-3">
      <h2 className="text-xl font-semibold text-foreground">
        How to read these numbers
      </h2>
      <Accordion
        type="multiple"
        defaultValue={["precision", "higher"]}
        className="rounded-md border border-border"
      >
        {ITEMS.map((item) => (
          <AccordionItem key={item.key} value={item.key} className="px-4">
            <AccordionTrigger>{item.title}</AccordionTrigger>
            <AccordionContent className="text-sm leading-6 text-muted-foreground">
              {item.body}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
}
