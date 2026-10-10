export function numeric(value: string | number | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatCurrency(value: number): string {
  const magnitude = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (magnitude >= 1_000_000_000) {
    const billions = (magnitude / 1_000_000_000).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return `${sign}$${billions} billion`;
  }
  if (magnitude >= 1_000_000) {
    return `${sign}$${Math.round(magnitude / 1_000_000).toLocaleString("en-US")} million`;
  }
  return `${sign}$${Math.round(magnitude).toLocaleString("en-US")}`;
}

export function formatPeople(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toLocaleString("en-US", {
      minimumFractionDigits: 2,
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

export function formatBillions(value: number): string {
  return `$${(value / 1_000_000_000).toLocaleString("en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} billion`;
}

export function formatPeopleRange(low: number, high: number): string {
  if (low === 0 && high === 0) {
    return "–";
  }
  return `${formatPeople(low)} to ${formatPeople(high)}`;
}

export function formatBillionsRange(low: number, high: number): string {
  const digits = { minimumFractionDigits: 1, maximumFractionDigits: 1 };
  const lowText = (low / 1_000_000_000).toLocaleString("en-US", digits);
  const highText = (high / 1_000_000_000).toLocaleString("en-US", digits);
  return `$${lowText} to $${highText} billion`;
}
