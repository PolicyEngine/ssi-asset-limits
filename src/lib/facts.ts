// Figures the page states in prose, computed from results.json so a
// republish can never leave a sentence behind its numbers.
import { formatBillions, formatPeople } from "@/src/lib/format";
import { AgeRow, OactLetter, Results, Scenario, Sensitivity } from "@/src/lib/results";

export function ageRow(scenario: Scenario, group: string): AgeRow | undefined {
  return scenario.by_age.find((row) => row.age_group === group);
}

export function times(value: number): string {
  return `${value.toLocaleString("en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} times`;
}

export function percent(value: number): string {
  return `${Math.round(value)} percent`;
}

function people(value: number): string {
  return value === 0 ? "none" : formatPeople(value);
}

/** OACT's estimate for one calendar year, from the letter that covers it. */
export function oactForYear(
  oact: OactLetter[],
  year: number,
): { letter: OactLetter; billions: number } | null {
  for (const letter of oact) {
    const match = letter.annual.find((row) => row.year === year);
    if (match && match.billions !== null) {
      return { letter, billions: match.billions };
    }
  }
  return null;
}

/** First-year and later-year range of the most recent OACT letter. */
export function oactProfile(oact: OactLetter[]) {
  const values = oact[0].annual
    .map((row) => row.billions)
    .filter((value): value is number => value !== null);
  const later = values.slice(1);
  return {
    first: values[0],
    laterLow: Math.min(...later),
    laterHigh: Math.max(...later),
  };
}

function billions(value: number): string {
  return `$${value.toFixed(1)} billion`;
}

export function oactSentence(results: Results): string {
  const profile = oactProfile(results.comparators.oact);
  const year = results.provenance.analysis_year;
  const forYear = oactForYear(results.comparators.oact, year);
  const yearClause = forYear
    ? `; its ${forYear.letter.date.split(", ")[1]} letter puts ${year} at ${billions(forYear.billions)}`
    : "";
  return `SSA's Office of the Chief Actuary (OACT) estimates the same limits, indexed to inflation, would add ${billions(profile.first)} in the first year and ${billions(profile.laterLow)} to ${billions(profile.laterHigh)} a year after that${yearClause}.`;
}

/** CBPP's count for an age group; for 65+ at $10k/$20k, its implied residual. */
export function cbppFor(scenario: Scenario, group: string) {
  const published = ageRow(scenario, group)?.cbpp_new_beneficiaries ?? null;
  if (published !== null) {
    return { value: published, implied: false };
  }
  const total = ageRow(scenario, "total_all_ages")?.cbpp_new_beneficiaries ?? 0;
  const children = ageRow(scenario, "children_under_18")?.cbpp_new_beneficiaries ?? 0;
  const adults = ageRow(scenario, "adults_18_64")?.cbpp_new_beneficiaries ?? 0;
  return { value: total - children - adults, implied: true };
}

export function cbppByAgeSentence(scenario: Scenario): string {
  const parts = [
    ["adults_18_64", "aged 18 to 64"],
    ["elderly_65_plus", "aged 65 and over"],
    ["children_under_18", "under 18"],
  ].map(([group, label]) => {
    const ours = ageRow(scenario, group)?.new_recipients ?? 0;
    const theirs = cbppFor(scenario, group);
    const against = theirs.implied
      ? `roughly ${formatPeople(theirs.value)} implied by CBPP`
      : `${people(theirs.value)} for CBPP`;
    return `${people(ours)} ${label} (against ${against})`;
  });
  return `${parts[0]}, ${parts[1]} and ${parts[2]}`;
}

export function totalRatioToCbpp(scenario: Scenario): number {
  const total = ageRow(scenario, "total_all_ages");
  return (total?.new_recipients ?? 0) / (total?.cbpp_new_beneficiaries ?? 1);
}

