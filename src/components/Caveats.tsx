import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@policyengine/ui-kit";
import {
  cbppByAgeSentence,
  cbppFor,
  childMeasure,
  costRatioToOact,
  deemingCosts,
  fineAgeRatio,
  maritalShares,
  percent,
  reportingShare,
  restoreComparison,
  socialSecurityShare,
  times,
} from "@/src/lib/facts";
import { formatPeople } from "@/src/lib/format";
import { Results } from "@/src/lib/results";

type Item = { key: string; title: string; body: string };

function precisionItem(results: Results): Item {
  const { households, households_with_99pct_of_weight: dense } = results.population;
  const ten = results.scenarios.find((item) => item.key === "ten_twenty");
  const records = ten?.by_age.find((row) => row.age_group === "total_all_ages")
    ?.new_recipient_records;
  return {
    key: "precision",
    title: "The estimates rest on few sample records",
    body: `The population file has ${households.toLocaleString("en-US")} households, but ${dense.toLocaleString("en-US")} of them carry 99 percent of the weight, and a reform that reaches a narrow group rests on few records: the new recipients under the $10,000 and $20,000 limits rest on ${records} sample records. The sampling ranges on this page show how far the estimates could move if the sample were redrawn. They do not include any of the problems listed below, so the real uncertainty is wider.`,
  };
}

function higherItem(results: Results): Item {
  const [ten, removal] = ["ten_twenty", "no_limit"].map((key) =>
    results.scenarios.find((item) => item.key === key),
  );
  const cost = ten && costRatioToOact(results, ten);
  const reporting = reportingShare(results, "ten_twenty", "18-64");
  const deeming = deemingCosts(results, "ten_twenty");
  const parts = [
    ten &&
      `For the $10,000 and $20,000 limits the model has ${cbppByAgeSentence(ten)}.`,
    removal && `For removing the limits it has ${cbppByAgeSentence(removal)}.`,
    cost &&
      `Its added SSI for the $10,000 and $20,000 limits is ${times(cost.ratio)} the $${cost.billions.toFixed(1)} billion that SSA's actuaries estimated for ${results.provenance.analysis_year} in their ${cost.letter.date.split(", ")[1]} letter; they have not estimated removing the limits.`,
    "We suspect the model overstates gains for people 65 and over: too few of its older recipients get Social Security (see the checks above), and part of that is a defect in the population file.",
    reporting &&
      `Some new recipients aged 18 to 64 may already receive SSI: ${percent(reporting.share_pct)} of them report SSI in the Census survey but are kept off it in the model by imputed savings above the limit.`,
    deeming &&
      `Other gaps push the other way: the model has almost no disabled children, and it does not yet count a spouse's or a parent's savings, which the sensitivity table shows would ${deeming.raises ? "raise" : "lower"} the added SSI from ${deeming.without} to ${deeming.with_}.`,
    "Read these figures as a rough estimate, not as a finding that the reform would cost this much.",
  ];
  return {
    key: "higher",
    title: "Why the 65-and-over figures may be too high, and what pushes the other way",
    body: parts.filter(Boolean).join(" "),
  };
}

function claimingItem(results: Results): Item {
  const adults = reportingShare(results, "ten_twenty", "18-64");
  const older = reportingShare(results, "ten_twenty", "65 or older");
  const reported =
    adults && older
      ? ` In this run, ${percent(adults.share_pct)} of the new recipients aged 18 to 64 under the $10,000 and $20,000 limits, and ${percent(older.share_pct)} of those 65 and over, report SSI in the Census survey; the rest are drawn.`
      : "";
  return {
    key: "claiming",
    title: "Who would claim is an assumption",
    body: `Each person in the population carries a fixed yes-or-no flag for whether they would claim SSI if eligible. Everyone who reported receiving SSI in the Census survey keeps a yes. Everyone else is drawn at one rate within their age group. For adults aged 18 to 64 and for people 65 and over, the rate is set so the model's December 2024 recipients match SSA's count. Too few children qualify to reach SSA's count, so for children the rate is the share of qualifying children who report receiving SSI. The rate does not depend on savings, so newly eligible people who do not report SSI claim at the same rate as everyone else in their age group who does not report it.${reported} CBPP's model instead has claiming fall as savings rise. Survey data cannot settle which is right, because people with savings above the limit cannot be on SSI today. In the Census Bureau's 2023 SIPP, among unmarried older people who appear income-eligible and have savings under $2,000, SSI receipt rises with savings when people with no savings are included, and falls with savings when they are left out (PolicyEngine/microcosm#584). Neither pattern shows how newly eligible people would claim.`,
  };
}

function childrenItem(results: Results): Item {
  const young = childMeasure(results, "Under 15 and meeting SSI's disability standard");
  const withSavings = childMeasure(results, "of which with any countable savings");
  const overLimit = childMeasure(results, "of which with countable savings over $2,000");
  const current = results.baseline.by_age.find((row) => row.age_group === "children_under_18");
  const records = (count: number) =>
    count === 1 ? "one sample record" : `${count} sample records`;
  return {
    key: "children",
    title: "Children with disabilities are almost entirely missing",
    body: [
      `The Census survey behind the population asks its disability questions only from age 15, so almost no child under 15 in the population meets SSI's disability standard${young ? ` (${records(young.records)})` : ""}.`,
      current &&
        `The model has ${formatPeople(current.policyengine_recipients)} child recipients, against SSA's ${formatPeople(current.ssa_recipients)}.`,
      "A stage that adds disabled children from the Census Bureau's SIPP is not part of the population used here (PolicyEngine/microcosm#509).",
      withSavings && overLimit &&
        `No child gains from a higher limit for two reasons: almost no disabled child in this population has savings of their own (${records(withSavings.records)} with any, ${overLimit.records === 0 ? "none" : records(overLimit.records)} over $2,000), and PolicyEngine does not yet count a parent's savings when it tests a child's eligibility, although SSA counts a parent's savings above an allowance (20 CFR 416.1202(b); PolicyEngine/policyengine-us#10040). The resource-deeming sensitivity above adds that rule.`,
    ]
      .filter(Boolean)
      .join(" "),
  };
}

