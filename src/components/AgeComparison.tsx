import { Card, CardContent, CardHeader, CardTitle, DataTable } from "@policyengine/ui-kit";
import { formatPeople, formatPeopleRange } from "@/src/lib/format";
import { Comparators, Scenario } from "@/src/lib/results";

export default function AgeComparison({
  scenario,
  cbpp,
  precisionNote,
}: {
  scenario: Scenario;
  cbpp: Comparators["cbpp"];
  precisionNote: string;
}) {
  const rows = scenario.by_age.map((row) => ({
    ...row,
    range: formatPeopleRange(row.new_recipients_low, row.new_recipients_high),
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>New recipients by age, compared with CBPP</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="overflow-x-auto">
          <DataTable
            columns={[
              { key: "label", header: "Age group" },
              {
                key: "new_recipients",
                header: "PolicyEngine",
                align: "right",
                format: (value) => formatPeople(Number(value)),
              },
              { key: "range", header: "Sampling range", align: "right" },
              {
                key: "new_recipient_records",
                header: "Sample records",
                align: "right",
              },
              {
                key: "cbpp_new_beneficiaries",
                header: "CBPP",
                align: "right",
                format: (value) =>
                  value === null ? "Not published" : formatPeople(Number(value)),
              },
              { key: "cbpp_note", header: "Note" },
            ]}
            data={rows}
          />
        </div>
        <p className="text-sm leading-6 text-muted-foreground">
          {precisionNote} CBPP&apos;s figures are from{" "}
          <a className="underline" href={cbpp.url}>
            {cbpp.citation}
          </a>
          . {cbpp.note}
        </p>
      </CardContent>
    </Card>
  );
}
