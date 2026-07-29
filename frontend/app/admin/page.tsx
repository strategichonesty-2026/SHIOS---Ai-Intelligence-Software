"use client";

import { useState } from "react";

export default function AdminPage() {
  const [runStatus, setRunStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [runLog, setRunLog] = useState<string>("");
  const [purgeStatus, setPurgeStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [purgeLog, setPurgeLog] = useState<string>("");

  async function runLoop() {
    setRunStatus("running");
    setRunLog("Triggering collection loop...");
    try {
      const res = await fetch("/api/run", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
      setRunStatus("done");
      setRunLog(
        `Loop accepted.\n\nStatus: ${data.status}\nMode: ${data.mode}\n\nCollecting real job postings from RemoteOK + GitHub + RSS. Takes 1–3 minutes.\n\nRefresh Jobs or Trends after a minute.`
      );
    } catch (err: any) {
      setRunStatus("error");
      setRunLog(`Error: ${err.message}`);
    }
  }

  async function purgeSynthetic() {
    setPurgeStatus("running");
    setPurgeLog("Removing demo data...");
    try {
      const res = await fetch("/api/purge-synthetic", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
      setPurgeStatus("done");
      setPurgeLog(
        `Done. Removed ${data.deleted_raw_documents ?? 0} synthetic records.\n\nRefresh the Jobs page — the demo banner should be gone.`
      );
    } catch (err: any) {
      setPurgeStatus("error");
      setPurgeLog(`Error: ${err.message}`);
    }
  }

  return (
    <div className="max-w-2xl space-y-8">
      <header>
        <p className="font-mono text-xs uppercase text-muted">Admin</p>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight">
          Collection controls
        </h1>
        <p className="mt-2 text-sm text-muted">
          Manage data collection and clean up demo data.
        </p>
      </header>

      {/* Step 1 — Remove demo data */}
      <div className="rounded-card border border-provisional bg-surface p-6 space-y-4">
        <div>
          <p className="font-mono text-xs uppercase text-provisional">Step 1 — Remove demo data</p>
          <p className="mt-1 text-sm text-muted">
            Deletes all synthetic sample_jobs records from the database. Run this once
            before collecting real data.
          </p>
        </div>
        <button
          onClick={purgeSynthetic}
          disabled={purgeStatus === "running" || purgeStatus === "done"}
          className={`rounded-card border px-4 py-2 font-mono text-sm transition-colors ${
            purgeStatus === "done"
              ? "border-line text-muted cursor-not-allowed"
              : purgeStatus === "running"
              ? "border-line text-muted cursor-not-allowed"
              : "border-provisional text-provisional hover:bg-provisionalSoft"
          }`}
        >
          {purgeStatus === "running" ? "Removing..." : purgeStatus === "done" ? "✓ Done" : "Remove demo data →"}
        </button>
        {purgeLog && (
          <pre className="mt-2 rounded-card border border-line bg-paper p-4 font-mono text-xs text-muted whitespace-pre-wrap">
            {purgeLog}
          </pre>
        )}
      </div>

      {/* Step 2 — Run collection loop */}
      <div className="rounded-card border border-line bg-surface p-6 space-y-4">
        <div>
          <p className="font-mono text-xs uppercase text-muted">Step 2 — Collect real data</p>
          <p className="mt-1 text-sm text-muted">
            Collects from RemoteOK + GitHub + RSS, extracts entities, computes
            trends, publishes forecasts and recommendations.
          </p>
        </div>
        <button
          onClick={runLoop}
          disabled={runStatus === "running"}
          className={`rounded-card border px-4 py-2 font-mono text-sm transition-colors ${
            runStatus === "running"
              ? "border-line text-muted cursor-not-allowed"
              : "border-proof text-proof hover:bg-proofSoft"
          }`}
        >
          {runStatus === "running" ? "Running..." : "Run collection loop now →"}
        </button>
        {runLog && (
          <pre className="mt-2 rounded-card border border-line bg-paper p-4 font-mono text-xs text-muted whitespace-pre-wrap">
            {runLog}
          </pre>
        )}
      </div>

      <div className="rounded-card border border-line bg-surface p-6 space-y-2">
        <p className="font-mono text-xs uppercase text-muted">Current data sources</p>
        <ul className="space-y-1 text-sm text-muted mt-2">
          <li><span className="text-proof font-medium">RemoteOK</span> — real remote job postings, no API key needed</li>
          <li><span className="text-proof font-medium">GitHub</span> — repository momentum by topic</li>
          <li><span className="text-proof font-medium">RSS</span> — tech news and articles</li>
        </ul>
      </div>
    </div>
  );
}
