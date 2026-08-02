/**
 * Server-side API client.
 *
 * Every page is a React Server Component, so the browser never holds an API key and no
 * client-side data fetching library is needed. `safeGet` returns null instead of throwing:
 * a dashboard that shows an honest empty state beats one that shows a stack trace.
 */

const BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000/api/v1";

const API_KEY = process.env.SHIOS_API_KEY ?? "";

export type Trend = {
  id: string;
  entity_type: string;
  entity_name: string;
  period: string;
  value: number;
  delta: number;
  delta_pct: number;
  direction: "up" | "down" | "flat";
  evidence_count: number;
};

export type Prediction = {
  id: string;
  statement: string;
  entity_type: string;
  entity_name: string;
  horizon: string;
  target_period: string;
  predicted_value: number;
  predicted_direction: "up" | "down" | "flat";
  confidence: number;
  status: string;
  review_date: string;
  evidence_count: number;
};

export type Recommendation = {
  id: string;
  audience_type: string;
  recommendation_text: string;
  confidence: number;
  status: string;
  evidence_count: number;
  prediction_id: string | null;
  created_at: string;
};

export type RecommendationDetail = Recommendation & {
  rationale: string | null;
  risks: string | null;
  alternative_scenarios: string | null;
  expected_outcomes: string | null;
  prediction: { id: string; statement: string; confidence: number; target_period: string } | null;
  evidence: { id: string; entity_name: string; period: string; snippet: string | null }[];
};

export type Overview = {
  window: { first_period: string | null; latest_period: string | null };
  counts: Record<string, number>;
  accuracy: {
    scored: number;
    mean_accuracy: number | null;
    direction_hit_rate: number | null;
    mean_calibration_delta: number | null;
  };
  risers: Trend[];
  fallers: Trend[];
};

export type Series = { name: string; values: number[] };
export type Explorer = { entity_type: string; periods: string[]; series: Series[] };

export type ReportSummary = {
  id: string;
  report_type: string;
  title: string;
  subtitle: string;
  period_start: string;
  period_end: string;
  created_at: string;
};

export type ReportDetail = ReportSummary & {
  body_markdown: string;
  payload: Record<string, any>;
};

export async function safeGet<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      headers: API_KEY ? { "x-api-key": API_KEY } : undefined,
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export type ArchiveWindowSummary = { period: string; trend_count: number; scored_forecasts: number };

export type ArchiveWindowDetail = {
  period: string;
  risers: Trend[];
  fallers: Trend[];
  scored_forecasts: {
    id: string;
    statement: string | null;
    target_period: string | null;
    predicted_value: number;
    actual_value: number;
    accuracy_score: number;
    direction_correct: boolean;
  }[];
};

export const api = {
  overview: () => safeGet<Overview>("/dashboard/overview"),
  archive: () => safeGet<{ items: ArchiveWindowSummary[] }>("/dashboard/archive"),
  archiveWindow: (period: string) =>
    safeGet<ArchiveWindowDetail>(`/dashboard/archive/${encodeURIComponent(period)}`),
  career: () => safeGet<{ period: string | null; top: Trend[]; predictions: Prediction[] }>("/dashboard/career"),
  technology: () =>
    safeGet<{ period: string | null; top: Trend[]; predictions: Prediction[] }>("/dashboard/technology"),
  explorer: (entityType: string) => safeGet<Explorer>(`/dashboard/explorer?entity_type=${entityType}&top=6`),
  latestTrends: (entityType: string) =>
    safeGet<{ period: string | null; items: Trend[] }>(`/trends/latest?entity_type=${entityType}&limit=25`),
  predictions: (limit = 25, offset = 0) =>
    safeGet<{ items: Prediction[]; limit: number; offset: number; total: number }>(
      `/predictions?limit=${limit}&offset=${offset}`
    ),
  accuracy: () =>
    safeGet<{
      scored: number;
      mean_accuracy: number | null;
      direction_hit_rate: number | null;
      mean_calibration_delta: number | null;
      by_period: { period: string; mean_accuracy: number; count: number }[];
      calibration: {
        metric: string;
        entity_type: string;
        samples: number;
        mean_accuracy: number;
        mean_calibration_delta: number;
        multiplier: number;
      }[];
    }>("/predictions/accuracy"),
  trendEvidence: (id: string) =>
    safeGet<{
      trend_id: string;
      entity_name: string;
      period: string;
      evidence: { id: string; snippet: string | null; source: string; normalized_document_id: string }[];
    }>(`/trends/${id}/evidence`),
  recommendations: () => safeGet<{ items: Recommendation[] }>("/recommendations?limit=40"),
  recommendation: (id: string) => safeGet<RecommendationDetail>(`/recommendations/${id}`),
  reports: () => safeGet<{ items: ReportSummary[] }>("/reports?limit=25"),
  report: (id: string) => safeGet<ReportDetail>(`/reports/${id}`),
};
