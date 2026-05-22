export function numeric(value: string | number | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatCurrency(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    notation: Math.abs(value) >= 1_000_000_000 ? "compact" : "standard",
    maximumFractionDigits: Math.abs(value) >= 1_000_000_000 ? 1 : 0,
  });
}

export function formatPeople(value: number): string {
  return value.toLocaleString("en-US", {
    notation: Math.abs(value) >= 1_000_000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  });
}

export function formatRate(value: number): string {
  return `${(value * 100).toLocaleString("en-US", {
    maximumFractionDigits: 2,
  })} pp`;
}
