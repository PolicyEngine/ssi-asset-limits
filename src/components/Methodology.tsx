import { Card, CardContent, CardHeader, CardTitle } from "@policyengine/ui-kit";
import { Provenance } from "@/src/lib/results";

const REPO_URL = "https://github.com/PolicyEngine/ssi-asset-limits";

export default function Methodology({ provenance }: { provenance: Provenance }) {
  const rows: [string, string][] = [
    ["Year analyzed", String(provenance.analysis_year)],
    [
      "Model",
      `${provenance.model_package} ${provenance.model_version}, via policyengine.py ${provenance.policyengine_version} (bundle ${provenance.bundle_id})`,
    ],
    [
      "Population",
      `Microcosm ${provenance.dataset}, build ${provenance.dataset_build_id}`,
    ],
    ["Population file SHA-256", provenance.dataset_sha256],
    ["Analysis code", provenance.code_commit],
    ["Generated", provenance.generated_at],
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Method and sources</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm leading-6 text-muted-foreground">
        <p>
          Each scenario is a full PolicyEngine microsimulation of the same
          population with the SSI resource limits changed from 2026 onward;
          the figures are the differences from current law. The population
          was run in household batches. Every marital, tax, SPM and family
          unit nests within one household, and no output published here
          depends on other households under this run&apos;s settings, which
          leave health benefits out of household income, so batching gives
          the same answer as one run.
        </p>
        <dl className="grid gap-2 sm:grid-cols-[12rem_minmax(0,1fr)]">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="font-medium text-foreground">{label}</dt>
              <dd className="break-all">{value}</dd>
            </div>
          ))}
        </dl>
        <p>
          The code, the result tables and the steps to reproduce them are in{" "}
          <a className="underline" href={REPO_URL}>
            PolicyEngine/ssi-asset-limits
          </a>
          .
        </p>
      </CardContent>
    </Card>
  );
}
