import { Card, CardContent, CardHeader, CardTitle, DataTable } from "@policyengine/ui-kit";
import { formatBillionsRange, formatCurrency } from "@/src/lib/format";
import { oactSentence } from "@/src/lib/facts";
import { OactLetter, Results, Scenario } from "@/src/lib/results";

function letterRow(letter: OactLetter) {
  const row: Record<string, string> = {
    letter: letter.date,
    effective: letter.effective,
  };
  for (const year of letter.annual) {
    row[String(year.year)] =
      year.billions === null ? "–" : `$${year.billions.toFixed(1)}B`;
  }
  row.total = `$${letter.total_billions.toFixed(1)}B (${letter.total_label})`;
  return row;
}

export default function CostComparison({
  scenario,
  results,
}: {
  scenario: Scenario;
  results: Results;
}) {
  const oact = results.comparators.oact;
  const cost = scenario.summary.find((row) => row.metric === "annual_ssi_cost");
  const total = scenario.by_age.find(
    (row) => row.age_group === "total_all_ages",
  );
  if (scenario.key !== "ten_twenty") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Cost compared with SSA&apos;s actuaries</CardTitle>
        </CardHeader>
        <CardContent className="text-sm leading-6 text-muted-foreground">
          SSA&apos;s Office of the Chief Actuary has not published an estimate
          for removing the limits, so there is no official cost to compare
          with this scenario.
        </CardContent>
      </Card>
    );
  }

  const years = Array.from(
    new Set(oact.flatMap((letter) => letter.annual.map((y) => y.year))),
  ).sort();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cost compared with SSA&apos;s actuaries</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm leading-6 text-muted-foreground">
        <p>
          PolicyEngine estimates the higher limits would add{" "}
          <strong className="text-foreground">
            {cost ? formatCurrency(cost.value) : "–"}
          </strong>{" "}
          in federal SSI payments in 2026
          {total
            ? ` (sampling range ${formatBillionsRange(total.annual_ssi_cost_low, total.annual_ssi_cost_high)})`
            : ""}
          . {oactSentence(results)}{" "}
          {oact.length === 1 ? "The letter assumes" : "The letters each assume"}{" "}
          the limits apply from January 1 of their first year. The table shows
          OACT&apos;s letters year by year.
        </p>
        <div className="overflow-x-auto">
          <DataTable
            columns={[
              { key: "letter", header: "OACT letter" },
              { key: "effective", header: "Effective" },
              ...years.map((year) => ({
                key: String(year),
                header: String(year),
                align: "right" as const,
              })),
              { key: "total", header: "10-year total", align: "right" as const },
            ]}
            data={oact.map(letterRow)}
          />
        </div>
        <ul className="list-disc space-y-1 pl-5">
          {oact.map((letter) => (
            <li key={letter.url}>
              <a className="underline" href={letter.url}>
                {letter.title}
              </a>{" "}
              ({letter.date}). {letter.indexing}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
