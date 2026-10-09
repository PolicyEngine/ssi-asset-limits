// Shape of public/data/results.json, written by `ssi-asset-limits-publish`.

export interface Provenance {
  analysis_year: number;
  policyengine_version: string;
  bundle_id: string;
  model_package: string;
  model_version: string;
  dataset: string;
  dataset_build_id: string;
  dataset_sha256: string;
  generated_at: string;
  code_commit: string;
  method_note: string;
}

export interface BaselineAgeRow {
  age_group: string;
  label: string;
  policyengine_recipients: number;
  ssa_recipients: number;
}

export interface Baseline {
  ssa_source_label: string;
  ssa_source_url: string;
  by_age: BaselineAgeRow[];
  total_recipients: number;
  total_federal_ssi: number;
}

export interface SummaryMetric {
  metric: string;
  label: string;
  value: number;
  unit: "currency" | "people" | "rate";
}

export interface AgeRow {
  age_group: string;
  label: string;
  new_recipients: number;
  annual_ssi_cost: number;
  cbpp_new_beneficiaries: number | null;
  cbpp_note: string;
}

export interface ResourceBinRow {
  resource_bin: string;
  people: number;
  ssi_increase: number;
  average_gain: number;
}

export interface Scenario {
  key: string;
  label: string;
  individual_limit: number | null;
  couple_limit: number | null;
  summary: SummaryMetric[];
  by_age: AgeRow[];
  resource_bins: ResourceBinRow[];
}

export interface OactYear {
  year: number;
  billions: number | null;
}

export interface OactLetter {
  date: string;
  title: string;
  url: string;
  effective: string;
  indexing: string;
  annual: OactYear[];
  total_label: string;
  total_billions: number;
}

export interface Comparators {
  cbpp: {
    citation: string;
    url: string;
    data_year: number;
    note: string;
  };
  oact: OactLetter[];
}

export interface Results {
  provenance: Provenance;
  baseline: Baseline;
  scenarios: Scenario[];
  comparators: Comparators;
}

export async function loadResults(path: string): Promise<Results | null> {
  const response = await fetch(path);
  if (!response.ok) {
    return null;
  }
  return (await response.json()) as Results;
}
