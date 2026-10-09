import { ChartContainer, DataTable, PEBarChart } from "@policyengine/ui-kit";
import { formatCurrency, formatPeople } from "@/src/lib/format";
import { Scenario } from "@/src/lib/results";

export default function ResourceBins({ scenario }: { scenario: Scenario }) {
  const chartData = scenario.resource_bins.map((row) => ({
    resource_bin: row.resource_bin,
    ssi_increase: row.ssi_increase,
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
          yKey="ssi_increase"
          height={340}
          fillColor="var(--chart-1)"
          formatTooltip={formatCurrency}
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
