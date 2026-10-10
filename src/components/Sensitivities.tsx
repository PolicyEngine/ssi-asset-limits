import { Card, CardContent, CardHeader, CardTitle, DataTable } from "@policyengine/ui-kit";
import { formatCurrency, formatPeople } from "@/src/lib/format";
import { Baseline, Scenario, Sensitivity } from "@/src/lib/results";

function pick<T extends { age_group: string }>(rows: T[], group: string) {
  return rows.find((row) => row.age_group === group);
}

export default function Sensitivities({
  scenario,
  baseline,
  sensitivities,
}: {
  scenario: Scenario;
  baseline: Baseline;
  sensitivities: Sensitivity[];
}) {
  const row = (
    label: string,
    baselineRows: Baseline["by_age"],
    byAge: { age_group: string; new_recipients: number; annual_ssi_cost: number }[],
  ) => ({
    run: label,
    current_65: pick(baselineRows, "elderly_65_plus")?.policyengine_recipients ?? 0,
    new_18_64: pick(byAge, "adults_18_64")?.new_recipients ?? 0,
    new_65: pick(byAge, "elderly_65_plus")?.new_recipients ?? 0,
    cost: pick(byAge, "total_all_ages")?.annual_ssi_cost ?? 0,
  });
  const rows = [
    row("Published estimate", baseline.by_age, scenario.by_age),
    ...sensitivities.map((sensitivity) =>
      row(
        sensitivity.label,
        sensitivity.baseline_by_age,
        sensitivity.scenarios.find((item) => item.key === scenario.key)?.by_age ??
          [],
      ),
    ),
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>How much the known problems move the estimate</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm leading-6 text-muted-foreground">
        <p>
          Each row below is a full rerun of the same microsimulation with one
          known problem corrected. They are diagnostics, not alternative
          estimates: each fixes one thing and leaves the others in place.
        </p>
        <div className="overflow-x-auto">
          <DataTable
            columns={[
              { key: "run", header: "Run" },
              {
                key: "current_65",
                header: "Recipients 65+ today",
                align: "right",
                format: (value) => formatPeople(Number(value)),
              },
              {
                key: "new_18_64",
                header: "New, 18 to 64",
                align: "right",
                format: (value) => formatPeople(Number(value)),
              },
              {
                key: "new_65",
                header: "New, 65 and over",
                align: "right",
                format: (value) => formatPeople(Number(value)),
              },
              {
                key: "cost",
                header: "Added SSI",
                align: "right",
                format: (value) => formatCurrency(Number(value)),
              },
            ]}
            data={rows}
          />
        </div>
        <ul className="list-disc space-y-1 pl-5">
          {sensitivities.map((sensitivity) => (
            <li key={sensitivity.key}>
              <strong className="text-foreground">{sensitivity.label}.</strong>{" "}
              {sensitivity.description}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
