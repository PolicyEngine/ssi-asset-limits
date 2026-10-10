// Figures the page states in prose, computed from results.json so a
// republish can never leave a sentence behind its numbers. Every helper
// returns null when the data cannot support its sentence, and callers then
// leave the sentence out.
import { formatBillions, formatPeople } from "@/src/lib/format";
import {
  AgeRow,
  OactLetter,
  Results,
  Scenario,
  Sensitivity,
} from "@/src/lib/results";

export function ageRow(scenario: Scenario, group: string): AgeRow | undefined {
  return scenario.by_age.find((row) => row.age_group === group);
}

export function times(value: number): string {
  return `${value.toLocaleString("en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} times`;
}

/** A share in words, never rounding a nonzero share to 0 or a partial to 100. */
export function percent(value: number): string {
  if (value > 0 && value < 0.5) {
    return "under 1 percent";
  }
  if (value >= 99.5 && value < 100) {
    return "over 99 percent";
  }
  return `${Math.round(value)} percent`;
}

function people(value: number): string {
  return value === 0 ? "none" : formatPeople(value);
}

function billions(value: number): string {
  return `$${value.toFixed(1)} billion`;
}

function letterYear(letter: OactLetter): string {
  return letter.date.split(", ")[1];
}

/** OACT's estimate for one calendar year, from the newest letter with one. */
export function oactForYear(
  oact: OactLetter[],
  year: number,
): { letter: OactLetter; billions: number } | null {
  for (const letter of newestFirst(oact)) {
    const match = letter.annual.find((row) => row.year === year);
    if (match && match.billions !== null) {
      return { letter, billions: match.billions };
    }
  }
  return null;
}

