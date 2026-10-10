import { describe, expect, it } from "vitest";
import {
  anyChildGains,
  cbppByAgeSentence,
  cbppFor,
  costRatioToOact,
  deemingCosts,
  erasedSocialSecurity,
  maritalShares,
  oactProfile,
  oactSentence,
  percent,
  restoreComparison,
  totalRatioToCbpp,
} from "@/src/lib/facts";
import { AgeRow, OactLetter, Results, Scenario } from "@/src/lib/results";

function row(group: string, fields: Partial<AgeRow>): AgeRow {
  return {
    age_group: group,
    label: group,
    new_recipients: 0,
    annual_ssi_cost: 0,
    cbpp_new_beneficiaries: null,
    cbpp_note: "",
    new_recipients_low: 0,
    new_recipients_high: 0,
    annual_ssi_cost_low: 0,
    annual_ssi_cost_high: 0,
    new_recipient_records: 0,
    new_recipient_effective_records: 0,
    ...fields,
  };
}

function scenario(key: string, rows: Record<string, Partial<AgeRow>>): Scenario {
  return {
    key,
    label: key,
    individual_limit: null,
    couple_limit: null,
    summary: [],
    resource_bins: [],
    by_age: Object.entries(rows).map(([group, fields]) => row(group, fields)),
  };
}

const TEN = scenario("ten_twenty", {
  children_under_18: { new_recipients: 0, cbpp_new_beneficiaries: 23_000 },
  adults_18_64: { new_recipients: 153_000, cbpp_new_beneficiaries: 154_000 },
  elderly_65_plus: { new_recipients: 363_000, cbpp_new_beneficiaries: null },
  total_all_ages: {
    new_recipients: 516_000,
    annual_ssi_cost: 3.6e9,
    cbpp_new_beneficiaries: 224_000,
  },
});

function letter(date: string, annual: [number, number | null][]): OactLetter {
  return {
    date,
    title: "",
    url: "",
    effective: "",
    indexing: "",
    annual: annual.map(([year, billions]) => ({ year, billions })),
    total_label: "",
    total_billions: 0,
  };
}

const LETTERS = [
  letter("January 29, 2024", [[2024, 0.5], [2025, 1.0], [2026, 1.0]]),
  letter("August 7, 2026", [[2026, null], [2027, 0.5], [2028, 1.0], [2029, 1.4]]),
];

function results(overrides: Partial<Results> = {}): Results {
  return {
    provenance: { analysis_year: 2026 } as Results["provenance"],
    population: { households: 1, persons: 1, households_with_99pct_of_weight: 1 },
    precision_note: "",
    baseline: {
      ssa_source_label: "",
      ssa_source_url: "",
      total_recipients: 0,
      total_federal_ssi: 0,
      by_age: [
        {
          age_group: "elderly_65_plus",
          label: "",
          policyengine_recipients: 2_000_000,
          ssa_recipients: 0,
          records: 0,
        },
      ],
    },
    scenarios: [TEN],
    comparators: { cbpp: {} as Results["comparators"]["cbpp"], oact: LETTERS },
    ...overrides,
  };
}

describe("percent", () => {
  it("never rounds a nonzero share to 0 or a partial one to 100", () => {
    expect(percent(0)).toBe("0 percent");
    expect(percent(0.4)).toBe("under 1 percent");
    expect(percent(15.24)).toBe("15 percent");
    expect(percent(99.6)).toBe("over 99 percent");
    expect(percent(100)).toBe("100 percent");
  });
});

describe("OACT", () => {
  it("uses the newest letter whatever the order", () => {
    expect(oactProfile(LETTERS)).toEqual({
      first: 0.5,
      later: { low: 1.0, high: 1.4 },
    });
    expect(oactProfile([...LETTERS].reverse())?.later?.high).toBe(1.4);
  });

  it("leaves out what a one-year letter cannot support", () => {
    const one = [letter("August 7, 2026", [[2027, 0.5]])];
    expect(oactProfile(one)).toEqual({ first: 0.5, later: null });
    const sentence = oactSentence(results({ comparators: { cbpp: {} as never, oact: one } }));
    expect(sentence).not.toContain("Infinity");
    expect(sentence).not.toContain("after that");
    expect(oactProfile([])).toBeNull();
  });

  it("compares cost with the estimate for the analysis year only", () => {
    expect(costRatioToOact(results(), TEN)?.ratio).toBeCloseTo(3.6);
    const later = results({ provenance: { analysis_year: 2031 } as never });
    expect(costRatioToOact(later, TEN)).toBeNull();
  });
});

describe("CBPP", () => {
  it("implies the unpublished row only when it is positive", () => {
    expect(cbppFor(TEN, "elderly_65_plus")).toEqual({ value: 47_000, implied: true });
    const overfull = scenario("ten_twenty", {
      children_under_18: { cbpp_new_beneficiaries: 100_000 },
      adults_18_64: { cbpp_new_beneficiaries: 200_000 },
      elderly_65_plus: { cbpp_new_beneficiaries: null },
      total_all_ages: { cbpp_new_beneficiaries: 224_000 },
    });
    expect(cbppFor(overfull, "elderly_65_plus")).toBeNull();
    expect(cbppByAgeSentence(overfull)).toContain("CBPP did not publish this row");
  });

  it("has no ratio without a CBPP total", () => {
    expect(totalRatioToCbpp(TEN)).toBeCloseTo(516 / 224);
    const missing = scenario("x", { total_all_ages: { new_recipients: 5 } });
    expect(totalRatioToCbpp(missing)).toBeNull();
  });
});

