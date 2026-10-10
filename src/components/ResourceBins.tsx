import { ChartContainer, DataTable, PEBarChart } from "@policyengine/ui-kit";
import { formatCurrency, formatPeople } from "@/src/lib/format";
import { Scenario } from "@/src/lib/results";

export default function ResourceBins({ scenario }: { scenario: Scenario }) {
  // Plot in millions of dollars so the axis reads cleanly.
  const chartData = scenario.resource_bins.map((row) => ({
    resource_bin: row.resource_bin,
    ssi_increase_millions: row.ssi_increase / 1_000_000,
  }));

  return (
    <div className="grid gap-4">
      <ChartContainer
        title="Added SSI by countable savings"
        subtitle="Annual SSI increase in 2026, by the person's countable savings under current law"
      >
        <PEBarChart
          data={chartData}
          xKey="resource_bin"
          yKey="ssi_increase_millions"
          yLabel="$ millions"
          height={340}
          fillColor="var(--chart-1)"
          formatTooltip={(value) => formatCurrency(value * 1_000_000)}
          margin={{ left: 24, right: 16, bottom: 88 }}
        />
      </ChartContainer>
      <div className="overflow-x-auto">
        <DataTable
          columns={[
            { key: "resource_bin", header: "Countable savings" },
            {
              key: "people",
              header: "People",
              align: "right",
              format: (value) => formatPeople(Number(value)),
            },
            {
              key: "ssi_increase",
              header: "Added SSI",
              align: "right",
              format: (value) => formatCurrency(Number(value)),
            },
          ]}
          data={scenario.resource_bins.map((row) => ({ ...row }))}
        />
      </div>
    </div>
  );
}
