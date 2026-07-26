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