describe("restore comparison", () => {
  const restored = {
    key: "restore_cps_social_security",
    label: "",
    description: "",
    provenance: {} as never,
    baseline_by_age: [
      {
        age_group: "elderly_65_plus",
        label: "",
        policyengine_recipients: 1_200_000,
        ssa_recipients: 0,
        records: 0,
      },
    ],
    scenarios: [
      {
        key: "ten_twenty",
        by_age: [
          {
            age_group: "elderly_65_plus",
            label: "",
            new_recipients: 150_000,
            annual_ssi_cost: 0,
            new_recipient_records: 0,
          },
        ],
      },
    ],
  };

  it("reports the change in each run's own terms", () => {
    const comparison = restoreComparison(results({ sensitivities: [restored] }));
    expect(comparison?.currentChangePct).toBeCloseTo(-40);
    expect(comparison?.rate).toBeCloseTo(18.15);
    expect(comparison?.restoredRate).toBeCloseTo(12.5);
  });

  it("has nothing to say without the rerun's scenario or caseload", () => {
    expect(restoreComparison(results())).toBeNull();
    const empty = { ...restored, scenarios: [] };
    expect(restoreComparison(results({ sensitivities: [empty] }))).toBeNull();
    const zero = {
      ...restored,
      baseline_by_age: [{ ...restored.baseline_by_age[0], policyengine_recipients: 0 }],
    };
    expect(restoreComparison(results({ sensitivities: [zero] }))).toBeNull();
  });
});

describe("children", () => {
  it("knows whether any scenario adds a child", () => {
    expect(anyChildGains(results())).toBe(false);
    const gain = scenario("no_limit", { children_under_18: { new_recipients: 26_000 } });
    expect(anyChildGains(results({ scenarios: [TEN, gain] }))).toBe(true);
  });
});

describe("held-out facts", () => {
  const checks = {
    recipients_by_fine_age: [],
    recipients_with_social_security: [],
    recipients_by_marital_status: [
      { marital_status: "No spouse", ssa_category: "No spouse", policyengine_share_pct: 78.5, ssa_share_pct: 91.8 },
      { marital_status: "Spouse also receives SSI", ssa_category: "Eligible spouse", policyengine_share_pct: 5.2, ssa_share_pct: 5.7 },
      { marital_status: "Spouse does not receive SSI", ssa_category: "Ineligible spouse", policyengine_share_pct: 16.3, ssa_share_pct: 2.4 },
    ],
    new_recipients_by_reporting: [],
    new_recipients_by_marital_status: [
      { scenario: "ten_twenty", age_band: "All ages", new_recipients: 0, with_spouse: 0, share_pct: 0 },
    ],
    children: [],
    new_recipients_with_erased_social_security: [
      { scenario: "ten_twenty", age_band: "65 or older", new_recipients: 362_628, with_erased_social_security: 195_268, share_pct: 53.8, records: 41, median_reported_social_security: 24_111 },
      { scenario: "ten_twenty", age_band: "Under 18", new_recipients: 0, with_erased_social_security: 0, share_pct: 0, records: 0, median_reported_social_security: 0 },
    ],
  };

  it("sums the married shares and leaves out an empty new-recipient share", () => {
    const shares = maritalShares(results({ held_out_checks: checks }));
    expect(shares?.married).toBeCloseTo(21.5);
    expect(shares?.ssaMarried).toBeCloseTo(8.1);
    expect(shares?.addedMarried).toBeNull();
  });

  it("states the erased Social Security only where there are new recipients", () => {
    const withChecks = results({ held_out_checks: checks });
    expect(erasedSocialSecurity(withChecks, "ten_twenty", "65 or older")?.records).toBe(41);
    expect(erasedSocialSecurity(withChecks, "ten_twenty", "Under 18")).toBeNull();
    expect(erasedSocialSecurity(results(), "ten_twenty", "65 or older")).toBeNull();
  });

  it("names the direction of the deeming change from the data", () => {
    const deeming = (cost: number) => ({
      key: "resource_deeming",
      label: "",
      description: "",
      provenance: {} as never,
      baseline_by_age: [],
      scenarios: [
        {
          key: "ten_twenty",
          by_age: [
            { age_group: "total_all_ages", label: "", new_recipients: 0, annual_ssi_cost: cost, new_recipient_records: 0 },
          ],
        },
      ],
    });
    expect(deemingCosts(results({ sensitivities: [deeming(4.2e9)] }), "ten_twenty")?.raises).toBe(true);
    expect(deemingCosts(results({ sensitivities: [deeming(3.0e9)] }), "ten_twenty")?.raises).toBe(false);
  });
});
