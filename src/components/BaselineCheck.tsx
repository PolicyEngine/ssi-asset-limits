import { Card, CardContent, CardHeader, CardTitle, DataTable } from "@policyengine/ui-kit";
import { formatPeople } from "@/src/lib/format";
import { Baseline } from "@/src/lib/results";

export default function BaselineCheck({ baseline }: { baseline: Baseline }) {
  const rows = baseline.by_age.map((row) => ({
    ...row,
    ratio:
      row.ssa_recipients > 0
        ? `${Math.round((100 * row.policyengine_recipients) / row.ssa_recipients)}%`
        : "–",
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Check: SSI recipients under current law</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm leading-6 text-muted-foreground">
        <p>
          Before trusting any change, we compare the model&apos;s current-law
          SSI caseload with SSA&apos;s count. A large gap in an age group means
          the model is missing part of the program for that group; see
          &quot;How to read these numbers&quot; below.
        </p>
        <div className="overflow-x-auto">
          <DataTable
            columns={[
              { key: "label", header: "Age group" },
              {
                key: "policyengine_recipients",
                header: "PolicyEngine, 2026",
                align: "right",
                format: (value) => formatPeople(Number(value)),
              },
              {
                key: "ssa_recipients",
                header: "SSA, December 2024",
                align: "right",
                format: (value) => formatPeople(Number(value)),
              },
              { key: "ratio", header: "PolicyEngine as % of SSA", align: "right" },
            ]}
            data={rows}
          />
        </div>
        <p>
          SSA counts people with a federal SSI payment in December 2024 (
          <a className="underline" href={baseline.ssa_source_url}>
            {baseline.ssa_source_label}
          </a>
          ). PolicyEngine counts people with federal SSI in 2026.
        </p>
      </CardContent>
    </Card>
  );
}
