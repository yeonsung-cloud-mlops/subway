export type Segment = {
  id: string;
  line: number;
  from_id: string;
  to_id: string;
  from_station: string;
  to_station: string;
  direction: string;
  service: string;
  car_count: number;
};
export type Prediction = {
  line: number;
  from_station: string;
  to_station: string;
  direction: string;
  service?: string;
  requested_at: string;
  service_date: string;
  time_bin: string;
  daytype: string;
  train_mean_congestion_pct: number;
  cars: {
    car: number;
    estimated_congestion_pct: number;
    scenario_range_pct: [number, number];
  }[];
  location_features: { transfer_board_cars: number[]; access_cars: number[] };
  warnings: string[];
  model_version: string;
  prediction_kind: string;
  evidence: Record<string, unknown>;
};
export const lineColors: Record<number, string> = {
  1: "#244c99",
  2: "#168443",
  3: "#c45a0c",
  4: "#167bac",
  5: "#8251ac",
  6: "#95602d",
  7: "#646c20",
  8: "#cc327d",
  9: "#806d39",
};
export function koreanNow() {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
    .format(new Date())
    .replace(" ", "T");
}
export function timeLabel(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
export async function api<T>(
  resource: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const r = await fetch("/api/metro/" + resource, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });
  let data;
  try {
    data = await r.json();
  } catch {
    throw new Error("서버 응답을 읽을 수 없습니다. 다시 시도해 주세요.");
  }
  if (!r.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "입력한 구간과 일시를 확인해 주세요.",
    );
  return data;
}
