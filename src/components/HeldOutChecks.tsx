import { Card, CardContent, CardHeader, CardTitle, DataTable } from "@policyengine/ui-kit";
import { formatPeople } from "@/src/lib/format";
import { HeldOutChecks as Checks, ShareCheck } from "@/src/lib/results";

const SUPPLEMENT_URL =
  "https://www.ssa.gov/policy/docs/statcomps/supplement/2025/7e.html";
const REPORT_URL =
  "https://www.ssa.gov/policy/docs/statcomps/ssi_asr/2024/sect02.html";

function percent(value: unknown): string {
  return `${Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 })}%`;
}

function ShareTable({ rows, first }: { rows: ShareCheck[]; first: string }) {
  const key = rows[0]?.marital_status !== undefined ? "marital_status" : "age_band";
  return (
    <div className="overflow-x-auto">
      <DataTable
        columns={[
          { key, header: first },
          {
            key: "policyengine_share_pct",
            header: "PolicyEngine",
            align: "right",
            format: percent,
          },
          { key: "ssa_share_pct", header: "SSA", align: "right", format: percent },
        ]}
        data={rows.map((row) => ({ ...row }))}
      />
    </div>
  );
}

export default function HeldOutChecks({ checks }: { checks: Checks }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Checks the model is not calibrated to</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-6 text-sm leading-6 text-muted-foreground">
        <p>
          The population is calibrated to SSA&apos;s recipient counts in three
          age groups, so matching those shows little. These three comparisons
          with SSA&apos;s December 2024 records are not calibration targets.
          Each matters for this reform, because savings, other income and a
          spouse&apos;s resources all differ across these groups.
        </p>
        <div className="grid gap-2">
          <h3 className="font-semibold text-foreground">
            Current recipients by age
          </h3>
          <div className="overflow-x-auto">
            <DataTable
              columns={[
                { key: "age_band", header: "Age" },
                {
                  key: "policyengine_recipients",
                  header: "PolicyEngine",
                  align: "right",
                  format: (value) => formatPeople(Number(value)),
                },
                {
                  key: "ssa_recipients",
                  header: "SSA",
                  align: "right",
                  format: (value) => formatPeople(Number(value)),
                },
              ]}
              data={checks.recipients_by_fine_age.map((row) => ({ ...row }))}
            />
          </div>
        </div>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="grid gap-2">
            <h3 className="font-semibold text-foreground">
              Share of recipients who also get Social Security
            </h3>
            <ShareTable
              rows={checks.recipients_with_social_security}
              first="Age"
            />
          </div>
          <div className="grid gap-2">
            <h3 className="font-semibold text-foreground">
              Recipients by marital status
            </h3>
            <ShareTable
              rows={checks.recipients_by_marital_status}
              first="Status"
            />
          </div>
        </div>
        <p>
          SSA figures: age from the{" "}
          <a className="underline" href={SUPPLEMENT_URL}>
            Annual Statistical Supplement 2025, Table 7.E3
          </a>{" "}
          (shares of all federally administered recipients, rounded to a tenth
          of a percent); Social Security and marital status from the{" "}
          <a className="underline" href={REPORT_URL}>
            SSI Annual Statistical Report 2024, Tables 9 and 12
          </a>
          .
        </p>
      </CardContent>
    </Card>
  );
}
