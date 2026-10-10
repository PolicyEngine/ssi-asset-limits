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
    title: "PolicyEngine's estimate is well above the outside estimates",
    body: "For the $10,000 and $20,000 limits, the added SSI here is about three times what SSA's actuaries estimate for a full year, and the number of new recipients is about twice CBPP's. We have no evidence that the outside estimates are too low. We do have evidence, in the checks below, that the model's SSI population differs from SSA's records in ways that matter for this reform. Read these figures as a rough, probably high estimate, not as a finding that the reform would cost this much.",
  },
  {
    key: "static",
    title: "This is a one-year, static estimate",
    body: "The new limits apply for all of 2026 to a population of US households built from 2024 survey data and projected to 2026. The estimate does not model how long it takes people to learn about a change and apply, or any change in how much people save. It covers federal SSI only, not state supplements or the Medicaid coverage that often comes with SSI.",
  },
  {
    key: "claiming",
    title: "Who would claim is an assumption",
    body: "Each person in the population carries a fixed yes-or-no flag for whether they would claim SSI if eligible. The flags are drawn at one rate for children, one for adults aged 18 to 64 and one for people 65 and over, each set to match SSA's count of people on SSI today; everyone who reported receiving SSI in the Census survey keeps a yes. Within an age group the rate does not depend on savings, so people who become eligible because of a higher limit are assumed to claim like people with almost no savings. CBPP's model instead has claiming fall as savings rise. Survey data cannot settle which is right, because people with savings above the limit cannot be on SSI today: among income-eligible older people with savings under $2,000 in the Census Bureau's SIPP, SSI receipt does not fall as savings rise (PolicyEngine/microcosm#584).",
  },
  {
    key: "children",
    title: "Children with disabilities are almost entirely missing",
    body: "The Census survey behind the population asks its disability questions only from age 15, so no child under 15 in the population meets SSI's disability standard, and no child gains from a higher limit. A stage that adds them from the Census Bureau's SIPP is not finished (PolicyEngine/microcosm#509). Separately, PolicyEngine does not yet count a parent's savings when it tests a child's eligibility, although SSA counts a parent's savings above an allowance (20 CFR 416.1202(b)). Until that is fixed (PolicyEngine/policyengine-us#3557), a change in the limit cannot change any child's eligibility in the model.",
  },
  {
    key: "couples",
    title: "Married people are over-represented, and a spouse's savings are not counted",
    body: "When both spouses are aged, blind or disabled, PolicyEngine tests their combined savings against the couple limit, as SSA does. When only one spouse is, SSA also counts the other spouse's savings (20 CFR 416.1202(a)); PolicyEngine does not yet. The population also records each household's savings on a single person, the household's reference person, so when that person is the spouse who does not qualify, the spouse who does is treated as having no savings. In the model about one in five current recipients has a spouse, against fewer than one in ten in SSA's records, and most of the people the model adds under higher limits are married.",
  },
  {
    key: "composition",
    title: "The model's SSI recipients are too young and too rarely on Social Security",
    body: "Within ages 18 to 64 the model has more than twice SSA's number of recipients in their twenties and about an eighth of SSA's number aged 60 to 64; only the total for the age group is calibrated. Among recipients 65 and over, about one in six in the model also receives Social Security, against more than half in SSA's records. Older people are more likely to have savings, and SSA's records show people with Social Security receiving much smaller SSI payments, so both gaps bear on who gains from a higher limit and by how much. Part of the Social Security gap is a defect in the population file, which sets Social Security to zero for some people who report it in the Census survey (PolicyEngine/microcosm#1178). Restoring it, in the table above, roughly halves the number of new recipients aged 65 and over.",
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
