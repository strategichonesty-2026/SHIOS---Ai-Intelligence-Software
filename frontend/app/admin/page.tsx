"use client";

import { useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export default function AdminPage() {
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [log, setLog] = useState<string>("");

  async function runLoop() {
    setStatus("running");
    setLog("Triggering collection loop...");
    try {
      const res = await fetch(`${API_BASE}/runs/pipeline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "full", background: true, limit: 300 }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
      }
      const data = await res.json();
      setStatus("done");
      setLog(
        `Loop accepted in background mode.\n\nStatus: ${data.status}\nMode: ${data.mode}\n\nThe system is now collecting real job postings from RemoteOK, scanning GitHub repos, and processing trends. This takes 1–3 minutes.\n\nRefresh the Trends or Jobs page after a minute to see real data.`
      );
    } catch (err: any) {
      setStatus("error");
      setLog(`Error: ${err.message}`);
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
          Manually trigger the data collection loop. Use this to pull fresh job
          postings from RemoteOK and update all trends, forecasts, and
          recommendations.
        </p>
      </header>

      <div className="rounded-card border border-line bg-surface p-6 space-y-4">
        <div>
          <p className="font-mono text-xs uppercase text-muted">Full collection loop</p>
          <p className="mt-1 text-sm text-muted">
            Collects from RemoteOK + GitHub + RSS, extracts entities, computes
            trends, publishes forecasts and recommendations.
          </p>
        </div>

        <button
          onClick={runLoop}
          disabled={status === "running"}
          className={`rounded-card border px-4 py-2 font-mono text-sm transition-colors ${
            status === "running"
              ? "border-line text-muted cursor-not-allowed"
              : "border-proof text-proof hover:bg-proofSoft"
          }`}
        >
          {status === "running" ? "Running..." : "Run collection loop now →"}
        </button>

        {log && (
          <pre className="mt-4 rounded-card border border-line bg-paper p-4 font-mono text-xs text-muted whitespace-pre-wrap">
            {log}
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
        <p className="text-xs text-muted mt-3">
          Demo data (sample_jobs) is disabled. All data shown is real once the
          loop runs.
        </p>
      </div>
    </div>
  );
}
