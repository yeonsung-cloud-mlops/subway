import { NextRequest, NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export async function POST(request: NextRequest) {
  const body = await request.text();
  if (body.length > 8192)
    return NextResponse.json(
      { detail: "요청이 너무 큽니다." },
      { status: 413 },
    );
  try {
    JSON.parse(body);
  } catch {
    return NextResponse.json(
      { detail: "잘못된 요청 형식입니다." },
      { status: 400 },
    );
  }
  try {
    const r = await fetch(
      new URL(
        "/v1/journeys/predict",
        process.env.METRO_API_URL || "http://127.0.0.1:8000",
      ),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(30000),
      },
    );
    return NextResponse.json(await r.json(), {
      status: r.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        detail:
          "이동 경로 예측 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      },
      { status: 502 },
    );
  }
}
