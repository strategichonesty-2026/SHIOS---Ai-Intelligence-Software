import { NextResponse } from "next/server";

const BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000/api/v1";

const API_KEY = process.env.SHIOS_API_KEY ?? process.env.API_KEY ?? "";
const HEADERS: Record<string, string> = API_KEY ? { "x-api-key": API_KEY } : {};

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const since = searchParams.get("since"); // ISO timestamp of when loop was triggered

  try {
    const [runsRes, overviewRes] = await Promise.all([
      fetch(`${BASE_URL}/runs?limit=1`, { headers: HEADERS, cache: "no-store" }),
      fetch(`${BASE_URL}/dashboard/overview`, { headers: HEADERS, cache: "no-store" }),
    ]);

    const runs = runsRes.ok ? await runsRes.json() : null;
    const overview = overviewRes.ok ? await overviewRes.json() : null;

    const latestRun = runs?.items?.[0];
    const done = latestRun?.status === "success" || latestRun?.status === "completed";

    return NextResponse.json({
      done,
      status: latestRun?.status ?? "unknown",
      jobs: overview?.counts?.jobs ?? 0,
      documents: overview?.counts?.documents ?? 0,
      trends: overview?.counts?.tracked_entities ?? null,
      source_errors: [], // Don't show historical errors — they confuse the current status
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message, done: false }, { status: 500 });
  }
}
