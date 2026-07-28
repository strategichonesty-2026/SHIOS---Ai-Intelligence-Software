export function signed(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(0)}`;
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

export function confidenceLabel(confidence: number): "proof" | "provisional" | "fail" {
  if (confidence >= 0.5) return "proof";
  if (confidence >= 0.2) return "provisional";
  return "fail";
}

export function titleCase(value: string): string {
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function shortDate(value: string): string {
  try {
    return new Date(value).toISOString().slice(0, 10);
  } catch {
    return value;
  }
}

/**
 * Convert ISO week string (e.g. "2026-W20") to a human date range.
 * Returns e.g. "May 12–18, 2026"
 * Falls back to the original string if it doesn't match the pattern.
 */
export function weekToDateRange(period: string): string {
  const match = period.match(/^(\d{4})-W(\d{2})$/);
  if (!match) return period;
  const year = parseInt(match[1], 10);
  const week = parseInt(match[2], 10);

  // ISO week 1 = week containing the first Thursday of the year.
  // Monday of week N:
  const jan4 = new Date(Date.UTC(year, 0, 4)); // Jan 4 is always in W1
  const w1Monday = new Date(jan4);
  w1Monday.setUTCDate(jan4.getUTCDate() - ((jan4.getUTCDay() + 6) % 7));

  const monday = new Date(w1Monday);
  monday.setUTCDate(w1Monday.getUTCDate() + (week - 1) * 7);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);

  const fmt = (d: Date) =>
    d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

  const startStr = fmt(monday);
  const endStr = fmt(sunday);
  const yearStr = sunday.getUTCFullYear();

  // If month is same, show "May 12–18, 2026"; otherwise "Apr 28–May 4, 2026"
  const sameMonth = monday.getUTCMonth() === sunday.getUTCMonth();
  if (sameMonth) {
    const monthName = monday.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
    const d1 = monday.getUTCDate();
    const d2 = sunday.getUTCDate();
    return `${monthName} ${d1}–${d2}, ${yearStr}`;
  }
  return `${startStr}–${endStr}, ${yearStr}`;
}
