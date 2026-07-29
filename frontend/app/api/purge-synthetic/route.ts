import { NextResponse } from "next/server";

const BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000/api/v1";

const API_KEY = process.env.SHIOS_API_KEY ?? process.env.API_KEY ?? "";

export async function POST() {
  try {
    const res = await fetch(`${BASE_URL}/runs/synthetic`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        ...(API_KEY ? { "x-api-key": API_KEY } : {}),
      },
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
