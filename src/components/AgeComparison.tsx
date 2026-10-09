import { Card, CardContent, CardHeader, CardTitle, DataTable } from "@policyengine/ui-kit";
import { formatCurrency, formatPeople } from "@/src/lib/format";
import { Comparators, Scenario } from "@/src/lib/results";

export default function AgeComparison({
  scenario,
  cbpp,
}: {
  scenario: Scenario;
  cbpp: Comparators["cbpp"];
}) {
  const rows = scenario.by_age.map((row) => ({ ...row }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>New recipients by age, compared with CBPP</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <DataTable
          columns={[
            { key: "label", header: "Age group" },
            {
              key: "new_recipients",
              header: "PolicyEngine: new recipients",
              align: "right",
              format: (value) => formatPeople(Number(value)),
            },
            {
              key: "annual_ssi_cost",
              header: "PolicyEngine: added SSI",
              align: "right",
              format: (value) => formatCurrency(Number(value)),
            },
            {
              key: "cbpp_new_beneficiaries",
              header: "CBPP: new beneficiaries",
              align: "right",
              format: (value) =>
                value === null ? "Not published" : formatPeople(Number(value)),
            },
            { key: "cbpp_note", header: "Note" },
          ]}
          data={rows}
        />
        <p className="text-sm leading-6 text-muted-foreground">
          CBPP&apos;s figures are from{" "}
          <a className="underline" href={cbpp.url}>
            {cbpp.citation}
          </a>
          . {cbpp.note}
        </p>
      </CardContent>
    </Card>
  );
}
