"use client";

import { useEffect, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  SegmentedControl,
} from "@policyengine/ui-kit";
import { costRatioToOact, times, totalRatioToCbpp } from "@/src/lib/facts";
import { loadResults, Results, Scenario } from "@/src/lib/results";
import AgeComparison from "@/src/components/AgeComparison";
import BaselineCheck from "@/src/components/BaselineCheck";
import Caveats from "@/src/components/Caveats";
import HeldOutChecks from "@/src/components/HeldOutChecks";
import CostComparison from "@/src/components/CostComparison";
import Methodology from "@/src/components/Methodology";
import ResourceBins from "@/src/components/ResourceBins";
import ScenarioSummary from "@/src/components/ScenarioSummary";
import Sensitivities from "@/src/components/Sensitivities";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const SHARED_WARNING =
  "These figures come from a model whose SSI population does not yet match SSA\u2019s records well, and they rest on few sample records.";

function warningText(results: Results, scenario: Scenario): string {
  const ratio = times(totalRatioToCbpp(scenario));
  const cost = costRatioToOact(results, scenario);
  const comparison =
    scenario.key === "ten_twenty" && cost
      ? `Added SSI is ${times(cost.ratio)} SSA\u2019s actuaries\u2019 estimate for ${results.provenance.analysis_year}, and new recipients are ${ratio} CBPP\u2019s count.`
      : `SSA\u2019s actuaries have not estimated this change. New recipients are ${ratio} CBPP\u2019s count.`;
  return `${SHARED_WARNING} ${comparison} We suspect the model overstates gains for people 65 and over, while other gaps push the other way. See \u201cHow to read these numbers\u201d before using them.`;
}

export default function DashboardClient() {
  const [results, setResults] = useState<Results | null>(null);
  const [failed, setFailed] = useState(false);
  const [scenarioKey, setScenarioKey] = useState("ten_twenty");

  useEffect(() => {
    void loadResults(`${BASE_PATH}/data/results.json`)
      .then((loaded) => {
        setResults(loaded);
        setFailed(loaded === null);
      })
      .catch(() => setFailed(true));
  }, []);

  const scenario =
    results?.scenarios.find((item) => item.key === scenarioKey) ??
    results?.scenarios[0];

  return (
    <main className="min-h-screen bg-background">
      <section className="border-b border-border bg-muted/35">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 md:px-6">
          <p className="text-sm font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            Supplemental Security Income
          </p>
          <h1 className="text-3xl font-semibold tracking-normal text-foreground md:text-4xl">
            SSI asset limits
          </h1>
          <p className="max-w-3xl text-base leading-7 text-muted-foreground">
            SSI counts savings against a limit of $2,000 for an individual and
            $3,000 for a married couple, unchanged since 1989. This page
            estimates what raising the limits to $10,000 and $20,000, or
            removing them, would cost in 2026 and who would gain, using
            PolicyEngine&apos;s microsimulation model on Microcosm&apos;s
            population of US households.
          </p>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-8 px-4 py-8 md:px-6">
        {failed && (
          <p className="text-sm text-muted-foreground">
            The results file could not be loaded.
          </p>
        )}
        {results && scenario && (
          <>
            <Alert>
              <AlertTitle>A rough estimate</AlertTitle>
              <AlertDescription>
                {warningText(results, scenario)}
              </AlertDescription>
            </Alert>
            <SegmentedControl
              value={scenario.key}
              onValueChange={setScenarioKey}
              options={results.scenarios.map((item) => ({
                label: item.label,
                value: item.key,
              }))}
            />
            <ScenarioSummary scenario={scenario} />
            <AgeComparison
              scenario={scenario}
              cbpp={results.comparators.cbpp}
              precisionNote={results.precision_note}
            />
            <CostComparison scenario={scenario} results={results} />
            <ResourceBins scenario={scenario} />
            <BaselineCheck baseline={results.baseline} />
            {results.held_out_checks && (
              <HeldOutChecks checks={results.held_out_checks} />
            )}
            {results.sensitivities && results.sensitivities.length > 0 && (
              <Sensitivities
                scenario={scenario}
                baseline={results.baseline}
                sensitivities={results.sensitivities}
              />
            )}
            <Caveats results={results} />
            <Methodology provenance={results.provenance} />
          </>
        )}
      </section>
    </main>
  );
}
