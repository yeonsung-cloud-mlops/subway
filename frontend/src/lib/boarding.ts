import type { Journey, DoorGuidance } from "./journey";
export function crowdColor(value: number) {
  const t = Math.max(0, Math.min(200, value)) / 100;
  const stops = [
    [157, 228, 210],
    [255, 215, 139],
    [242, 142, 161],
  ];
  const a = stops[t <= 1 ? 0 : 1],
    b = stops[t <= 1 ? 1 : 2],
    f = t <= 1 ? t : t - 1;
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * f)).join(",")})`;
}
export function lowerCrowdingCars(leg: Journey["legs"][number]) {
  const cars = leg.cars.filter((c) =>
    Number.isFinite(c.estimated_mean_congestion_pct),
  );
  if (!cars.length) return [];
  const min = Math.min(
    ...cars.map((c) => Math.round(c.estimated_mean_congestion_pct * 10)),
  );
  const winners = cars.filter(
    (c) => Math.round(c.estimated_mean_congestion_pct * 10) === min,
  );
  return winners.length === cars.length ? [] : winners.map((c) => c.car);
}
export type DoorPoint = { car: number; door: number; purpose: string };
export function legDoors(
  journey: Journey,
  index: number,
): { points: DoorPoint[]; guidance?: DoorGuidance; purpose: string } {
  const leg = journey.legs[index],
    end = Math.max(...leg.step_indices);
  if (index === journey.legs.length - 1) {
    const g = journey.arrival_alighting_guidance;
    return {
      purpose: "도착역 하차 접근",
      guidance: g,
      points: (g?.points || [])
        .filter((p) => p.car <= leg.car_count)
        .map((p) => ({ ...p, purpose: "하차 접근" })),
    };
  }
  const next = journey.steps
    .slice(end + 1)
    .find((s) => s.kind === "transfer" || s.kind === "ride");
  const g = next?.kind === "transfer" ? next.door_guidance : undefined;
  const points = (g?.routes || []).flatMap((r) => {
    const p = r.alight as { car?: number; door?: number };
    return p.car && p.door && p.car <= leg.car_count
      ? [{ car: p.car, door: p.door, purpose: "빠른 환승" }]
      : [];
  });
  return {
    purpose: "빠른 환승 하차",
    guidance: g,
    points: points.filter(
      (p, i, a) =>
        a.findIndex((x) => x.car === p.car && x.door === p.door) === i,
    ),
  };
}
