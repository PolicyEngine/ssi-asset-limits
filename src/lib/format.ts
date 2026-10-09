export function numeric(value: string | number | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatCurrency(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    notation: Math.abs(value) >= 1_000_000_000 ? "compact" : "standard",
    maximumFractionDigits: Math.abs(value) >= 1_000_000_000 ? 2 : 0,
  });
}

export function formatPeople(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toLocaleString("en-US", {
      maximumFractionDigits: 2,
    })} million`;
  }
  // Below a million, round to the nearest thousand, as CBPP and SSA tables do.
  return (Math.round(value / 1_000) * 1_000).toLocaleString("en-US");
}

export function formatRate(value: number): string {
  return `${(value * 100).toLocaleString("en-US", {
    maximumFractionDigits: 2,
  })} pp`;
}

export function formatMetricValue(
  value: number,
  unit: "currency" | "people" | "rate",
): string {
  if (unit === "currency") {
    return formatCurrency(value);
  }
  if (unit === "people") {
    return formatPeople(value);
  }
  return formatRate(value);
}

export function formatRatio(value: number): string {
  return `${value.toLocaleString("en-US", { maximumFractionDigits: 1 })}×`;
}