function newestFirst(oact: OactLetter[]): OactLetter[] {
  return [...oact].sort(
    (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
  );
}

/** First-year and later-year range of the newest OACT letter. */
export function oactProfile(oact: OactLetter[]) {
  const newest = newestFirst(oact)[0];
  const values = (newest?.annual ?? [])
    .map((row) => row.billions)
    .filter((value): value is number => value !== null);
  if (values.length === 0) {
    return null;
  }
  const later = values.slice(1);
  return {
    first: values[0],
    later: later.length ? { low: Math.min(...later), high: Math.max(...later) } : null,
  };
}

export function oactSentence(results: Results): string | null {
  const profile = oactProfile(results.comparators.oact);
  if (!profile) {
    return null;
  }
  const year = results.provenance.analysis_year;
  const forYear = oactForYear(results.comparators.oact, year);
  const later = profile.later
    ? profile.later.low === profile.later.high
      ? ` and ${billions(profile.later.low)} a year after that`
      : ` and ${billions(profile.later.low)} to ${billions(profile.later.high)} a year after that`
    : "";
  const yearClause = forYear
    ? `; its ${letterYear(forYear.letter)} letter puts ${year} at ${billions(forYear.billions)}`
    : "";
  return `SSA's Office of the Chief Actuary (OACT) estimates the same limits, indexed to inflation, would add ${billions(profile.first)} in the first year${later}${yearClause}.`;
}

/** CBPP's count for an age group, or its implied residual when unpublished. */
export function cbppFor(
  scenario: Scenario,
  group: string,
): { value: number; implied: boolean } | null {
  const published = ageRow(scenario, group)?.cbpp_new_beneficiaries ?? null;
  if (published !== null) {
    return { value: published, implied: false };
  }
  const total = ageRow(scenario, "total_all_ages")?.cbpp_new_beneficiaries;
  const children = ageRow(scenario, "children_under_18")?.cbpp_new_beneficiaries;
  const adults = ageRow(scenario, "adults_18_64")?.cbpp_new_beneficiaries;
  if (total == null || children == null || adults == null) {
    return null;
  }
  const residual = total - children - adults;
  return residual > 0 ? { value: residual, implied: true } : null;
}

export function cbppByAgeSentence(scenario: Scenario): string {
  const parts = [
    ["adults_18_64", "aged 18 to 64"],
    ["elderly_65_plus", "aged 65 and over"],
    ["children_under_18", "under 18"],
  ].map(([group, label]) => {
    const ours = ageRow(scenario, group)?.new_recipients ?? 0;
    const theirs = cbppFor(scenario, group);
    const against = !theirs
      ? "CBPP did not publish this row"
      : theirs.implied
        ? `against roughly ${formatPeople(theirs.value)} implied by CBPP`
        : `against ${people(theirs.value)} for CBPP`;
    return `${people(ours)} ${label} (${against})`;
  });
  return `${parts[0]}, ${parts[1]} and ${parts[2]}`;
}

export function totalRatioToCbpp(scenario: Scenario): number | null {
  const total = ageRow(scenario, "total_all_ages");
  const cbpp = total?.cbpp_new_beneficiaries;
  return total && cbpp ? total.new_recipients / cbpp : null;
}

export function costRatioToOact(results: Results, scenario: Scenario) {
  const forYear = oactForYear(
    results.comparators.oact,
    results.provenance.analysis_year,
  );
  const cost = ageRow(scenario, "total_all_ages")?.annual_ssi_cost;
  return forYear && cost !== undefined && forYear.billions > 0
    ? { ratio: cost / 1e9 / forYear.billions, ...forYear, year: letterYear(forYear.letter) }
    : null;
}

export function sensitivityByKey(
  results: Results,
  key: string,
): Sensitivity | undefined {
  return results.sensitivities?.find((item) => item.key === key);
}

function current65(rows: { age_group: string; policyengine_recipients: number }[]) {
  return rows.find((row) => row.age_group === "elderly_65_plus")?.policyengine_recipients;
}

/** The restore rerun against the published run, each in its own terms. */
export function restoreComparison(results: Results) {
  const restored = sensitivityByKey(results, "restore_cps_social_security");
  const ten = results.scenarios.find((item) => item.key === "ten_twenty");
  const restoredTen = restored?.scenarios.find((item) => item.key === "ten_twenty");
  if (!restored || !ten || !restoredTen) {
    return null;
  }
  const current = current65(results.baseline.by_age);
  const restoredCurrent = current65(restored.baseline_by_age);
  const added = ageRow(ten, "elderly_65_plus")?.new_recipients;
  const restoredAdded = restoredTen.by_age.find(
    (row) => row.age_group === "elderly_65_plus",
  )?.new_recipients;
  if (!current || !restoredCurrent || added === undefined || restoredAdded === undefined) {
    return null;
  }
  return {
    currentChangePct: 100 * (restoredCurrent / current - 1),
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
    ? {
        without: formatBillions(without),
        with_: formatBillions(with_),
        raises: with_ > without,
      }
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

/** Whether any scenario adds a child recipient. */
export function anyChildGains(results: Results): boolean {
  return results.scenarios.some(
    (scenario) => (ageRow(scenario, "children_under_18")?.new_recipients ?? 0) > 0,
  );
}

export function fineAgeRatio(results: Results, band: string): number | null {
  const row = results.held_out_checks?.recipients_by_fine_age.find(
    (item) => item.age_band === band,
  );
  return row && row.ssa_recipients > 0
    ? row.policyengine_recipients / row.ssa_recipients
    : null;
}

export function maritalShares(results: Results) {
  const rows = results.held_out_checks?.recipients_by_marital_status;
  if (!rows) {
    return null;
  }
  const withSpouse = rows.filter((row) => row.marital_status !== "No spouse");
  const nonRecipient = rows.find(
    (row) => row.marital_status === "Spouse does not receive SSI",
  );
  const added = results.held_out_checks?.new_recipients_by_marital_status.find(
    (row) => row.scenario === "ten_twenty" && row.age_band === "All ages",
  );
  return {
    married: withSpouse.reduce((sum, row) => sum + row.policyengine_share_pct, 0),
    ssaMarried: withSpouse.reduce((sum, row) => sum + row.ssa_share_pct, 0),
    nonRecipient: nonRecipient?.policyengine_share_pct ?? 0,
    ssaIneligible: nonRecipient?.ssa_share_pct ?? 0,
    addedMarried: added && added.new_recipients > 0 ? added.share_pct : null,
  };
}

export function socialSecurityShare(results: Results, band: string) {
  return results.held_out_checks?.recipients_with_social_security.find(
    (row) => row.age_band === band,
  );
}

export function erasedSocialSecurity(results: Results, scenario: string, band: string) {
  const row = results.held_out_checks?.new_recipients_with_erased_social_security.find(
    (item) => item.scenario === scenario && item.age_band === band,
  );
  return row && row.new_recipients > 0 && row.records > 0 ? row : null;
}
