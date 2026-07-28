/**
 * Client for the Executive Intelligence endpoints.
 * Mirrors lib/api.ts conventions: server-side only, fails soft to null.
 */

import { safeGet } from "./api";

export type SourceRow = {
  source: string;
  label: string;
  category: string;
  doc_type: string;
  evidence_count: number;
  document_count: number;
  last_updated: string | null;
  reliability: string;
  reliability_basis: string;
  synthetic: boolean;
  primary_source: boolean;
};

export type EvidenceBreakdown = {
  total_evidence: number;
  total_documents: number;
  categories: {
    category: string;
    evidence_count: number;
    document_count: number;
    last_updated: string | null;
    sources: string[];
    synthetic_only: boolean;
  }[];
  sources: SourceRow[];
  not_collected: { category: string; note: string }[];
  note: string;
};

export type JobRow = {
  id: string;
  position: string;
  normalized_role: string;
  company: string | null;
  location: string;
  remote_type: string;
  seniority: string;
  salary_min: number | null;
  salary_max: number | null;
  salary_known: boolean;
  posted_at: string;
  source: string;
  synthetic: boolean;
  skills: string[];
  technologies: string[];
  document_id: string;
};

export type JobFacets = {
  roles: string[];
  seniority: string[];
  remote_type: string[];
  companies: string[];
  skills: string[];
  total_jobs: number;
  with_salary: number;
  salary_coverage: number | null;
};

export type TrustPayload = {
  target_type: string;
  target_id: string;
  headline: string;
  evidence_count: number;
  confidence: number | null;
  source_diversity: {
    distinct_sources: number;
    sources: { source: string; count: number; share: number }[];
    concentration: number | null;
  };
  last_updated: string | null;
  prediction_history: {
    entity: string;
    forecasts_published: number;
    forecasts_scored: number;
    mean_accuracy: number | null;
  } | null;
  reality_validation: Record<string, unknown> | null;
  explainability: Record<string, unknown>;
  related_sources: {
    document_id: string;
    title: string;
    doc_type: string;
    source: string;
    observed_at: string;
  }[];
};

export const intelligence = {
  evidenceBreakdown: () => safeGet<EvidenceBreakdown>("/evidence/breakdown"),
  evidenceBySource: (source: string) =>
    safeGet<{ source: string; label: string; reliability: string; reliability_basis: string; synthetic: boolean; items: any[] }>(
      `/evidence/by-source/${encodeURIComponent(source)}?limit=50`,
    ),
  jobs: (qs = "") => safeGet<{ total: number; returned: number; items: JobRow[]; note: string }>(`/jobs?limit=50${qs}`),
  jobFacets: () => safeGet<JobFacets>("/jobs/facets"),
  trust: (targetType: string, id: string) => safeGet<TrustPayload>(`/trust/${targetType}/${id}`),
};

/** §2 — plain-language banding for calibration delta. */
export function reliabilityBand(delta: number | null | undefined): {
  label: "Excellent" | "Good" | "Fair" | "Needs Improvement" | "Not yet measured";
  tone: "proof" | "provisional" | "fail" | "muted";
  meaning: string;
} {
  if (delta === null || delta === undefined) {
    return {
      label: "Not yet measured",
      tone: "muted",
      meaning: "No forecast has been scored yet, so reliability is unproven.",
    };
  }
  const size = Math.abs(delta);
  const direction =
    delta < 0
      ? "The system claimed more certainty than it earned, so confidence has been lowered."
      : "The system claimed less certainty than it earned, so confidence has been raised.";
  if (size <= 0.05) return { label: "Excellent", tone: "proof", meaning: "Stated confidence closely matched real outcomes." };
  if (size <= 0.1) return { label: "Good", tone: "proof", meaning: direction };
  if (size <= 0.2) return { label: "Fair", tone: "provisional", meaning: direction };
  return { label: "Needs Improvement", tone: "fail", meaning: direction };
}
