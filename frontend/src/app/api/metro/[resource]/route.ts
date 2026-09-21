import { NextRequest, NextResponse } from "next/server";
export const dynamic = "force-dynamic";
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ resource: string }> },
) {
  const { resource } = await context.params;
  if (!(
    (request.method === "GET" && ["segments", "model"].includes(resource)) ||
    (request.method === "POST" && resource === "predict")
  ))
    return NextResponse.json(
      { detail: "지원하지 않는 요청입니다." },
      { status: 404 },
    );
  let body: string | undefined;
  if (request.method === "POST") {
    body = await request.text();
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
  }
  try {
    const url = new URL(
      "/v1/" + resource,
      process.env.METRO_API_URL || "http://127.0.0.1:8000",
    );
    const response = await fetch(url, {
      method: request.method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    const data = await response.json();
    return NextResponse.json(data, {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        detail: "예측 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST };
