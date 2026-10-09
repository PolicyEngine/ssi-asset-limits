import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@policyengine/ui-kit";

const ITEMS = [
  {
    key: "static",
    title: "This is a one-year, static estimate",
    body: "The new limits apply for all of 2026 to a population of US households built from 2024 survey data and projected to 2026. The estimate does not model how long it takes people to learn about a change and apply, or any change in how much people save. It covers federal SSI only, not state supplements or the Medicaid coverage that often comes with SSI.",
  },
  {
    key: "claiming",
    title: "Who claims SSI drives most of the difference from CBPP",
    body: "Each person in the population carries a fixed yes-or-no flag for whether they would claim SSI if eligible. The flags are drawn at one rate for children, one for adults aged 18 to 64 and one for people 65 and over, each set to match SSA's count of people on SSI today; everyone who reported receiving SSI in the Census survey keeps a yes. Within an age group the rate does not depend on savings, so people who become eligible because of a higher limit claim at the same rate as people with almost no savings. CBPP's model has claiming fall as savings rise, which is likely the main reason its estimate for people 65 and over is far lower. Work to add that savings gradient is tracked in PolicyEngine/microcosm#584.",
  },
  {
    key: "children",
    title: "Children with disabilities are almost entirely missing",
    body: "The Census survey behind the population asks its disability questions only from age 15, so the population has almost no children under 15 who meet SSI's disability standard, and no child gains from a higher limit. A stage that adds them from the Census Bureau's SIPP is in review (PolicyEngine/microcosm#509). Separately, PolicyEngine does not yet count a parent's savings when it tests a child's eligibility, although SSA counts a parent's savings above an allowance (20 CFR 416.1202(b)). Until that is fixed (PolicyEngine/policyengine-us#3557), a change in the limit cannot change any child's eligibility in the model.",
  },
  {
    key: "couples",
    title: "Married couples where only one spouse qualifies",
    body: "When both spouses are aged, blind or disabled, PolicyEngine tests their combined savings against the couple limit, as SSA does. When only one spouse is, SSA also counts the other spouse's savings (20 CFR 416.1202(a)); PolicyEngine does not yet. The population also records each household's savings on a single person, the household's reference person, so when that person is the spouse who does not qualify, the spouse who does is treated as having no savings.",
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
      <Accordion type="multiple" className="rounded-md border border-border">
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