function couplesItem(results: Results): Item {
  const shares = maritalShares(results);
  const numbers = shares
    ? ` In the model ${percent(shares.married)} of current recipients live with a spouse, against ${percent(shares.ssaMarried)} in SSA's records, and ${percent(shares.nonRecipient)} have a spouse who does not receive SSI, against ${percent(shares.ssaIneligible)} with an ineligible spouse.${shares.addedMarried === null ? "" : ` ${percent(shares.addedMarried)} of the people the model adds under the $10,000 and $20,000 limits live with a spouse.`}`
    : "";
  return {
    key: "couples",
    title: "Married people are over-represented, and a spouse's savings are not counted",
    body: `When both spouses are aged, blind or disabled, PolicyEngine tests their combined savings against the couple limit, as SSA does. When only one spouse is, SSA also counts the other spouse's savings (20 CFR 416.1202(a)); PolicyEngine does not yet. The population also records each household's savings on a single person, the household's reference person, so when that person is the spouse who does not qualify, the spouse who does is treated as having no savings.${numbers}`,
  };
}

function compositionItem(results: Results): Item {
  const twenties = fineAgeRatio(results, "22-29");
  const sixties = fineAgeRatio(results, "60-64");
  const older = socialSecurityShare(results, "65 or older");
  const restore = restoreComparison(results);
  const parts = [
    twenties !== null &&
      sixties !== null &&
      `Within ages 18 to 64 the model has ${times(twenties)} SSA's number of recipients aged 22 to 29 and ${percent(100 * sixties)} of SSA's number aged 60 to 64; only the age group's total is targeted.`,
    older &&
      `Among recipients 65 and over, ${percent(older.policyengine_share_pct)} in the model also receive Social Security, against ${percent(older.ssa_share_pct)} in SSA's records.`,
    "Older people are more likely to have savings, and Social Security counts as income for SSI, lowering the payment, so both gaps bear on who gains from a higher limit and by how much. Part of the Social Security gap is a defect in the population file, which sets Social Security to zero for some people who report it in the Census survey (PolicyEngine/microcosm#1178).",
    restore &&
      `Restoring it, in the sensitivity table above, also removes ${percent(restore.currentFallPct)} of current recipients aged 65 and over, because the claiming rates were set to match SSA's count with the benefit erased. New recipients 65 and over under the $10,000 and $20,000 limits fall from ${percent(restore.rate)} to ${percent(restore.restoredRate)} of each run's current recipients that age. So that rerun cannot say how many new recipients a corrected population would have; the fix belongs in the population file.`,
  ];
  return {
    key: "composition",
    title: "The model's SSI recipients are too young and too rarely on Social Security",
    body: parts.filter(Boolean).join(" "),
  };
}

function comparatorsItem(results: Results): Item {
  const ten = results.scenarios.find((item) => item.key === "ten_twenty");
  const implied = ten ? cbppFor(ten, "elderly_65_plus") : null;
  return {
    key: "comparators",
    title: "What the comparisons do and do not show",
    body: `CBPP (2023) estimated new beneficiaries, not cost, from 2014 SIPP data, scaled to SSA's 2014 caseload by age. For the $10,000 limit it did not publish a number for people 65 and over because the sample was too small${implied?.implied ? `; subtracting its published rows from its total leaves about ${formatPeople(implied.value)}, but CBPP notes its rows may not sum` : ""}. SSA's actuaries estimate cost, not recipients, for limits indexed to inflation, over a ten-year window; their 2026 letter says it uses the Current Population Survey. Neither is a measurement of what would happen; both are models, and so is this one.`,
  };
}

const STATIC: Item = {
  key: "static",
  title: "This is a one-year, static estimate",
  body: "The new limits apply for all of 2026 to a population of US households built from 2024 survey data and projected to 2026. The estimate does not model how long it takes people to learn about a change and apply, or any change in how much people save. The added SSI on this page is federal SSI only. The changes in household income and poverty also include the other benefits the model ties to SSI, such as state supplements and lower SNAP benefits, but not Medicaid coverage, which the model leaves out of income.",
};

const SAVINGS: Item = {
  key: "savings",
  title: "Savings are imputed, and only bank accounts, stocks and bonds count",
  body: "Each household's savings are drawn from a statistical model of either the Census Bureau's Survey of Income and Program Participation (2023) or the Federal Reserve's Survey of Consumer Finances (2022), half from each, rather than observed for that household, and the totals are not calibrated to a benchmark. PolicyEngine counts bank accounts, stocks and bonds as SSI resources. SSA also counts some other assets, such as retirement accounts from which the person can withdraw a lump sum (POMS SI 01120.210), so the model misses some savings that would put people over the limit today.",
};

export default function Caveats({ results }: { results: Results }) {
  const items = [
    precisionItem(results),
    higherItem(results),
    STATIC,
    claimingItem(results),
    childrenItem(results),
    couplesItem(results),
    compositionItem(results),
    SAVINGS,
    comparatorsItem(results),
  ];
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
        {items.map((item) => (
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