export function costRatioToOact(results: Results, scenario: Scenario) {
  const forYear = oactForYear(
    results.comparators.oact,
    results.provenance.analysis_year,
  );
  const cost = ageRow(scenario, "total_all_ages")?.annual_ssi_cost ?? 0;
  return forYear ? { ratio: cost / 1e9 / forYear.billions, ...forYear } : null;
}

export function sensitivityByKey(
  results: Results,
  key: string,
): Sensitivity | undefined {
  return results.sensitivities?.find((item) => item.key === key);
}

function baseline65(rows: { age_group: string; policyengine_recipients: number }[]) {
  return rows.find((row) => row.age_group === "elderly_65_plus")?.policyengine_recipients ?? 0;
}

/** New 65+ recipients per current 65+ recipient, in a run's own terms. */
export function restoreComparison(results: Results) {
  const restored = sensitivityByKey(results, "restore_cps_social_security");
  const ten = results.scenarios.find((item) => item.key === "ten_twenty");
  if (!restored || !ten) {
    return null;
  }
  const restoredTen = restored.scenarios.find((item) => item.key === "ten_twenty");
  const current = baseline65(results.baseline.by_age);
  const restoredCurrent = baseline65(restored.baseline_by_age);
  const added = ageRow(ten, "elderly_65_plus")?.new_recipients ?? 0;
  const restoredAdded =
    restoredTen?.by_age.find((row) => row.age_group === "elderly_65_plus")
      ?.new_recipients ?? 0;
  return {
    currentFallPct: 100 * (1 - restoredCurrent / current),
    rate: (100 * added) / current,
    restoredRate: (100 * restoredAdded) / restoredCurrent,
  };
}

export function deemingCosts(results: Results, key: string) {
  const deeming = sensitivityByKey(results, "resource_deeming");
  const scenario = results.scenarios.find((item) => item.key === key);
  const with_ = deeming?.scenarios
    .find((item) => item.key === key)
    ?.by_age.find((row) => row.age_group === "total_all_ages")?.annual_ssi_cost;
  const without = scenario && ageRow(scenario, "total_all_ages")?.annual_ssi_cost;
  return with_ !== undefined && without !== undefined
    ? { without: formatBillions(without), with_: formatBillions(with_), raises: with_ > without }
    : null;
}

export function reportingShare(results: Results, scenario: string, band: string) {
  return results.held_out_checks?.new_recipients_by_reporting.find(
    (row) => row.scenario === scenario && row.age_band === band,
  );
}

export function childMeasure(results: Results, measure: string) {
  return results.held_out_checks?.children.find((row) => row.measure === measure);
}

export function fineAgeRatio(results: Results, band: string): number | null {
  const row = results.held_out_checks?.recipients_by_fine_age.find(
    (item) => item.age_band === band,
  );
  return row ? row.policyengine_recipients / row.ssa_recipients : null;
}

export function maritalShares(results: Results) {
  const rows = results.held_out_checks?.recipients_by_marital_status;
  if (!rows) {
    return null;
  }
  const notSpouse = rows.filter((row) => row.marital_status !== "No spouse");
  const nonRecipient = rows.find(
    (row) => row.marital_status === "Spouse does not receive SSI",
  );
  const added = results.held_out_checks?.new_recipients_by_marital_status.find(
    (row) => row.scenario === "ten_twenty" && row.age_band === "All ages",
  );
  return {
    married: notSpouse.reduce((sum, row) => sum + row.policyengine_share_pct, 0),
    ssaMarried: notSpouse.reduce((sum, row) => sum + row.ssa_share_pct, 0),
    nonRecipient: nonRecipient?.policyengine_share_pct ?? 0,
    ssaIneligible: nonRecipient?.ssa_share_pct ?? 0,
    addedMarried: added?.share_pct ?? null,
  };
}

export function socialSecurityShare(results: Results, band: string) {
  return results.held_out_checks?.recipients_with_social_security.find(
    (row) => row.age_band === band,
  );
}
