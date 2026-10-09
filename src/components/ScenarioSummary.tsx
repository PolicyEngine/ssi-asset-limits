import { MetricCard } from "@policyengine/ui-kit";
import { formatMetricValue } from "@/src/lib/format";
import { Scenario } from "@/src/lib/results";

const HEADLINE_METRICS = [
  "annual_ssi_cost",
  "new_recipients",
  "average_gain",
  "people_lifted_from_poverty",
];

const SECONDARY_METRICS = ["net_fiscal_cost", "snap_change", "reform_recipients"];

export default function ScenarioSummary({ scenario }: { scenario: Scenario }) {
  const pick = (keys: string[]) =>
    keys
      .map((key) => scenario.summary.find((row) => row.metric === key))
      .filter((row) => row !== undefined);

  return (
    <div className="grid gap-4">
      <h2 className="text-xl font-semibold text-foreground">
        {scenario.label}: effects in 2026
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {pick(HEADLINE_METRICS).map((row) => (
          <MetricCard
            key={row.metric}
            label={row.label}
            value={formatMetricValue(row.value, row.unit)}
            format="string"
          />
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {pick(SECONDARY_METRICS).map((row) => (
          <MetricCard
            key={row.metric}
            label={row.label}
            value={formatMetricValue(row.value, row.unit)}
            format="string"
          />
        ))}
      </div>
    </div>
  );
}
