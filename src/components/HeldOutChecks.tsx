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
  return (
    <div className="overflow-x-auto">
      <DataTable
        columns={[
          { key: "age_band", header: first },
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
        <CardTitle>Checks the model is not targeted to</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-6 text-sm leading-6 text-muted-foreground">
        <p>
          The model&apos;s claiming flags are set so its December 2024
          recipients match SSA&apos;s counts for adults aged 18 to 64 and for
          people 65 and over, so matching those totals shows little; the child
          total falls far short. These three comparisons with SSA&apos;s
          December 2024 records are not targets. Each matters for this reform,
          because savings, other income and a spouse&apos;s resources all
          differ across these groups.
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
              Recipients by whether a spouse lives with them
            </h3>
            <div className="overflow-x-auto">
              <DataTable
                columns={[
                  { key: "marital_status", header: "PolicyEngine" },
                  {
                    key: "policyengine_share_pct",
                    header: "Share",
                    align: "right",
                    format: percent,
                  },
                  { key: "ssa_category", header: "SSA" },
                  {
                    key: "ssa_share_pct",
                    header: "Share",
                    align: "right",
                    format: percent,
                  },
                ]}
                data={checks.recipients_by_marital_status.map((row) => ({
                  ...row,
                }))}
              />
            </div>
            <p>
              The model does not record whether a spouse who gets no SSI is
              eligible, so its last row also counts eligible spouses who do not
              claim, unlike SSA&apos;s ineligible-spouse row.
            </p>
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
